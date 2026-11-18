from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import config


class AudioExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration_seconds: float
    width: Optional[int]
    height: Optional[int]
    has_audio: bool
    has_video: bool
    format_name: str


def check_ffmpeg_available() -> tuple[bool, bool]:
    ffmpeg_ok = shutil.which(config.FFMPEG_BINARY) is not None
    ffprobe_ok = shutil.which(config.FFPROBE_BINARY) is not None
    return ffmpeg_ok, ffprobe_ok


def probe_media(video_path: Path) -> MediaInfo:
    if not video_path.exists():
        raise AudioExtractionError(f"Input video file does not exist: {video_path}")

    cmd = [
        config.FFPROBE_BINARY,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AudioExtractionError(
            "FFprobe was not found on PATH. Install FFmpeg and ensure ffprobe is accessible."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractionError("Media inspection timed out while probing the video file.") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Unknown ffprobe error").strip()
        raise AudioExtractionError(f"Invalid or unreadable media file: {err}")

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AudioExtractionError("Could not parse media metadata returned by ffprobe.") from exc

    streams = payload.get("streams", [])
    fmt = payload.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration_raw = fmt.get("duration") or (video_stream or {}).get("duration") or (audio_stream or {}).get("duration") or 0
    try:
        duration_seconds = round(float(duration_raw), 3)
    except (TypeError, ValueError):
        duration_seconds = 0.0

    width = int(video_stream["width"]) if video_stream and video_stream.get("width") else None
    height = int(video_stream["height"]) if video_stream and video_stream.get("height") else None

    return MediaInfo(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        has_audio=audio_stream is not None,
        has_video=video_stream is not None,
        format_name=str(fmt.get("format_name") or "unknown"),
    )


def extract_audio_to_wav(video_path: Path, output_wav_path: Path) -> MediaInfo:
    info = probe_media(video_path)
    if not info.has_video and not info.has_audio:
        raise AudioExtractionError("Uploaded file contains neither video nor audio streams.")
    if not info.has_audio:
        raise AudioExtractionError(
            "This video does not contain an audio track to transcribe."
        )

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        config.FFMPEG_BINARY,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        str(config.VOSK_AUDIO_CHANNELS),
        "-ar",
        str(config.VOSK_SAMPLE_RATE),
        "-sample_fmt",
        "s16",
        "-f",
        "wav",
        str(output_wav_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AudioExtractionError(
            "FFmpeg was not found on PATH. Please install FFmpeg before processing videos."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractionError("Audio extraction timed out.") from exc

    if proc.returncode != 0 or not output_wav_path.exists() or output_wav_path.stat().st_size == 0:
        err = (proc.stderr or proc.stdout or "FFmpeg failed to extract audio").strip()
        tail = err.splitlines()[-1] if err else "Unknown FFmpeg error"
        raise AudioExtractionError(f"FFmpeg audio extraction failed: {tail}")

    return info
