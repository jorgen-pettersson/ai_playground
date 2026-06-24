import argparse
import subprocess
from pathlib import Path

def extract_frames(input_file: str, scene_threshold: float = 0.2) -> None:
    """Extract unique frames from video using ffmpeg scene detection."""
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        exit(1)
    
    # Create slides directory
    slides_dir = Path("output/slides")
    slides_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output pattern: slides/{filename}_slide_%04d.jpg
    output_pattern = slides_dir / f"{input_path.stem}_slide_%04d.jpg"
    
    print(f"Extracting frames from: {input_path}")
    print(f"Output directory: {slides_dir}")
    print(f"Scene detection threshold: {scene_threshold}")
    
    # Build ffmpeg command
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-vf", f"select='gt(scene,{scene_threshold})'",
        "-vsync", "vfr",
        "-qscale:v", "2",
        str(output_pattern)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✓ Frame extraction complete")
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frames: {e}")
        exit(1)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract unique frames from video using ffmpeg")
    parser.add_argument("input_file", type=str, help="Path to the video file")
    parser.add_argument("--threshold", type=float, default=0.2, help="Scene detection threshold (default: 0.2)")
    args = parser.parse_args()
    
    extract_frames(args.input_file, args.threshold)
