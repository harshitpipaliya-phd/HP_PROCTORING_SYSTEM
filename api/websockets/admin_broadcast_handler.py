"""
api/websockets/admin_broadcast_handler.py
==========================================
WebSocket endpoint for cross-session admin dashboard feed.
Spec: /ws/admin/broadcast
Broadcasts risk/violation events across ALL active sessions.
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any

from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError

from core.config import get_settings


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


async def ws_admin_broadcast_endpoint(websocket: WebSocket):
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

    from api.websockets.dashboard_handler import hub
    await hub.connect(websocket)

    await websocket.send_text(json.dumps({
        "event": "broadcast_connected",
        "user": user_email,
        "message": "Receiving all-session risk updates",
    }))

    try:
        while True:
            await asyncio.sleep(0.5)
            msg = json.dumps({
                "event": "broadcast_tick",
                "ts": datetime.utcnow().isoformat(),
            })
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)
