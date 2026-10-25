"""Deployment settings. The default model is bundled next to the application."""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Only load trusted project checkpoints; model files are never accepted via the API.
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", str(BASE_DIR / "checkpoints" / "best_model.pth"))
SOURCE_NAMES = ("vocals", "drums", "bass", "other")
MODEL_DEVICE = os.getenv("MODEL_DEVICE", "auto").lower()
# Empty chooses 10 seconds for the original model and 6 seconds for V2 models.
INFERENCE_SEGMENT_SECONDS = os.getenv("INFERENCE_SEGMENT_SECONDS", "").strip()
INFERENCE_OVERLAP = float(os.getenv("INFERENCE_OVERLAP", "0.5"))
if not 0 <= INFERENCE_OVERLAP < 1:
    raise ValueError("INFERENCE_OVERLAP must be in [0, 1).")

def resolve_ffmpeg_binary():
    """Prefer explicit/system FFmpeg, then the optional bundled Python binary."""
    explicit = os.getenv("FFMPEG_BINARY", "").strip()
    if explicit:
        return explicit
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        # Keep the actionable decoder error when neither installation exists.
        return "ffmpeg"


FFMPEG_BINARY = resolve_ffmpeg_binary()

UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
RESULT_DIR = BASE_DIR / "storage" / "results"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
if MAX_UPLOAD_MB <= 0:
    raise ValueError("MAX_UPLOAD_MB must be positive.")

# In-memory job tracking requires one Uvicorn worker, including on GPU servers.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
if STORAGE_BACKEND not in {"local", "s3", "gcs"}:
    raise ValueError("STORAGE_BACKEND must be local, s3 or gcs.")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
S3_PRESIGNED_EXPIRE_SECONDS = int(os.getenv("S3_PRESIGNED_EXPIRE_SECONDS", "3600"))
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
GCS_PRESIGNED_EXPIRE_SECONDS = int(os.getenv("GCS_PRESIGNED_EXPIRE_SECONDS", "3600"))
# Empty uses each upload request's origin, so Android emulator download links work.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
