"""
api/schemas/admin.py
====================
Schemas for admin endpoints (organizations, exams).
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class OrganizationRequest(BaseModel):
    name: str
    slug: str
    settings: Optional[Dict[str, Any]] = None


class ExamRequest(BaseModel):
    name: str
    organization_id: Optional[str] = None
    duration_minutes: int = Field(default=60, ge=1)
    risk_weights: Optional[Dict[str, int]] = None
    proctoring_config: Optional[Dict[str, Any]] = None


class OrganizationResponse(BaseModel):
    organization_id: str
    name: str
    slug: str
    settings: Optional[dict]


class ExamResponse(BaseModel):
    exam_id: str
    name: str
    organization_id: Optional[str]
    duration_minutes: int
    risk_weights: Optional[dict]
    proctoring_config: Optional[dict]


class SessionFlagRequest(BaseModel):
    reason: str
    notes: Optional[str] = None


class SessionFlagResponse(BaseModel):
    session_id: str
    flagged: bool
    reason: str
    notes: Optional[str]


class UserCreateRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = Field(default="proctor", pattern="^(superadmin|admin|proctor)$")
    organization_id: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    organization_id: Optional[str]
    is_active: bool
    created_at: Optional[str]


class CandidateUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    organization_id: Optional[str] = None
    enrolled: Optional[bool] = None
    face_embedding: Optional[dict] = None
