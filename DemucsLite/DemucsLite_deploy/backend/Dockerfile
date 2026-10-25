FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_DEVICE=cpu

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
# x86 CPU wheels avoid downloading unused CUDA runtime libraries.
RUN if [ "$(uname -m)" = "x86_64" ]; then \
      python -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu; \
    else \
      python -m pip install torch==2.5.1 torchaudio==2.5.1; \
    fi \
    && python -m pip install -r requirements.txt

COPY app ./app
COPY audio_sep ./audio_sep
COPY checkpoints ./checkpoints
RUN useradd --create-home --uid 10001 separator \
    && mkdir -p /app/storage/uploads /app/storage/results \
    && chown -R separator:separator /app/storage
USER separator
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# One worker: the application stores job state in this process.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
