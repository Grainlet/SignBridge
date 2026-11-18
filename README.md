# SignBridge — Video Accessibility & Offline Transcription

**Every Video. Every Sign. Everyone Included.**

SignBridge is a lightweight, local-first web application that makes uploaded videos and supported YouTube links accessible by extracting speech audio with FFmpeg, transcribing it offline with Vosk, translating transcripts into ASL glosses, compiling prerecorded human ASL video clips from the **WLASL (Word-Level American Sign Language)** dataset via FFmpeg, and playing both videos in master-clock synchronization.

---

## Project Structure

```text
SignBridge/
├── app.py                          # Flask web server & REST API endpoints
├── config.py                       # Paths, FFmpeg/Vosk/WLASL settings, upload limits
├── requirements.txt                # Python 3.11 dependencies
├── launch.bat                      # One-click Windows launcher
├── README.md
│
├── backend/
│   ├── __init__.py
│   ├── video_input.py              # File upload validation & yt-dlp YouTube fetching
│   ├── audio_extraction.py         # FFprobe inspection & FFmpeg 16 kHz mono WAV extraction
│   ├── transcription.py            # Cached offline Vosk speech recognition + word timestamps
│   ├── sign_translation.py         # Rule-based English -> ASL phrase & grammar translator
│   ├── sign_matcher.py             # WLASL sign clip matcher & local dataset cache
│   ├── video_compiler.py           # FFmpeg interpreter video compiler & sync.json generator
│   └── job_manager.py              # Background worker thread & persistent JSON job store
│
├── scripts/
│   └── bootstrap_sign_library.py   # Downloads starter verified human ASL clips from WLASL
│
├── models/
│   └── vosk-model-small-en-us/     # Local offline Vosk English model
│
├── sign_library/
│   ├── metadata.json               # Verified prerecorded starter human ASL clips
│   ├── wlasl_index.json            # 2,000-gloss WLASL index (Voxel51/WLASL)
│   ├── greetings/
│   ├── questions/
│   ├── daily_life/
│   ├── conversations/
│   ├── dataset_cache/              # On-demand cached WLASL clips
│   └── normalized/                 # Normalized 480x360@25fps ASL segments
│
├── templates/
│   ├── index.html                  # Home: upload dropzone, YouTube URL form, recent jobs
│   ├── processing.html             # Live 7-stage backend pipeline tracker
│   └── player.html                 # Dual-video synchronized player & transcript panel
│
├── static/
│   ├── css/style.css               # Minimal dark studio stylesheet
│   ├── js/
│   │   ├── main.js                 # Upload XHR progress, URL validation, recent jobs
│   │   ├── processing.js           # Real backend job polling
│   │   ├── player.js               # Master-clock dual-video sync, draggable/resizable PIP
│   │   └── transcript.js           # Search, active sentence tracking, click-to-seek, export
│   └── assets/logo.svg
│
├── uploads/                        # Uploaded / downloaded source videos by job ID
├── processing/                     # Job state JSON & temporary files
└── output/                         # Generated transcript.json, interpreter.mp4, sync.json
```

---

## Windows Setup Instructions

### 1. Install Python 3.11
Download Python 3.11 (64-bit) from [python.org](https://www.python.org/downloads/windows/) and ensure **"Add python.exe to PATH"** is checked during installation.

### 2. Install FFmpeg & FFprobe (Windows)
```cmd
winget install Gyan.FFmpeg
```
Reopen Command Prompt and verify:
```cmd
ffmpeg -version
ffprobe -version
```

### 3. Download and Configure the Vosk Offline Model
1. Download `vosk-model-small-en-us-0.15.zip` (~40 MB) from `https://alphacephei.com/vosk/models`.
2. Extract it so `am/`, `conf/`, `graph/`, `ivector/` sit directly inside `models/vosk-model-small-en-us/`.

### 4. Sign Language Dataset (WLASL)
SignBridge ships with `sign_library/wlasl_index.json` (2,000 ASL glosses from `Voxel51/WLASL`) and 57 pre-downloaded starter clips in `sign_library/metadata.json`. Additional matched glosses are downloaded automatically into `sign_library/dataset_cache/` when needed. To re-populate the starter pack manually:
```cmd
python scripts\bootstrap_sign_library.py
```

### 5. Launch SignBridge on Windows
Double-click `launch.bat` or run:
```cmd
launch.bat
```

---

## API Endpoints

- `POST /api/upload` — Upload a video file (`multipart/form-data`, field name `video`) and start background processing.
- `POST /api/youtube` — Submit `{ "url": "https://..." }` for supported public YouTube videos via `yt-dlp`.
- `GET /api/jobs/<job_id>` — Real-time job status, current stage, progress percentage, transcript preview, and error messages.
- `GET /api/transcript/<job_id>` — Full Vosk transcription JSON with word/sentence timestamps and ASL gloss mappings.
- `GET /api/player/<job_id>` — Original video URL, compiled ASL interpreter video URL, media dimensions/duration.
- `GET /api/sync/<job_id>` — Synchronization metadata JSON mapping original timestamps to interpreter segments.
- `GET /api/video/<job_id>/<video_type>` — HTTP range-capable stream for `original` or `interpreter` video.
- `GET /api/library` — Starter sign library and WLASL index summary.
- `GET /api/health` — Checks FFmpeg, FFprobe, local Vosk model, and WLASL dataset readiness.

---

## Testing End-to-End

1. Check `/api/health` returns `"ffmpeg": true`, `"ffprobe": true`, `"vosk_model": true`, and `"wlasl_gloss_count": 2000`.
2. Upload an `.mp4` video with spoken English (or paste a public non-DRM YouTube URL).
3. Watch `/processing/<job_id>` advance through audio extraction, Vosk transcription, ASL translation, WLASL clip matching, and FFmpeg interpreter compilation.
4. On `/player/<job_id>`, play the video and verify the floating Picture-in-Picture (or Side-by-Side) human ASL interpreter stays synchronized on play, pause, seek, and speed changes.
5. Run the automated backend test suite:
   ```bash
   python -m unittest discover -s tests -v
   ```
