# TODO — HP Proctoring System (v2.0.0)

## Phase 1 — Critical Bug Fixes ✅ COMPLETE

- [x] BUG-1: NameError in `video_ai/risk_engine.py:get_ai_verdict()`
- [x] BUG-2: Wrong RGB→BGR color conversion in `api.py`
- [x] BUG-3: Wrong `tempfile` suffix in `api.py`
- [x] BUG-4: Audio MIME check too strict in `api.py`
- [x] BUG-5: `start_session()` positional argument ambiguity
- [x] BUG-6: Invalid `st.image(width='stretch')` in `app.py`
- [x] BUG-7: `tempfile` suffix bug in `app.py`
- [x] BUG-8: Missing `success` key in `analyze_frame()` result
- [x] BUG-9: `_error_payload()` wrong nested structure
- [x] BUG-10: COCO class 67 (cell phone) missing
- [x] BUG-11: COCO class 84 (book) missing
- [x] BUG-12: `datetime.utcnow()` deprecated in `database/queries.py`
- [x] BUG-13: `datetime.utcnow()` deprecated in `screen_monitoring/*.py`
- [x] BUG-14: Trainer saves wrong meta filename
- [x] BUG-15: Missing `.vscode/` config files

## Phase 2 — Production Readiness ✅ COMPLETE (this release)

- [x] C1: Fix NameError in `/health` endpoint (import datetime as _dt)
- [x] C2: Enable pgvector extension + `vector(128)` for face_references
- [x] C3-C5: Add missing packages to requirements.txt (pydantic-settings, sqlalchemy, alembic, asyncpg, face-recognition, dlib, structlog, sentry-sdk)
- [x] H1: Initialize Alembic migration system (`alembic/` + first revision)
- [x] H2: Register `/verify/face` route in `ai_workers/app.py`
- [x] H3: Wire 30s screenshot interval in `core/session.py`
- [x] H4: Implement 10-min re-verification background loop
- [x] H5: Ensure Redis→PostgreSQL risk score flush runs every 10s
- [x] H6: Add structlog initialization to `api/main.py`
- [x] H7: Add Sentry SDK initialization (gated on SENTRY_DSN)
- [x] Rename `/analyze/frame` → add spec-compliant `/analyze/video` alias
- [x] Fix `ai_workers/README.md`: change `sdk: gradio` → `sdk: docker`
- [x] Merge `media_storage.py` + `media_store.py` into single canonical service
- [x] Add backward-compat shim for `media_store.py` imports

## Phase 3 — Testing ✅ IMPROVED

- [x] Fix integration test failure (datetime NameError in /health)
- [x] Add `tests/unit/test_media_storage.py`
- [x] Add `tests/unit/test_risk_engine_service.py` (spec compliance)
- [x] Add `tests/unit/test_face_verification.py` (cosine similarity)
- [x] Add `tests/integration/test_ai_worker_routes.py` (/verify/face, /analyze/video)

## Remaining / Future Work

- [ ] Install face-recognition + dlib in production (needs cmake in build)
- [ ] speechbrain VAD: replace scikit-learn audio classifier with speechbrain (spec preferred)
- [ ] Python 3.10 pin: add `python_requires = ">=3.10,<3.13"` to pyproject.toml
- [ ] factory-boy integration tests for candidate/session CRUD
- [ ] CI: run `ruff check .` in `.github/workflows/ci.yml`
