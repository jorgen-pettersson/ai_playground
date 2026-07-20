import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import wave
import threading
import logging
import tempfile
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
#import pyaudiowpatch as pyaudio
from openai import OpenAI

log = logging.getLogger("recorder")
logging.basicConfig(level=logging.INFO)

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


def _extract_error_details(error: Exception) -> str:
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


def _raw_segments_from_result(result) -> list:
    if hasattr(result, '__dict__'):
        raw_segments = result.__dict__.get('segments')
        if isinstance(raw_segments, dict):
            nested_segments = raw_segments.get('segments')
            if isinstance(nested_segments, list):
                log.info(
                    "Unwrapped nested segments payload from __dict__ on %s: %s",
                    type(result).__name__,
                    len(nested_segments),
                )
                return list(nested_segments)
        if isinstance(raw_segments, (list, tuple)):
            return list(raw_segments)

    if hasattr(result, 'segments'):
        segments = result.segments
        if isinstance(segments, dict):
            nested_segments = segments.get('segments')
            if isinstance(nested_segments, list):
                log.info(
                    "Unwrapped nested segments payload from attribute on %s: %s",
                    type(result).__name__,
                    len(nested_segments),
                )
                return list(nested_segments)
        if isinstance(segments, (list, tuple)):
            return list(segments)
        log.info("Unsupported segments container on %s: %s", type(result).__name__, type(segments).__name__)

    if hasattr(result, 'model_dump'):
        try:
            payload = result.model_dump()
            segments = payload.get('segments') if isinstance(payload, dict) else None
            if isinstance(segments, dict):
                nested_segments = segments.get('segments')
                if isinstance(nested_segments, list):
                    log.info(
                        "Unwrapped nested segments payload from model_dump() on %s: %s",
                        type(result).__name__,
                        len(nested_segments),
                    )
                    return list(nested_segments)
            if segments:
                return list(segments)
            log.info(
                "model_dump() for %s returned segments=%s",
                type(result).__name__,
                0 if not segments else len(segments),
            )
        except Exception as e:
            log.info("Failed to read segments via model_dump() from %s: %s", type(result).__name__, e)

    if isinstance(result, dict):
        segments = result.get('segments')
        if isinstance(segments, dict):
            nested_segments = segments.get('segments')
            if isinstance(nested_segments, list):
                return list(nested_segments)
        return list(segments) if segments else []
    return []


def _segment_preview(segment) -> str:
    if hasattr(segment, 'model_dump'):
        payload = segment.model_dump()
    elif isinstance(segment, dict):
        payload = segment
    else:
        payload = {
            'start': getattr(segment, 'start', None),
            'end': getattr(segment, 'end', None),
            'text': getattr(segment, 'text', None),
        }

    text = (payload.get('text') or '').strip().replace('\n', ' ')
    if len(text) > 80:
        text = text[:77] + '...'
    return f"start={payload.get('start')} end={payload.get('end')} text={text!r}"


def _load_slides_metadata(input_path: Path) -> list[dict]:
    output_dir = Path("output")
    metadata_file = output_dir / f"{input_path.stem}_metadata.json"

    if metadata_file.exists():
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        return [
            slide for slide in metadata.get('slides', [])
            if slide.get('timestamp') is not None
        ]

    return []


def _segment_to_dict(segment) -> dict | None:
    if hasattr(segment, 'model_dump'):
        segment_dict = segment.model_dump()
    elif isinstance(segment, dict):
        segment_dict = segment.copy()
    else:
        start = getattr(segment, 'start', None)
        end = getattr(segment, 'end', None)
        text = getattr(segment, 'text', None)
        if start is None or end is None or text is None:
            log.info("Dropping segment missing attributes: %s", _segment_preview(segment))
            return None
        segment_dict = {
            'start': start,
            'end': end,
            'text': text,
        }

    if segment_dict.get('start') is None or segment_dict.get('end') is None:
        log.info("Dropping segment missing start/end: %s", _segment_preview(segment))
        return None
    if segment_dict.get('text') is None:
        segment_dict['text'] = ''

    return segment_dict


