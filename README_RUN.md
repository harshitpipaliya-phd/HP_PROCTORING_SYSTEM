# HP Proctoring System — Run Guide (v2.0.0)

## Prerequisites

- Python 3.10+ (tested on 3.10 and 3.12)
- Redis (optional — in-memory fallback available)
- Supabase account (optional — app works without DB)
- Cloudinary account (optional — local storage fallback)

---

## 1. Quick Start

```bash
# 1. Clone / unzip project
cd hp_proctoring

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# Optional: AI-heavy packages (face-recognition requires cmake)
# pip install face-recognition dlib  # needs cmake + C++ build tools

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set INTERNAL_API_KEY

# 5a. Run FastAPI backend
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 5b. Run Streamlit UI (separate terminal)
streamlit run app.py

# 5c. Run AI workers (separate terminal, optional)
uvicorn ai_workers.app:app --host 0.0.0.0 --port 8001 --reload

# 5d. Run Celery worker (requires Redis)
celery -A workers.celery_app worker --loglevel=info
```

---

## 2. VS Code (Recommended)

Open the project folder in VS Code. Launch configurations are pre-configured in `.vscode/launch.json`:

- **Run FastAPI (Render)** → starts API on port 8000
- **Run Streamlit UI** → starts UI on port 8501
- **Run AI Workers** → starts AI worker on port 8001
- **Run Celery Worker** → starts background task processor
- **Run Pytest** → runs full test suite

---

## 3. Database Setup (Supabase)

1. Create a Supabase project at https://supabase.com
2. Go to **SQL Editor** and run `database/migrations/001_initial_schema.sql`
3. Enable pgvector: Dashboard → Database → Extensions → search "vector" → Enable
4. Copy your project URL and service role key to `.env`

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
```

### Alembic (for schema version control)

```bash
# Run migrations
alembic -c alembic.ini upgrade head

# Create a new migration after model changes
alembic -c alembic.ini revision --autogenerate -m "describe_change"
```

---

## 4. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Optional | Supabase project URL |
| `SUPABASE_KEY` | Optional | Supabase service role key |
| `INTERNAL_API_KEY` | Required | Shared secret for Render↔HF auth |
| `JWT_SECRET_KEY` | Required | JWT signing secret |
| `REDIS_URL` | Optional | Redis connection string |
| `AI_WORKER_URL` | Optional | HuggingFace Space URL |
| `CLOUDINARY_CLOUD_NAME` | Optional | Cloudinary account |
| `CLOUDINARY_API_KEY` | Optional | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Optional | Cloudinary API secret |
| `SENTRY_DSN` | Optional | Sentry DSN for error tracking |
| `HP_WEBHOOK_SECRET` | Optional | HMAC secret for HP webhook |

---

## 5. Deployment

### Render (API + Worker)

```bash
# Push code; render.yaml defines 3 services:
# - proctoring-api (web)
# - proctoring-worker (background)
# - proctoring-redis (Redis)
```

Set all env vars in Render Dashboard → Service → Environment.

### HuggingFace Spaces (AI Workers)

1. Create a new Space with **SDK: Docker**
2. Push `ai_workers/` folder contents
3. Set `INTERNAL_API_KEY` and Supabase credentials as Space Secrets
4. Copy the Space URL to `AI_WORKER_URL` on Render

---

## 6. Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only  
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=api --cov=core --cov=video_ai --cov-report=term-missing
```

---

## 7. Architecture Diagram

```
Candidate Browser (WebRTC)
        │
        ▼ WS /ws/stream/{session_id}
FastAPI (Render) ─── httpx ──→ AI Workers (HuggingFace Spaces)
        │                           • /analyze/video
        │                           • /analyze/audio
        │                           • /verify/face
        ▼
  Redis Streams ──→ Celery Workers
        │                 │
        │          generate_report
        │          process_frame
        ▼          cleanup
  Supabase (PostgreSQL + pgvector)
        │
        ▼
  Cloudinary (media evidence)
        │
        ▼
  HP Webhook (behavior_flags)
```
