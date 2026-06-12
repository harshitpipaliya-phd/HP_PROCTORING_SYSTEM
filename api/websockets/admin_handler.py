"""
api/websockets/admin_handler.py
================================
WebSocket endpoint for live admin proctoring feed.
Spec: /ws/admin/{session_id}
Admins receive real-time risk updates and violation alerts for a specific session.
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any

from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError

from core.config import get_settings
from core.session import get_session_by_id
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


async def ws_admin_session_endpoint(websocket: WebSocket, session_id: str):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing JWT token")
        return

    try:
        payload = _verify_ws_jwt(token)
        user_role = payload.get("role", "user")
        if user_role not in ("admin", "superadmin", "proctor"):
            await websocket.close(code=1008, reason=f"Role '{user_role}' not authorized")
            return
        user_email = payload.get("email", "admin")
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        return

    sess = get_session_by_id(session_id)
    if not sess:
        await websocket.close(code=1008, reason="Session not found")
        return

    await websocket.accept()
    await websocket.send_text(json.dumps({
        "event": "admin_connected",
        "session_id": session_id,
        "user": user_email,
    }))

    try:
        while True:
            await asyncio.sleep(0.5)
            status = {
                "event": "admin_tick",
                "session_id": session_id,
                "ts": datetime.utcnow().isoformat(),
                "risk_score": getattr(sess, "risk_score", 0),
                "focus_score": getattr(sess, "focus_score", 100),
                "violations_count": len(getattr(sess, "violations", [])),
                "tab_switches": getattr(sess, "tab_switches", 0),
                "attention_breaks": getattr(sess, "attention_breaks", 0),
                "total_frames": getattr(sess, "total_frames", 0),
                "active": getattr(sess, "_active", False),
            }
            await websocket.send_text(json.dumps(status))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
