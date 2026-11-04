"""Music separation API. Use one Uvicorn worker for the in-memory job store."""
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from app.config import UPLOAD_DIR, RESULT_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_MB, STORAGE_BACKEND, PUBLIC_BASE_URL
from app.model_loader import load_model, get_model_info
from app.job_store import job_store, JobStatus
from app.pipeline import run_separation_pipeline

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(application):
    load_model()
    yield


app = FastAPI(title="Music Source Separation API", version="2.0.0", lifespan=lifespan)
if STORAGE_BACKEND == "local":
    app.mount("/files", StaticFiles(directory=str(RESULT_DIR)), name="files")


@app.get("/health")
def health_check():
    model = get_model_info()
    return {"status": "ok" if model["ready"] else "starting", **model}


@app.post("/separate")
async def separate_audio(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(400, f"Unsupported extension '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    if not get_model_info().get("ready"):
        await file.close()
        raise HTTPException(503, "Model is not ready.")
    job_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{job_id}{ext}"
    size = 0
    try:
        with input_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_MB} MB upload limit.")
                destination.write(chunk)
        if not size:
            raise HTTPException(400, "The uploaded file is empty.")
    except Exception:
        input_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    job_store.create(job_id, filename=file.filename)
    origin = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    background_tasks.add_task(run_separation_pipeline, job_id, str(input_path), public_base_url=origin)
    logger.info("Accepted job=%s, bytes=%s", job_id, size)
    return {"job_id": job_id, "status": JobStatus.PENDING}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job ID was not found.")
    return job
