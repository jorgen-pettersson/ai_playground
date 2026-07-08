import argparse
import json
import logging
import re
from pathlib import Path

from transformers import AutoTokenizer

from berget_rag import DEFAULTS, create_client, embed_text
from chunk_repository import connect_db, default_db_url, delete_chunks_for_source, insert_chunk_rows


DEFAULTS = DEFAULTS | {
    "max_embed_tokens": 400,
    "min_chars": 20,
}

log = logging.getLogger("embed_chunks")
logging.basicConfig(level=logging.INFO)


def _load_transcription_json(input_path: Path) -> dict:
    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_slide_chunks(data: dict, input_path: Path, video_file: str | None) -> list[dict]:
    slides = data.get("slides", [])
    failed_chunks = data.get("failed_chunks", [])
    rows = []

    for i, slide in enumerate(slides):
        spoken_text = (slide.get("text") or "").strip()
        next_slide = slides[i + 1] if i + 1 < len(slides) else None
        rows.append({
            "slide_index": slide.get("frame"),
            "timestamp_start": slide.get("timestamp"),
            "timestamp_end": next_slide.get("timestamp") if next_slide else None,
            "image_path": slide.get("image"),
            "slide_text": None,
            "spoken_text": spoken_text,
            "chunk_text": spoken_text,
            "metadata": {
                "chunk_type": "slide",
                "source_json": str(input_path),
                "input_file": data.get("input_file"),
                "frame": slide.get("frame"),
                "failed_chunks_count": len(failed_chunks),
                "embedding_model": DEFAULTS["embedding_model"],
                "video_file": video_file,
                "source_chunk": slide,
            },
        })

    return rows


def _normalize_segment_chunks(data: dict, input_path: Path, video_file: str | None) -> list[dict]:
    segments = data.get("segments", [])
    failed_chunks = data.get("failed_chunks", [])
    rows = []

    for segment in segments:
        spoken_text = (segment.get("text") or "").strip()
        rows.append({
            "slide_index": None,
            "timestamp_start": segment.get("start"),
            "timestamp_end": segment.get("end"),
            "image_path": None,
            "slide_text": None,
            "spoken_text": spoken_text,
            "chunk_text": spoken_text,
            "metadata": {
                "chunk_type": "segment",
                "source_json": str(input_path),
                "input_file": data.get("input_file"),
                "failed_chunks_count": len(failed_chunks),
                "embedding_model": DEFAULTS["embedding_model"],
                "video_file": video_file,
                "source_chunk": segment,
            },
        })

    return rows


def _build_rows(data: dict, input_path: Path, video_file: str | None) -> list[dict]:
    slides = data.get("slides", [])
    if slides:
        return _normalize_slide_chunks(data, input_path, video_file)
    return _normalize_segment_chunks(data, input_path, video_file)


