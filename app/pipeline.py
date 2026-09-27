"""
Luồng xử lý chính: audio đầu vào -> model DemucsLite -> 4 file nguồn tách riêng
-> upload cloud -> cập nhật job status với download links.
"""
import logging
import torch
import torchaudio
import soundfile as sf

from app.config import RESULT_DIR, SOURCE_NAMES
from app.model_loader import get_model, get_device
from app.job_store import job_store, JobStatus
from app.cloud_storage import upload_folder

logger = logging.getLogger("uvicorn.error")


def run_separation_pipeline(job_id: str, input_path: str):
    try:
        job_store.update(job_id, status=JobStatus.PROCESSING)
        logger.info(f"[pipeline] Bắt đầu xử lý job {job_id}")

        model = get_model()
        device = get_device()

        # 1. Đọc audio bằng soundfile thay cho torchaudio.load
        data, sample_rate = sf.read(str(input_path), dtype="float32", always_2d=True)
        waveform = torch.from_numpy(data.T)

        # 2. Resample về 44.1 kHz nếu audio khác chuẩn
        TARGET_SR = 44100
        if sample_rate != TARGET_SR:
            resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=TARGET_SR)
            waveform = resampler(waveform)
            sample_rate = TARGET_SR

        # 3. Đảm bảo chuẩn 2 kênh Stereo
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
        elif waveform.shape[0] > 2:
            waveform = waveform[:2, :]

        # 4. Chạy mô hình tách âm
        mixture = waveform.unsqueeze(0).to(device)
        with torch.no_grad():
            sources = model(mixture)

        sources = sources.squeeze(0).cpu()

        # 5. Tạo thư mục lưu kết quả
        job_result_dir = RESULT_DIR / job_id
        job_result_dir.mkdir(parents=True, exist_ok=True)

        # 6. LƯU BẰNG SOUNDFILE (KHÔNG DÙNG torchaudio.save ĐỂ TRÁNH LỖI TORCHCODEC)
        for i, source_name in enumerate(SOURCE_NAMES):
            out_file = job_result_dir / f"{source_name}.wav"
            stem_data = sources[i].numpy().T
            sf.write(str(out_file), stem_data, sample_rate, subtype="PCM_16")

        logger.info(f"[pipeline] Đã xuất xong 4 file audio cho job {job_id}")

        # 7. Upload và hoàn tất
        result_urls = upload_folder(job_id, job_result_dir)
        job_store.update(job_id, status=JobStatus.DONE, result_urls=result_urls)
        logger.info(f"[pipeline] Hoàn thành job {job_id}")

    except Exception as e:
        logger.error(f"[pipeline] Lỗi khi xử lý job {job_id}: {str(e)}")
        job_store.update(job_id, status=JobStatus.FAILED, error=str(e))