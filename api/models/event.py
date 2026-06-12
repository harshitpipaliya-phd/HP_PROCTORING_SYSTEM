"""
api/models/event.py
====================
ORM model for proctoring events (browser integrity + detection events).

Missing model — created to fill spec gap.
Events include: face_absent, window_blur, fullscreen_exit, tab_switch,
                multiple_persons, phone_detected, etc.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProctoringEvent(Base):
    """
    Single proctoring event tied to a session.
    Maps to the `proctoring_events` table in Supabase.
    """
    __tablename__ = "proctoring_events"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=True)

    # Event classification
    event_type = Column(String, nullable=False, index=True)
    # e.g. "face_absent", "window_blur", "fullscreen_exit", "tab_switch",
    #      "multiple_persons", "phone_detected", "audio_anomaly", etc.

    event_source = Column(String, nullable=True)
    # e.g. "browser", "video_ai", "audio", "screen_monitoring"

    # Risk contribution of this single event
    risk_weight = Column(Integer, default=0)

    # Cumulative session risk at time of event
    risk_score_at_event = Column(Integer, default=0)

    # Optional structured payload (bounding boxes, confidence scores, etc.)
    payload = Column(JSON, default={})

    # Severity: LOW / MEDIUM / HIGH / CRITICAL
    severity = Column(String, default="LOW")

    # Whether this event triggered an alert / webhook
    alert_sent = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<ProctoringEvent {self.event_type} session={self.session_id} @{self.created_at}>"
