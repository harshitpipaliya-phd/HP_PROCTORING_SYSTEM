"""
api/routers/monitoring.py
=========================
Monitoring endpoints: violations, risk, reports, tab-switch, monitors, events.
Original: api.py lines 365–525
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse, StreamingResponse
import io

from video_ai.risk_engine import (
    generate_report, generate_report_text, get_ai_verdict, get_violation_summary,
    generate_report_pdf, get_active_weights, set_active_weights, load_risk_weights,
    build_hp_webhook_payload,
)
from core.session import get_session_status, get_current_session, record_tab_switch
from database import log_event, log_report, db_available
from screen_monitoring.watcher import get_monitor_watcher
from screen_monitoring.capture import is_screen_capture_available
from video_ai.processor import get_event_log, get_behavior_trends
from api.core.dependencies import get_current_user, require_role

from api.schemas.detection import RiskWeightsRequest, RiskWeightsLoadRequest

router = APIRouter(prefix="/v1/monitor", tags=["Monitoring"])


@router.get("/violations")
def api_violations(user: dict = Depends(get_current_user)):
    summary = get_violation_summary()
    session = get_current_session()
    violations = session.violations[-50:] if session else []
    return {"summary": summary, "total": len(violations), "list": violations}


@router.get("/risk")
def api_risk(user: dict = Depends(get_current_user)):
    status = get_session_status()
    return {
        "risk_score": status.get("risk_score", 0),
        "focus_score": status.get("focus_score", 100),
        "ai_verdict": get_ai_verdict(),
        "attention_breaks": status.get("attention_breaks", 0),
        "tab_switches": status.get("tab_switches", 0),
        "violation_summary": get_violation_summary(),
    }


@router.get("/report")
def api_report(user: dict = Depends(get_current_user)):
    status = get_session_status()
    report = generate_report(status)
    session = get_current_session()
    if session:
        try:
            log_report(session.session_id, report)
        except Exception:
            pass
    return report


@router.get("/report/text", response_class=PlainTextResponse)
def api_report_text(user: dict = Depends(get_current_user)):
    status = get_session_status()
    report = generate_report(status)
    return generate_report_text(report)


@router.get("/report/pdf")
def api_report_pdf(user: dict = Depends(get_current_user)):
    session_state = get_session_status()
    if not session_state.get("session_id"):
        raise HTTPException(status_code=400, detail="No active or completed session")
    report = generate_report(session_state)
    pdf_bytes = generate_report_pdf(report)
    if pdf_bytes is None:
        raise HTTPException(status_code=503, detail="PDF unavailable — install: pip install reportlab")
    sid = report.get("session_id", "session")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{sid}.pdf'},
    )


@router.get("/report/hp-payload")
def api_hp_payload(user: dict = Depends(get_current_user)):
    session_state = get_session_status()
    if not session_state.get("session_id"):
        raise HTTPException(status_code=400, detail="No session available")
    report = generate_report(session_state)
    payload = build_hp_webhook_payload(report)
    return {"success": True, "hp_payload": payload}


@router.get("/events")
def api_events(
    limit: int = Query(default=100, le=500),
    user: dict = Depends(get_current_user)
):
    events = get_event_log()
    trends = get_behavior_trends()
    return {"total": len(events), "events": events[-limit:], "trends": trends}


@router.get("/monitors")
def api_monitors(user: dict = Depends(get_current_user)):
    watcher = get_monitor_watcher()
    if not watcher:
        return {"monitor_count": 0, "changed": False, "error": "Watcher unavailable"}
    status = watcher.check_changes()
    return {
        "monitor_count": status["data"].get("monitor_count", 0),
        "browser_count": status["data"].get("browser_count", 0),
        "changed": status["changed"],
        "change_event": status.get("change_event"),
        "monitors": status["data"].get("monitors", []),
        "screen_capture_available": is_screen_capture_available(),
    }


@router.post("/tab-switch")
def api_tab_switch(
    req: dict,
    user: dict = Depends(get_current_user)
):
    session = get_current_session()
    if not session or not getattr(session, "_active", False):
        return {"recorded": False, "reason": "No active session"}
    record_tab_switch()
    try:
        log_event(req.get("user_id", "api_user"), "tab_switch", "browser_event")
    except Exception:
        pass
    status = get_session_status()
    return {"recorded": True, "tab_switches": status.get("tab_switches", 0),
            "risk_score": status.get("risk_score", 0)}


@router.get("/stats")
def api_stats(
    hours: int = Query(default=24, description="Look-back window in hours"),
    user: dict = Depends(get_current_user)
):
    if not db_available():
        return {"success": False, "message": "Database not available"}
    try:
        from database.queries import fetch_risk_stats
        stats = fetch_risk_stats(hours)
        return {"success": True, "hours": hours, "stats": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/risk-weights")
def api_get_risk_weights(user: dict = Depends(get_current_user)):
    return {"success": True, "weights": get_active_weights()}


@router.post("/risk-weights")
def api_set_risk_weights(
    body: RiskWeightsRequest,
    user: dict = Depends(require_role("admin", "superadmin"))
):
    set_active_weights(body.weights)
    return {"success": True, "weights": body.weights}


@router.post("/risk-weights/load")
def api_load_risk_weights(
    body: RiskWeightsLoadRequest,
    user: dict = Depends(require_role("admin", "superadmin"))
):
    weights = load_risk_weights(exam_id=body.exam_id, organization_id=body.organization_id)
    set_active_weights(weights)
    return {"success": True, "weights": weights}


@router.post("/face-absent")
def api_face_absent(
    req: dict = None,
    user: dict = Depends(get_current_user)
):
    """Record a face_absent event — candidate not visible in frame."""
    from core.session import record_face_absent, get_current_session as _gcs
    session = _gcs()
    if not session or not getattr(session, "_active", False):
        return {"recorded": False, "reason": "No active session"}
    record_face_absent()
    try:
        from database import log_event
        uid = (req or {}).get("user_id", "api_user")
        log_event(uid, "face_absent", "browser_event")
    except Exception:
        pass
    status = get_session_status()
    return {"recorded": True, "risk_score": status.get("risk_score", 0)}


@router.post("/window-blur")
def api_window_blur(
    req: dict = None,
    user: dict = Depends(get_current_user)
):
    """Record a window_blur event — browser window lost focus."""
    from core.session import record_window_blur, get_current_session as _gcs
    session = _gcs()
    if not session or not getattr(session, "_active", False):
        return {"recorded": False, "reason": "No active session"}
    record_window_blur()
    try:
        from database import log_event
        uid = (req or {}).get("user_id", "api_user")
        log_event(uid, "window_blur", "browser_event")
    except Exception:
        pass
    status = get_session_status()
    return {"recorded": True, "risk_score": status.get("risk_score", 0), "focus_score": status.get("focus_score", 100)}


@router.post("/fullscreen-exit")
def api_fullscreen_exit(
    req: dict = None,
    user: dict = Depends(get_current_user)
):
    """Record a fullscreen_exit event — candidate exited fullscreen mode."""
    from core.session import record_fullscreen_exit, get_current_session as _gcs
    session = _gcs()
    if not session or not getattr(session, "_active", False):
        return {"recorded": False, "reason": "No active session"}
    record_fullscreen_exit()
    try:
        from database import log_event
        uid = (req or {}).get("user_id", "api_user")
        log_event(uid, "fullscreen_exit", "browser_event")
    except Exception:
        pass
    status = get_session_status()
    return {"recorded": True, "risk_score": status.get("risk_score", 0)}
