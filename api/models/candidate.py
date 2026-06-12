"""
api/models/candidate.py
=======================
ORM model for candidates.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    external_id = Column(String, index=True)
    organization_id = Column(String, index=True)
    enrolled = Column(Boolean, default=True)
    face_embedding = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Candidate {self.name} ({self.id})>"
