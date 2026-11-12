FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates \
    && arch="$(uname -m)" \
    && if [ "$arch" = "aarch64" ]; then deno_arch="aarch64-unknown-linux-gnu"; else deno_arch="x86_64-unknown-linux-gnu"; fi \
    && curl -fsSL "https://github.com/denoland/deno/releases/latest/download/deno-${deno_arch}.zip" -o /tmp/deno.zip \
    && unzip -o /tmp/deno.zip -d /usr/local/bin \
    && rm -f /tmp/deno.zip \
    && chmod +x /usr/local/bin/deno \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY telegram_bot_worker.py .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
