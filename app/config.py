"""
Cấu hình tập trung cho toàn bộ ứng dụng.
Đọc từ biến môi trường để dễ triển khai (local / Docker / cloud) mà không sửa code.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Model ---
CHECKPOINT_PATH = os.getenv("CHECKPOINT_PATH", str(BASE_DIR / "checkpoints" / "demucs_lite_best.pth"))
SOURCE_NAMES = ["vocals", "drums", "bass", "other"]
MODEL_CHANNELS = int(os.getenv("MODEL_CHANNELS", 32))
MODEL_DEPTH = int(os.getenv("MODEL_DEPTH", 5))

# --- Storage cục bộ (dùng làm buffer trước khi đẩy lên cloud) ---
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
RESULT_DIR = BASE_DIR / "storage" / "results"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", 50))

# --- Cloud storage ---
# "local"  : không cần cấu hình gì, phục vụ file qua chính FastAPI (dùng để demo/nộp bài)
# "s3"     : cần AWS_* env vars + S3_BUCKET
# "gcs"    : cần GOOGLE_APPLICATION_CREDENTIALS + GCS_BUCKET
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
S3_PRESIGNED_EXPIRE_SECONDS = int(os.getenv("S3_PRESIGNED_EXPIRE_SECONDS", 3600))

GCS_BUCKET = os.getenv("GCS_BUCKET", "")
GCS_PRESIGNED_EXPIRE_SECONDS = int(os.getenv("GCS_PRESIGNED_EXPIRE_SECONDS", 3600))

# Base URL công khai của chính API (dùng khi STORAGE_BACKEND=local để build download link)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
