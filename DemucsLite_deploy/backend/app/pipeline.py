"""Decode, separate overlapping chunks, and export Android-compatible WAV files."""
import logging
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from app.config import RESULT_DIR, FFMPEG_BINARY, INFERENCE_SEGMENT_SECONDS, INFERENCE_OVERLAP
from app.model_loader import get_model, get_device, get_model_info
from app.job_store import job_store, JobStatus
from app.cloud_storage import upload_folder
from audio_sep.inference import overlap_add

logger = logging.getLogger("uvicorn.error")
_inference_lock = threading.Lock()
SAMPLE_RATE = 44100


def decode_audio(path):
    """Keep full-song buffers on CPU. FFmpeg handles codecs and resampling."""
    try:
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    except (RuntimeError, ValueError, OSError):
        data, sample_rate = None, None
    if data is not None and sample_rate == SAMPLE_RATE and data.shape[1] in (1, 2):
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
    else:
        command = [FFMPEG_BINARY, "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-i", str(path), "-vn", "-f", "f32le", "-acodec", "pcm_f32le",
                   "-ar", str(SAMPLE_RATE), "-ac", "2", "pipe:1"]
        try:
            decoded = subprocess.run(command, check=True, capture_output=True, timeout=300)
        except FileNotFoundError as error:
            raise RuntimeError("FFmpeg is required for MP3/M4A decoding and resampling.") from error
        except subprocess.TimeoutExpired as error:
            raise ValueError("Audio decoding exceeded 300 seconds.") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or b"").decode("utf-8", errors="replace")[-1000:]
            raise ValueError(f"Cannot decode the uploaded audio: {detail}") from error
        if len(decoded.stdout) % 8:
            raise ValueError("FFmpeg returned an incomplete stereo audio frame.")
        data = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2)
    if not data.size or not np.isfinite(data).all():
        raise ValueError("Audio must contain nonempty, finite samples.")
    return torch.from_numpy(np.ascontiguousarray(data.T)).float()


def export_pcm_stems(estimates, directory, sources):
    """Apply one shared headroom gain only if a stem exceeds PCM full scale."""
    if estimates.ndim != 3 or estimates.shape[0] != len(sources) or estimates.shape[1] != 2 or not estimates.shape[-1]:
        raise ValueError("Expected nonempty [sources, 2, samples] model estimates.")
    if not torch.isfinite(estimates).all():
        raise ValueError("Model produced nonfinite audio.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    peak = float(estimates.abs().max())
    gain = ((32767 / 32768) / peak) if peak > 1 else 1.0
    for source, estimate in zip(sources, estimates):
        if source not in {"vocals", "drums", "bass", "other"}:
            raise ValueError("Unexpected source name.")
        sf.write(str(directory / f"{source}.wav"), (estimate.detach().cpu() * gain).numpy().T,
                 SAMPLE_RATE, subtype="PCM_16")
    return gain


def run_separation_pipeline(job_id: str, input_path: str, public_base_url=None):
    output_dir = RESULT_DIR / job_id
    try:
        # Each background task waits its turn; GPU/CPU inference has one owner.
        with _inference_lock:
            job_store.update(job_id, status=JobStatus.PROCESSING)
            model = get_model()
            mixture = decode_audio(input_path)
            configured = INFERENCE_SEGMENT_SECONDS
            segment = float(configured) if configured else (10.0 if get_model_info().get("model_kind") == "legacy_lite" else 6.0)
            if segment <= 0:
                raise ValueError("INFERENCE_SEGMENT_SECONDS must be positive.")
            estimates = overlap_add(model, mixture, segment_seconds=segment,
                                    overlap=INFERENCE_OVERLAP, device=get_device())
            gain = export_pcm_stems(estimates, output_dir, model.sources)
            result_urls = upload_folder(job_id, output_dir, public_base_url=public_base_url)
            job_store.update(job_id, status=JobStatus.DONE, result_urls=result_urls)
            logger.info("Separation complete: job=%s, sources=%s, common_output_gain=%.6f", job_id, model.sources, gain)
    except Exception as error:
        logger.exception("Separation failed: job=%s", job_id)
        shutil.rmtree(output_dir, ignore_errors=True)
        job_store.update(job_id, status=JobStatus.FAILED, error=str(error))
    finally:
        Path(input_path).unlink(missing_ok=True)
