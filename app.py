from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge

import config
from backend.audio_extraction import check_ffmpeg_available
from backend.job_manager import (
    PIPELINE_STAGES,
    create_upload_job,
    create_youtube_job,
    delete_job_files,
    generate_job_id,
    get_job,
    list_recent_jobs,
)
from backend.sign_matcher import load_sign_library
from backend.sign_translation import load_available_glosses
from backend.transcription import is_vosk_model_ready
from backend.video_input import VideoInputError, save_uploaded_video, validate_youtube_url


def create_app() -> Flask:
    config.ensure_directories()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(_err: RequestEntityTooLarge):
        max_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        return (
            jsonify(
                {
                    "error": f"Uploaded file exceeds the {max_mb} MB size limit."
                }
            ),
            413,
        )

\
\
\

    @app.get("/")
    def home_page():
        return render_template("index.html")

    @app.get("/processing/<job_id>")
    def processing_page(job_id: str):
        return render_template("processing.html", job_id=job_id)

    @app.get("/player/<job_id>")
    def player_page(job_id: str):
        return render_template("player.html", job_id=job_id)

\
\
\

    @app.get("/api/health")
    def health():
        ffmpeg_ok, ffprobe_ok = check_ffmpeg_available()
        vosk_ok = is_vosk_model_ready()
        glosses = load_available_glosses()
        library = load_sign_library()
        return jsonify(
            {
                "status": "ok",
                "ffmpeg": ffmpeg_ok,
                "ffprobe": ffprobe_ok,
                "vosk_model": vosk_ok,
                "vosk_model_path": str(config.VOSK_MODEL_PATH),
                "wlasl_gloss_count": len(glosses),
                "starter_signs_count": len(library.get("signs", [])),
                "allowed_extensions": sorted(config.ALLOWED_VIDEO_EXTENSIONS),
                "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
            }
        )

    @app.get("/api/library")
    def sign_library_info():
        library = load_sign_library()
        glosses = load_available_glosses()
        return jsonify(
            {
                "dataset": library.get("dataset", "WLASL (Voxel51/WLASL)"),
                "starter_signs_count": len(library.get("signs", [])),
                "total_indexed_glosses": len(glosses),
                "signs": library.get("signs", []),
            }
        )

    @app.get("/api/jobs")
    def jobs_list():
        jobs = list_recent_jobs(limit=12)
        sanitized = [
            {
                "job_id": j["job_id"],
                "title": j.get("title"),
                "source_type": j.get("source_type"),
                "status": j.get("status"),
                "stage": j.get("stage"),
                "progress": j.get("progress", 0),
                "word_count": j.get("word_count"),
                "segment_count": j.get("segment_count"),
                "created_at": j.get("created_at"),
            }
            for j in jobs
        ]
        return jsonify({"jobs": sanitized})

    @app.post("/api/upload")
    def upload_video():
        if "video" not in request.files:
            return jsonify({"error": "Missing 'video' file field in upload request."}), 400

        file_storage = request.files["video"]
        job_id = generate_job_id()

        try:
            saved_path = save_uploaded_video(file_storage, job_id)
        except VideoInputError as exc:
            return jsonify({"error": str(exc)}), 400

        job = create_upload_job(
            job_id=job_id,
            video_path=saved_path,
            original_filename=file_storage.filename or saved_path.name,
        )
        return (
            jsonify(
                {
                    "job_id": job["job_id"],
                    "status": job["status"],
                    "stage": job["stage"],
                    "redirect_url": f"/processing/{job['job_id']}",
                }
            ),
            202,
        )

    @app.post("/api/youtube")
    def submit_youtube():
        payload = request.get_json(silent=True) or {}
        youtube_url = str(payload.get("url") or "").strip()

        try:
            validated_url = validate_youtube_url(youtube_url)
        except VideoInputError as exc:
            return jsonify({"error": str(exc)}), 400

        job = create_youtube_job(validated_url)
        return (
            jsonify(
                {
                    "job_id": job["job_id"],
                    "status": job["status"],
                    "stage": job["stage"],
                    "redirect_url": f"/processing/{job['job_id']}",
                }
            ),
            202,
        )

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Processing job not found."}), 404

        return jsonify(
            {
                "job_id": job["job_id"],
                "title": job.get("title"),
                "source_type": job.get("source_type"),
                "source_url": job.get("source_url"),
                "original_filename": job.get("original_filename"),
                "status": job["status"],
                "stage": job["stage"],
                "stage_label": job.get("stage_label"),
                "progress": job.get("progress", 0),
                "stage_progress": job.get("stage_progress", 0),
                "transcript_preview": job.get("transcript_preview", ""),
                "media_info": job.get("media_info"),
                "segment_count": job.get("segment_count"),
                "word_count": job.get("word_count"),
                "error": job.get("error"),
                "stages": PIPELINE_STAGES,
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
            }
        )

    @app.delete("/api/jobs/<job_id>")
    def delete_job(job_id: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Processing job not found."}), 404
        delete_job_files(job_id)
        return jsonify({"deleted": True, "job_id": job_id})

    @app.get("/api/transcript/<job_id>")
    def get_transcript(job_id: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Processing job not found."}), 404

        transcript_path = Path(job["transcript_path"])
        if not transcript_path.exists():
            if job["status"] == "failed":
                return jsonify({"error": job.get("error") or "Job failed."}), 400
            return jsonify({"error": "Transcript is not ready yet."}), 409

        data = json.loads(transcript_path.read_text(encoding="utf-8"))
        return jsonify({"job_id": job_id, "title": job.get("title"), **data})

    @app.get("/api/player/<job_id>")
    def get_player_info(job_id: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Processing job not found."}), 404

        video_ready = bool(job.get("video_path")) and Path(job["video_path"]).exists()
        interpreter_ready = (
            bool(job.get("interpreter_path")) and Path(job["interpreter_path"]).exists()
        )
        return jsonify(
            {
                "job_id": job_id,
                "title": job.get("title"),
                "status": job.get("status"),
                "source_type": job.get("source_type"),
                "media_info": job.get("media_info"),
                "original_video_url": f"/api/video/{job_id}/original" if video_ready else None,
                "interpreter_video_url": (
                    f"/api/video/{job_id}/interpreter" if interpreter_ready else None
                ),
                "interpreter_available": interpreter_ready,
                "asl_pipeline_status": job.get("asl_pipeline_status", "pending_phase_3"),
                "transcript_url": f"/api/transcript/{job_id}",
                "sync_url": f"/api/sync/{job_id}",
            }
        )

    @app.get("/api/sync/<job_id>")
    def get_sync_metadata(job_id: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Processing job not found."}), 404

        sync_path = Path(job["sync_path"])
        if not sync_path.exists():
            return jsonify({"error": "Synchronization metadata is not ready yet."}), 409

        data = json.loads(sync_path.read_text(encoding="utf-8"))
        return jsonify(data)

    @app.get("/api/video/<job_id>/<video_type>")
    def serve_video(job_id: str, video_type: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "Processing job not found."}), 404

        if video_type == "original":
            raw_path = job.get("video_path")
        elif video_type == "interpreter":
            raw_path = job.get("interpreter_path")
        else:
            return jsonify({"error": "Unsupported video type."}), 400

        if not raw_path:
            return jsonify({"error": f"{video_type.capitalize()} video is not available."}), 404

        video_path = Path(raw_path)
        if not video_path.exists():
            return jsonify({"error": "Video file no longer exists on disk."}), 404

        return send_file(str(video_path), conditional=True)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
