FROM python:3.10-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
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

COPY requirements.txt .
COPY requirements_ai.txt* ./

RUN pip install --upgrade pip setuptools wheel

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

RUN if [ -f requirements_ai.txt ]; then 
pip install --prefix=/install --no-cache-dir -r requirements_ai.txt; 
fi

FROM python:3.10-slim AS runtime

WORKDIR /app

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

COPY --from=builder /install /usr/local

COPY . .

RUN mkdir -p static/screenshots static/reports logs models

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
