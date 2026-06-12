# HP Proctoring Backend — Full Bug Report & Fixes

**Analysis Date:** June 9, 2026  
**Files Reviewed:** 20+ Python files across 5 modules  
**Total Bugs Found:** 13 bugs + 2 missing features

---

## Summary Table

| # | File | Bug Type | Severity | Status |
|---|------|----------|----------|--------|
| 1 | `video_ai/risk_engine.py` | `NameError`: `status` used before assignment | 🔴 Critical | ✅ Fixed |
| 2 | `api.py` | Wrong RGB→BGR colour conversion | 🔴 Critical | ✅ Fixed |
| 3 | `api.py` | `tempfile` suffix includes full filename, not just extension | 🟠 High | ✅ Fixed |
| 4 | `api.py` | Audio MIME check rejects valid `application/octet-stream` | 🟠 High | ✅ Fixed |
| 5 | `api.py` | `start_session()` called with positional args (ambiguous) | 🟡 Medium | ✅ Fixed |
| 6 | `app.py` | `st.image(width='stretch')` — invalid Streamlit parameter | 🔴 Critical | ✅ Fixed |
| 7 | `app.py` | `tempfile` suffix is full filename, not extension | 🟠 High | ✅ Fixed |
| 8 | `video_ai/processor.py` | `result["success"]` key never set, but checked by `app.py` | 🟠 High | ✅ Fixed |
| 9 | `video_ai/processor.py` | `_error_payload()` returns nested `data` dict instead of flat structure | 🟠 High | ✅ Fixed |
| 10 | `video_ai/object_detection.py` | COCO class 67 (`cell phone`) missing from detection classes | 🔴 Critical | ✅ Fixed |
| 11 | `video_ai/object_detection.py` | COCO class 84 (`book`) missing from detection classes | 🔴 Critical | ✅ Fixed |
| 12 | `database/queries.py` | `datetime.utcnow()` deprecated (Python 3.12+) | 🟡 Medium | ✅ Fixed |
| 13 | `screen_monitoring/*.py` | `datetime.utcnow()` deprecated (Python 3.12+) | 🟡 Medium | ✅ Fixed |
| 14 | `audio_proctoring/trainer.py` | Meta file saved as `audio_classifier_meta.json` but config expects `model_meta.json` | 🟠 High | ✅ Fixed |
| 15 | `.vscode/` | Missing VS Code launch & settings config | ℹ️ Dev QoL | ✅ Added |

---

## Detailed Bug Descriptions

---

### Bug 1 — `NameError` in `risk_engine.py:get_ai_verdict()` 🔴 CRITICAL

**File:** `video_ai/risk_engine.py`  
**Line:** ~46

**Problem:**
```python
def get_ai_verdict(risk_score: int = None, focus_score: int = None) -> str:
    from core.session import get_session_status

    if risk_score is None:
        status = get_session_status()      # status assigned here
        risk_score = status.get("risk_score", 0)

    if focus_score is None:
        focus_score = status.get("focus_score", 100)  # ❌ NameError if risk_score was provided!
```
When `risk_score` is passed explicitly but `focus_score` is `None`, `status` is never assigned, causing `NameError: name 'status' is not defined`.

**Fix:**
```python
if risk_score is None or focus_score is None:
    status = get_session_status()
    if risk_score is None:
        risk_score = status.get("risk_score", 0)
    if focus_score is None:
        focus_score = status.get("focus_score", 100)
```

---

### Bug 2 — Wrong BGR Colour Conversion in `api.py` 🔴 CRITICAL

**File:** `api.py`  
**Line:** ~215

**Problem:**
```python
if len(image.shape) == 3 and image.shape[2] == 3:
    # Assume RGB, convert to BGR
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)   # ❌ Always runs!
```
`cv2.imdecode()` **always** returns BGR. Converting BGR→BGR via `COLOR_RGB2BGR` swaps the red and blue channels on every frame, making all colour-based detection wrong.

**Fix:** Remove the forced conversion entirely. The comment is also incorrect.

---

### Bug 3 — Wrong `tempfile` Suffix in `api.py` 🟠 HIGH

**File:** `api.py`  
**Line:** ~247

**Problem:**
```python
with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename or ".audio") as tmp:
```
`file.filename` is e.g. `"speech_test.wav"`. Using that as the `suffix` creates a temp file like `/tmp/tmpXXXXspeech_test.wav` — this is a full filename, not an extension suffix. On some OS the `.wav` extension is then mangled.

**Fix:**
```python
_ext = os.path.splitext(file.filename or "upload.audio")[1] or ".audio"
with tempfile.NamedTemporaryFile(delete=False, suffix=_ext) as tmp:
```

---

### Bug 4 — Audio MIME Type Check Too Strict in `api.py` 🟠 HIGH

**File:** `api.py`  
**Line:** ~244

**Problem:**
```python
allowed_types = ["audio/wav", "audio/mpeg", "audio/mp3", ..., "application/octet-stream"]
if not any(t in content_type.lower() for t in ["audio", "wav", "mp3", "flac", "ogg"]):
    raise HTTPException(400, ...)
```
`"application/octet-stream"` is in `allowed_types` but the actual check does not include `"octet-stream"` in the pattern list. So `application/octet-stream` (the most common MIME type for uploaded files via mobile apps/curl) is rejected.

