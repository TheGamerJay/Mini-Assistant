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

WORKDIR /app/backend

EXPOSE 8000

# Railway injects $PORT; fall back to 8000 locally
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
