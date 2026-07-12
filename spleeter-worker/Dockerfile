FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# spleeter 2.4.0 pins tensorflow<2.10, tapi wheel itu tidak pernah dirilis untuk
# linux/arm64 (Apple Silicon) -- 2.10 adalah rilis TF pertama dengan wheel arm64.
# Kodenya sendiri tetap kompatibel dengan TF 2.10, jadi install tanpa deps spleeter
# lalu pakai dependency di atas yang sudah dipin manual.
RUN pip install --no-cache-dir --no-deps spleeter==2.4.0

COPY app.py .

# Pre-download bobot model Spleeter supaya request pertama tidak menunggu unduhan
RUN python -c "from spleeter.separator import Separator; Separator('spleeter:4stems')"

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
