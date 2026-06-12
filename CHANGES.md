# Changelog — v2.0.0 (Production Final)

## Bug Fixes (All 15 from BUG_REPORT.md)

### Critical Fixes
- **[BUG-1]** `video_ai/risk_engine.py` — `get_ai_verdict()` now fetches `status` once if
  either `risk_score` or `focus_score` is `None`, preventing `NameError`.
- **[BUG-2]** `api.py` — Removed forced `cv2.COLOR_RGB2BGR` conversion. `cv2.imdecode`
  always returns BGR; the conversion was swapping channels on every frame.
- **[BUG-6]** `app.py` — `st.image(width='stretch')` → `st.image(use_container_width=True)`.
  The old parameter caused `StreamlitAPIException` crashing the Video tab.
- **[BUG-10]** `video_ai/object_detection.py` — Added COCO class 67 (`cell phone`) to
  `_COCO_CLASSES` and `_PROHIBITED_CLASSES`. Phone detection was never triggering via class ID.
- **[BUG-11]** `video_ai/object_detection.py` — Added COCO class 84 (`book`) to
  `_COCO_CLASSES` and `_PROHIBITED_CLASSES`. Book detection was never triggering via class ID.

### High Severity Fixes
- **[BUG-3]** `api.py` — `tempfile.NamedTemporaryFile(suffix=file.filename)` → now uses
  `os.path.splitext(file.filename)[1]` for correct extension-only suffix.
- **[BUG-4]** `api.py` — Audio MIME check now also accepts `application/octet-stream` by
  including an extension-based fallback check.
- **[BUG-7]** `app.py` — Same tempfile suffix fix as BUG-3 applied to Streamlit upload handler.
- **[BUG-8]** `video_ai/processor.py` — Added `"success": True` to the initial result dict
  so `app.py`'s `results.get("success", True)` check has a real value.
- **[BUG-9]** `video_ai/processor.py` — `_error_payload()` now returns a flat structure
  matching the normal result shape (not nested under `"data":`).
- **[BUG-14]** `audio_proctoring/trainer.py` — Trainer now saves metadata to
  `models/model_meta.json` (matching `core/config.py`), not `audio_classifier_meta.json`.

### Medium Severity Fixes
- **[BUG-5]** `api.py` + `app.py` — `start_session(sid, uid)` → `start_session(session_id=sid, user_id=uid)`.
  Keyword arguments prevent silent positional breakage if signature changes.
- **[BUG-12]** `database/queries.py` — `datetime.utcnow()` → `datetime.now(timezone.utc)`.
  Fixes `DeprecationWarning` on Python 3.12+.
- **[BUG-13]** `screen_monitoring/capture.py`, `watcher.py`, `detector.py` — Same timezone fix.
- **[BUG-15]** `.vscode/launch.json` + `settings.json` — Added launch configurations for
  Streamlit UI, FastAPI, and audio model trainer.

## New Features in v2.0.0

### UI (app.py)
- Sidebar with live risk score gauge, session timer, auto-refresh toggle
- High-risk alert banners at top of page (risk ≥ 40 or ≥ 70)
- Live event ticker showing last 6 events with color coding
- Risk score progress bars in breakdown panel
- Analytics tab with risk timeline chart and attention chart
- Evidence filter slider by minimum risk score
- Evidence manifest JSON download
- Session CSV and JSON export buttons
- System tab shows full feature matrix and startup guide
- Graceful import fallback — UI never crashes on missing dependencies

### API (api.py)
- Added `/stats` endpoint for aggregated risk statistics
- `/report/text` now uses `PlainTextResponse` for proper content-type
- Added `Query()` parameters with bounds validation on limit params
- Improved error messages throughout
- Added `risk_flags` to `/session/status` response
- Added `started_at` to `/session/start` response
