"""
api/websockets/stream_video_handler.py
=======================================
WebSocket endpoint for candidate video+audio streaming during proctoring.
Spec: /ws/stream/{session_id}
Accepts base64 JPEG frames + optional PCM audio chunks.
Broadcasts violation events to dashboard hub in real-time.
"""

import json
import base64
import asyncio
import time
from typing import Dict, Any

from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError

from core.config import get_settings
from core.session import get_session_by_id, update_session_risk
from api.websockets.dashboard_handler import broadcast_event


def _verify_ws_jwt(token: str) -> dict:
    settings = get_settings()
    if not settings.JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY not configured")
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_signature": True, "verify_aud": False},
        )
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid JWT: {str(e)}")


async def ws_stream_endpoint(websocket: WebSocket, session_id: str):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing JWT token")
        return

    try:
        payload = _verify_ws_jwt(token)
        user_id = payload.get("sub", "ws_user")
        user_role = payload.get("role", "user")
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        return

    sess = _validate_session_and_role(session_id, user_id, user_role)

    await websocket.accept()
    await websocket.send_text(json.dumps({
        "event": "connected",
        "session_id": session_id,
        "message": "Stream WebSocket ready. Send JSON: {frame_b64, audio_b64?, timestamp?}",
    }))

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            await _handle_stream_message(websocket, session_id, user_id, msg, sess)
    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({"event": "error", "message": "Invalid JSON"}))
    except Exception as e:
        await websocket.send_text(json.dumps({"event": "error", "message": str(e)}))


def _validate_session_and_role(session_id: str, user_id: str, role: str):
    from core.session import get_session_by_id
    sess = get_session_by_id(session_id)
    if not sess:
        raise ValueError("Session not found or expired")
    if role not in ("superadmin", "admin", "proctor"):
        if sess.user_id != user_id:
            raise ValueError("Not authorized for this session")
    return sess


async def _handle_stream_message(websocket: WebSocket, session_id: str, user_id: str, msg: Dict, sess):
    frame_b64 = msg.get("frame_b64")
    timestamp = msg.get("timestamp", time.time())

    if not frame_b64:
        await websocket.send_text(json.dumps({"event": "error", "message": "Missing frame_b64"}))
        return

    try:
        frame_bytes = base64.b64decode(frame_b64)
    except Exception:
        await websocket.send_text(json.dumps({"event": "error", "message": "Invalid base64 frame"}))
        return

    import numpy as np
    import cv2 as _cv2
    np_arr = np.frombuffer(frame_bytes, np.uint8)
    frame = _cv2.imdecode(np_arr, _cv2.IMREAD_COLOR)
    if frame is None:
        await websocket.send_text(json.dumps({"event": "error", "message": "Frame decode failed"}))
        return

    from video_ai.processor import analyze_frame
    _, result = analyze_frame(frame)

    risk_score = result.get("risk_score", 0)
    flags = result.get("risk_flags", [])
    violations = result.get("events", [])

    update_session_risk(risk_score, flags)
    for v in violations:
        vtype = v.get("type", "unknown")
        if sess:
            sess.add_violation(vtype, v)
    _broadcast_violations(session_id, violations, risk_score)

    response = {
        "event": "frame_processed",
        "session_id": session_id,
        "timestamp": timestamp,
        "risk_score": risk_score,
        "risk_flags": flags,
        "focus_score": result.get("focus_score", 100),
    }
    await websocket.send_text(json.dumps(response))


def _broadcast_violations(session_id: str, violations: list, risk_score: int):
    payload = {
        "event": "violation_update",
        "session_id": session_id,
        "risk_score": risk_score,
        "new_violations": violations,
        "count": len(violations),
    }
    asyncio.ensure_future(broadcast_event(payload))
