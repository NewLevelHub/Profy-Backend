FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=300 --retries 10 -r requirements.txt

# App code only. University photos are NOT baked in — they live in a host
# folder bind-mounted at runtime (STORAGE_FS_ROOT, see docker-compose.yml)
# and are served by nginx, not this process. `.dockerignore` also keeps
# .env / .venv / .git out of the image.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
