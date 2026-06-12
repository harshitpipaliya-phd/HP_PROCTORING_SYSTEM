# HP Proctoring Backend — Complete Setup Guide

## Prerequisites

### Python Version (CRITICAL)
```
Python 3.10.x  ← REQUIRED
```
This project requires Python 3.10. `dlib` and `face-recognition` do NOT build on Python 3.12.

**Download Python 3.10.11:**  
https://www.python.org/downloads/release/python-31011/

### Visual Studio Build Tools (Windows — for dlib)
Required to compile `dlib` from source on Windows.
Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/

During installation, select:
- Desktop development with C++
- MSVC Compiler
- Windows 10/11 SDK
- CMake tools for Windows

---

## Local Setup (Windows)

```powershell
# 1. Create venv with Python 3.10 specifically
py -3.10 -m venv venv

# 2. Activate it
venv\Scripts\activate

# 3. Upgrade pip
python -m pip install --upgrade pip

# 4. Install dependencies
pip install -r requirements.txt
```

If dlib fails to build:
```powershell
# Install pre-built dlib wheel first, then requirements
pip install dlib==19.24.2 --find-links https://github.com/jloh02/dlib/releases
pip install face-recognition==1.3.0
pip install -r requirements.txt
```

---

## Local Setup (Linux/macOS)

```bash
# Install system deps (Ubuntu/Debian)
sudo apt-get install -y cmake build-essential libopenblas-dev liblapack-dev \
    libgl1-mesa-glx libglib2.0-0 libboost-python-dev libboost-thread-dev

# Create and activate venv
python3.10 -m venv venv
source venv/bin/activate

# Install
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Environment Variables

```bash
cp .env.example .env
# Open .env and fill in ALL placeholder values
```

Required values to set:
- `SUPABASE_URL` — your Supabase project URL
- `SUPABASE_KEY` — your Supabase service role key
- `JWT_SECRET_KEY` — generate: `python -c "import secrets; print(secrets.token_hex(32))"`
- `INTERNAL_API_KEY` — generate: `python -c "import secrets; print(secrets.token_hex(32))"`
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` — from Cloudinary dashboard

---

## Running

```bash
# Streamlit UI
streamlit run app.py

# FastAPI backend (separate terminal)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# AI worker (separate terminal, optional)
uvicorn ai_workers.app:app --host 0.0.0.0 --port 8001 --reload

# Train audio model (one-time)
python audio_proctoring/trainer.py

# Database migrations
alembic upgrade head
```

---

## Docker (Production)

```bash
# Build
docker build -t hp-proctoring .

# Run
docker run -p 8000:8000 --env-file .env hp-proctoring
```

---

## Troubleshooting

### dlib fails to install
→ You need Python 3.10 + cmake + VS Build Tools (Windows) or build-essential (Linux)  
→ The system gracefully falls back to MediaPipe face detection if dlib is unavailable

### `ERROR: Operation cancelled by user`
→ You pressed Ctrl+C during installation. Run `pip install -r requirements.txt` again.

### `ModuleNotFoundError: No module named 'cv2'`
→ Install: `pip install opencv-python-headless`

### Redis connection refused
→ The app works without Redis (falls back to in-memory). To run Redis locally:  
  `docker run -p 6379:6379 redis:7-alpine`

### Supabase errors on startup
→ Check your SUPABASE_URL and SUPABASE_KEY in .env. The app degrades gracefully without DB.
