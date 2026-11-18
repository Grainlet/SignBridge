from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import config
from backend.audio_extraction import AudioExtractionError, extract_audio_to_wav
from backend.sign_matcher import SignMatcherError, match_translated_segments
from backend.sign_translation import translate_sentences
from backend.transcription import TranscriptionError, transcribe_wav
from backend.video_compiler import VideoCompilationError, compile_interpreter_track
from backend.video_input import VideoInputError, download_youtube_video

_JOBS_LOCK = threading.Lock()

PIPELINE_STAGES = [
    {"id": "ingesting", "label": "Uploading / fetching video"},
    {"id": "extracting_audio", "label": "Extracting audio (16 kHz mono WAV)"},
    {"id": "transcribing", "label": "Transcribing speech offline (Vosk)"},
    {"id": "translating", "label": "Translating transcript into ASL"},
    {"id": "matching", "label": "Matching prerecorded sign-language recordings"},
    {"id": "compiling", "label": "Compiling synchronized interpreter video"},
    {"id": "completed", "label": "Preparing synchronized playback"},
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_file(job_id: str) -> Path:
    return config.PROCESSING_FOLDER / job_id / "job.json"


def _write_job(job: dict[str, Any]) -> None:
    job_path = _job_file(job["job_id"])
    job_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = job_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    tmp_path.replace(job_path)


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    if not re_valid_job_id(job_id):
        return None
    path = _job_file(job_id)
    if not path.exists():
        return None
    with _JOBS_LOCK:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def re_valid_job_id(job_id: str) -> bool:
    return bool(job_id) and all(c in "0123456789abcdef-" for c in job_id.lower()) and len(job_id) <= 64


def list_recent_jobs(limit: int = 12) -> list[dict[str, Any]]:
    if not config.PROCESSING_FOLDER.exists():
        return []
    jobs: list[dict[str, Any]] = []
    for entry in config.PROCESSING_FOLDER.iterdir():
        if not entry.is_dir():
            continue
        job_json = entry / "job.json"
        if not job_json.exists():
            continue
        try:
            data = json.loads(job_json.read_text(encoding="utf-8"))
            jobs.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return jobs[:limit]


def update_job(job_id: str, **updates: Any) -> Optional[dict[str, Any]]:
    with _JOBS_LOCK:
        path = _job_file(job_id)
        if not path.exists():
            return None
        job = json.loads(path.read_text(encoding="utf-8"))
        job.update(updates)
        job["updated_at"] = _utc_now_iso()
        _write_job(job)
        return job


def generate_job_id() -> str:
    return uuid.uuid4().hex[:12]


def create_upload_job(job_id: str, video_path: Path, original_filename: str) -> dict[str, Any]:
    job = {
        "job_id": job_id,
        "source_type": "upload",
        "source_url": None,
        "title": Path(original_filename).stem or "Uploaded Video",
        "original_filename": original_filename,
        "video_path": str(video_path),
        "audio_path": None,
        "transcript_path": str(config.OUTPUT_FOLDER / job_id / "transcript.json"),
        "interpreter_path": str(config.OUTPUT_FOLDER / job_id / "interpreter.mp4"),
        "sync_path": str(config.OUTPUT_FOLDER / job_id / "sync.json"),
        "status": "queued",
        "stage": "ingesting",
        "stage_label": "Video uploaded, queued for audio extraction",
        "progress": 10,
        "stage_progress": 100,
        "transcript_preview": "",
        "media_info": None,
        "error": None,
        "milestone": "phase_1_5_complete",
        "asl_pipeline_status": "queued",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }
    with _JOBS_LOCK:
        _write_job(job)

    worker = threading.Thread(
        target=_run_pipeline,
        args=(job_id,),
        daemon=True,
        name=f"signbridge-job-{job_id}",
    )
    worker.start()
    return job


def create_youtube_job(youtube_url: str) -> dict[str, Any]:
    job_id = generate_job_id()
    job = {
        "job_id": job_id,
        "source_type": "youtube",
        "source_url": youtube_url,
        "title": "YouTube Video",
        "original_filename": None,
        "video_path": None,
        "audio_path": None,
        "transcript_path": str(config.OUTPUT_FOLDER / job_id / "transcript.json"),
        "interpreter_path": str(config.OUTPUT_FOLDER / job_id / "interpreter.mp4"),
        "sync_path": str(config.OUTPUT_FOLDER / job_id / "sync.json"),
        "status": "processing",
        "stage": "ingesting",
        "stage_label": "Fetching video via yt-dlp",
        "progress": 5,
        "stage_progress": 0,
        "transcript_preview": "",
        "media_info": None,
        "error": None,
        "milestone": "phase_1_5_complete",
        "asl_pipeline_status": "queued",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }
    with _JOBS_LOCK:
        _write_job(job)

    worker = threading.Thread(
        target=_run_pipeline,
        args=(job_id,),
        daemon=True,
        name=f"signbridge-yt-{job_id}",
    )
    worker.start()
    return job


def _cleanup_temp_files(wav_path: Path, compile_work_dir: Path) -> None:
    try:
        if wav_path.exists():
            wav_path.unlink()
    except OSError:
        pass
    try:
        if compile_work_dir.exists():
            shutil.rmtree(compile_work_dir, ignore_errors=True)
    except OSError:
        pass


def _enrich_transcript_with_asl(
    transcript: dict[str, Any],
    matched_segments: list[dict[str, Any]],
    transcript_path: Path,
) -> None:
    by_id = {seg.get("segment_id"): seg for seg in matched_segments}
    for sentence in transcript.get("sentences", []):
        matched = by_id.get(sentence.get("id"))
        if matched:
            sentence["asl_status"] = matched.get("asl_status", "unavailable")
            sentence["glosses"] = matched.get("glosses", [])
            sentence["asl_gloss_text"] = matched.get("asl_gloss_text", "")
            sentence["missing_words"] = matched.get("missing_words", [])
            sentence["matched_words"] = matched.get("matched_words", [])
    transcript_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")


def _run_pipeline(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return

    wav_path = config.PROCESSING_FOLDER / job_id / "audio_16k_mono.wav"
    compile_work_dir = config.PROCESSING_FOLDER / job_id / "compile_tmp"
    transcript_path = Path(job["transcript_path"])
    interpreter_path = Path(job["interpreter_path"])
    sync_path = Path(job["sync_path"])

    try:
        \
        if job["source_type"] == "youtube":
            update_job(
                job_id,
                status="processing",
                stage="ingesting",
                stage_label="Fetching YouTube video",
                progress=6,
            )

            def on_download_progress(pct: int, label: str) -> None:
                overall = 5 + int((pct / 100.0) * 15)
                update_job(
                    job_id,
                    stage="ingesting",
                    stage_label=label,
                    stage_progress=pct,
                    progress=overall,
                )

            video_path, title = download_youtube_video(
                job["source_url"],
                job_id,
                progress_callback=on_download_progress,
            )
            update_job(
                job_id,
                video_path=str(video_path),
                original_filename=video_path.name,
                title=title,
                progress=20,
                stage_progress=100,
            )
        else:
            video_path = Path(job["video_path"])

        update_job(
            job_id,
            status="processing",
            stage="extracting_audio",
            stage_label="Extracting 16 kHz mono WAV audio with FFmpeg",
            progress=24,
            stage_progress=10,
        )
        media_info = extract_audio_to_wav(video_path, wav_path)
        update_job(
            job_id,
            audio_path=str(wav_path),
            media_info={
                "duration_seconds": media_info.duration_seconds,
                "width": media_info.width,
                "height": media_info.height,
                "has_audio": media_info.has_audio,
                "has_video": media_info.has_video,
                "format_name": media_info.format_name,
            },
            progress=34,
            stage_progress=100,
        )

        \
        update_job(
            job_id,
            stage="transcribing",
            stage_label="Transcribing audio offline with Vosk",
            progress=36,
            stage_progress=0,
        )

        def on_transcribe_progress(pct: int, preview: str) -> None:
            overall = 36 + int((pct / 100.0) * 24)
            update_job(
                job_id,
                stage="transcribing",
                stage_label=f"Transcribing speech ({pct}%)",
                stage_progress=pct,
                progress=overall,
                transcript_preview=preview[-600:] if preview else "",
            )

        transcript = transcribe_wav(
            wav_path=wav_path,
            output_json_path=transcript_path,
            progress_callback=on_transcribe_progress,
        )

        \
        update_job(
            job_id,
            stage="translating",
            stage_label="Translating transcript into ASL glosses",
            progress=62,
            stage_progress=0,
            asl_pipeline_status="translating",
        )
        translations = translate_sentences(transcript.get("sentences", []))

        \
        update_job(
            job_id,
            stage="matching",
            stage_label="Matching prerecorded ASL sign recordings (WLASL)",
            progress=68,
            stage_progress=0,
            asl_pipeline_status="matching",
        )

        def on_match_progress(pct: int, label: str) -> None:
            overall = 68 + int((pct / 100.0) * 12)
            update_job(
                job_id,
                stage="matching",
                stage_label=label,
                stage_progress=pct,
                progress=overall,
            )

        matched_segments = match_translated_segments(
            translations,
            progress_callback=on_match_progress,
        )
        _enrich_transcript_with_asl(transcript, matched_segments, transcript_path)

        \
        update_job(
            job_id,
            stage="compiling",
            stage_label="Compiling synchronized ASL interpreter video",
            progress=82,
            stage_progress=0,
            asl_pipeline_status="compiling",
        )

        def on_compile_progress(pct: int, label: str) -> None:
            overall = 82 + int((pct / 100.0) * 16)
            update_job(
                job_id,
                stage="compiling",
                stage_label=label,
                stage_progress=pct,
                progress=overall,
            )

        total_dur = float(
            media_info.duration_seconds
            or transcript.get("duration_seconds")
            or 1.0
        )
        compile_interpreter_track(
            matched_segments=matched_segments,
            total_video_duration=total_dur,
            work_dir=compile_work_dir,
            output_video_path=interpreter_path,
            sync_json_path=sync_path,
            progress_callback=on_compile_progress,
        )

        _cleanup_temp_files(wav_path, compile_work_dir)

        final_preview = transcript.get("text", "")
        update_job(
            job_id,
            status="completed",
            stage="completed",
            stage_label="Synchronized video & ASL interpreter ready",
            progress=100,
            stage_progress=100,
            audio_path=None,
            asl_pipeline_status="compiled",
            transcript_preview=final_preview[:600],
            segment_count=len(transcript.get("sentences", [])),
            word_count=len(transcript.get("segments", [])),
        )
    except (
        VideoInputError,
        AudioExtractionError,
        TranscriptionError,
        SignMatcherError,
        VideoCompilationError,
    ) as exc:
        _cleanup_temp_files(wav_path, compile_work_dir)
        update_job(
            job_id,
            status="failed",
            stage="failed",
            stage_label="Processing failed",
            asl_pipeline_status="failed",
            error=str(exc),
        )
    except Exception as exc:
        _cleanup_temp_files(wav_path, compile_work_dir)
        update_job(
            job_id,
            status="failed",
            stage="failed",
            stage_label="Unexpected processing error",
            asl_pipeline_status="failed",
            error=f"Unexpected error: {exc}",
        )


def delete_job_files(job_id: str) -> bool:
    if not re_valid_job_id(job_id):
        return False
    for root in (config.UPLOAD_FOLDER, config.PROCESSING_FOLDER, config.OUTPUT_FOLDER):
        target = root / job_id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    return True
