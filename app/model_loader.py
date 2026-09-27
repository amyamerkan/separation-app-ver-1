"""
Load model DemucsLite từ checkpoint đã train ở notebook w5.
Model được load MỘT LẦN duy nhất (singleton) khi server khởi động,
tránh việc load lại (rất chậm) ở mỗi request.
"""
import logging
import torch

from scripts.demucs_lite import DemucsLite
from app.config import CHECKPOINT_PATH, MODEL_CHANNELS, MODEL_DEPTH, SOURCE_NAMES

logger = logging.getLogger("uvicorn.error")

_model = None
_device = None


def load_model():
    """Được gọi ở FastAPI startup event. Raise lỗi rõ ràng nếu thiếu checkpoint."""
    global _model, _device
    if _model is not None:
        return _model

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"[model_loader] Đang load checkpoint: {CHECKPOINT_PATH} lên {_device}")

    model = DemucsLite(
        sources=len(SOURCE_NAMES),
        audio_channels=2,
        channels=MODEL_CHANNELS,
        depth=MODEL_DEPTH,
    )
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=_device, weights_only=False)
    state_dict = checkpoint["model_state_dict"] if "model_state_dict" in checkpoint else checkpoint
    model.load_state_dict(state_dict)
    model.to(_device)
    model.eval()

    _model = model
    logger.info("[model_loader] Model đã sẵn sàng.")
    return _model


def get_model():
    if _model is None:
        raise RuntimeError(
            "Model chưa được load. Đảm bảo load_model() đã chạy trong startup event của FastAPI."
        )
    return _model


def get_device():
    return _device