def _map_transcriptions_to_slides(slides_data: list[dict], result: dict) -> list[dict]:
    mapped_transcriptions = []

    if slides_data and result.get('segments'):
        for i, slide_data in enumerate(slides_data):
            slide_start = slide_data['timestamp']
            slide_end = slides_data[i + 1]['timestamp'] if i + 1 < len(slides_data) else float('inf')

            slide_text = []
            for segment in result['segments']:
                seg_start = segment.get('start', 0)
                if seg_start >= slide_start and seg_start < slide_end:
                    slide_text.append(segment.get('text', ''))

            mapped_transcriptions.append({
                'frame': slide_data['frame'],
                'timestamp': slide_start,
                'image': slide_data['image'],
                'text': ' '.join(text.strip() for text in slide_text if text.strip())
            })
    elif not result.get('segments') and slides_data and result.get('text'):
        total_duration = slides_data[-1]['timestamp'] + 60  # estimate total duration
        text_by_char = result['text']
        chars_per_second = len(text_by_char) / total_duration

        for i, slide_data in enumerate(slides_data):
            slide_start = slide_data['timestamp']
            slide_end = slides_data[i + 1]['timestamp'] if i + 1 < len(slides_data) else total_duration

            char_start = int(slide_start * chars_per_second)
            char_end = int(slide_end * chars_per_second)

            slide_text = text_by_char[char_start:char_end]
            mapped_transcriptions.append({
                'frame': slide_data['frame'],
                'timestamp': slide_start,
                'image': slide_data['image'],
                'text': slide_text.strip()
            })

    return mapped_transcriptions


def _write_transcription_outputs(input_path: Path, result: dict, slides_data: list[dict]) -> tuple[Path, Path]:
    output_dir = Path("output")
    texts_dir = output_dir / "texts"
    texts_dir.mkdir(parents=True, exist_ok=True)

    output_txt_path = texts_dir / f"{input_path.stem}.txt"
    with open(output_txt_path, 'w', encoding='utf-8') as f:
        f.write(result.get('text', ''))

    mapped_transcriptions = _map_transcriptions_to_slides(slides_data, result)
    failed_chunks = result.get('failed_chunks', [])

    output_json_path = output_dir / f"{input_path.stem}_transcribed.json"
    metadata = {
        "input_file": input_path.name,
        "transcript_text": result.get('text', ''),
        "segments": result.get('segments', []),
        "slides": mapped_transcriptions,
        "failed_chunks": failed_chunks,
    }

    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return output_txt_path, output_json_path

def _transcribe_file(audio_path: Path, client: OpenAI, cfg: dict, audio_duration: float = None) -> dict:
    """Transcribe a single audio file via berget.ai API. Returns response with timestamps."""
    log.info(f"Starting transcription for: {audio_path.name}")
    
    try:
        with open(audio_path, "rb") as f:
            kwargs = {
                "model": cfg["whisper_model"],
                "file": f,
                "language": cfg["language"],
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment"]
            }
            if cfg.get("prompt"):
                kwargs["prompt"] = cfg["prompt"]
            result = client.audio.transcriptions.create(**kwargs)
            raw_segments = _raw_segments_from_result(result)
            log.info(
                "Transcription response for %s: type=%s has_segments=%s raw_segments=%s",
                audio_path.name,
                type(result).__name__,
                hasattr(result, 'segments') or (isinstance(result, dict) and 'segments' in result),
                len(raw_segments),
            )
            if raw_segments:
                log.info("First raw segment for %s: %s", audio_path.name, _segment_preview(raw_segments[0]))
            
            log.info(f"Transcription completed for: {audio_path.name}")
            
            # If we don't get segments, generate synthetic timestamps
            if not hasattr(result, 'segments') or not result.segments:
                log.warning("No segments returned, generating synthetic timestamps")
                text = result.text if hasattr(result, 'text') else result
                # Split text into sentences and generate timestamps
                sentences = [s.strip() for s in text.split('.') if s.strip()]
                if audio_duration and sentences:
                    segment_duration = audio_duration / len(sentences)
                    segments = []
                    for i, sentence in enumerate(sentences):
                        start = i * segment_duration
                        end = start + segment_duration
                        segments.append({
                            'start': start,
                            'end': end,
                            'text': sentence + '.'
                        })
                    result = SimpleNamespace(text=text, segments=segments)
                    log.info("Generated %s synthetic segments for %s", len(segments), audio_path.name)
                else:
                    log.error("Could not generate synthetic timestamps - missing audio duration or text")
        return result
    except Exception as e:
        log.error(f"Error during transcription of {audio_path.name}: {_extract_error_details(e)}")
        raise


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


