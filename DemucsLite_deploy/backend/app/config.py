import os
from pathlib import Path
import torch

class Settings:
    PROJECT_NAME: str = "DemucsLite Audio Separation API"
    VERSION: str = "2.0.0"

    # Hugging Face Hub
    HF_MODEL_REPO: str = os.getenv("HF_MODEL_REPO", "username/demucslite-v2")
    HF_MODEL_FILE: str = os.getenv("HF_MODEL_FILE", "best_model.pth")
    HF_TOKEN: str | None = os.getenv("HF_TOKEN") or None
    MODEL_CACHE_DIR: Path = Path(os.getenv("MODEL_CACHE_DIR", "/cache/models"))

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_CONTAINER_NAME: str = os.getenv("AZURE_CONTAINER_NAME", "audio-files")
    AZURE_SAS_EXPIRY_HOURS: int = int(os.getenv("AZURE_SAS_EXPIRY_HOURS", "24"))

    # Audio & Model Inference
    STEMS: tuple[str, ...] = ("vocals", "drums", "bass", "other")
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "44100"))
    SEGMENT_SECONDS: float = float(os.getenv("CHUNK_SECONDS", "6.0"))
    OVERLAP: float = float(os.getenv("OVERLAP_RATIO", "0.25"))
    DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Thư mục tạm trong container khi đang tách nhạc
    WORK_DIR: Path = Path(os.getenv("WORK_DIR", "/tmp/demucslite_jobs"))

settings = Settings()
settings.WORK_DIR.mkdir(parents=True, exist_ok=True)
settings.MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)