import argparse
import subprocess
from pathlib import Path

def extract_audio(input_file: str) -> None:
    """Extract audio from video file using FFmpeg and save as MP3."""
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        exit(1)
    
    # Create audio directory
    audio_dir = Path("output/audio")
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output filename: take original filename and change extension to .mp3
    output_filename = input_path.stem + ".mp3"
    output_path = audio_dir / output_filename
    
    print(f"Extracting audio from: {input_path}")
    print(f"Output directory: {audio_dir}")
    
    # Build ffmpeg command. This is more reliable than VLC for paths with
    # spaces, commas, and non-ASCII characters.
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vn",
        "-codec:a", "libmp3lame",
        "-b:a", "320k",
        "-ac", "2",
        "-ar", "48000",
        str(output_path),
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✓ Audio extraction complete: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e}")
        exit(1)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg.")
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract MP3 audio from video file using ffmpeg")
    parser.add_argument("input_file", type=str, help="Path to the video file to extract audio from")
    args = parser.parse_args()
    
    extract_audio(args.input_file)
