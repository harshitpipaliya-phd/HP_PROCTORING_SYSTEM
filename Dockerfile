# HP Proctoring Backend - Production Dockerfile

# ============================================

# -------------------------

# Stage 1 - Builder

# -------------------------

FROM python:3.10-slim AS builder

WORKDIR /build

# Install build dependencies

RUN apt-get update && apt-get install -y --no-install-recommends 
build-essential 
gcc 
g++ 
cmake 
python3-dev 
libgl1 
libglib2.0-0 
libsm6 
libxext6 
libxrender1 
libgomp1 
curl 
&& rm -rf /var/lib/apt/lists/*

# Copy requirements

COPY requirements.txt .
COPY requirements_ai.txt* ./

# Upgrade pip

RUN pip install --upgrade pip setuptools wheel

# Install dependencies

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Install AI dependencies if available

RUN if [ -f requirements_ai.txt ]; then 
pip install --prefix=/install --no-cache-dir -r requirements_ai.txt; 
fi

# -------------------------

# Stage 2 - Runtime

# -------------------------

FROM python:3.10-slim AS runtime

WORKDIR /app

# Install runtime dependencies

RUN apt-get update && apt-get install -y --no-install-recommends 
build-essential 
gcc 
g++ 
cmake 
python3-dev 
libgl1 
libglib2.0-0 
libsm6 
libxext6 
libxrender1 
libgomp1 
curl 
&& rm -rf /var/lib/apt/lists/*

# Copy installed packages

COPY --from=builder /install /usr/local

# Copy app source

COPY . .

# Create required folders

RUN mkdir -p 
static/screenshots 
static/reports 
logs 
models

# Create non-root user

RUN useradd -m -u 1000 appuser && 
chown -R appuser:appuser /app

USER appuser

# Expose backend port

EXPOSE 8000

# Health check

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 
CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI app

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
