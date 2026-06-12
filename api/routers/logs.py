"""
api/routers/logs.py
===================
Database log endpoints.
Original: api.py lines 472–507
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/v1/logs", tags=["Logs"])


@router.get("/behavior")
def api_logs_behavior(limit: int = Query(default=20, le=200)):
    from database import fetch_recent_logs, is_available as db_available
    if not db_available():
        return {"success": False, "message": "Database not available", "logs": []}
    logs = fetch_recent_logs("behavior_logs", limit)
    return {"success": True, "total": len(logs), "logs": logs}


@router.get("/audio")
def api_logs_audio(limit: int = Query(default=20, le=200)):
    from database import fetch_recent_logs, is_available as db_available
    if not db_available():
        return {"success": False, "message": "Database not available", "logs": []}
    logs = fetch_recent_logs("audio_logs", limit)
    return {"success": True, "total": len(logs), "logs": logs}


@router.get("/sessions")
def api_logs_sessions(limit: int = Query(default=20, le=200)):
    from database import fetch_sessions, is_available as db_available
    if not db_available():
        return {"success": False, "message": "Database not available", "logs": []}
    sessions = fetch_sessions(limit=limit)
    return {"success": True, "total": len(sessions), "sessions": sessions}
