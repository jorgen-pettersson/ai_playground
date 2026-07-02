import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from extract_audio import extract_audio
from extract_framesv2 import extract_frames


def _run_script(script_name: str, args: list[str]) -> None:
    script_path = Path(__file__).resolve().parent / script_name
    cmd = [sys.executable, str(script_path), *args]
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full transcription pipeline for one MP4 file")
    parser.add_argument("input_file", help="Path to the MP4 file")
    parser.add_argument("--course-id", required=True, help="Course identifier for embed_chunks.py")
    parser.add_argument("--presentation-id", required=True, help="Presentation identifier for embed_chunks.py")
    parser.add_argument("--db-url", help="Postgres connection URL for embed_chunks.py")
    parser.add_argument("--video-file", help="Optional override for video_file stored by embed_chunks.py")
    parser.add_argument("--replace-source", action="store_true", help="Delete existing rows for the same course_id and presentation_id before insert")
    parser.add_argument("--embedding-model", help="Embedding model override for embed_chunks.py")
    parser.add_argument("--expected-embedding-dimensions", type=int, help="Expected embedding dimensions override for embed_chunks.py")
    parser.add_argument("--max-embed-tokens", type=int, help="Maximum tokens per embedded subchunk")
    parser.add_argument("--api-base-url", help="Berget API base URL override for transcribe.py and embed_chunks.py")
    parser.add_argument("--min-chars", type=int, help="Skip embedded chunks shorter than this many characters")
    parser.add_argument("--scene-threshold", type=float, default=0.2, help="Scene detection threshold for extract_framesv2.py")
    parser.add_argument("--blank-brightness-threshold", type=float, default=245.0, help="Blank frame brightness threshold for extract_framesv2.py")
    parser.add_argument("--blank-variance-threshold", type=float, default=80.0, help="Blank frame variance threshold for extract_framesv2.py")
    parser.add_argument("--blank-white-ratio-threshold", type=float, default=0.85, help="Blank frame white ratio threshold for extract_framesv2.py")
    parser.add_argument("--duplicate-diff-threshold", type=float, default=6.0, help="Duplicate frame diff threshold for extract_framesv2.py")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    audio_path = Path("output/audio") / f"{input_path.stem}.mp3"
    transcription_json_path = Path("output") / f"{audio_path.stem}_transcribed.json"

    print(f"Input video: {input_path}")
    print(f"Derived audio path: {audio_path}")
    print(f"Derived transcription JSON: {transcription_json_path}")

    print("Step 1-2/4: extract audio and frames in parallel")
    with ThreadPoolExecutor(max_workers=2) as executor:
        audio_future = executor.submit(extract_audio, str(input_path))
        frames_future = executor.submit(
            extract_frames,
            str(input_path),
            args.scene_threshold,
            args.blank_brightness_threshold,
            args.blank_variance_threshold,
            args.blank_white_ratio_threshold,
            args.duplicate_diff_threshold,
        )
        audio_future.result()
        frames_future.result()

    print("Step 3/4: transcribe audio")
    transcribe_args = [str(audio_path)]
    if args.api_base_url:
        transcribe_args.extend(["--api-base-url", args.api_base_url])
    _run_script("transcribe.py", transcribe_args)

    print("Step 4/4: embed chunks")
    embed_args = [
        str(transcription_json_path),
        "--course-id", args.course_id,
        "--presentation-id", args.presentation_id,
    ]
    if args.db_url:
        embed_args.extend(["--db-url", args.db_url])
    if args.video_file:
        embed_args.extend(["--video-file", args.video_file])
    if args.replace_source:
        embed_args.append("--replace-source")
    if args.embedding_model:
        embed_args.extend(["--embedding-model", args.embedding_model])
    if args.expected_embedding_dimensions is not None:
        embed_args.extend(["--expected-embedding-dimensions", str(args.expected_embedding_dimensions)])
    if args.max_embed_tokens is not None:
        embed_args.extend(["--max-embed-tokens", str(args.max_embed_tokens)])
    if args.api_base_url:
        embed_args.extend(["--api-base-url", args.api_base_url])
    if args.min_chars is not None:
        embed_args.extend(["--min-chars", str(args.min_chars)])
    _run_script("embed_chunks.py", embed_args)

    print("Pipeline complete")
    print(f"Audio: {audio_path}")
    print(f"Transcription JSON: {transcription_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
