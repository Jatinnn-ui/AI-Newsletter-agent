# Combined image: build the React frontend, then serve it from the FastAPI
# backend. One container, one port (8000), one URL. Build context = repo root.

# --- Stage 1: build the frontend static assets ---------------------------
FROM node:24-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Same-origin in the combined deploy: the frontend calls the backend on the
# same host, so the API base URL is empty (relative paths).
ARG VITE_API_BASE_URL=""
ARG VITE_API_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- Stage 2: backend + bundled frontend ---------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OUTPUT_DIR=/data/output \
    DATA_DIR=/data/state

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/app ./app
# Bundle the built frontend so FastAPI can serve it from /app/app/static.
COPY --from=frontend /fe/dist ./app/static

RUN useradd --create-home appuser && mkdir -p /data && chown appuser /data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
