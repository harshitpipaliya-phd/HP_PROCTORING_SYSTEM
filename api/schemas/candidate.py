"""
api/schemas/candidate.py
=======================
Schemas for candidate enrollment and lookup.
"""

from pydantic import BaseModel, Field
from typing import Optional


class CandidateEnrollRequest(BaseModel):
    name: str
    email: str
    external_id: Optional[str] = None
    organization_id: Optional[str] = None
    face_embedding: Optional[dict] = None


class CandidateResponse(BaseModel):
    candidate_id: str
    name: str
    email: str
    external_id: Optional[str]
    organization_id: Optional[str]
    enrolled: bool
