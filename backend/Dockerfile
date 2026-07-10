FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Torch CPU-only wheels (jauh lebih kecil dari build CUDA default)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchaudio==2.4.1
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /app/downloads /app/splits

# Pre-download bobot model Demucs supaya request pertama tidak menunggu unduhan
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
