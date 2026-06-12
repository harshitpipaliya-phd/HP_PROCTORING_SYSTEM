"""
api/routers/events.py
======================
Event timeline endpoints.
Spec: GET /v1/events?session_id=
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List

from core.session import get_session_by_id, get_current_session
from video_ai.processor import get_event_log
from api.core.dependencies import get_current_user

router = APIRouter(prefix="/v1", tags=["Events"])


@router.get("/events")
def api_get_events(
    session_id: Optional[str] = Query(default=None, description="Filter events by session ID"),
    limit: int = Query(default=100, le=500, description="Maximum number of events to return"),
    user: dict = Depends(get_current_user),
):
    """Get paginated event timeline for a session."""
    try:
        if session_id:
            session = get_session_by_id(session_id)
            if session:
                events = session.events[-limit:] if session.events else []
            else:
                events = []
        else:
            events = get_event_log()[-limit:] if get_event_log() else []
        
        return {
            "success": True,
            "session_id": session_id,
            "total": len(events),
            "limit": limit,
            "events": events,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))