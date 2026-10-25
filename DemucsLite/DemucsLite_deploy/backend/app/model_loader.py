"""Load the bundled original model or a new self-describing V2 checkpoint."""
import logging
import re
from pathlib import Path

import torch
from torch import nn

from app.config import CHECKPOINT_PATH, MODEL_DEVICE, SOURCE_NAMES
from audio_sep.inference import load_checkpoint
from audio_sep.legacy_model import DemucsLite

logger = logging.getLogger("uvicorn.error")
_model = None
_device = None
_metadata = {}


class NamedLegacySeparator(nn.Module):
    """Give the original architecture named sources for split inference."""

    def __init__(self, model, sources, sample_rate=44100):
        super().__init__()
        self.model = model
        self.sources = tuple(sources)
        self.samplerate = sample_rate
        self.audio_channels = model.audio_channels

    def forward(self, mixture):
        return self.model(mixture)


def _source_names(checkpoint):
    sources = checkpoint.get("source_names", checkpoint.get("sources", SOURCE_NAMES))
    if not isinstance(sources, (list, tuple)) or len(sources) != 4 or set(sources) != set(SOURCE_NAMES):
        raise ValueError("Checkpoint must identify vocals, drums, bass and other exactly once.")
    return tuple(sources)


def _legacy_config(state, checkpoint):
    """Infer tensor-dependent dimensions rather than hardcoding model size."""
    encoder_indices = sorted({int(match.group(1)) for key in state
                              if (match := re.fullmatch(r"encoders\.(\d+)\.conv\.weight", key))})
    if not encoder_indices or encoder_indices != list(range(len(encoder_indices))):
        raise ValueError("Unrecognized original DemucsLite encoder state.")
    first = state["encoders.0.conv.weight"]
    audio_channels, channels, kernel_size = int(first.shape[1]), int(first.shape[0]), int(first.shape[2])
    depth = len(encoder_indices)
    growth = (int(state["encoders.1.conv.weight"].shape[0]) / channels) if depth > 1 else 2
    layers = {int(match.group(1)) for key in state
              if (match := re.fullmatch(r"lstm\.weight_ih_l(\d+)", key))}
    declared = checkpoint.get("model_config", {})
    if not isinstance(declared, dict):
        raise ValueError("Invalid original checkpoint model_config.")
    config = dict(sources=len(_source_names(checkpoint)), audio_channels=audio_channels,
                  channels=channels, depth=depth, growth=growth, kernel_size=kernel_size,
                  stride=int(declared.get("stride", 4)), lstm_layers=len(layers))
    if audio_channels != 2 or not layers:
        raise ValueError("This API requires a stereo original DemucsLite checkpoint with an LSTM.")
    # Stride has no tensor representation; old checkpoints use notebook stride=4.
    for name in ("channels", "depth", "audio_channels", "kernel_size", "lstm_layers"):
        if name in declared and declared[name] != config[name]:
            raise ValueError(f"Checkpoint metadata and tensors disagree about {name}.")
    return config


def load_model_checkpoint(path, device="cpu"):
    """Load a trusted .pth and return model plus concise deployment metadata."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Model checkpoint does not exist: {path}")
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict):
        raise ValueError("Checkpoint must be a dictionary.")
    if checkpoint.get("format_version") == 2:
        # Avoid keeping two full checkpoint copies while the V2 loader reads it.
        del checkpoint
        model, checkpoint = load_checkpoint(path, device=device)
        kind = checkpoint["model_kind"]
        config = checkpoint["model_config"]
    else:
        state = checkpoint.get("model_state_dict", checkpoint.get("state_dict", checkpoint))
        config = _legacy_config(state, checkpoint)
        original = DemucsLite(**config)
        original.load_state_dict(state, strict=True)
        model = NamedLegacySeparator(original, _source_names(checkpoint), checkpoint.get("sample_rate", 44100))
        model.to(device).eval()
        kind = "legacy_lite"
    if tuple(model.sources) != tuple(dict.fromkeys(model.sources)) or set(model.sources) != set(SOURCE_NAMES):
        raise ValueError("This application requires the four named music sources.")
    if getattr(model, "audio_channels", 2) != 2 or getattr(model, "samplerate", 44100) != 44100:
        raise ValueError("This application requires a stereo 44100 Hz checkpoint.")
    metadata = {
        "ready": True, "model_kind": kind, "checkpoint": path.name,
        "epoch": checkpoint.get("epoch"), "device": str(device),
        "sample_rate": 44100, "sources": list(model.sources),
        "selected_weights": checkpoint.get("selected_weights", "model"),
        "model_config": config,
    }
    return model, metadata


def load_model():
    global _model, _device, _metadata
    if _model is not None:
        return _model
    if MODEL_DEVICE not in {"auto", "cpu", "cuda"}:
        raise ValueError("MODEL_DEVICE must be auto, cpu or cuda.")
    _device = ("cuda" if torch.cuda.is_available() else "cpu") if MODEL_DEVICE == "auto" else MODEL_DEVICE
    if _device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("MODEL_DEVICE=cuda requested, but CUDA is unavailable.")
    _model, _metadata = load_model_checkpoint(CHECKPOINT_PATH, _device)
    logger.info("Model ready: %s, epoch=%s, device=%s", _metadata["model_kind"], _metadata["epoch"], _device)
    return _model


def get_model():
    if _model is None:
        raise RuntimeError("Model has not been loaded. Start the server with its lifespan enabled.")
    return _model


def get_device():
    return _device


def get_model_info():
    return dict(_metadata, ready=_model is not None)
