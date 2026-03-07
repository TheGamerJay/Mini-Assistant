# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps

COPY frontend/ ./
# Bake the Railway backend URL at build time
ARG REACT_APP_BACKEND_URL=https://mini-assistant-production.up.railway.app
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN npm run build

# ── Stage 2: Python backend + built frontend ──────────────────────────────────
FROM python:3.11-slim

# System deps needed by heavy packages
# - gcc/g++/cmake: torch, cryptography, ctranslate2
# - libssl/libffi: cryptography, cffi
# - libjpeg/zlib: pillow
# - libxml2/xslt: lxml
# - libopenblas: faiss-cpu, scipy, numpy
# - libgomp: torch, faiss-cpu (OpenMP)
# - libjq: jq Python package
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    cmake \
    libssl-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    libxml2-dev \
    libxslt1-dev \
    libopenblas-dev \
    libgomp1 \
    libjq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer unless requirements.txt changes)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built React app into backend/static so FastAPI can serve it
COPY --from=frontend-builder /frontend/build ./backend/static

WORKDIR /app/backend

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 locally
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
