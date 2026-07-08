import json
import logging
import os

import psycopg


log = logging.getLogger("chunk_repository")

DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_NAME = "ragtest1"
DEFAULT_DB_PORT = 5434


def default_db_url() -> str | None:
    user = os.environ.get("RAG_USER")
    password = os.environ.get("RAG_PWD")
    if not user or not password:
        return None

    return f"postgresql://{user}:{password}@{DEFAULT_DB_HOST}:{DEFAULT_DB_PORT}/{DEFAULT_DB_NAME}"


def connect_db(db_url: str):
    return psycopg.connect(db_url)


def delete_chunks_for_source(conn, course_id: str, presentation_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "delete from chunks where course_id = %s and presentation_id = %s",
            (course_id, presentation_id),
        )
        return cur.rowcount


def insert_chunk_rows(
    conn,
    rows: list[dict],
    embeddings: list[list[float]],
    course_id: str,
    presentation_id: str,
    video_file: str | None,
) -> int:
    inserted = 0

    with conn.cursor() as cur:
        for row, embedding in zip(rows, embeddings, strict=True):
            cur.execute(
                """
                insert into chunks (
                    course_id,
                    presentation_id,
                    video_file,
                    slide_index,
                    timestamp_start,
                    timestamp_end,
                    image_path,
                    slide_text,
                    spoken_text,
                    chunk_text,
                    metadata,
                    embedding
                ) values (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, cast(%s as jsonb), cast(%s as vector)
                )
                """,
                _chunk_insert_params(row, embedding, course_id, presentation_id, video_file),
            )
            inserted += 1

    return inserted


def search_course_chunks(conn, course_id: str, embedding: list[float], min_similarity: float, limit: int) -> list[dict]:
    vector = _vector_literal(embedding)
    with conn.cursor() as cur:
        cur.execute(
            """
            select
                id,
                presentation_id,
                video_file,
                slide_index,
                timestamp_start,
                timestamp_end,
                image_path,
                spoken_text,
                chunk_text,
                metadata,
                similarity
            from (
                select
                    id,
                    presentation_id,
                    video_file,
                    slide_index,
                    timestamp_start,
                    timestamp_end,
                    image_path,
                    spoken_text,
                    chunk_text,
                    metadata,
                    1 - (embedding <=> %s) as similarity
                from chunks
                where course_id = %s
            ) matches
            where similarity >= %s
            order by similarity desc, id asc
            limit %s
            """,
            (vector, course_id, min_similarity, limit),
        )
        columns = [description.name for description in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def list_course_recordings(conn, course_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct presentation_id
            from chunks
            where course_id = %s
              and presentation_id is not null
              and presentation_id <> ''
            order by presentation_id asc
            """,
            (course_id,),
        )
        recordings = [row[0] for row in cur.fetchall()]
        preview = recordings[:10]
        log.info(
            "list_course_recordings for course_id=%s returned %s rows%s",
            course_id,
            len(recordings),
            f": {preview}" if preview else "",
        )
        return recordings


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(value) for value in embedding) + "]"


def _chunk_insert_params(
    row: dict,
    embedding: list[float],
    course_id: str,
    presentation_id: str,
    video_file: str | None,
) -> tuple:
    return (
        course_id,
        presentation_id,
        video_file,
        row["slide_index"],
        row["timestamp_start"],
        row["timestamp_end"],
        row["image_path"],
        row["slide_text"],
        row["spoken_text"],
        row["chunk_text"],
        json.dumps(row["metadata"], ensure_ascii=False),
        _vector_literal(embedding),
    )
