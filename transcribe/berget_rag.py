import json
import os

import psycopg
from openai import APIError, OpenAI


DEFAULTS = {
    "api_base_url": "https://api.berget.ai/v1",
    "db_host": "localhost",
    "db_name": "ragtest1",
    "db_port": 5434,
    "embedding_model": "intfloat/multilingual-e5-large-instruct",
    "expected_embedding_dimensions": 1024,
}


def format_embedding_input(text: str, role: str) -> str:
    text = text.strip()
    if role == "passage":
        return f"passage: {text}"
    if role == "query":
        return f"query: {text}"
    raise ValueError(f"Unsupported embedding role: {role}")


def default_db_url() -> str | None:
    user = os.environ.get("RAG_USER")
    password = os.environ.get("RAG_PWD")
    if not user or not password:
        return None

    return (
        f"postgresql://{user}:{password}@{DEFAULTS['db_host']}:{DEFAULTS['db_port']}"
        f"/{DEFAULTS['db_name']}"
    )


def connect_db(db_url: str):
    return psycopg.connect(db_url)


def create_client(api_base_url: str) -> OpenAI:
    api_key = os.environ.get("BERGET_API_KEY", "")
    if not api_key:
        raise ValueError("BERGET_API_KEY environment variable not set")

    return OpenAI(api_key=api_key, base_url=api_base_url, timeout=60, max_retries=0)


def extract_error_details(error: Exception) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        text = getattr(response, "text", None)
        if text:
            return text

        try:
            return json.dumps(response.json(), ensure_ascii=False, indent=2)
        except Exception:
            pass

    body = getattr(error, "body", None)
    if body is not None:
        if isinstance(body, str):
            return body
        try:
            return json.dumps(body, ensure_ascii=False, indent=2)
        except Exception:
            return str(body)

    return str(error)


def embed_text(
    client: OpenAI,
    text: str,
    embedding_model: str,
    expected_embedding_dimensions: int | None,
    role: str,
) -> list[float]:
    formatted_text = format_embedding_input(text, role)

    try:
        result = client.embeddings.create(model=embedding_model, input=formatted_text)
    except APIError as error:
        raise RuntimeError(
            f"Embedding request failed for model {embedding_model}: {extract_error_details(error)}"
        ) from error

    embedding = result.data[0].embedding
    if expected_embedding_dimensions is not None and len(embedding) != expected_embedding_dimensions:
        raise ValueError(
            f"Model {embedding_model} returned {len(embedding)} dimensions, but the importer expects "
            f"{expected_embedding_dimensions} for the current database schema. "
            f"Update the chunks.embedding column to vector({len(embedding)}) or use a different model."
        )

    return embedding


def vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(value) for value in embedding) + "]"
