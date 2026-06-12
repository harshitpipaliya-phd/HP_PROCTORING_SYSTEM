"""
api/models/session.py
=====================
ORM model for a proctoring session.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProctoringSession(Base):
    __tablename__ = "proctoring_sessions"

    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    candidate_id = Column(String, index=True)
    exam_id = Column(String, index=True)
    organization_id = Column(String, index=True)
    status = Column(String, default="active")
    risk_score = Column(Integer, default=0)
    focus_score = Column(Integer, default=100)
    total_frames = Column(Integer, default=0)
    violations_count = Column(Integer, default=0)
    tab_switches = Column(Integer, default=0)
    attention_breaks = Column(Integer, default=0)
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    stop_reason = Column(String, nullable=True)
    metadata = Column(JSON, default={})

    def __repr__(self) -> str:
        return f"<ProctoringSession {self.session_id} ({self.status})>"
