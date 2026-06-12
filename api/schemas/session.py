"""
api/schemas/session.py
======================
Schemas for session management endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


class StartRequest(BaseModel):
    user_id: Optional[str] = Field(default="api_user", description="Candidate ID")
    session_id: Optional[str] = Field(default=None, description="Custom session ID (UUID generated if omitted)")
    exam_id: Optional[str] = Field(default=None, description="Linked exam ID")
    organization_id: Optional[str] = Field(default=None, description="Linked organization ID")
    candidate_id: Optional[str] = Field(default=None, description="Linked candidate ID")


class StartRequestV2(BaseModel):
    user_id: Optional[str] = Field(default="api_user")
    session_id: Optional[str] = Field(default=None)
    exam_id: Optional[str] = Field(default=None)
    organization_id: Optional[str] = Field(default=None)
    candidate_id: Optional[str] = Field(default=None)


class StopRequest(BaseModel):
    reason: Optional[str] = Field(default="manual", description="Reason for stopping the session")


class SessionStatusResponse(BaseModel):
    active: bool
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    risk_score: int = 0
    focus_score: int = 100
    attention_breaks: int = 0
    tab_switches: int = 0
    violations: list = []
    total_frames: int = 0
