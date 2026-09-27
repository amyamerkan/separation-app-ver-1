"""
Lớp trừu tượng lưu trữ file kết quả sau khi tách nhạc và sinh download link.

Hỗ trợ 3 backend, chọn qua biến môi trường STORAGE_BACKEND:
  - "local": phục vụ file tĩnh ngay từ FastAPI (app/main.py mount /files).
             Không cần tài khoản cloud -> dùng để chạy demo / nộp bài ngay.
  - "s3"   : đẩy lên AWS S3, sinh presigned URL có thời hạn.
  - "gcs"  : đẩy lên Google Cloud Storage, sinh signed URL có thời hạn.

Mỗi hàm upload_folder() nhận job_id + thư mục local chứa các file .wav đã tách,
trả về dict {tên_file: url_tải_về}.
"""
import os
import logging
from pathlib import Path
from typing import Dict

from app.config import (
    STORAGE_BACKEND,
    S3_BUCKET,
    S3_REGION,
    S3_PRESIGNED_EXPIRE_SECONDS,
    GCS_BUCKET,
    GCS_PRESIGNED_EXPIRE_SECONDS,
    PUBLIC_BASE_URL,
)

logger = logging.getLogger("uvicorn.error")


def upload_folder(job_id: str, local_dir: Path) -> Dict[str, str]:
    if STORAGE_BACKEND == "s3":
        return _upload_s3(job_id, local_dir)
    if STORAGE_BACKEND == "gcs":
        return _upload_gcs(job_id, local_dir)
    return _upload_local(job_id, local_dir)


# ---------------------------------------------------------------------------
# Backend: local (không cần cloud, phục vụ file qua chính API)
# ---------------------------------------------------------------------------
def _upload_local(job_id: str, local_dir: Path) -> Dict[str, str]:
    urls = {}
    for f in sorted(local_dir.glob("*.wav")):
        # File đã nằm sẵn trong storage/results/<job_id>/, chỉ cần build URL
        # tương ứng với route static đã mount trong app/main.py (/files/...)
        urls[f.name] = f"{PUBLIC_BASE_URL}/files/{job_id}/{f.name}"
    logger.info(f"[cloud_storage] (local) {len(urls)} file sẵn sàng cho job {job_id}")
    return urls


# ---------------------------------------------------------------------------
# Backend: AWS S3
# ---------------------------------------------------------------------------
def _upload_s3(job_id: str, local_dir: Path) -> Dict[str, str]:
    import boto3
    from botocore.config import Config

    if not S3_BUCKET:
        raise RuntimeError("Thiếu biến môi trường S3_BUCKET")

    s3 = boto3.client("s3", region_name=S3_REGION, config=Config(signature_version="s3v4"))
    urls = {}
    for f in sorted(local_dir.glob("*.wav")):
        key = f"results/{job_id}/{f.name}"
        s3.upload_file(str(f), S3_BUCKET, key)
        urls[f.name] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=S3_PRESIGNED_EXPIRE_SECONDS,
        )
    logger.info(f"[cloud_storage] (s3) Đã upload {len(urls)} file lên bucket {S3_BUCKET}")
    return urls


# ---------------------------------------------------------------------------
# Backend: Google Cloud Storage
# ---------------------------------------------------------------------------
def _upload_gcs(job_id: str, local_dir: Path) -> Dict[str, str]:
    from google.cloud import storage
    import datetime

    if not GCS_BUCKET:
        raise RuntimeError("Thiếu biến môi trường GCS_BUCKET")

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    urls = {}
    for f in sorted(local_dir.glob("*.wav")):
        blob_name = f"results/{job_id}/{f.name}"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(f))
        urls[f.name] = blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=GCS_PRESIGNED_EXPIRE_SECONDS),
            method="GET",
        )
    logger.info(f"[cloud_storage] (gcs) Đã upload {len(urls)} file lên bucket {GCS_BUCKET}")
    return urls
