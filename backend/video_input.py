from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import yt_dlp
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

import config


class VideoInputError(RuntimeError):
    pass


_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def is_allowed_video_filename(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in config.ALLOWED_VIDEO_EXTENSIONS


def validate_youtube_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        raise VideoInputError("Please enter a YouTube video URL.")

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise VideoInputError("YouTube URL must start with http:// or https://.")

    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise VideoInputError(
            "Unsupported URL host. Please provide a valid youtube.com or youtu.be link."
        )

    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
        if not _YOUTUBE_VIDEO_ID_RE.match(video_id):
            raise VideoInputError("Invalid youtu.be short link.")
        return cleaned

    path = parsed.path or ""
    if path.startswith("/watch"):
        \
        query_parts = dict(
            part.split("=", 1) for part in parsed.query.split("&") if "=" in part
        )
        vid = query_parts.get("v", "")
        if not _YOUTUBE_VIDEO_ID_RE.match(vid):
            raise VideoInputError("YouTube watch URL is missing a valid 11-character video ID.")
        return cleaned

    if path.startswith("/shorts/") or path.startswith("/embed/") or path.startswith("/live/"):
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and _YOUTUBE_VIDEO_ID_RE.match(parts[1]):
            return cleaned

    raise VideoInputError(
        "Unsupported YouTube URL format. Use a standard watch, shorts, or youtu.be video link."
    )


def save_uploaded_video(file_storage: FileStorage, job_id: str) -> Path:
    if file_storage is None or not file_storage.filename:
        raise VideoInputError("No video file was provided.")

    safe_name = secure_filename(file_storage.filename)
    if not safe_name:
        raise VideoInputError("Invalid video filename.")

    if not is_allowed_video_filename(safe_name):
        allowed = ", ".join(sorted(config.ALLOWED_VIDEO_EXTENSIONS))
        raise VideoInputError(
            f"Unsupported file format '{Path(safe_name).suffix or 'unknown'}'. Supported formats: {allowed}."
        )

    job_upload_dir = config.UPLOAD_FOLDER / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)
    destination = job_upload_dir / safe_name

    file_storage.save(str(destination))

    if not destination.exists() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise VideoInputError("Uploaded file is empty.")

    return destination


def _classify_yt_dlp_error(message: str) -> str:
    lower = message.lower()
    if "private video" in lower:
        return "This YouTube video is private and cannot be accessed."
    if "sign in to confirm your age" in lower or "age-restricted" in lower:
        return "This YouTube video is age-restricted and requires authentication."
    if "drm" in lower or "protected" in lower:
        return "This video is DRM-protected and cannot be downloaded."
    if "video unavailable" in lower or "not available" in lower:
        return "This YouTube video is unavailable or has been removed."
    if "geo" in lower or "country" in lower:
        return "This YouTube video is restricted in this region."
    if "live event will begin" in lower or "is_live" in lower:
        return "Upcoming or active livestreams are not supported."
    return f"YouTube download failed: {message}"


def download_youtube_video(
    url: str,
    job_id: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> tuple[Path, str]:
    validated_url = validate_youtube_url(url)
    job_upload_dir = config.UPLOAD_FOLDER / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(job_upload_dir / "source.%(ext)s")

    def _progress_hook(data: dict) -> None:
        if not progress_callback:
            return
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            downloaded = data.get("downloaded_bytes") or 0
            if total > 0:
                pct = min(99, int((downloaded / total) * 100))
                progress_callback(pct, f"Downloading video ({pct}%)")
        elif status == "finished":
            progress_callback(100, "Download complete, preparing audio extraction")

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_progress_hook],
        "socket_timeout": 30,
        "retries": 2,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(validated_url, download=True)
            if not info:
                raise VideoInputError("Could not retrieve metadata for the provided YouTube URL.")
            if info.get("is_live"):
                raise VideoInputError("Live streams are not supported. Provide a completed video.")
            title = str(info.get("title") or "YouTube Video")
    except yt_dlp.utils.DownloadError as exc:
        raise VideoInputError(_classify_yt_dlp_error(str(exc))) from exc
    except VideoInputError:
        raise
    except Exception as exc:
        raise VideoInputError(f"Failed to fetch YouTube video: {exc}") from exc

    candidates = [
        p for p in job_upload_dir.iterdir()
        if p.is_file() and not p.name.endswith((".part", ".ytdl", ".temp"))
    ]
    if not candidates:
        raise VideoInputError("Video download completed, but no playable output file was created.")

    mp4_candidates = [p for p in candidates if p.suffix.lower() == ".mp4"]
    chosen = mp4_candidates[0] if mp4_candidates else max(candidates, key=lambda p: p.stat().st_size)

    if chosen.stat().st_size == 0:
        raise VideoInputError("Downloaded video file is empty.")

    return chosen, title
