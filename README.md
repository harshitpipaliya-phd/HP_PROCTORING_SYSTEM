---
title: HP Proctoring Backend
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# HP Proctoring Backend

AI-powered proctoring system: Video AI + Audio Analysis + Screen Monitoring.

## Quick Start

### Local (Docker)
```bash
docker build -t hp-proctoring .
docker run -p 8000:8000 \
  -e SUPABASE_URL=your_url \
  -e SUPABASE_KEY=your_key \
  hp-proctoring
```

### API Docs
- FastAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

### HuggingFace Spaces
This Space runs the FastAPI backend on port 8000.
Set `SUPABASE_URL` and `SUPABASE_KEY` in Space secrets.

## Features
- Video AI: eye tracking, head pose, person/object/phone detection
- Audio: file-based + WebSocket PCM real-time streaming
- Screen: multi-monitor detection, auto-interval screenshots
- Reports: JSON + text + **PDF** (ReportLab)
- HP Competency Model: integrity/focus/discipline mapping
- Cloudinary: screenshot & report upload
- Supabase: full normalized schema + RLS

## Database Setup
Run `database/migrations/001_initial_schema.sql` in your Supabase SQL editor.
