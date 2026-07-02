import argparse

from berget_rag import DEFAULTS, connect_db, create_client, default_db_url, embed_text, vector_literal


# --select id, 1 - (embedding <=> cast(%s as vector)) as similarity
def _find_matches(conn, course_id: str, embedding: list[float], min_similarity: float) -> list[tuple[int, float]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select id, similarity
            from (
                select id, 1 - (embedding <=> %s) as similarity
                from chunks
                where course_id = %s
            ) matches
            where similarity >= %s
            order by similarity desc, id asc
            -- limit 10    
            """,
            (vector_literal(embedding), course_id, min_similarity),
        )
        return [(row[0], float(row[1])) for row in cur.fetchall()]


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
    
    print(embedding)

    with connect_db(args.db_url) as conn:
        matches = _find_matches(conn, args.course_id, embedding, args.min_similarity)

    for row_id, similarity in matches:
        print(f"{row_id}\t{similarity:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
