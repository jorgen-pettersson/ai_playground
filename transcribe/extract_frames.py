import argparse
import json
import subprocess
import re
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
    
    # Build ffmpeg command with showinfo to capture frame info
    cmd = [
        "ffmpeg",
        "-loglevel", "verbose",
        "-i", str(input_path),
        "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
        "-vsync", "vfr",
        "-qscale:v", "2",
        str(output_pattern)
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Parse timestamps from ffmpeg stderr
        timestamps = []
        frame_pattern = re.compile(r'pts_time:[\s]*([\d\.]+)')

        for line in result.stderr.splitlines():
            if 'showinfo' in line or 'select' in line:
                match = frame_pattern.search(line)
                if match:
                    timestamp = float(match.group(1))
                    timestamps.append(timestamp)
        
        # Get actual slide files created by ffmpeg
        slide_files = sorted(slides_dir.glob("*.jpg"), key=lambda p: p.stem)
        
        # Create metadata file in output directory
        output_dir = Path("output")
        metadata_file = output_dir / f"{input_path.stem}_metadata.json"

        slides = []
        for idx, slide_file in enumerate(slide_files):
            frame_num = int(slide_file.stem.split('_')[-1])
            timestamp = timestamps[idx] if idx < len(timestamps) else None
            relative_path = slide_file.relative_to(output_dir)
            slides.append({
                "frame": frame_num,
                "timestamp": timestamp,
                "image": str(relative_path),
            })

        metadata = {
            "input_file": input_path.name,
            "total_frames": len(slides),
            "slides": slides,
        }

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        print(f"✓ Frame extraction complete: {len(slide_files)} frames")
        print(f"✓ Metadata saved to: {metadata_file}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frames: {e}")
        print(f"FFmpeg stderr: {e.stderr}")
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
