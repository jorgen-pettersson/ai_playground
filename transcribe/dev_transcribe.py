import argparse
import json
import os
import sys
from pathlib import Path

from openai import APIError, APIStatusError, OpenAI


DEFAULTS = {
    "whisper_model": "KBLab/kb-whisper-large",
    "language": "sv",
    "api_base_url": "https://api.berget.ai/v1",
}


def _extract_error_payload(error: Exception) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload one audio file to Berget and print the transcript"
    )
    parser.add_argument("input_file", help="Path to the MP3 or audio file")
    parser.add_argument("--model", default=DEFAULTS["whisper_model"], help="Whisper model")
    parser.add_argument("--language", default=DEFAULTS["language"], help="Language code")
    parser.add_argument("--prompt", help="Optional transcription prompt")
    args = parser.parse_args()

    api_key = os.environ.get("BERGET_API_KEY", "")
    if not api_key:
        print("Error: BERGET_API_KEY environment variable not set", file=sys.stderr)
        return 1

    input_path = Path(args.input_file)
    if not input_path.exists() or not input_path.is_file():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    client = OpenAI(
        api_key=api_key,
        base_url=DEFAULTS["api_base_url"],
        timeout=60,
        max_retries=0,
    )

    try:
        with input_path.open("rb") as audio_file:
            request = {
                "model": args.model,
                "file": audio_file,
                "language": args.language,
            }
            if args.prompt:
                request["prompt"] = args.prompt

            result = client.audio.transcriptions.create(**request)
    except APIStatusError as error:
        print(_extract_error_payload(error), file=sys.stderr)
        return 1
    except APIError as error:
        print(_extract_error_payload(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1

    text = getattr(result, "text", "")
    if not text or not text.strip():
        print("Error: Empty transcription response", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
