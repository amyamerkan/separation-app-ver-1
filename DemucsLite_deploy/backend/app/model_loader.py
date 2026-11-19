from pathlib import Path
import torch
from huggingface_hub import hf_hub_download
from app.config import settings
from audio_sep.inference import load_checkpoint

_loaded_model: torch.nn.Module | None = None

def download_checkpoint() -> Path:
    """Tải checkpoint từ Hugging Face Hub về Modal Volume nếu chưa có."""
    local_ckpt = settings.MODEL_CACHE_DIR / settings.HF_MODEL_FILE
    if local_ckpt.exists():
        return local_ckpt

    downloaded_path = hf_hub_download(
        repo_id=settings.HF_MODEL_REPO,
        filename=settings.HF_MODEL_FILE,
        local_dir=str(settings.MODEL_CACHE_DIR),
        token=settings.HF_TOKEN,
    )
    return Path(downloaded_path)

def get_model() -> torch.nn.Module:
    """Khởi tạo và nạp checkpoint V2 (DemucsLiteV2 / PretrainedSeparator) lên GPU."""
    global _loaded_model
    if _loaded_model is not None:
        return _loaded_model

    ckpt_path = download_checkpoint()
    model, _ = load_checkpoint(str(ckpt_path), device=settings.DEVICE)
    _loaded_model = model
    return _loaded_model