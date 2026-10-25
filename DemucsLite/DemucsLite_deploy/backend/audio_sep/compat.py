"""Scoped compatibility for trusted official Demucs 4 checkpoints on PyTorch 2.6+."""
import os
from threading import Lock

_LOAD_LOCK = Lock()


def official_model(name):
    if name not in ("htdemucs", "htdemucs_ft"):
        raise ValueError("Only official htdemucs/htdemucs_ft names are supported.")
    from demucs.pretrained import get_model
    # Demucs 4 torch.load omits weights_only. PyTorch 2.6 changed its default.
    # Limit the compatibility setting to official, checksum-verified downloads.
    with _LOAD_LOCK:
        key = "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"
        previous = os.environ.get(key)
        os.environ[key] = "1"
        try:
            return get_model(name)
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
