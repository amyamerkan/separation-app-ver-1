import shutil
import subprocess
from pathlib import Path
from typing import Any
import numpy as np
import soundfile as sf
import torch
from app.config import settings
from app.cloud_storage import get_storage
from app.job_store import job_store
from app.model_loader import get_model
from audio_sep.inference import load_audio, overlap_add

def _decode_to_wav(src_path: Path, dst_path: Path, sample_rate: int) -> Path:
    """Dùng ffmpeg chuẩn hóa mp3/m4a/flac/wav sang WAV Stereo để load_audio đọc an toàn."""
    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-ac", "2", "-ar", str(sample_rate),
        "-c:a", "pcm_f32le", str(dst_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Lỗi giải mã audio bằng ffmpeg: {proc.stderr[-300:]}")
    return dst_path

def process_separation_job(job_id: str, local_input_path: Path, original_filename: str) -> dict[str, Any]:
    job_dir = settings.WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    storage = get_storage()

    try:
        job_store.update_job(job_id, status="processing", progress=10)

        # 1. Lưu file nhạc gốc lên Azure Blob Storage
        ext = local_input_path.suffix.lower() or ".wav"
        content_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
        }
        input_blob_path = f"uploads/{job_id}/original{ext}"
        input_sas_url = storage.upload_file_and_get_sas(
            local_path=local_input_path,
            blob_path=input_blob_path,
            content_type=content_types.get(ext, "application/octet-stream"),
        )
        job_store.update_job(job_id, input_url=input_sas_url, progress=25)

        # 2. Giải mã và chuẩn hóa tần số lấy mẫu khớp với model
        model = get_model()
        target_sr = getattr(model, "samplerate", settings.SAMPLE_RATE)
        decoded_wav = _decode_to_wav(local_input_path, job_dir / "decoded.wav", target_sr)
        wav = load_audio(decoded_wav, sample_rate=target_sr)

        # 3. Tách 4 stems bằng overlap_add trên GPU
        job_store.update_job(job_id, status="processing", progress=45)
        estimates = overlap_add(
            model=model,
            mixture=wav,
            segment_seconds=settings.SEGMENT_SECONDS,
            overlap=settings.OVERLAP,
            device=settings.DEVICE,
        )
        if not torch.isfinite(estimates).all():
            raise ValueError("Kết quả tách từ model chứa giá trị không hợp lệ (NaN/Inf).")
        job_store.update_job(job_id, status="processing", progress=80)

        # 4. Xuất 4 file WAV theo đúng thứ tự model.sources và đẩy lên Azure Blob
        stem_urls: dict[str, str] = {}
        for stem_name, stem_tensor in zip(model.sources, estimates):
            stem_local_path = job_dir / f"{stem_name}.wav"
            audio_np = np.clip(stem_tensor.detach().cpu().numpy().T, -1.0, 1.0)
            sf.write(str(stem_local_path), audio_np, target_sr, subtype="PCM_16")

            blob_stem_path = f"outputs/{job_id}/{stem_name}.wav"
            stem_urls[stem_name] = storage.upload_file_and_get_sas(
                local_path=stem_local_path,
                blob_path=blob_stem_path,
                content_type="audio/wav",
            )

        # 5. Hoàn tất với status="done" khớp với StudioSession.java
        return job_store.update_job(
            job_id,
            status="done",
            progress=100,
            stems=stem_urls,
            result_urls=stem_urls,
        )

    except Exception as exc:
        job_store.update_job(
            job_id,
            status="failed",
            error=str(exc),
        )
        raise
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)