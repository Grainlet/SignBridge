import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = Path(os.environ.get("SIGNBRIDGE_UPLOAD_DIR", BASE_DIR / "uploads"))
PROCESSING_FOLDER = Path(os.environ.get("SIGNBRIDGE_PROCESSING_DIR", BASE_DIR / "processing"))
OUTPUT_FOLDER = Path(os.environ.get("SIGNBRIDGE_OUTPUT_DIR", BASE_DIR / "output"))
MODELS_DIR = Path(os.environ.get("SIGNBRIDGE_MODELS_DIR", BASE_DIR / "models"))
SIGN_LIBRARY_DIR = Path(os.environ.get("SIGNBRIDGE_LIBRARY_DIR", BASE_DIR / "sign_library"))

DEFAULT_VOSK_MODEL_NAME = "vosk-model-small-en-us"
VOSK_MODEL_PATH = Path(
    os.environ.get("VOSK_MODEL_PATH", MODELS_DIR / DEFAULT_VOSK_MODEL_NAME)
)

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_UPLOAD_BYTES = int(os.environ.get("SIGNBRIDGE_MAX_UPLOAD_MB", "500")) * 1024 * 1024

VOSK_SAMPLE_RATE = 16000
VOSK_AUDIO_CHANNELS = 1
AUDIO_CHUNK_FRAMES = 4000

FFMPEG_BINARY = os.environ.get("FFMPEG_BINARY", "ffmpeg")
FFPROBE_BINARY = os.environ.get("FFPROBE_BINARY", "ffprobe")

WLASL_INDEX_PATH = SIGN_LIBRARY_DIR / "wlasl_index.json"
SIGN_METADATA_PATH = SIGN_LIBRARY_DIR / "metadata.json"
WLASL_CACHE_DIR = SIGN_LIBRARY_DIR / "dataset_cache"
WLASL_NORMALIZED_DIR = SIGN_LIBRARY_DIR / "normalized"
WLASL_HF_BASE = "https://huggingface.co/datasets/Voxel51/WLASL/resolve/main/"

INTERPRETER_WIDTH = 480
INTERPRETER_HEIGHT = 360
INTERPRETER_FPS = 25

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"


def ensure_directories() -> None:
    for directory in (
        UPLOAD_FOLDER,
        PROCESSING_FOLDER,
        OUTPUT_FOLDER,
        MODELS_DIR,
        SIGN_LIBRARY_DIR,
        SIGN_LIBRARY_DIR / "greetings",
        SIGN_LIBRARY_DIR / "questions",
        SIGN_LIBRARY_DIR / "daily_life",
        SIGN_LIBRARY_DIR / "conversations",
        WLASL_CACHE_DIR,
        WLASL_NORMALIZED_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
