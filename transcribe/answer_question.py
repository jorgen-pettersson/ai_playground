import argparse

from berget_rag import DEFAULTS
from chunk_repository import default_db_url
from course_rag import DEFAULT_COURSE_ID, answer_course_question


def main() -> int:
    resolved_default_db_url = default_db_url()
    parser = argparse.ArgumentParser(description="Answer a course question using RAG plus Berget chat completions")
    parser.add_argument("question", help="Question to answer")
    parser.add_argument("--course-id", default=DEFAULT_COURSE_ID, help="Course identifier to filter on")
    parser.add_argument(
        "--db-url",
        default=resolved_default_db_url,
        help="Postgres connection URL including user and password. Defaults to postgresql://$RAG_USER:$RAG_PWD@localhost:5434/ragtest1",
    )
    parser.add_argument("--api-base-url", default=DEFAULTS["api_base_url"], help="Berget API base URL")
    parser.add_argument("--embedding-model", default=DEFAULTS["embedding_model"], help="Embedding model name")
    parser.add_argument("--expected-embedding-dimensions", type=int, default=DEFAULTS["expected_embedding_dimensions"], help="Expected embedding dimension size for database validation")
    parser.add_argument("--chat-model", default="openai/gpt-oss-120b", help="Chat completion model")
    parser.add_argument("--min-similarity", type=float, default=0.7, help="Minimum cosine similarity to count as a match")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of retrieved chunks")
    parser.add_argument("--temperature", type=float, default=0.7, help="Chat completion temperature")
    parser.add_argument("--max-tokens", type=int, default=1000, help="Maximum completion tokens")
    parser.add_argument("--show-context", action="store_true", help="Print the constructed user prompt before the answer")
    args = parser.parse_args()

    if not args.db_url:
        raise ValueError("--db-url is required unless RAG_USER and RAG_PWD are set")
    if not -1.0 <= args.min_similarity <= 1.0:
        raise ValueError("--min-similarity must be between -1.0 and 1.0")

    result = answer_course_question(
        args.question,
        course_id=args.course_id,
        db_url=args.db_url,
        api_base_url=args.api_base_url,
        embedding_model=args.embedding_model,
        expected_embedding_dimensions=args.expected_embedding_dimensions,
        chat_model=args.chat_model,
        min_similarity=args.min_similarity,
        limit=args.limit,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    if args.show_context:
        print("=== Context ===")
        print(result["user_prompt"])
        print("=== Answer ===")
    print(result["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
