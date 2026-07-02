import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat


def _extract_candidate_frames(input_path: Path, scene_threshold: float) -> tuple[list[Path], list[float], Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{input_path.stem}_slides_"))
    output_pattern = temp_dir / f"{input_path.stem}_candidate_%04d.jpg"

    cmd = [
        "ffmpeg",
        "-loglevel", "verbose",
        "-i", str(input_path),
        "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
        "-vsync", "vfr",
        "-qscale:v", "2",
        str(output_pattern),
    ]

    result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    timestamps = []
    frame_pattern = re.compile(r'pts_time:[\s]*([\d\.]+)')
    for line in result.stderr.splitlines():
        if 'showinfo' in line or 'select' in line:
            match = frame_pattern.search(line)
            if match:
                timestamps.append(float(match.group(1)))

    candidate_files = sorted(temp_dir.glob("*.jpg"), key=lambda p: p.stem)
    return candidate_files, timestamps, temp_dir


def _image_stats(image_path: Path) -> dict:
    with Image.open(image_path) as img:
        gray = img.convert("L")
        resized = gray.resize((320, 180))
        cropped = resized.crop((24, 16, 296, 164))
        stat = ImageStat.Stat(resized)
        mean = stat.mean[0]
        variance = stat.var[0]
        histogram = resized.histogram()
        total_pixels = resized.width * resized.height
        white_ratio = sum(histogram[245:]) / total_pixels
        dark_ratio = sum(histogram[:20]) / total_pixels
        edge_mean = ImageStat.Stat(cropped.filter(ImageFilter.FIND_EDGES)).mean[0]
        cropped_stat = ImageStat.Stat(cropped)
        cropped_variance = cropped_stat.var[0]

    return {
        "mean": mean,
        "variance": variance,
        "cropped_variance": cropped_variance,
        "white_ratio": white_ratio,
        "dark_ratio": dark_ratio,
        "edge_mean": edge_mean,
    }


def _is_blank(stats: dict, blank_brightness_threshold: float, blank_variance_threshold: float, blank_white_ratio_threshold: float) -> bool:
    low_information = stats["edge_mean"] <= 6.0 and stats["cropped_variance"] <= blank_variance_threshold * 1.2

    return (
        (
            stats["mean"] >= blank_brightness_threshold
            and stats["variance"] <= blank_variance_threshold
            and stats["white_ratio"] >= blank_white_ratio_threshold
        )
        or (
            stats["variance"] <= blank_variance_threshold * 0.7
            and stats["white_ratio"] >= blank_white_ratio_threshold * 0.65
            and low_information
        )
        or (
            stats["mean"] >= blank_brightness_threshold - 25
            and low_information
            and stats["dark_ratio"] <= 0.02
        )
        or (
            stats["white_ratio"] >= 0.65
            and stats["edge_mean"] <= 9.5
        )
    )


def _frame_diff_score(first_path: Path, second_path: Path) -> float:
    with Image.open(first_path) as first_img, Image.open(second_path) as second_img:
        first = first_img.convert("L").resize((320, 180)).crop((24, 16, 296, 164))
        second = second_img.convert("L").resize((320, 180)).crop((24, 16, 296, 164))
        diff = ImageChops.difference(first, second)
        stat = ImageStat.Stat(diff)
        return stat.mean[0]


def _frame_score(stats: dict, file_path: Path) -> float:
    # Favor contentful, non-blank frames with more detail.
    return (
        stats["cropped_variance"]
        + (stats["edge_mean"] * 8)
        - (stats["white_ratio"] * 100)
        + math.log(max(file_path.stat().st_size, 1))
    )


def _drop_bridge_transitions(candidates: list[dict], duplicate_diff_threshold: float) -> list[dict]:
    if len(candidates) < 3:
        return candidates

    filtered = []
    for index, candidate in enumerate(candidates):
        if index == 0 or index == len(candidates) - 1:
            filtered.append(candidate)
            continue

        previous_candidate = candidates[index - 1]
        next_candidate = candidates[index + 1]
        previous_diff = _frame_diff_score(previous_candidate["path"], candidate["path"])
        next_diff = _frame_diff_score(candidate["path"], next_candidate["path"])
        skip_diff = _frame_diff_score(previous_candidate["path"], next_candidate["path"])

        if (
            skip_diff <= duplicate_diff_threshold
            and previous_diff > duplicate_diff_threshold * 3
            and next_diff > duplicate_diff_threshold * 3
        ):
            continue

        filtered.append(candidate)

    return filtered


def _is_transition_like(candidate: dict, anchor: dict, duplicate_diff_threshold: float) -> bool:
    anchor_diff = _frame_diff_score(anchor["path"], candidate["path"])
    if anchor_diff <= duplicate_diff_threshold * 1.8:
        return True

    return (
        candidate["stats"]["edge_mean"] <= max(anchor["stats"]["edge_mean"] * 0.65, 6.0)
        and candidate["stats"]["cropped_variance"] <= max(anchor["stats"]["cropped_variance"] * 0.6, 90.0)
        and candidate["stats"]["white_ratio"] >= anchor["stats"]["white_ratio"]
    )


def _filter_candidates(
    candidate_files: list[Path],
    timestamps: list[float],
    blank_brightness_threshold: float,
    blank_variance_threshold: float,
    blank_white_ratio_threshold: float,
    duplicate_diff_threshold: float,
) -> list[dict]:
    candidates = []
    for idx, candidate_file in enumerate(candidate_files):
        stats = _image_stats(candidate_file)
        candidates.append({
            "path": candidate_file,
            "timestamp": timestamps[idx] if idx < len(timestamps) else None,
            "stats": stats,
            "score": _frame_score(stats, candidate_file),
            "is_blank": _is_blank(
                stats,
                blank_brightness_threshold,
                blank_variance_threshold,
                blank_white_ratio_threshold,
            ),
        })

    non_blank_candidates = [candidate for candidate in candidates if not candidate["is_blank"]]
    non_blank_candidates = _drop_bridge_transitions(non_blank_candidates, duplicate_diff_threshold)

    kept_groups: list[list[dict]] = []
    current_group: list[dict] = []
    current_anchor: dict | None = None

    for candidate in non_blank_candidates:
        if not current_group:
            current_group = [candidate]
            current_anchor = candidate
            continue

        assert current_anchor is not None
        anchor_diff = _frame_diff_score(current_anchor["path"], candidate["path"])
        prev_diff = _frame_diff_score(current_group[-1]["path"], candidate["path"])
        if anchor_diff <= duplicate_diff_threshold or prev_diff <= duplicate_diff_threshold or _is_transition_like(candidate, current_anchor, duplicate_diff_threshold):
            current_group.append(candidate)
            if candidate["score"] > current_anchor["score"]:
                current_anchor = candidate
        else:
            kept_groups.append(current_group)
            current_group = [candidate]
            current_anchor = candidate

    if current_group:
        kept_groups.append(current_group)

    filtered = []
    for group in kept_groups:
        best = max(group, key=lambda item: item["score"])
        filtered.append(best)

    return filtered


def _write_outputs(input_path: Path, filtered_candidates: list[dict], original_candidate_count: int, output_dir: Path) -> Path:
    slides_dir = output_dir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)

    for existing_file in slides_dir.glob(f"{input_path.stem}_slide_*.jpg"):
        existing_file.unlink()

    slides = []
    for index, candidate in enumerate(filtered_candidates, start=1):
        output_name = f"{input_path.stem}_slide_{index:04d}.jpg"
        output_path = slides_dir / output_name
        shutil.copy2(candidate["path"], output_path)
        slides.append({
            "frame": index,
            "timestamp": candidate["timestamp"],
            "image": str(output_path.relative_to(output_dir)),
        })

    metadata = {
        "input_file": input_path.name,
        "original_candidate_count": original_candidate_count,
        "total_frames": len(slides),
        "slides": slides,
    }

    metadata_path = output_dir / f"{input_path.stem}_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return metadata_path


