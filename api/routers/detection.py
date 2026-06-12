"""
api/routers/detection.py
========================
Video, audio, and screen detection endpoints.
Original: api.py lines 227–358
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Depends
from fastapi.responses import PlainTextResponse
import base64
import numpy as np
import cv2
import tempfile
import os
from datetime import datetime

from video_ai.processor import analyze_frame
from video_ai.risk_engine import generate_report, generate_report_text, get_ai_verdict, get_violation_summary
from audio_proctoring.stream import analyze_audio_file
from screen_monitoring.capture import capture_all_monitors, is_screen_capture_available
from screen_monitoring.watcher import get_monitor_watcher
from screen_monitoring.detector import detect_monitors
from core.session import get_current_session, update_session_risk, record_tab_switch, get_session_status
from database import log_event, log_audio_event, log_behavior_event
from api.core.dependencies import get_current_user

from api.schemas.detection import (
    VideoDetectRequest, TabSwitchRequest, AudioDetectRequest,
    AutoScreenshotRequest,
)

router = APIRouter(prefix="/v1/detect", tags=["Detection"])

_SKIP_LOG = {
    "session_stopped", "stop_reason", "session_active", "stopped",
    "violations", "total_frames", "session_id", "face_locations",
    "fps", "risk_score", "focus_score", "ai_verdict",
    "annotated_frame", "evidence",
}


@router.post("/video")
def api_detect_video(
    body: VideoDetectRequest,
    user: dict = Depends(get_current_user)
):
    session = get_current_session()
    if not session or not getattr(session, "_active", False):
        raise HTTPException(400, "No active session. Call POST /session/start first.")
    try:
        img_bytes = base64.b64decode(body.image_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(422, "Image decode failed")
    except Exception as e:
        raise HTTPException(422, f"Image decode error: {e}")

    _, result = analyze_frame(image)
    for k, v in result.items():
        if k not in _SKIP_LOG and not k.startswith("_"):
            try:
                log_event(body.user_id, k, str(v)[:200])
            except Exception:
                pass

    update_session_risk(result.get("risk_score", 0), result.get("risk_flags", []))
    try:
        log_behavior_event(result)
    except Exception:
        pass

    result.pop("annotated_frame", None)
    result.pop("evidence", None)
    return {"success": True, "session_id": session.session_id,
            "timestamp": datetime.now().isoformat(), "data": result}


@router.post("/audio")
async def api_detect_audio(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    session = get_current_session()
    if not session or not getattr(session, "_active", False):
        raise HTTPException(400, "No active session. Call POST /session/start first.")

    content_type = (file.content_type or "").lower()
    fname = (file.filename or "").lower()
    _AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac")
    _AUDIO_MIMES = ("audio", "wav", "mp3", "flac", "ogg", "octet-stream")
    mime_ok = any(t in content_type for t in _AUDIO_MIMES)
    ext_ok = any(fname.endswith(e) for e in _AUDIO_EXTS)
    if not (mime_ok or ext_ok):
        raise HTTPException(400, f"Unsupported file type: {content_type} / {fname}")

    _ext = os.path.splitext(file.filename or "upload.audio")[1] or ".audio"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=_ext) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        result = analyze_audio_file(tmp_path, user.get("user_id", "api_user"))
        try:
            log_audio_event(result)
        except Exception:
            pass

        update_session_risk(
            int(result.get("total_risk", 0)),
            [f"AUDIO_{result.get('risk_level','LOW')}"]
        )
        return {"success": True, "session_id": session.session_id,
                "timestamp": datetime.now().isoformat(), "data": result}
    except Exception as e:
        raise HTTPException(500, f"Audio analysis failed: {e}")
    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


screen_router = APIRouter(prefix="/capture", tags=["Screen"])


@screen_router.post("/screens")
def api_capture_screens(user: dict = Depends(get_current_user)):
    if not is_screen_capture_available():
        return {"success": False,
                "message": "Screen capture not available", "screenshots": []}
    shots = capture_all_monitors()
    return {"success": True, "timestamp": datetime.now().isoformat(),
            "count": len(shots), "screenshots": shots}


@screen_router.post("/screens/auto/start")
def api_auto_screenshot_start(
    req: AutoScreenshotRequest,
    user: dict = Depends(get_current_user)
):
    watcher = get_monitor_watcher()
    status = get_session_status()
    watcher.start_auto_screenshots(
        interval_seconds=req.interval_seconds,
        upload_cloudinary=req.upload_cloudinary,
        session_id=status.get("session_id"),
    )
    return {"success": True, "interval_seconds": req.interval_seconds}


@screen_router.post("/screens/auto/stop")
def api_auto_screenshot_stop(user: dict = Depends(get_current_user)):
    get_monitor_watcher().stop_auto_screenshots()
    return {"success": True, "message": "Auto-screenshot stopped"}


router.include_router(screen_router)
