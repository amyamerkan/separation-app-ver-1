import uuid
import shutil
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.job_store import job_store
from app.model_loader import get_model
from app.pipeline import process_separation_job

MODEL_LOAD_ERROR: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global MODEL_LOAD_ERROR
    try:
        get_model()
        MODEL_LOAD_ERROR = None
    except Exception:
        MODEL_LOAD_ERROR = traceback.format_exc()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {
        "status": "ok" if MODEL_LOAD_ERROR is None else "model_error",
        "device": settings.DEVICE,
        "hf_repo": settings.HF_MODEL_REPO,
        "azure_container": settings.AZURE_CONTAINER_NAME,
        "model_error": MODEL_LOAD_ERROR,
    }

@app.post("/separate")
@app.post("/api/separate")
async def separate_audio_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    wait: bool = Query(False),
):
    if MODEL_LOAD_ERROR is not None:
        raise HTTPException(status_code=500, detail=f"Model chưa sẵn sàng: {MODEL_LOAD_ERROR}")
    if not file.filename:
        raise HTTPException(status_code=400, detail="File tải lên không hợp lệ")

    job_id = str(uuid.uuid4())
    job_dir = settings.WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    ext = "." + file.filename.split(".")[-1] if "." in file.filename else ".wav"
    local_input_path = job_dir / f"input{ext}"

    with open(local_input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    job_store.create_job(job_id=job_id, filename=file.filename)

    if wait:
        return process_separation_job(job_id, local_input_path, file.filename)
    background_tasks.add_task(process_separation_job, job_id, local_input_path, file.filename)
    return job_store.get_job(job_id)

@app.get("/status/{job_id}")
@app.get("/jobs/{job_id}")
@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã xử lý này")
    return job