def _transcribe_chunks(chunk_paths: list[Path], client: OpenAI, cfg: dict, progress_callback=None) -> dict:
    """Transcribe audio chunks sequentially and concatenate results with adjusted timestamps."""
    all_segments = []
    all_text_parts = []
    failed_chunks = []
    current_offset = 0

    for index, chunk_path in enumerate(chunk_paths, start=1):
        log.info(f"Transcribing chunk: {chunk_path.name}")
        chunk_start = current_offset
        chunk_duration = cfg.get("chunk_duration", 120)

        try:
            chunk_duration = _get_audio_duration(chunk_path)
            result = _transcribe_file(chunk_path, client, cfg, chunk_duration)
            segments_data = _raw_segments_from_result(result)
            log.info("Chunk %s raw segment count: %s", chunk_path.name, len(segments_data))

            accepted_segments = 0
            rejected_segments = 0
            for segment in segments_data:
                try:
                    segment_dict = _segment_to_dict(segment)
                    if segment_dict is None:
                        rejected_segments += 1
                        continue

                    segment_dict['start'] += current_offset
                    segment_dict['end'] += current_offset
                    all_segments.append(segment_dict)
                    accepted_segments += 1
                except Exception as e:
                    log.info(f"Error processing segment: {e}")
                    rejected_segments += 1

            log.info(
                "Chunk %s normalized segments: accepted=%s rejected=%s cumulative=%s",
                chunk_path.name,
                accepted_segments,
                rejected_segments,
                len(all_segments),
            )

            chunk_text = result.text if hasattr(result, 'text') else ""
            if chunk_text and chunk_text.strip():
                all_text_parts.append(chunk_text.strip())
        except Exception as e:
            log.exception(f"Chunk failed: {chunk_path.name}")
            failed_chunks.append({
                'index': index,
                'name': chunk_path.name,
                'start': chunk_start,
                'end': chunk_start + chunk_duration if chunk_duration is not None else None,
                'error': _extract_error_details(e),
            })
        finally:
            current_offset += chunk_duration

            if progress_callback:
                progress_callback({
                    "text": "\n\n".join(all_text_parts).strip(),
                    "segments": list(all_segments),
                    "failed_chunks": list(failed_chunks),
                })

    return {
        "text": "\n\n".join(all_text_parts).strip(),
        "segments": all_segments,
        "failed_chunks": failed_chunks,
    }


