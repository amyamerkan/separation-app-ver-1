import modal

# Xây dựng môi trường container trên Modal
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "torch",
        "torchaudio",
        "fastapi[standard]",
        "uvicorn",
        "python-multipart",
        "soundfile",
        "librosa",
        "numpy",
        "scipy",
        "huggingface_hub",
        "azure-storage-blob",
    )
    .add_local_dir("app", remote_path="/root/app")
    .add_local_dir("audio_sep", remote_path="/root/audio_sep")
)

app = modal.App("demucslite-separation-backend", image=image)

# Volume lưu đệm best_model.pth trên Modal để không phải tải lại từ Hugging Face mỗi lần bật GPU
model_volume = modal.Volume.from_name("demucslite-model-cache", create_if_missing=True)

@app.function(
    gpu="T4",
    volumes={"/cache/models": model_volume},
    secrets=[modal.Secret.from_name("demucs-env-secrets")],
    scaledown_window=60,  # Giữ GPU ấm 60 giây sau khi xử lý xong request
    timeout=600,
)
@modal.asgi_app()
def fastapi_app():
    import sys
    if "/root" not in sys.path:
        sys.path.insert(0, "/root")
    from app.main import app as web_app
    return web_app