**Fix:** Also check the file extension as a fallback.

---

### Bug 5 — `start_session()` Positional Argument Ambiguity in `api.py` 🟡 MEDIUM

**File:** `api.py`, `app.py`

**Problem:**
```python
sid = start_session(body.session_id, body.user_id)
```
The signature is `start_session(session_id=None, user_id="default_user")`. This works now but is fragile — if parameter order changes, it silently breaks (user_id treated as session_id).

**Fix:** Use keyword arguments:
```python
sid = start_session(session_id=body.session_id, user_id=body.user_id)
```

---

### Bug 6 — Invalid `st.image()` Parameter in `app.py` 🔴 CRITICAL

**File:** `app.py`  
**Lines:** ~97, ~272

**Problem:**
```python
st.image(output_frame, channels="BGR", width='stretch')
```
`width` expects an **integer** (pixels) in Streamlit, not the string `'stretch'`. This raises a `StreamlitAPIException` at runtime, crashing the entire Video AI tab.

**Fix:**
```python
st.image(output_frame, channels="BGR", use_container_width=True)
```

---

### Bug 7 — `tempfile` Suffix Bug in `app.py` 🟠 HIGH

**File:** `app.py`  
**Line:** ~167

Same root cause as Bug 3. `audio_file.name` is the full filename from the upload widget.

**Fix:** Use `os.path.splitext(audio_file.name)[1]`.

---

### Bug 8 — Missing `success` Key in `analyze_frame()` Result 🟠 HIGH

**File:** `video_ai/processor.py`

**Problem:**
`app.py` checks `results.get("success", True)` but `analyze_frame()` never sets `result["success"]`. This means the check always defaults to `True` (via the fallback), which is fine for now — but if `_error_payload()` is returned, `app.py` never detects the failure because `_error_payload` also had the wrong structure (Bug 9).

**Fix:** Set `"success": True` in the initial result dict.

---

### Bug 9 — `_error_payload()` Returns Wrong Structure 🟠 HIGH

**File:** `video_ai/processor.py`

**Problem:**
```python
def _error_payload(msg):
    return {
        "success": False,
        "data": {             # ❌ Nested under "data"
            "risk_score": 0,
            ...
        }
    }
```
`app.py` reads `result.get("risk_score", 0)` directly (top level), not `result["data"]["risk_score"]`. When `_error_payload()` is returned, every data access in the UI silently returns the default value, hiding the error.

**Fix:** Return a flat structure matching the normal result shape.

---

### Bug 10 & 11 — COCO Class IDs Missing for Phone & Book Detection 🔴 CRITICAL

**File:** `video_ai/object_detection.py`

**Problem:**
```python
_COCO_CLASSES = {0: "person", 72: "laptop", 73: "remote", 74: "keyboard"}
_PROHIBITED_CLASSES = {72, 73, 74}
```
COCO class **67** is `"cell phone"` and class **84** is `"book"`. Both are missing. This means YOLOv8's class-ID-based detection **never** triggers for phones or books — only the label string match fallback works, which is less reliable.

**Fix:**
```python
_COCO_CLASSES = {
    0: "person", 63: "laptop", 67: "cell phone",
    72: "laptop", 73: "remote", 74: "keyboard", 84: "book"
}
_PROHIBITED_CLASSES = {63, 67, 72, 73, 74, 84}
```

---

### Bug 12 — `datetime.utcnow()` Deprecated in `database/queries.py` 🟡 MEDIUM

**File:** `database/queries.py`

`datetime.utcnow()` is deprecated since Python 3.12 and raises `DeprecationWarning`. Should use `datetime.now(timezone.utc)`.

---

### Bug 13 — `datetime.utcnow()` Deprecated in `screen_monitoring/*.py` 🟡 MEDIUM

**Files:** `capture.py`, `watcher.py`, `detector.py`

Same as Bug 12.

---

### Bug 14 — Trainer Saves Wrong Meta Filename 🟠 HIGH

**File:** `audio_proctoring/trainer.py`

**Problem:**
```python
meta_path = output_path.replace(".pkl", "_meta.json")
# → "models/audio_classifier_meta.json"
```
But `core/config.py` sets:
```python
MODEL_META_PATH: str = "models/model_meta.json"
```
The classifier tries to load `model_meta.json` but trainer saves `audio_classifier_meta.json`. The model metadata is never found at runtime.

**Fix:**
```python
meta_path = os.path.join(os.path.dirname(output_path), "model_meta.json")
```

---

## VS Code Setup (Added)

`.vscode/launch.json` — Three launch configurations:
- **Run Streamlit App** (`app.py` on port 8501)
- **Run FastAPI** (`api.py` via uvicorn on port 8000 with `--reload`)
- **Train Audio Model** (trainer script)

`.vscode/settings.json` — Python interpreter, linting, formatting, file exclusions.

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in env vars
cp .env.example .env
# Edit .env: add SUPABASE_URL and SUPABASE_KEY if using DB

# 3a. Run Streamlit UI
streamlit run app.py

# 3b. Run FastAPI backend
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 4. (Optional) Train audio model
python audio_proctoring/trainer.py
```
