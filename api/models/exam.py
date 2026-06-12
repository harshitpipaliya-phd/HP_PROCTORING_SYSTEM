"""
api/models/exam.py
==================
ORM models for organizations and exams.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)
    settings = Column(Text, default="{}")
    risk_weights = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    organization_id = Column(String, index=True)
    duration_minutes = Column(Integer, default=60)
    risk_weights = Column(Text, default="{}")
    proctoring_config = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
