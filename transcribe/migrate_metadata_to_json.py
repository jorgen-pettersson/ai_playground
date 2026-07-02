import argparse
import json
import re
from pathlib import Path


TIMESTAMP_ROW_PATTERN = re.compile(
    r'^\|\s*(\d+)\s*\|\s*([\d.]+)s\s*\((\d+):(\d+)\)\s*\|\s*(.+?)\s*\|\s*$'
)
N_A_ROW_PATTERN = re.compile(r'^\|\s*(\d+)\s*\|\s*N/A\s*\|\s*(.+?)\s*\|\s*$')
TOTAL_FRAMES_PATTERN = re.compile(r'^Total frames extracted:\s*(\d+)\s*$')


def _parse_metadata_file(metadata_file: Path) -> dict:
    slides = []
    total_frames = None

    with open(metadata_file, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            total_match = TOTAL_FRAMES_PATTERN.match(line)
            if total_match:
                total_frames = int(total_match.group(1))
                continue

            timestamp_match = TIMESTAMP_ROW_PATTERN.match(line)
            if timestamp_match:
                slides.append({
                    "frame": int(timestamp_match.group(1)),
                    "timestamp": float(timestamp_match.group(2)),
                    "image": timestamp_match.group(5).strip(),
                })
                continue

            na_match = N_A_ROW_PATTERN.match(line)
            if na_match:
                slides.append({
                    "frame": int(na_match.group(1)),
                    "timestamp": None,
                    "image": na_match.group(2).strip(),
                })

    if total_frames is None:
        total_frames = len(slides)

    input_name = metadata_file.name.removesuffix("_metadata.md")
    return {
        "input_file": input_name,
        "total_frames": total_frames,
        "slides": slides,
    }


def migrate_metadata_file(metadata_file: Path, overwrite: bool = False) -> Path:
    output_file = metadata_file.with_name(metadata_file.name.removesuffix(".md") + ".json")
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_file}")

    metadata = _parse_metadata_file(metadata_file)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return output_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate frame metadata markdown files to JSON")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Specific *_metadata.md files to migrate. Defaults to output/*_metadata.md",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSON files",
    )
    args = parser.parse_args()

    if args.paths:
        metadata_files = [Path(path) for path in args.paths]
    else:
        metadata_files = sorted(Path("output").glob("*_metadata.md"))

    if not metadata_files:
        print("No *_metadata.md files found")
        return 0

    exit_code = 0
    for metadata_file in metadata_files:
        if not metadata_file.exists():
            print(f"Skipping missing file: {metadata_file}")
            exit_code = 1
            continue

        try:
            output_file = migrate_metadata_file(metadata_file, overwrite=args.overwrite)
            print(f"Migrated: {metadata_file} -> {output_file}")
        except Exception as error:
            print(f"Failed: {metadata_file}: {error}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
