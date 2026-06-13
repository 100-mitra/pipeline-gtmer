# Backend image — Render (primary) / Hugging Face Spaces (fallback).
# The pipeline CLI is run locally; this image serves only the read API.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY pipeline ./pipeline
RUN pip install --upgrade pip && pip install .

# Render/HF inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn pipeline.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