def _transcribe_file_with_chunks(audio_path: Path, client: OpenAI, cfg: dict, progress_callback=None) -> dict:
    """Transcribe audio file, splitting into chunks if needed. Returns segments with timestamps."""
    chunk_duration = cfg.get("chunk_duration", 120)
    duration = _get_audio_duration(audio_path)

    log.info(f"Audio duration: {duration:.2f}s, chunk duration: {chunk_duration}s")

    if duration <= chunk_duration:
        result = _transcribe_file(audio_path, client, cfg, duration)
        segments_data = []
        raw_segments = _raw_segments_from_result(result)
        log.info("Single-file raw segment count for %s: %s", audio_path.name, len(raw_segments))
        accepted_segments = 0
        rejected_segments = 0
        for segment in raw_segments:
            try:
                segment_dict = _segment_to_dict(segment)
                if segment_dict is not None:
                    segments_data.append(segment_dict)
                    accepted_segments += 1
                else:
                    rejected_segments += 1
            except Exception as e:
                log.info(f"Error processing segment: {e}")
                rejected_segments += 1
        log.info(
            "Single-file normalized segments for %s: accepted=%s rejected=%s",
            audio_path.name,
            accepted_segments,
            rejected_segments,
        )
        text = result.text if hasattr(result, 'text') else ""
        final_result = {"text": text, "segments": segments_data, "failed_chunks": []}
        if progress_callback:
            progress_callback(final_result)
        return final_result

    chunk_paths = _split_audio_file(audio_path, chunk_duration)

    if not chunk_paths:
        log.error("Failed to split audio file")
        return {"text": "", "segments": [], "failed_chunks": []}

    try:
        return _transcribe_chunks(chunk_paths, client, cfg, progress_callback)
    finally:
        if not cfg.get("keep_audio", False):
            temp_dir = chunk_paths[0].parent
            shutil.rmtree(temp_dir, ignore_errors=True)



cfg = load_config()
parser = argparse.ArgumentParser(description="Transcribe audio file using Whisper API")
parser.add_argument("input_file", type=str, help="Path to the audio file to transcribe")
parser.add_argument("--api-base-url", type=str, help="Override Berget API base URL")
args = parser.parse_args()

if args.api_base_url:
    cfg["api_base_url"] = args.api_base_url

api_key = os.environ.get("BERGET_API_KEY", "")

if not api_key:
    print("Error: BERGET_API_KEY environment variable not set")
    print("Please set it with: export BERGET_API_KEY=your_key")
    exit(1)

try:
    client = OpenAI(api_key=api_key, base_url=cfg["api_base_url"],
                    timeout=60, max_retries=0)
    log.info(f"API client initialized successfully")
except Exception as e:
    print(f"Error initializing API client: {e}")
    exit(1)

input_path = Path(args.input_file)
if not input_path.exists():
    print(f"Error: File not found: {input_path}")
    exit(1)

log.info(f"Processing audio file: {input_path.name}")
slides_data = _load_slides_metadata(input_path)
output_txt_path = None
output_metadata_path = None


def _persist_progress(partial_result: dict) -> None:
    global output_txt_path, output_metadata_path
    output_txt_path, output_metadata_path = _write_transcription_outputs(input_path, partial_result, slides_data)


result = _transcribe_file_with_chunks(input_path, client, cfg, _persist_progress)

# Validate transcription result
if not result.get('text') or not result['text'].strip():
    log.error("No transcription received from API")
    print(f"Error: No transcription received from API")
    print(f"File: {input_path.name}")
    print(f"Audio duration: {_get_audio_duration(input_path):.2f}s")
    print(f"Possible causes:")
    print(f"  - API key not configured correctly")
    print(f"  - Audio file may be corrupted or empty")
    print(f"  - Network connectivity issues")
    print(f"  - API service temporarily unavailable")
    if result.get('failed_chunks'):
        print("Failed chunks:")
        for failed_chunk in result['failed_chunks']:
            print(f"  - Chunk {failed_chunk['index']} ({failed_chunk['name']}): {failed_chunk['error']}")
    exit(1)

log.info(f"Transcription successful, {len(result.get('text', ''))} characters received")
output_txt_path, output_metadata_path = _write_transcription_outputs(input_path, result, slides_data)

if result.get('failed_chunks'):
    print(f"Warning: {len(result['failed_chunks'])} chunk(s) failed during transcription")
    for failed_chunk in result['failed_chunks']:
        print(f"  - Chunk {failed_chunk['index']} ({failed_chunk['name']}): {failed_chunk['error']}")

print(f"Transcription saved to: {output_txt_path}")
print(f"Transcription metadata saved to: {output_metadata_path}")
