import argparse
import subprocess
from pathlib import Path

def extract_audio(input_file: str) -> None:
    """Extract audio from video file using VLC and save as MP3."""
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
    
    # Build cvlc command
    cmd = [
        "cvlc",
        "--play-and-exit",
        str(input_path),
        "--no-sout-video",
        "--sout-audio",
        f"--sout=#transcode{{acodec=mp3,ab=320,channels=2,samplerate=48000}}:std{{access=file,mux=raw,dst={output_path}}}"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✓ Audio extraction complete: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error extracting audio: {e}")
        exit(1)
    except FileNotFoundError:
        print("Error: cvlc not found. Please install VLC media player.")
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract MP3 audio from video file using VLC")
    parser.add_argument("input_file", type=str, help="Path to the video file to extract audio from")
    args = parser.parse_args()
    
    extract_audio(args.input_file)