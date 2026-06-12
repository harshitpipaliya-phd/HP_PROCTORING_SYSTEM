"""
api/routers/reports.py
========================
Report endpoints for session reports.
Spec: GET /v1/reports/{session_id}, GET /v1/reports/{session_id}/pdf
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
import io
from typing import Optional

from core.session import get_session_by_id, get_current_session
from video_ai.risk_engine import generate_report, generate_report_text, generate_report_pdf, build_hp_webhook_payload
from api.core.dependencies import get_current_user

router = APIRouter(prefix="/v1", tags=["Reports"])


@router.get("/reports/{session_id}")
def api_get_report(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Get session report data."""
    session = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_state = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "exam_id": session.exam_id,
        "organization_id": session.organization_id,
        "candidate_id": session.candidate_id,
        "risk_score": session.risk_score,
        "focus_score": session.focus_score,
        "violations": session.violations,
        "tab_switches": session.tab_switches,
        "attention_breaks": session.attention_breaks,
        "total_frames": session.total_frames,
    }
    
    report = generate_report(session_state)
    return {"success": True, "report": report}


@router.get("/reports/{session_id}/pdf")
def api_get_report_pdf(
    session_id: str,
    upload_cloudinary: bool = Query(default=False, description="Upload PDF to Cloudinary"),
    user: dict = Depends(get_current_user),
):
    """Get session report as PDF."""
    session = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_state = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "exam_id": session.exam_id,
        "organization_id": session.organization_id,
        "candidate_id": session.candidate_id,
        "risk_score": session.risk_score,
        "focus_score": session.focus_score,
        "violations": session.violations,
        "tab_switches": session.tab_switches,
        "attention_breaks": session.attention_breaks,
        "total_frames": session.total_frames,
    }
    
    report = generate_report(session_state)
    pdf_bytes = generate_report_pdf(report)
    
    if pdf_bytes is None:
        raise HTTPException(status_code=503, detail="PDF unavailable — install: pip install reportlab")
    
    result = {"success": True}
    
    if upload_cloudinary:
        from api.services.media_storage import MediaStorageService
        storage = MediaStorageService()
        pdf_path = f"static/reports/report_{session_id}.pdf"
        
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        
        upload = storage.upload_report(pdf_path, session_id)
        if upload:
            result["cloudinary"] = upload
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{session_id}.pdf"'},
    )


@router.get("/reports/{session_id}/hp-payload")
def api_get_report_hp_payload(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Get HP-compatible webhook payload for a session report."""
    session = get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_state = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "exam_id": session.exam_id,
        "organization_id": session.organization_id,
        "candidate_id": session.candidate_id,
        "risk_score": session.risk_score,
        "focus_score": session.focus_score,
        "violations": session.violations,
        "tab_switches": session.tab_switches,
        "attention_breaks": session.attention_breaks,
        "total_frames": session.total_frames,
    }
    
    report = generate_report(session_state)
    payload = build_hp_webhook_payload(report)
    return {"success": True, "hp_payload": payload}