import argparse

from berget_rag import DEFAULTS, create_client, embed_text
from chunk_repository import connect_db, default_db_url, search_course_chunks


def main() -> int:
    resolved_default_db_url = default_db_url()
    parser = argparse.ArgumentParser(description="Embed a query and list matching chunk rows")
    parser.add_argument("query_text", help="Text to embed and search for")
    parser.add_argument("--course-id", required=True, help="Course identifier to filter on")
    parser.add_argument(
        "--db-url",
        default=resolved_default_db_url,
        help="Postgres connection URL including user and password. Defaults to postgresql://$RAG_USER:$RAG_PWD@localhost:5434/ragtest1",
    )
    parser.add_argument("--embedding-model", default=DEFAULTS["embedding_model"], help="Embedding model name")
    parser.add_argument("--expected-embedding-dimensions", type=int, default=DEFAULTS["expected_embedding_dimensions"], help="Expected embedding dimension size for database validation")
    parser.add_argument("--api-base-url", default=DEFAULTS["api_base_url"], help="Berget API base URL")
    parser.add_argument("--min-similarity", type=float, default=0.7, help="Minimum cosine similarity to count as a match")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of rows to return")
    args = parser.parse_args()

    if not args.db_url:
        raise ValueError("--db-url is required unless RAG_USER and RAG_PWD are set")
    if not -1.0 <= args.min_similarity <= 1.0:
        raise ValueError("--min-similarity must be between -1.0 and 1.0")

    client = create_client(args.api_base_url)
    embedding = embed_text(
        client,
        args.query_text,
        args.embedding_model,
        args.expected_embedding_dimensions,
        role="query",
    )

    with connect_db(args.db_url) as conn:
        matches = search_course_chunks(conn, args.course_id, embedding, args.min_similarity, args.limit)

    for match in matches:
        print(f"{match['id']}\t{float(match['similarity']):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