def _token_count(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def _split_atomic_text(tokenizer, text: str, max_tokens: int) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    parts = []

    for start in range(0, len(token_ids), max_tokens):
        chunk_ids = token_ids[start:start + max_tokens]
        part = tokenizer.decode(chunk_ids, skip_special_tokens=True).strip()
        if part:
            parts.append(part)

    return parts


def _split_text_to_fit(tokenizer, text: str, max_tokens: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if _token_count(tokenizer, text) <= max_tokens:
        return [text]

    sentences = [part.strip() for part in re.split(r'(?<=[.!?])\s+|\n+', text) if part.strip()]
    if not sentences:
        return _split_atomic_text(tokenizer, text, max_tokens)

    chunks = []
    current_parts = []

    for sentence in sentences:
        sentence_tokens = _token_count(tokenizer, sentence)
        if sentence_tokens > max_tokens:
            if current_parts:
                chunks.append(" ".join(current_parts).strip())
                current_parts = []
            chunks.extend(_split_atomic_text(tokenizer, sentence, max_tokens))
            continue

        candidate_parts = current_parts + [sentence]
        candidate_text = " ".join(candidate_parts).strip()
        if _token_count(tokenizer, candidate_text) <= max_tokens:
            current_parts = candidate_parts
        else:
            if current_parts:
                chunks.append(" ".join(current_parts).strip())
            current_parts = [sentence]

    if current_parts:
        chunks.append(" ".join(current_parts).strip())

    return [chunk for chunk in chunks if chunk]


def _split_rows_for_embedding(rows: list[dict], tokenizer, max_tokens: int) -> list[dict]:
    split_rows = []

    for row in rows:
        parts = _split_text_to_fit(tokenizer, row["chunk_text"], max_tokens)
        if not parts:
            split_rows.append(row)
            continue

        if len(parts) == 1:
            row["metadata"]["subchunk_index"] = 1
            row["metadata"]["subchunk_count"] = 1
            split_rows.append(row)
            continue

        for index, part in enumerate(parts, start=1):
            split_row = row.copy()
            split_row["spoken_text"] = part
            split_row["chunk_text"] = part
            split_row["metadata"] = dict(row["metadata"])
            split_row["metadata"]["chunk_type"] = f"{row['metadata']['chunk_type']}_subchunk"
            split_row["metadata"]["source_chunk_type"] = row["metadata"].get("chunk_type")
            split_row["metadata"]["subchunk_index"] = index
            split_row["metadata"]["subchunk_count"] = len(parts)
            split_row["metadata"]["split_strategy"] = "token_budget"
            split_row["metadata"]["max_embed_tokens"] = max_tokens
            split_rows.append(split_row)

    return split_rows


def _filter_rows(rows: list[dict], min_chars: int) -> tuple[list[dict], int]:
    filtered = []
    skipped = 0

    for row in rows:
        chunk_text = row["chunk_text"].strip()
        if not chunk_text or len(chunk_text) < min_chars:
            skipped += 1
            continue
        filtered.append(row)

    return filtered, skipped


def main() -> int:
    resolved_default_db_url = default_db_url()
    parser = argparse.ArgumentParser(description="Embed transcription chunks and store them in Postgres")
    parser.add_argument("input_json", help="Path to transcription metadata JSON, for example output/Tall_transcribed.json")
    parser.add_argument(
        "--db-url",
        default=resolved_default_db_url,
        help="Postgres connection URL including user and password. Defaults to postgresql://$RAG_USER:$RAG_PWD@localhost:5434/ragtest1",
    )
    parser.add_argument("--course-id", required=True, help="Course identifier")
    parser.add_argument("--presentation-id", required=True, help="Presentation identifier")
    parser.add_argument("--video-file", help="Override video_file stored in the database")
    parser.add_argument("--replace-source", action="store_true", help="Delete existing rows for the same course_id and presentation_id before insert")
    parser.add_argument("--embedding-model", default=DEFAULTS["embedding_model"], help="Embedding model name")
    parser.add_argument("--expected-embedding-dimensions", type=int, default=DEFAULTS["expected_embedding_dimensions"], help="Expected embedding dimension size for database validation")
    parser.add_argument("--max-embed-tokens", type=int, default=DEFAULTS["max_embed_tokens"], help="Maximum tokens per embedded subchunk")
    parser.add_argument("--api-base-url", default=DEFAULTS["api_base_url"], help="Berget API base URL")
    parser.add_argument("--min-chars", type=int, default=DEFAULTS["min_chars"], help="Skip chunks shorter than this many characters")
    parser.add_argument("--dry-run", action="store_true", help="Prepare rows and embeddings without writing to the database")
    args = parser.parse_args()

    input_path = Path(args.input_json)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not args.db_url:
        raise ValueError("--db-url is required unless RAG_USER and RAG_PWD are set")

    data = _load_transcription_json(input_path)
    video_file = args.video_file if args.video_file is not None else data.get("input_file")
    rows = _build_rows(data, input_path, video_file)
    tokenizer = AutoTokenizer.from_pretrained(args.embedding_model)
    rows = _split_rows_for_embedding(rows, tokenizer, args.max_embed_tokens)
    rows, skipped = _filter_rows(rows, args.min_chars)

    if not rows:
        print("No chunks to embed after filtering")
        return 0

    client = create_client(args.api_base_url)
    embeddings = []
    for index, row in enumerate(rows, start=1):
        log.info("Embedding chunk %s/%s", index, len(rows))
        embedding = embed_text(
            client,
            row["chunk_text"],
            args.embedding_model,
            args.expected_embedding_dimensions,
            role="passage",
        )
        row["metadata"]["embedding_model"] = args.embedding_model
        row["metadata"]["embedding_dimensions"] = len(embedding)
        row["metadata"]["embedding_role"] = "passage"
        embeddings.append(embedding)

    if args.dry_run:
        print(f"Dry run: prepared {len(rows)} rows, skipped {skipped}, no database changes made")
        return 0

    deleted = 0
    with connect_db(args.db_url) as conn:
        if args.replace_source:
            deleted = delete_chunks_for_source(conn, args.course_id, args.presentation_id)

        inserted = insert_chunk_rows(conn, rows, embeddings, args.course_id, args.presentation_id, video_file)
        conn.commit()

    print(f"Imported {inserted} rows from {input_path}")
    print(f"Skipped {skipped} chunks shorter than {args.min_chars} characters")
    if args.replace_source:
        print(f"Deleted {deleted} existing rows for course_id={args.course_id} presentation_id={args.presentation_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
