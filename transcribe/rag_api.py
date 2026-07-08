import json
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from berget_rag import DEFAULTS, chat_complete_raw
from chunk_repository import connect_db, default_db_url, list_course_recordings
from course_rag import DEFAULT_COURSE_ID, SYSTEM_PROMPT, answer_course_question, prepare_course_question


CHAT_MODEL_DEFAULT = "openai/gpt-oss-120b"

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Forestry Course RAG API")
log = logging.getLogger("rag_api")


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = CHAT_MODEL_DEFAULT
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1000
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "berget"


def _message_text(message: ChatMessage) -> str:
    content = message.content
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_question(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        text = _message_text(message)
        if message.role == "user" and text:
            return text
    raise HTTPException(status_code=400, detail="Request must include at least one non-empty user message")


def _supported_tools() -> list[dict[str, Any]]:
    backend_tools = [
        {
            "type": "function",
            "function": {
                "name": "list_recordings",
                "description": "Returns the catalog of available recordings and presentations."
                "Use ONLY when the user asks for a list of recordings, presentations, lectures, sessions, or videos."
                "Do NOT use when the user asks about the content, topics, concepts, or knowledge taught in the course.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
    ]
    tool_names = [((tool.get("function") or {}).get("name")) for tool in backend_tools]
    log.info("Backend tools for Berget request: %s", tool_names)
    return backend_tools


def _assistant_message_from_choice(choice) -> dict[str, Any]:
    message = choice.message
    assistant_message = {
        "role": "assistant",
        "content": message.content,
    }
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        assistant_message["tool_calls"] = [tool_call.model_dump() for tool_call in tool_calls]
    return assistant_message


def _tool_message_for_call(tool_call: dict[str, Any], db_url: str) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    name = function.get("name")
    log.info("Executing tool call name=%s id=%s args=%s", name, tool_call.get("id"), function.get("arguments"))

    if name == "list_recordings":
        with connect_db(db_url) as conn:
            recordings = list_course_recordings(conn, DEFAULT_COURSE_ID)
        payload = {"recordings": recordings}
    else:
        payload = {"error": f"Unsupported tool: {name}"}

    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id"),
        "content": json.dumps(payload, ensure_ascii=False),
    }


def _complete_with_tools(question: str, prepared: dict, request: ChatCompletionRequest, db_url: str) -> str:
    merged_tools = _supported_tools()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prepared["user_prompt"]},
    ]

    result = chat_complete_raw(
        prepared["client"],
        request.model,
        messages=messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        tools=merged_tools,
        tool_choice=request.tool_choice,
    )

    if not result.choices:
        return ""

    first_choice = result.choices[0]
    tool_calls = getattr(first_choice.message, "tool_calls", None)
    if not tool_calls:
        log.info("Berget returned no tool calls")
        return answer_course_question(
            question,
            course_id=DEFAULT_COURSE_ID,
            db_url=db_url,
            api_base_url=DEFAULTS["api_base_url"],
            embedding_model=DEFAULTS["embedding_model"],
            expected_embedding_dimensions=DEFAULTS["expected_embedding_dimensions"],
            chat_model=request.model,
            min_similarity=0.7,
            limit=5,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )["answer"]

    log.info(
        "Berget returned tool calls: %s",
        [((tool_call.function.name if getattr(tool_call, 'function', None) else None), getattr(tool_call, 'id', None)) for tool_call in tool_calls],
    )

    assistant_message = _assistant_message_from_choice(first_choice)
    tool_messages = [_tool_message_for_call(tool_call.model_dump(), db_url) for tool_call in tool_calls]
    follow_up_messages = [*messages, assistant_message, *tool_messages]
    log.info("Sending follow-up request with %s tool message(s)", len(tool_messages))

    follow_up = chat_complete_raw(
        prepared["client"],
        request.model,
        messages=follow_up_messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    if not follow_up.choices:
        return ""
    return follow_up.choices[0].message.content or ""


def _build_chat_response(answer: str, model: str) -> dict[str, Any]:
    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": answer,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def _sse_message(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream_chat_response(client, model: str, user_prompt: str, temperature: float, max_tokens: int):
    from berget_rag import stream_chat_complete

    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"

    yield _sse_message(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                }
            ],
        }
    )

    stream = stream_chat_complete(
        client,
        model,
        SYSTEM_PROMPT,
        user_prompt,
        temperature,
        max_tokens,
    )

    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        choice = chunk.choices[0]
        delta = getattr(choice, "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        if isinstance(content, list):
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        if content:
            yield _sse_message(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
            )

    yield _sse_message(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
    )
    yield "data: [DONE]\n\n"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    model_cards = [ModelCard(id=CHAT_MODEL_DEFAULT)]
    return {
        "object": "list",
        "data": [model.model_dump() for model in model_cards],
    }


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest) -> Any:
    db_url = default_db_url()
    if not db_url:
        raise HTTPException(status_code=500, detail="Database URL is not configured. Set RAG_USER and RAG_PWD.")

    if request.tools:
        log.info("Ignoring %s client-provided tool(s); using backend-supported tools only", len(request.tools))

    question = _extract_question(request.messages)

    try:
        if request.stream:
            if request.tools:
                raise HTTPException(status_code=400, detail="tool calling is not yet supported with stream=true")
            prepared = prepare_course_question(
                question,
                course_id=DEFAULT_COURSE_ID,
                db_url=db_url,
                api_base_url=DEFAULTS["api_base_url"],
                embedding_model=DEFAULTS["embedding_model"],
                expected_embedding_dimensions=DEFAULTS["expected_embedding_dimensions"],
                min_similarity=0.7,
                limit=5,
            )
            return StreamingResponse(
                _stream_chat_response(
                    prepared["client"],
                    request.model,
                    prepared["user_prompt"],
                    request.temperature,
                    request.max_tokens,
                ),
                media_type="text/event-stream",
            )

        if request.tools:
            prepared = prepare_course_question(
                question,
                course_id=DEFAULT_COURSE_ID,
                db_url=db_url,
                api_base_url=DEFAULTS["api_base_url"],
                embedding_model=DEFAULTS["embedding_model"],
                expected_embedding_dimensions=DEFAULTS["expected_embedding_dimensions"],
                min_similarity=0.7,
                limit=5,
            )
            answer = _complete_with_tools(question, prepared, request, db_url)
            return _build_chat_response(answer, request.model)

        result = answer_course_question(
            question,
            course_id=DEFAULT_COURSE_ID,
            db_url=db_url,
            api_base_url=DEFAULTS["api_base_url"],
            embedding_model=DEFAULTS["embedding_model"],
            expected_embedding_dimensions=DEFAULTS["expected_embedding_dimensions"],
            chat_model=request.model,
            min_similarity=0.7,
            limit=5,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return _build_chat_response(result["answer"], request.model)
