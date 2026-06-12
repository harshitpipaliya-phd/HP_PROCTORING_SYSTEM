---
title: HP Proctoring AI Workers
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: docker
pinned: true
---

# HP Proctoring AI Workers

AI inference worker for the HP Proctoring system. Deployed as a Docker-based FastAPI service on HuggingFace Spaces.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/analyze/video` | POST | Spec-compliant: analyze a video frame (alias for /analyze/frame) |
| `/analyze/frame` | POST | Analyze a video frame for behavior detection |
| `/analyze/audio` | POST | Analyze an audio file |
| `/verify/face` | POST | Verify a live face against enrolled candidate embedding |
| `/health` | GET | Health check endpoint |

## Authentication

All endpoints (except `/health`) require `X-Internal-API-Key` header matching `INTERNAL_API_KEY` env var.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `INTERNAL_API_KEY` | Shared secret for Render ↔ HuggingFace auth |
| `SUPABASE_URL` | Supabase project URL (for face_references lookup) |
| `SUPABASE_KEY` | Supabase service role key |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary account |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `SENTRY_DSN` | Optional Sentry DSN for error tracking |

## Models Used

- **MediaPipe Face Mesh** — Eye tracking, head pose, gaze direction
- **YOLOv8n** — Person and object detection (COCO classes including phone/book)
- **face_recognition (dlib)** — 128-d face embeddings for identity verification

## Notes

- Models are loaded once at startup via `loader.py` singleton (not per-request).
- HuggingFace free tier has cold start (~10–30s). Use paid persistent storage Space to keep models warm.
- The Render API calls this worker via `httpx` with `timeout=5s` and `retries=2`.
- Cold-start 503 errors are handled gracefully — frame is skipped, no risk event fired.
