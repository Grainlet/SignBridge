from __future__ import annotations

import json
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

import config

_MATCHER_LOCK = threading.Lock()
_INDEX_CACHE: Optional[dict[str, list[dict[str, Any]]]] = None
_METADATA_BY_GLOSS: Optional[dict[str, dict[str, Any]]] = None


class SignMatcherError(RuntimeError):
    pass


def load_sign_library(metadata_path: Optional[Path] = None) -> dict[str, Any]:
    target = Path(metadata_path or config.SIGN_METADATA_PATH)
    if not target.exists():
        return {"version": "1.0", "signs": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _get_wlasl_index() -> dict[str, list[dict[str, Any]]]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        if config.WLASL_INDEX_PATH.exists():
            _INDEX_CACHE = json.loads(
                config.WLASL_INDEX_PATH.read_text(encoding="utf-8")
            )
        else:
            _INDEX_CACHE = {}
    return _INDEX_CACHE


def _get_metadata_map() -> dict[str, dict[str, Any]]:
    global _METADATA_BY_GLOSS
    if _METADATA_BY_GLOSS is None:
        meta = load_sign_library()
        mapping: dict[str, dict[str, Any]] = {}
        for item in meta.get("signs", []):
            key = str(item.get("english_phrase") or "").strip().lower()
            if key:
                mapping[key] = item
        _METADATA_BY_GLOSS = mapping
    return _METADATA_BY_GLOSS


def _probe_video_duration(video_path: Path) -> Optional[float]:
    try:
        proc = subprocess.run(
            [
                config.FFPROBE_BINARY,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return None
        info = json.loads(proc.stdout or "{}")
        streams = info.get("streams", [])
        vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not vstream:
            return None
        dur = float(info.get("format", {}).get("duration") or vstream.get("duration") or 0)
        return round(dur, 3) if dur > 0 else None
    except Exception:
        return None


def resolve_gloss_clip(gloss: str) -> Optional[dict[str, Any]]:
    clean_gloss = (gloss or "").strip().lower()
    if not clean_gloss:
        return None

    with _MATCHER_LOCK:
        \
        meta_map = _get_metadata_map()
        if clean_gloss in meta_map:
            entry = meta_map[clean_gloss]
            local_path = config.SIGN_LIBRARY_DIR / entry["video_path"]
            if local_path.exists() and local_path.stat().st_size > 0:
                return {
                    "id": entry["id"],
                    "gloss": clean_gloss,
                    "video_path": str(local_path),
                    "duration": float(entry.get("duration") or 1.8),
                    "dataset": entry.get("dataset", "WLASL"),
                    "verified": True,
                }

        slug = clean_gloss.replace(" ", "_")
        config.WLASL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_path = config.WLASL_CACHE_DIR / f"{slug}.mp4"
        if cached_path.exists() and cached_path.stat().st_size > 0:
            dur = _probe_video_duration(cached_path)
            if dur:
                return {
                    "id": f"wlasl_cache_{slug}",
                    "gloss": clean_gloss,
                    "video_path": str(cached_path),
                    "duration": dur,
                    "dataset": "WLASL (Voxel51/WLASL)",
                    "verified": True,
                }
            cached_path.unlink(missing_ok=True)

        index = _get_wlasl_index()
        candidates = index.get(clean_gloss, [])
        for cand in candidates:
            url = config.WLASL_HF_BASE + cand["filepath"]
            tmp_path = cached_path.with_suffix(".mp4.tmp")
            try:
                urllib.request.urlretrieve(url, str(tmp_path))
                if tmp_path.exists() and tmp_path.stat().st_size > 1000:
                    dur = _probe_video_duration(tmp_path)
                    if dur:
                        tmp_path.replace(cached_path)
                        return {
                            "id": f"wlasl_cache_{slug}",
                            "gloss": clean_gloss,
                            "video_path": str(cached_path),
                            "duration": dur,
                            "dataset": "WLASL (Voxel51/WLASL)",
                            "verified": True,
                        }
            except Exception:
                pass
            finally:
                tmp_path.unlink(missing_ok=True)

    return None


def match_translated_segments(
    translations: list[dict[str, Any]],
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> list[dict[str, Any]]:
    matched_segments: list[dict[str, Any]] = []
    total = max(1, len(translations))

    for idx, item in enumerate(translations):
        clips: list[dict[str, Any]] = []
        unresolved_glosses: list[str] = []

        for gloss in item.get("glosses", []):
            clip = resolve_gloss_clip(gloss)
            if clip:
                clips.append(clip)
            else:
                unresolved_glosses.append(gloss)

        missing_words = list(item.get("missing_words", [])) + unresolved_glosses
        if not clips:
            asl_status = "unavailable"
        elif missing_words:
            asl_status = "partial"
        else:
            asl_status = "matched"

        matched_segments.append(
            {
                **item,
                "clips": clips,
                "missing_words": missing_words,
                "asl_status": asl_status,
                "asl_available": len(clips) > 0,
            }
        )

        if progress_callback:
            pct = int(((idx + 1) / total) * 100)
            progress_callback(pct, f"Matched signs for segment {idx + 1}/{total}")

    return matched_segments
