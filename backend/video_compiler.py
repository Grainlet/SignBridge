from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Optional

import config

_NORM_LOCK = threading.Lock()


class VideoCompilationError(RuntimeError):
    pass


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _normalize_source_clip(
    source_path: Path,
    gloss: str,
    normalized_path: Path,
) -> Path:
    with _NORM_LOCK:
        if normalized_path.exists() and normalized_path.stat().st_size > 1000:
            return normalized_path

        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = normalized_path.with_name(f"tmp_{normalized_path.name}")

        label = _escape_drawtext(gloss.upper())
        vf = (
            f"scale={config.INTERPRETER_WIDTH}:{config.INTERPRETER_HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={config.INTERPRETER_WIDTH}:{config.INTERPRETER_HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2:color=#0E0E12,"
            f"fps={config.INTERPRETER_FPS},"
            f"drawbox=x=0:y=ih-34:w=iw:h=34:color=#0A0A0C@0.72:t=fill,"
            f"drawtext=text='{label}':fontcolor=#F4F4F5:fontsize=15:"
            "x=12:y=h-24,"
            "format=yuv420p"
        )

        cmd = [
            config.FFMPEG_BINARY,
            "-y",
            "-i",
            str(source_path),
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(tmp_out),
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if proc.returncode != 0 or not tmp_out.exists():
            err = (proc.stderr or proc.stdout or "Failed to normalize clip").strip()
            raise VideoCompilationError(f"FFmpeg clip normalization failed for '{gloss}': {err[-300:]}")

        tmp_out.replace(normalized_path)
        return normalized_path


def _generate_slate_segment(
    output_path: Path,
    duration: float,
    title: str,
    subtitle: str = "",
) -> None:
    safe_dur = max(0.08, round(duration, 3))
    filters = [f"fps={config.INTERPRETER_FPS}", "format=yuv420p"]

    if title:
        esc_title = _escape_drawtext(title)
        filters.insert(
            0,
            f"drawtext=text='{esc_title}':fontcolor=#A1A1AA:fontsize=16:"
            "x=(w-text_w)/2:y=(h-text_h)/2-10",
        )
    if subtitle:
        esc_sub = _escape_drawtext(subtitle)
        filters.insert(
            1,
            f"drawtext=text='{esc_sub}':fontcolor=#71717A:fontsize=12:"
            "x=(w-text_w)/2:y=(h-text_h)/2+16",
        )

    cmd = [
        config.FFMPEG_BINARY,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=#0E0E12:s={config.INTERPRETER_WIDTH}x{config.INTERPRETER_HEIGHT}:r={config.INTERPRETER_FPS}:d={safe_dur}",
        "-vf",
        ",".join(filters),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0 or not output_path.exists():
        err = (proc.stderr or proc.stdout or "Slate generation failed").strip()
        raise VideoCompilationError(f"FFmpeg slate generation failed: {err[-300:]}")


def _adjust_clip_speed(
    normalized_clip: Path,
    output_path: Path,
    speed_factor: float,
) -> float:
    clamped = max(0.75, min(1.45, speed_factor))
    pts_mult = round(1.0 / clamped, 4)

    cmd = [
        config.FFMPEG_BINARY,
        "-y",
        "-i",
        str(normalized_clip),
        "-an",
        "-vf",
        f"setpts={pts_mult}*PTS,fps={config.INTERPRETER_FPS},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0 or not output_path.exists():
        raise VideoCompilationError("FFmpeg clip retiming failed.")

    probe = subprocess.run(
        [
            config.FFPROBE_BINARY,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return round(float(probe.stdout.strip()), 3)
    except ValueError:
        return 1.5


def compile_interpreter_track(
    matched_segments: list[dict[str, Any]],
    total_video_duration: float,
    work_dir: Path,
    output_video_path: Path,
    sync_json_path: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    output_video_path.parent.mkdir(parents=True, exist_ok=True)
    sync_json_path.parent.mkdir(parents=True, exist_ok=True)

    timeline_files: list[Path] = []
    sync_entries: list[dict[str, Any]] = []
    cursor = 0.0
    seg_counter = 0

    def add_standby(dur: float, title: str = "Listening", subtitle: str = "") -> None:
        nonlocal cursor, seg_counter
        if dur < 0.08:
            return
        seg_counter += 1
        slate_path = work_dir / f"seg_{seg_counter:04d}_slate.mp4"
        _generate_slate_segment(slate_path, dur, title=title, subtitle=subtitle)
        timeline_files.append(slate_path)
        cursor = round(cursor + dur, 3)

    total_segments = max(1, len(matched_segments))

    for idx, seg in enumerate(matched_segments):
        orig_start = float(seg.get("start", 0.0))
        orig_end = float(seg.get("end", orig_start + 1.0))
        next_start = (
            float(matched_segments[idx + 1]["start"])
            if idx + 1 < len(matched_segments)
            else max(total_video_duration, orig_end)
        )

        \
        if orig_start - cursor > 0.12:
            add_standby(orig_start - cursor, title="Listening", subtitle="Pause in speech")

        interp_start = cursor
        clips = seg.get("clips", [])
        asl_status = seg.get("asl_status", "unavailable")

        \
        available_window = max(0.8, next_start - interp_start)

        if not clips:
            \
            slate_dur = max(0.5, min(available_window, max(0.8, orig_end - interp_start)))
            seg_counter += 1
            unavail_path = work_dir / f"seg_{seg_counter:04d}_unavail.mp4"
            _generate_slate_segment(
                unavail_path,
                slate_dur,
                title="ASL Translation Unavailable",
                subtitle="No verified clip for this phrase",
            )
            timeline_files.append(unavail_path)
            cursor = round(cursor + slate_dur, 3)
            sync_entries.append(
                {
                    "id": seg.get("segment_id"),
                    "original_start": round(orig_start, 3),
                    "original_end": round(orig_end, 3),
                    "interpreter_start": round(interp_start, 3),
                    "interpreter_end": round(cursor, 3),
                    "phrase_id": None,
                    "glosses": [],
                    "matched_words": [],
                    "missing_words": seg.get("missing_words", []),
                    "asl_status": "unavailable",
                    "available": False,
                    "text": seg.get("source_text", ""),
                }
            )
        else:
            raw_total = sum(float(c.get("duration") or 1.8) for c in clips)
            \
            speed_factor = 1.0
            if raw_total > available_window and available_window > 0.5:
                speed_factor = min(1.4, raw_total / available_window)

            used_clip_ids: list[str] = []
            for clip in clips:
                slug = clip["gloss"].replace(" ", "_")
                norm_path = config.WLASL_NORMALIZED_DIR / f"{slug}.mp4"
                _normalize_source_clip(Path(clip["video_path"]), clip["gloss"], norm_path)

                if abs(speed_factor - 1.0) > 0.06:
                    seg_counter += 1
                    retimed_path = work_dir / f"seg_{seg_counter:04d}_{slug}.mp4"
                    actual_dur = _adjust_clip_speed(norm_path, retimed_path, speed_factor)
                    timeline_files.append(retimed_path)
                    cursor = round(cursor + actual_dur, 3)
                else:
                    timeline_files.append(norm_path)
                    cursor = round(cursor + float(clip.get("duration") or 1.8), 3)

                used_clip_ids.append(clip["id"])

            sync_entries.append(
                {
                    "id": seg.get("segment_id"),
                    "original_start": round(orig_start, 3),
                    "original_end": round(orig_end, 3),
                    "interpreter_start": round(interp_start, 3),
                    "interpreter_end": round(cursor, 3),
                    "phrase_id": "+".join(used_clip_ids),
                    "glosses": seg.get("glosses", []),
                    "matched_words": seg.get("matched_words", []),
                    "missing_words": seg.get("missing_words", []),
                    "asl_status": asl_status,
                    "available": True,
                    "text": seg.get("source_text", ""),
                }
            )

        if progress_callback:
            pct = min(85, int(((idx + 1) / total_segments) * 80))
            progress_callback(pct, f"Prepared ASL segment {idx + 1}/{total_segments}")

    if total_video_duration - cursor > 0.15:
        add_standby(total_video_duration - cursor, title="Listening", subtitle="")

    if not timeline_files:
        add_standby(max(1.0, total_video_duration), title="No Speech Detected", subtitle="")

    if progress_callback:
        progress_callback(90, "Concatenating ASL interpreter video with FFmpeg")

    concat_list_path = work_dir / "concat_list.txt"
    concat_lines = [f"file '{p.resolve().as_posix()}'" for p in timeline_files]
    concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    tmp_output = output_video_path.with_name(f"tmp_{output_video_path.name}")
    cmd = [
        config.FFMPEG_BINARY,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        "-f",
        "mp4",
        str(tmp_output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0 or not tmp_output.exists():
        err = (proc.stderr or proc.stdout or "Concatenation failed").strip()
        raise VideoCompilationError(f"FFmpeg interpreter compilation failed: {err[-300:]}")

    tmp_output.replace(output_video_path)

    sync_payload = {
        "asl_compiled": True,
        "dataset": "WLASL (Voxel51/WLASL)",
        "interpreter_duration": round(cursor, 3),
        "original_duration": round(total_video_duration, 3),
        "segments": sync_entries,
    }
    sync_json_path.write_text(json.dumps(sync_payload, indent=2), encoding="utf-8")

    if progress_callback:
        progress_callback(100, "Interpreter video ready")

    return sync_payload