def extract_frames(
    input_file: str,
    scene_threshold: float = 0.2,
    blank_brightness_threshold: float = 245.0,
    blank_variance_threshold: float = 80.0,
    blank_white_ratio_threshold: float = 0.85,
    duplicate_diff_threshold: float = 6.0,
) -> None:
    input_path = Path(input_file)

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        raise SystemExit(1)

    print(f"Extracting frames from: {input_path}")
    print(f"Scene detection threshold: {scene_threshold}")

    try:
        candidate_files, timestamps, temp_dir = _extract_candidate_frames(input_path, scene_threshold)
        filtered_candidates = _filter_candidates(
            candidate_files,
            timestamps,
            blank_brightness_threshold,
            blank_variance_threshold,
            blank_white_ratio_threshold,
            duplicate_diff_threshold,
        )

        output_dir = Path("output")
        metadata_path = _write_outputs(input_path, filtered_candidates, len(candidate_files), output_dir)

        print(f"✓ Candidate frames extracted: {len(candidate_files)}")
        print(f"✓ Final slide frames kept: {len(filtered_candidates)}")
        print(f"✓ Metadata saved to: {metadata_path}")
    except subprocess.CalledProcessError as error:
        print(f"Error extracting frames: {error}")
        print(f"FFmpeg stderr: {error.stderr}")
        raise SystemExit(1)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        raise SystemExit(1)
    finally:
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and filter slide frames from video")
    parser.add_argument("input_file", type=str, help="Path to the video file")
    parser.add_argument("--threshold", type=float, default=0.2, help="Scene detection threshold (default: 0.2)")
    parser.add_argument("--blank-brightness-threshold", type=float, default=245.0, help="Mean brightness threshold for blank frame filtering")
    parser.add_argument("--blank-variance-threshold", type=float, default=80.0, help="Variance threshold for blank frame filtering")
    parser.add_argument("--blank-white-ratio-threshold", type=float, default=0.85, help="White pixel ratio threshold for blank frame filtering")
    parser.add_argument("--duplicate-diff-threshold", type=float, default=6.0, help="Mean absolute grayscale difference threshold for duplicate grouping")
    args = parser.parse_args()

    extract_frames(
        args.input_file,
        args.threshold,
        args.blank_brightness_threshold,
        args.blank_variance_threshold,
        args.blank_white_ratio_threshold,
        args.duplicate_diff_threshold,
    )
