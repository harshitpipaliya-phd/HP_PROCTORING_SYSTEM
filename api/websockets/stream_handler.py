"""
api/websockets/stream_handler.py
================================
Real-time audio WebSocket handler.
Handles raw PCM audio streaming from browser clients.
Original: api.py websocket /ws/audio/{session_id}
"""

import json
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from jose import jwt, JWTError

from audio_proctoring.stream import create_ws_audio_session, close_ws_audio_session


def _verify_ws_jwt(token: str) -> dict:
    """Verify JWT token from WebSocket query params."""
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


async def ws_audio_stream(websocket: WebSocket, session_id: str):
    """
    Real-time raw PCM audio WebSocket.
    Client sends: 16-bit LE PCM bytes at 16kHz mono.
    Server sends: JSON classification per chunk.
    Requires JWT token in query params: ?token=...
    """
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
    
    await websocket.accept()
    ws_sess = create_ws_audio_session(user_id=user_id, session_id=session_id)
    try:
        while True:
            raw = await websocket.receive_bytes()
            result = ws_sess.push_chunk(raw)
            await websocket.send_text(json.dumps(result))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS audio] Error: {e}")
    finally:
        summary = close_ws_audio_session(session_id)
        try:
            await websocket.send_text(json.dumps({"event": "session_ended", "summary": summary}))
        except Exception:
            pass
