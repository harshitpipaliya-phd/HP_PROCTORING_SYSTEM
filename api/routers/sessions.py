"""
api/routers/sessions.py
=======================
Session management endpoints.
Spec: POST /v1/sessions, GET /v1/sessions/{id}, POST /v1/sessions/{id}/end, POST /v1/sessions/{id}/terminate
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from core.session import (
    start_session, stop_session, get_session_status, get_current_session,
    get_session_by_id, record_tab_switch, update_session_risk,
)
from database import log_session
from api.schemas.session import StartRequest, StartRequestV2, StopRequest
from api.core.dependencies import get_current_user

router = APIRouter(prefix="/v1/sessions", tags=["Sessions"])


@router.post("", summary="Start a new proctoring session")
def api_start_session(
    body: StartRequest,
    user: dict = Depends(get_current_user)
):
    session = get_current_session()
    if session and getattr(session, "_active", False):
        return {"success": True, "session_id": session.session_id,
                "message": "Session already active"}
    sid = start_session(session_id=body.session_id, user_id=body.user_id,
                        exam_id=body.exam_id, organization_id=body.organization_id,
                        candidate_id=body.candidate_id)
    log_session(sid, body.user_id, "session_start")
    return {"success": True, "session_id": sid, "message": "Proctoring session started",
            "user_id": body.user_id, "started_at": datetime.now().isoformat()}


@router.get("/{session_id}", summary="Get session by ID")
def api_get_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    session = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "success": True,
        "session": {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "candidate_id": session.candidate_id,
            "exam_id": session.exam_id,
            "organization_id": session.organization_id,
            "status": "active" if getattr(session, "_active", False) else "ended",
            "risk_score": session.risk_score,
            "focus_score": session.focus_score,
            "total_frames": session.total_frames,
            "violations_count": len(session.violations),
            "tab_switches": session.tab_switches,
            "attention_breaks": session.attention_breaks,
            "start_time": session.start_time,
            "end_time": session.end_time,
        }
    }


@router.post("/{session_id}/end", summary="End a session")
def api_end_session(
    session_id: str,
    body: StopRequest,
    user: dict = Depends(get_current_user)
):
    session = get_session_by_id(session_id)
    if not session or not getattr(session, "_active", False):
        raise HTTPException(status_code=400, detail="No active session to end")
    info = stop_session(body.reason)
    log_session(session.session_id, session.user_id, "session_end",
                {"reason": body.reason})
    return {"success": True, **info}


@router.post("/{session_id}/terminate", summary="Terminate a session")
def api_terminate_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    session = get_session_by_id(session_id)
    if not session or not getattr(session, "_active", False):
        raise HTTPException(status_code=400, detail="No active session to terminate")
    info = stop_session("terminated")
    log_session(session.session_id, session.user_id, "session_terminated",
                {"reason": "terminated"})
    return {"success": True, **info}


@router.get("/{session_id}/events", summary="Get session events")
def api_get_session_events(
    session_id: str,
    limit: int = 100,
    user: dict = Depends(get_current_user)
):
    session = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    events = session.events[-limit:] if session.events else []
    return {"success": True, "session_id": session_id, "total": len(events), "events": events}
