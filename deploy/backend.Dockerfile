# Backend image: FastAPI + APScheduler (uvicorn, single worker so the in-process
# scheduler runs exactly once). Build context is the REPO ROOT.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# PyMySQL is pure-Python; pandas/numpy/etc ship linux wheels — no build toolchain needed.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ ./
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
