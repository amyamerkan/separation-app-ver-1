"""
API tách nguồn âm thanh (Music Source Separation).

Chạy thử:
    uvicorn app.main:app --reload

Xem docs tự sinh tại: http://localhost:8000/docs

Luồng hoạt động:
  1. POST /separate         -> client upload file, nhận về job_id ngay (xử lý nền)
  2. GET  /status/{job_id}  -> client poll cho tới khi status == "done"
  3. Khi "done", response đã kèm sẵn download links trong result_urls
"""
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles

from app.config import (
    UPLOAD_DIR,
    RESULT_DIR,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_MB,
    STORAGE_BACKEND,
)
from app.model_loader import load_model
from app.job_store import job_store, JobStatus
from app.pipeline import run_separation_pipeline

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Music Source Separation API",
    description="Nhận file nhạc, tách thành vocals/drums/bass/other bằng DemucsLite.",
    version="1.0.0",
)

# Khi STORAGE_BACKEND=local, phục vụ file kết quả trực tiếp qua route tĩnh này
if STORAGE_BACKEND == "local":
    app.mount("/files", StaticFiles(directory=str(RESULT_DIR)), name="files")


@app.on_event("startup")
def on_startup():
    """Load model 1 lần duy nhất khi server khởi động, không load lại mỗi request."""
    load_model()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/separate")
async def separate_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng '{ext}' không được hỗ trợ. Chỉ chấp nhận: {sorted(ALLOWED_EXTENSIONS)}",
        )

    job_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{job_id}{ext}"

    # Ghi file theo chunk để tránh load toàn bộ vào RAM, đồng thời kiểm tra dung lượng
    size = 0
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    with open(input_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out_file.close()
                input_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File vượt quá giới hạn {MAX_UPLOAD_MB}MB")
            out_file.write(chunk)

    job_store.create(job_id, filename=file.filename)
    background_tasks.add_task(run_separation_pipeline, job_id, str(input_path))

    logger.info(f"[main] Nhận job mới {job_id} ({file.filename}, {size/1e6:.2f} MB)")
    return {"job_id": job_id, "status": JobStatus.PENDING}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Không tìm thấy job_id này")
    return job
