import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import time
import wave
import threading
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
#import pyaudiowpatch as pyaudio
from openai import OpenAI

log = logging.getLogger("recorder")


DEFAULTS = {
    "whisper_model": "KBLab/kb-whisper-large",
    "llm_model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "language": "sv",
    "keep_audio": False,
    "min_seconds": 30,
    "output_dir": "~/Recordings",
    "api_base_url": "https://api.berget.ai/v1",
    "chunk_duration": 120,
}

def load_config() -> dict:
    return DEFAULTS

def _transcribe_file(audio_path: Path, client: OpenAI, cfg: dict) -> str:
    """Transcribe a single audio file via berget.ai API. Returns plain text."""
    with open(audio_path, "rb") as f:
        kwargs = {
            "model": cfg["whisper_model"],
            "file": f,
            "language": cfg["language"],
        }
        if cfg.get("prompt"):
            kwargs["prompt"] = cfg["prompt"]
        result = client.audio.transcriptions.create(**kwargs)
    return result.text.strip()


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio file duration in seconds using FFprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _split_audio_file(audio_path: Path, chunk_duration: int) -> list[Path]:
    """Split MP3 file into chunks using FFmpeg."""
    temp_dir = tempfile.mkdtemp(prefix="transcribe_chunks_")
    
    cmd = [
        "ffmpeg",
        "-i", str(audio_path),
        "-f", "segment",
        "-segment_time", str(chunk_duration),
        "-c", "copy",
        f"{temp_dir}/chunk_%03d.mp3"
    ]
    
    subprocess.run(cmd, capture_output=True, check=True)
    
    chunk_files = sorted(Path(temp_dir).glob("chunk_*.mp3"))
    return chunk_files if chunk_files else []


def _transcribe_chunks(chunk_paths: list[Path], client: OpenAI, cfg: dict) -> str:
    """Transcribe audio chunks sequentially and concatenate results."""
    transcriptions = []
    
    for chunk_path in chunk_paths:
        log.info(f"Transcribing chunk: {chunk_path.name}")
        text = _transcribe_file(chunk_path, client, cfg)
        transcriptions.append(text)
    
    return " ".join(transcriptions)


def _transcribe_file_with_chunks(audio_path: Path, client: OpenAI, cfg: dict) -> str:
    """Transcribe audio file, splitting into chunks if needed."""
    chunk_duration = cfg.get("chunk_duration", 120)
    duration = _get_audio_duration(audio_path)
    
    log.info(f"Audio duration: {duration:.2f}s, chunk duration: {chunk_duration}s")
    
    if duration <= chunk_duration:
        return _transcribe_file(audio_path, client, cfg)
    
    chunk_paths = _split_audio_file(audio_path, chunk_duration)
    
    if not chunk_paths:
        log.error("Failed to split audio file")
        return ""
    
    try:
        return _transcribe_chunks(chunk_paths, client, cfg)
    finally:
        if not cfg.get("keep_audio", False):
            temp_dir = chunk_paths[0].parent
            shutil.rmtree(temp_dir, ignore_errors=True)



cfg = load_config()
api_key = os.environ.get("BERGET_API_KEY", "")

client = OpenAI(api_key=api_key, base_url=cfg["api_base_url"],
                timeout=60, max_retries=0)

parser = argparse.ArgumentParser(description="Transcribe audio file using Whisper API")
parser.add_argument("input_file", type=str, help="Path to the audio file to transcribe")
args = parser.parse_args()

input_path = Path(args.input_file)
if not input_path.exists():
    print(f"Error: File not found: {input_path}")
    exit(1)

text = _transcribe_file_with_chunks(input_path, client, cfg)

output_path = input_path.with_suffix(".txt")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"Transcription saved to: {output_path}")