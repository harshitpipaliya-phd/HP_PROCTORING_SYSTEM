"""
api/models/user.py
==================
ORM model for users (admin, proctor, superadmin).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="proctor", index=True)
    organization_id = Column(String, index=True, nullable=True)
    is_active = Column(Boolean, default=True)
    password_hash = Column(String, nullable=True)
    metadata = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
