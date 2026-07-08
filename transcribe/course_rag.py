from berget_rag import chat_complete, create_client, embed_text
from chunk_repository import connect_db, search_course_chunks


DEFAULT_COURSE_ID = "skogskurs"

OLD_SYSTEM_PROMPT = (
    "You are an assistant for a forestry course. Answer using the provided course material whenever possible. "
    "If the course material does not contain enough information, clearly say so instead of making up an answer. "
    "When possible, cite the presentation name and slide number."
    "If the question are in swedish, answer in swedish. If the question is in english, answer in english."
)

SYSTEM_PROMPT = (
    """
    You are an assistant for a forestry course.

    You have access to this tool:

    list_recordings:
    Use this tool only when the user asks for a catalog/list of available recordings, lectures, presentations, or course sessions.

    Examples that MUST use list_recordings:
    - "Vilka föreläsningar ingår i kursen?"
    - "Lista alla inspelningar"
    - "What recordings are available?"
    - "Show all presentations"

    Examples that MUST NOT use list_recordings:
    - "Vad säger kursen om granbarkborre?"
    - "Vilka trädslag behandlas i kursen?"
    - "Förklara gallring"
    - "När ska man röja?"
    - "Sammanfatta föreläsningen om gran"

    For normal knowledge questions, answer using the provided course material. If no relevant material is available, say so.
    Answer in the same language as the user.
    """
)


def format_timestamp(seconds: float | None) -> str | None:
    if seconds is None:
        return None

    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def format_context_block(match: dict) -> str:
    presentation_name = match.get("presentation_id") or match.get("video_file") or "Unknown presentation"
    lines = [
        "Presentation:",
        str(presentation_name),
        "",
    ]

    slide_index = match.get("slide_index")
    if slide_index is not None:
        lines.extend([f"Slide {slide_index}", ""])

    start = format_timestamp(match.get("timestamp_start"))
    end = format_timestamp(match.get("timestamp_end"))
    if start and end:
        lines.extend(["Timestamp:", f"{start} - {end}", ""])
    elif start:
        lines.extend(["Timestamp:", start, ""])

    transcript = (match.get("chunk_text") or match.get("spoken_text") or "").strip()
    lines.extend(["Transcript:", transcript])
    return "\n".join(lines)


def build_user_prompt(question: str, matches: list[dict]) -> str:
    material_sections = []
    if matches:
        for match in matches:
            material_sections.append(format_context_block(match))
    else:
        material_sections.append("No matching course material found.")

    return (
        f"Question:\n\n{question.strip()}\n\n"
        f"Course material:\n\n"
        + "\n\n-------------------\n\n".join(material_sections)
    )


def prepare_course_question(
    question: str,
    *,
    course_id: str,
    db_url: str,
    api_base_url: str,
    embedding_model: str,
    expected_embedding_dimensions: int,
    min_similarity: float,
    limit: int,
) -> dict:
    client = create_client(api_base_url)
    query_embedding = embed_text(
        client,
        question,
        embedding_model,
        expected_embedding_dimensions,
        role="query",
    )

    with connect_db(db_url) as conn:
        matches = search_course_chunks(conn, course_id, query_embedding, min_similarity, limit)

    user_prompt = build_user_prompt(question, matches)
    return {
        "client": client,
        "matches": matches,
        "user_prompt": user_prompt,
    }


def answer_course_question(
    question: str,
    *,
    course_id: str,
    db_url: str,
    api_base_url: str,
    embedding_model: str,
    expected_embedding_dimensions: int,
    chat_model: str,
    min_similarity: float,
    limit: int,
    temperature: float,
    max_tokens: int,
) -> dict:
    prepared = prepare_course_question(
        question,
        course_id=course_id,
        db_url=db_url,
        api_base_url=api_base_url,
        embedding_model=embedding_model,
        expected_embedding_dimensions=expected_embedding_dimensions,
        min_similarity=min_similarity,
        limit=limit,
    )
    answer = chat_complete(
        prepared["client"],
        chat_model,
        SYSTEM_PROMPT,
        prepared["user_prompt"],
        temperature,
        max_tokens,
    )
    return {
        "answer": answer,
        "matches": prepared["matches"],
        "user_prompt": prepared["user_prompt"],
    }
