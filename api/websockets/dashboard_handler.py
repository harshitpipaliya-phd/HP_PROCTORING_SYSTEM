"""
api/websockets/dashboard_handler.py
====================================
Real-time dashboard WebSocket handler.
Broadcasts live risk/flags/risk_score updates to connected dashboard clients.
"""

import json
import asyncio
from datetime import datetime
from typing import List, Dict
from fastapi import WebSocket
from jose import jwt, JWTError


def _verify_dashboard_jwt(token: str) -> dict:
    """Verify JWT token for dashboard access."""
    from core.config import get_settings
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


class _DashboardHub:
    """Simple in-memory pub/sub for dashboard subscribers."""

    def __init__(self):
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, payload: dict):
        dead: List[WebSocket] = []
        payload["ts"] = datetime.utcnow().isoformat()
        msg = json.dumps(payload)
        for ws in self._connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        async with self._lock:
            for ws in dead:
                if ws in self._connections:
                    self._connections.remove(ws)


hub = _DashboardHub()


async def ws_dashboard(websocket: WebSocket):
    """
    Server-pushes live risk / flag updates to dashboards.
    Requires JWT token in query params: ?token=...
    Only admin/superadmin roles can connect.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing JWT token")
        return
    
    try:
        payload = _verify_dashboard_jwt(token)
        user_role = payload.get("role", "user")
        if user_role not in ("admin", "superadmin", "proctor"):
            await websocket.close(code=1008, reason=f"Role '{user_role}' not authorized")
            return
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        return
    
    await hub.connect(websocket)
    try:
        while True:
            await asyncio.sleep(0.5)
            from core.session import get_session_status
            st = get_session_status()
            await websocket.send_text(json.dumps({
                "event": "tick",
                "risk_score": st.get("risk_score", 0),
                "focus_score": st.get("focus_score", 100),
                "violation_count": len(st.get("violations", [])),
                "tab_switches": st.get("tab_switches", 0),
                "attention_breaks": st.get("attention_breaks", 0),
            }))
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)


async def broadcast_event(payload: dict):
    """Helper to push events to any connected dashboard."""
    await hub.broadcast(payload)
