# HP Proctoring — All Fixes Applied

## Critical Code Fixes

### Fix 1 — Redis TTL Never Applied (video_ai/risk_engine.py)
The `ttl` parameter was accepted but never passed to Redis.  
Now calls `r.expire(key, ttl)` after every `incrby`.

### Fix 2 — Candidate ID Mapping Bug (video_ai/risk_engine.py)
Webhook payload was sending `report.get("user_id")` as `candidate_id`.  
Fixed to `report.get("candidate_id")`.

### Fix 3 — Unused settings Import (video_ai/risk_engine.py)
`from core.config import get_settings; settings = get_settings()` was imported
inside `upload_report_to_cloudinary()` but `settings` was never used.  
Removed.

### Fix 4 — Metrics Missing risk_score/focus_score (video_ai/risk_engine.py)
`generate_report()` metrics dict now includes `risk_score` and `focus_score`
as required by the spec.

### Fix 5 — generate_report() Not Safe Against None (video_ai/risk_engine.py)
Added `session_state = session_state or {}` and int-coercion guards at the top.

### Fix 6 — Risk Level Thresholds Misaligned (core/session.py)
`to_summary()` was using HIGH≥70 / MEDIUM≥40.  
Fixed to HIGH≥80 / MEDIUM≥50 / LOW≥25 / MINIMAL (matches spec §6.2 and risk_engine.py).

### Fix 7 — COCO Class IDs Missing (video_ai/object_detection.py) — Already Fixed
Cell phone (67) and book (84) were missing from `_COCO_CLASSES` and `_PROHIBITED_CLASSES`.

### Fix 8 — NameError in get_ai_verdict (video_ai/risk_engine.py) — Already Fixed
`status` variable referenced before assignment when risk_score was provided but focus_score was None.

### Fix 9 — _error_payload Wrong Structure (video_ai/processor.py) — Already Fixed
Changed from nested `{"data": {...}}` to flat structure matching normal result.

### Fix 10 — Invalid st.image() Parameter (app.py) — Already Fixed
`width='stretch'` → `use_container_width=True`.

### Fix 11 — tempfile Suffix Bug (app.py) — Already Fixed
`suffix=audio_file.name` → `suffix=os.path.splitext(audio_file.name)[1]`.

### Fix 12 — BGR Color Conversion Bug (api/main.py) — Already Fixed
Removed forced `cv2.cvtColor(image, cv2.COLOR_RGB2BGR)` after `cv2.imdecode` (which always returns BGR).

### Fix 13 — Audio MIME Type Rejects octet-stream (api/main.py) — Already Fixed
Added extension-based fallback check alongside MIME type.

### Fix 14 — trainer.py Saves Wrong Meta Filename — Already Fixed
Was: `audio_classifier_meta.json`. Fixed to: `model_meta.json` (matches config.py).

### Fix 15 — datetime.utcnow() Deprecated — Already Fixed
All files now use `datetime.now(timezone.utc)`.

### Fix 16 — FaceAnalyzer Class Missing (ai_workers/models/face_analyzer.py) — Already Fixed
Added complete `FaceAnalyzer` class with 3-tier fallback: face_recognition → MediaPipe → OpenCV Haar.

### Fix 17 — SpeechBrain VAD Not Implemented (audio_proctoring/vad.py) — Already Fixed
Full `SpeechBrainVAD` + `SignalVAD` fallback implemented.

## Security Fixes

### Fix 18 — Real Credentials Exposed in .env
All real Supabase, JWT, Cloudinary, and webhook secrets replaced with labeled placeholders.  
`.env.example` updated to match.  
`.gitignore` already blocks `.env`.

## Infrastructure Fixes

### Fix 19 — cmake Missing from Main Dockerfile
Added cmake, libboost-python-dev, libboost-thread-dev, libopenblas-dev, liblapack-dev  
to the builder stage so dlib compiles inside Docker.

### Fix 20 — Celery Worker Missing from render.yaml — Already Fixed
Added `hp-proctoring-celery-worker` (type: worker) and `hp-proctoring-celery-beat`.

## Root Cause of Installation Failure

The `ERROR: Operation cancelled by user` you saw is NOT a code bug.
It means you pressed Ctrl+C (or closed the terminal) while pip was installing dlib.

The actual requirement conflict is:
- Your machine: Python 3.12
- Project requirement: Python 3.10

**Solution:** Install Python 3.10 and create a new venv with `py -3.10 -m venv venv`.  
See SETUP.md for complete instructions.
