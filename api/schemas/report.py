"""
api/schemas/report.py
=====================
Pydantic request/response schemas for session reports.

Missing schema — created to fill spec gap.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ViolationEntry(BaseModel):
    """A single violation entry in a report."""
    event_type: str
    timestamp: Optional[str] = None
    count: Optional[int] = None
    weight: Optional[int] = None
    details: Optional[Dict[str, Any]] = None


class HPCompetencyScore(BaseModel):
    """HP competency model score (integrity/focus/discipline)."""
    score: float = Field(ge=0.0, le=1.0, description="Normalized score 0–1")
    level: str = Field(description="LOW | MEDIUM | HIGH")
    hits: int = Field(default=0, description="Number of violations in this domain")


class ReportResponse(BaseModel):
    """Full session report response."""
    success: bool = True
    report: Optional[Dict[str, Any]] = None


class ReportSummary(BaseModel):
    """Lightweight report summary (for listing)."""
    session_id: str
    user_id: Optional[str] = None
    candidate_id: Optional[str] = None
    exam_id: Optional[str] = None
    risk_score: int = 0
    focus_score: int = 100
    verdict: str = "CLEAN"
    total_violations: int = 0
    risk_level: str = "LOW"
    timestamp: Optional[str] = None


class ReportListResponse(BaseModel):
    """Response for listing multiple reports."""
    success: bool = True
    total: int = 0
    reports: List[ReportSummary] = []


class HPWebhookPayloadResponse(BaseModel):
    """Response containing the HP-compatible webhook payload."""
    success: bool = True
    hp_payload: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class GenerateReportRequest(BaseModel):
    """Request to generate or regenerate a report for a session."""
    session_id: str
    upload_cloudinary: bool = Field(
        default=False,
        description="Upload generated PDF to Cloudinary",
    )
    send_webhook: bool = Field(
        default=False,
        description="Dispatch HP webhook after report generation",
    )


class ReportFilterRequest(BaseModel):
    """Filter parameters for listing reports."""
    organization_id: Optional[str] = None
    exam_id: Optional[str] = None
    verdict: Optional[str] = Field(
        default=None,
        description="Filter by verdict: CLEAN | SUSPICIOUS | HIGH_RISK",
    )
    risk_min: Optional[int] = Field(default=None, ge=0, le=100)
    risk_max: Optional[int] = Field(default=None, ge=0, le=100)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
