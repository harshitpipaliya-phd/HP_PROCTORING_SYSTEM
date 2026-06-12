"""
api/schemas/event.py
====================
Pydantic request/response schemas for proctoring events.

Missing schema — created to fill spec gap.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class BrowserEventRequest(BaseModel):
    """Generic browser-side proctoring event (face_absent, window_blur, fullscreen_exit, etc.)."""
    event_type: str = Field(
        ...,
        description=(
            "Event type: face_absent | window_blur | fullscreen_exit | "
            "tab_switch | custom_event"
        ),
    )
    session_id: Optional[str] = Field(default=None, description="Session ID")
    user_id: Optional[str] = Field(default="api_user", description="Candidate user ID")
    payload: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Arbitrary event-specific metadata",
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO-8601 client-side timestamp (server time used if omitted)",
    )


class FaceAbsentEventRequest(BaseModel):
    """Face absent event — candidate's face not detected in frame."""
    user_id: Optional[str] = Field(default="api_user")
    duration_seconds: Optional[float] = Field(
        default=None,
        description="How long the face has been absent (seconds)",
    )


class WindowBlurEventRequest(BaseModel):
    """Window blur event — browser window lost focus."""
    user_id: Optional[str] = Field(default="api_user")
    blur_count: Optional[int] = Field(
        default=None,
        description="Cumulative blur count in this session",
    )


class FullscreenExitEventRequest(BaseModel):
    """Fullscreen exit event — candidate exited required fullscreen."""
    user_id: Optional[str] = Field(default="api_user")
    exit_count: Optional[int] = Field(
        default=None,
        description="How many times fullscreen has been exited",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class EventRecordedResponse(BaseModel):
    """Response after a browser event is recorded."""
    recorded: bool
    event_type: Optional[str] = None
    risk_score: Optional[int] = None
    focus_score: Optional[int] = None
    reason: Optional[str] = None


class EventListResponse(BaseModel):
    """Paginated list of events for a session."""
    success: bool = True
    session_id: Optional[str] = None
    total: int = 0
    limit: int = 100
    events: List[Dict[str, Any]] = []


class EventSummary(BaseModel):
    """Summary of event counts grouped by type."""
    session_id: Optional[str] = None
    event_counts: Dict[str, int] = Field(default_factory=dict)
    total_risk_from_events: int = 0
    highest_severity: str = "LOW"
