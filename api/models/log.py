"""
api/models/log.py
=================
ORM models for audit log tables.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy import ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class BehaviorLog(Base):
    __tablename__ = "behavior_logs"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, index=True)
    user_id = Column(String, index=True)
    looking_away = Column(Boolean, default=False)
    gaze_direction = Column(String, default="N/A")
    head_direction = Column(String, default="N/A")
    person_count = Column(Integer, default=0)
    multiple_persons = Column(Boolean, default=False)
    phone_detected = Column(Boolean, default=False)
    risk_score = Column(Integer, default=0)
    attention_score = Column(Integer, default=0)
    events_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)


class AudioLog(Base):
    __tablename__ = "audio_logs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    total_risk = Column(Integer, default=0)
    risk_level = Column(String, default="LOW")
    speech_segments = Column(Integer, default=0)
    anomaly_segments = Column(Integer, default=0)
    background_voice_segments = Column(Integer, default=0)
    unauthorized_segments = Column(Integer, default=0)
    estimated_speakers = Column(Integer, default=0)
    volume = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    risk_score = Column(Integer)
    focus_score = Column(Integer)
    verdict = Column(String)
    total_violations = Column(Integer)
    report_json = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
