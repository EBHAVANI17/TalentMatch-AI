# Build from the repository root:  docker build -f backend/Dockerfile .

# --- Stage 1: build the React workspace (web/) -------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Stage 2: API + both frontends -------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/backend

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Bake the local embedding model into the image so containers never download it at runtime.
ENV EMBEDDING_CACHE_DIR=/srv/models/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/srv/models/fastembed')"

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY frontend /srv/frontend
COPY --from=web /web/dist /srv/web/dist

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /srv/backend/data /srv/backend/storage \
    && chown -R appuser /srv/backend
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
