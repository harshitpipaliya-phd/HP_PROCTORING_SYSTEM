"""
video_ai/risk_engine.py
=======================
Risk scoring engine and session reporting for HP Proctoring.

Enhancements (v2.1):
- Single authoritative risk-weight table (removed duplicate in processor.py)
- Per-organization / per-exam configurable weights fetched from DB
- PDF report generation via ReportLab
- HP webhook payload builder (hp_mapper)
- behavior_flags mapped to HP competency model (integrity/focus/discipline)
- Cloudinary upload support for PDF reports
"""

import io
import os
import json
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Risk thresholds — aligned with spec (Section 6.2)
# HIGH >= 80, MEDIUM >= 50, LOW >= 25
# ---------------------------------------------------------------------------
_HIGH_RISK_THRESHOLD = 80
_MEDIUM_RISK_THRESHOLD = 50
_LOW_RISK_THRESHOLD = 25

# ---------------------------------------------------------------------------
# Default risk weights (single authoritative source)
# ---------------------------------------------------------------------------
DEFAULT_RISK_WEIGHTS: Dict[str, int] = {
    "multiple_persons":    50,
    "phone_detected":      30,
    "book_detected":       20,
    "notes_detected":      15,
    "laptop_detected":     25,
    "looking_away":        10,
    "head_not_center":     10,
    "unusual_gesture":     15,
    "phone_hold_gesture":  20,
    "writing_gesture":     12,
    "frequent_look_away":  10,
    "low_blink_rate":       5,
    "audio_anomaly":       30,
    "background_voice":    40,
    "unauthorized_speaker": 50,
    "TAB_SWITCH":          15,
    "ATTENTION_BREAK":      5,
    # Spec gap fix: browser/proctoring integrity events
    "face_absent":         20,   # candidate face not visible in frame
    "window_blur":         10,   # browser window lost focus
    "fullscreen_exit":     15,   # candidate exited fullscreen mode
}

# Module-level override (loaded per session from exam/org config)
_active_risk_weights: Dict[str, int] = dict(DEFAULT_RISK_WEIGHTS)
_weights_lock = threading.Lock()

# Redis connection for atomic risk scoring
_redis_client = None
_redis_available = False
_redis_lock = threading.Lock()


def _get_redis_client():
    global _redis_client, _redis_available
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client if _redis_available else None
        try:
            import redis as _redis_mod
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_client = _redis_mod.Redis.from_url(url, decode_responses=True)
            _redis_client.ping()
            _redis_available = True
        except Exception:
            _redis_client = None
            _redis_available = False
        return _redis_client if _redis_available else None


def redis_incrby_risk(session_id: str, delta: int, ttl: int = 3600) -> int:
    """
    Atomically increment risk score for a session in Redis.
    Returns the new value. Falls back to returning 0 if Redis unavailable.
    """
    r = _get_redis_client()
    if not r:
        return 0
    key = f"hp:risk:{session_id}"
    try:
        new_score = r.incrby(key, delta)
        r.expire(key, ttl)          # BUG FIX: TTL was accepted but never applied
        return int(new_score)
    except Exception as e:
        print(f"[risk_engine] redis_incrby_risk failed: {e}")
        return 0


def redis_set_risk(session_id: str, value: int, ttl: int = 3600) -> bool:
    """Set risk score for a session in Redis."""
    r = _get_redis_client()
    if not r:
        return False
    key = f"hp:risk:{session_id}"
    try:
        r.set(key, value, ex=ttl)
        return True
    except Exception:
        return False


def redis_get_risk(session_id: str) -> int:
    """Get the current Redis risk score for a session."""
    r = _get_redis_client()
    if not r:
        return 0
    key = f"hp:risk:{session_id}"
    try:
        val = r.get(key)
        return int(val) if val is not None else 0
    except Exception:
        return 0


def redis_flush_risk_to_memory(session_id: str) -> int:
    """Read risk from Redis into memory and clear the key. Returns the value."""
    val = redis_get_risk(session_id)
    r = _get_redis_client()
    if r:
        try:
            r.delete(f"hp:risk:{session_id}")
        except Exception:
            pass
    return val


def load_risk_weights(exam_id: str = None, organization_id: str = None) -> Dict[str, int]:
    """
    Load risk weights from exam → organization → defaults (priority order).
    Merges only keys that exist in defaults to prevent injection.
    """
    weights = dict(DEFAULT_RISK_WEIGHTS)
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return weights

        # Org-level weights
        if organization_id:
            resp = _supabase.table("organizations").select("risk_weights").eq(
                "id", organization_id
            ).single().execute()
            if resp.data and resp.data.get("risk_weights"):
                org_w = resp.data["risk_weights"]
                if isinstance(org_w, str):
                    org_w = json.loads(org_w)
                for k, v in org_w.items():
                    if k in weights:
                        weights[k] = int(v)

        # Exam-level weights (override org)
        if exam_id:
            resp = _supabase.table("exams").select("risk_weights").eq(
                "id", exam_id
            ).single().execute()
            if resp.data and resp.data.get("risk_weights"):
                exam_w = resp.data["risk_weights"]
                if isinstance(exam_w, str):
                    exam_w = json.loads(exam_w)
                for k, v in exam_w.items():
                    if k in weights:
                        weights[k] = int(v)
    except Exception as e:
        print(f"[risk_engine] load_risk_weights failed: {e}")

    return weights


def set_active_weights(weights: Dict[str, int]):
    """Set the module-level active risk weights."""
    global _active_risk_weights
    with _weights_lock:
        _active_risk_weights = {**DEFAULT_RISK_WEIGHTS, **weights}


def get_active_weights() -> Dict[str, int]:
    with _weights_lock:
        return dict(_active_risk_weights)


# ---------------------------------------------------------------------------
# Violation / verdict helpers
# ---------------------------------------------------------------------------

def get_violation_summary() -> Dict[str, Any]:
    from core.session import get_session_status
    status = get_session_status()
    violations = status.get("violations", [])

    violation_counts = {}
    for v in violations:
        v_type = v if isinstance(v, str) else v.get("type", "unknown")
        violation_counts[v_type] = violation_counts.get(v_type, 0) + 1

    return {
        "total": len(violations),
        "by_type": violation_counts,
        "high_risk_count": sum(
            1 for v in violations
            if isinstance(v, dict) and v.get("risk", 0) >= _HIGH_RISK_THRESHOLD
        ),
    }


def get_ai_verdict(risk_score: int = None, focus_score: int = None) -> str:
    from core.session import get_session_status
    if risk_score is None or focus_score is None:
        status = get_session_status()
        if risk_score is None:
            risk_score = status.get("risk_score", 0)
        if focus_score is None:
            focus_score = status.get("focus_score", 100)

    if risk_score >= _HIGH_RISK_THRESHOLD:
        return "FAIL"
    elif risk_score >= _MEDIUM_RISK_THRESHOLD:
        return "FAIL" if focus_score < 50 else "REVIEW"
    elif risk_score >= _LOW_RISK_THRESHOLD:
        return "REVIEW"
    else:
        return "PASS" if focus_score >= 70 else "REVIEW"


def _get_risk_level(risk_score: int) -> str:
    if risk_score >= _HIGH_RISK_THRESHOLD:
        return "HIGH"
    elif risk_score >= _MEDIUM_RISK_THRESHOLD:
        return "MEDIUM"
    elif risk_score >= _LOW_RISK_THRESHOLD:
        return "LOW"
    else:
        return "MINIMAL"


# ---------------------------------------------------------------------------
# HP Competency Mapper
# ---------------------------------------------------------------------------

def map_behavior_flags_to_hp(violations: List[Any]) -> Dict[str, Any]:
    """
    Map violation types to HP competency model dimensions:
      - integrity  : honesty / anti-cheating signals
      - focus      : attention / engagement signals
      - discipline : rule-following / procedural signals
    """
    integrity_flags = {
        "MULTIPLE_PERSONS", "PHONE_DETECTED", "phone_detected",
        "unauthorized_speaker", "background_voice", "LOOKING_AWAY",
    }
    focus_flags = {
        "ATTENTION_BREAK", "looking_away", "frequent_look_away",
        "low_blink_rate", "head_not_center",
    }
    discipline_flags = {
        "TAB_SWITCH", "tab_switch", "book_detected", "notes_detected",
        "laptop_detected", "unusual_gesture", "writing_gesture",
    }

    integrity_hits = 0
    focus_hits = 0
    discipline_hits = 0

    for v in violations:
        v_type = v if isinstance(v, str) else v.get("type", "")
        if v_type in integrity_flags:
            integrity_hits += 1
        if v_type in focus_flags:
            focus_hits += 1
        if v_type in discipline_flags:
            discipline_hits += 1

    total = max(integrity_hits + focus_hits + discipline_hits, 1)

    return {
        "integrity": {
            "score": max(0, 100 - integrity_hits * 15),
            "flags": integrity_hits,
            "level": "LOW" if integrity_hits >= 3 else ("MEDIUM" if integrity_hits >= 1 else "HIGH"),
        },
        "focus": {
            "score": max(0, 100 - focus_hits * 10),
            "flags": focus_hits,
            "level": "LOW" if focus_hits >= 5 else ("MEDIUM" if focus_hits >= 2 else "HIGH"),
        },
        "discipline": {
            "score": max(0, 100 - discipline_hits * 12),
            "flags": discipline_hits,
            "level": "LOW" if discipline_hits >= 3 else ("MEDIUM" if discipline_hits >= 1 else "HIGH"),
        },
    }


# ---------------------------------------------------------------------------
# HP Webhook Payload builder
# ---------------------------------------------------------------------------

def build_hp_webhook_payload(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build HP-compatible webhook payload from a session report.
    Maps internal fields to HP proctoring integration schema.
    """
    ra = report.get("risk_assessment", {})
    metrics = report.get("metrics", {})
    violations = report.get("violations", {})
    behavior_flags = report.get("behavior_flags", {})

    return {
        "hp_schema_version": "1.0",
        "session_id": report.get("session_id"),
        "candidate_id": report.get("candidate_id"),  # BUG FIX: was wrongly mapped to user_id
        "exam_id": report.get("exam_id"),
        "timestamp": report.get("timestamp"),
        "proctoring_result": {
            "verdict": ra.get("ai_verdict", "INCONCLUSIVE"),
            "risk_score": ra.get("risk_score", 0),
            "focus_score": ra.get("focus_score", 100),
            "risk_level": ra.get("risk_level", "MINIMAL"),
        },
        "competency_scores": {
            "integrity": behavior_flags.get("integrity", {}).get("score", 100),
            "focus":     behavior_flags.get("focus", {}).get("score", 100),
            "discipline": behavior_flags.get("discipline", {}).get("score", 100),
        },
        "metrics": {
            "total_frames":      metrics.get("total_frames", 0),
            "tab_switches":      metrics.get("tab_switches", 0),
            "attention_breaks":  metrics.get("attention_breaks", 0),
            "total_violations":  violations.get("total", 0),
        },
        "violation_types": list(violations.get("by_type", {}).keys()),
        "recommendations": report.get("recommendations", []),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(session_state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive session report including HP behavior_flags."""
    # BUG FIX: guard against None input
    session_state = session_state or {}

    risk_score = int(session_state.get("risk_score", 0) or 0)
    focus_score = int(session_state.get("focus_score", 100) or 100)
    violations = session_state.get("violations", [])
    if not isinstance(violations, list):
        violations = []
    tab_switches = session_state.get("tab_switches", 0)
    attention_breaks = session_state.get("attention_breaks", 0)
    total_frames = session_state.get("total_frames", 0)

    verdict = get_ai_verdict(risk_score, focus_score)
    behavior_flags = map_behavior_flags_to_hp(violations)

    violation_types = {}
    for v in violations:
        v_type = v if isinstance(v, str) else v.get("type", "unknown")
        violation_types[v_type] = violation_types.get(v_type, 0) + 1

    report = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_state.get("session_id"),
        "user_id": session_state.get("user_id"),
        "exam_id": session_state.get("exam_id"),
        "organization_id": session_state.get("organization_id"),
        "candidate_id": session_state.get("candidate_id"),
        "risk_assessment": {
            "risk_score": risk_score,
            "focus_score": focus_score,
            "ai_verdict": verdict,
            "risk_level": _get_risk_level(risk_score),
        },
        "metrics": {
            "total_frames": total_frames,
            "tab_switches": tab_switches,
            "attention_breaks": attention_breaks,
            "violations_total": len(violations),
            "risk_score": risk_score,    # BUG FIX: spec requires these in metrics
            "focus_score": focus_score,
        },
        "violations": {
            "total": len(violations),
            "by_type": violation_types,
            "list": violations[-50:],
        },
        "behavior_flags": behavior_flags,
        "recommendations": _generate_recommendations(risk_score, focus_score, violations),
        "summary": _generate_summary_text(risk_score, focus_score, verdict, violations),
    }

    return report


def generate_report_text(report: Dict[str, Any]) -> str:
    """Generate human-readable text report."""
    ra = report.get("risk_assessment", {})
    metrics = report.get("metrics", {})
    bf = report.get("behavior_flags", {})

    lines = [
        "=" * 60,
        "HP PROCTORING SESSION REPORT",
        "=" * 60,
        f"Timestamp:   {report.get('timestamp', 'N/A')}",
        f"Session ID:  {report.get('session_id', 'N/A')}",
        f"User ID:     {report.get('user_id', 'N/A')}",
        f"Exam ID:     {report.get('exam_id', 'N/A')}",
        "",
        "RISK ASSESSMENT",
        "-" * 40,
        f"Risk Score:  {ra.get('risk_score', 0)}/100",
        f"Focus Score: {ra.get('focus_score', 100)}/100",
        f"AI Verdict:  {ra.get('ai_verdict', 'N/A')}",
        f"Risk Level:  {ra.get('risk_level', 'N/A')}",
        "",
        "METRICS",
        "-" * 40,
        f"Total Frames:     {metrics.get('total_frames', 0)}",
        f"Tab Switches:     {metrics.get('tab_switches', 0)}",
        f"Attention Breaks: {metrics.get('attention_breaks', 0)}",
        f"Total Violations: {metrics.get('violations_total', 0)}",
    ]

    violations = report.get("violations", {})
    if violations.get("by_type"):
        lines += ["", "VIOLATION BREAKDOWN", "-" * 40]
        for v_type, count in violations["by_type"].items():
            lines.append(f"  {v_type}: {count}")

    if bf:
        lines += ["", "HP COMPETENCY SCORES", "-" * 40]
        for dim, data in bf.items():
            lines.append(
                f"  {dim.capitalize():12s}: {data.get('score', 100)}/100"
                f"  [{data.get('level', 'N/A')}]  flags={data.get('flags', 0)}"
            )

    recommendations = report.get("recommendations", [])
    if recommendations:
        lines += ["", "RECOMMENDATIONS", "-" * 40]
        for rec in recommendations:
            lines.append(f"  - {rec}")

    lines += ["", "=" * 60]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF Report Generation (ReportLab)
# ---------------------------------------------------------------------------

def generate_report_pdf(report: Dict[str, Any]) -> Optional[bytes]:
    """
    Generate a PDF report using ReportLab.
    Returns PDF bytes or None if ReportLab is not installed.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        print("[risk_engine] reportlab not installed — PDF generation skipped")
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=18, spaceAfter=6, alignment=TA_CENTER,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=13, spaceAfter=4, spaceBefore=12,
        textColor=colors.HexColor("#1a237e"),
    )
    body_style = styles["BodyText"]

    ra = report.get("risk_assessment", {})
    metrics = report.get("metrics", {})
    bf = report.get("behavior_flags", {})
    violations = report.get("violations", {})

    verdict = ra.get("ai_verdict", "INCONCLUSIVE")
    verdict_color = {
        "PASS": colors.green,
        "REVIEW": colors.orange,
        "FAIL": colors.red,
    }.get(verdict, colors.grey)

    story = []

    # Header
    story.append(Paragraph("HP PROCTORING SESSION REPORT", title_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 0.3*cm))

    # Meta
    meta_data = [
        ["Session ID", report.get("session_id", "N/A")],
        ["User / Candidate", report.get("user_id", "N/A")],
        ["Exam ID", report.get("exam_id", "N/A") or "—"],
        ["Generated", report.get("timestamp", datetime.now().isoformat())],
    ]
    meta_table = Table(meta_data, colWidths=[4*cm, 12*cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5*cm))

    # Verdict banner
    verdict_para = Paragraph(
        f"<b>AI VERDICT: {verdict}</b>",
        ParagraphStyle("verdict", fontSize=14, alignment=TA_CENTER, textColor=verdict_color),
    )
    story.append(verdict_para)
    story.append(Spacer(1, 0.4*cm))

    # Risk Assessment
    story.append(Paragraph("Risk Assessment", h2_style))
    risk_data = [
        ["Risk Score", f"{ra.get('risk_score', 0)} / 100"],
        ["Focus Score", f"{ra.get('focus_score', 100)} / 100"],
        ["Risk Level", ra.get("risk_level", "N/A")],
    ]
    risk_table = Table(risk_data, colWidths=[5*cm, 11*cm])
    risk_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(risk_table)

    # Metrics
    story.append(Paragraph("Session Metrics", h2_style))
    met_data = [
        ["Total Frames", str(metrics.get("total_frames", 0))],
        ["Tab Switches", str(metrics.get("tab_switches", 0))],
        ["Attention Breaks", str(metrics.get("attention_breaks", 0))],
        ["Total Violations", str(metrics.get("violations_total", 0))],
    ]
    met_table = Table(met_data, colWidths=[5*cm, 11*cm])
    met_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(met_table)

    # Violation breakdown
    if violations.get("by_type"):
        story.append(Paragraph("Violation Breakdown", h2_style))
        viol_data = [["Violation Type", "Count"]] + [
            [k, str(v)] for k, v in violations["by_type"].items()
        ]
        viol_table = Table(viol_data, colWidths=[10*cm, 6*cm])
        viol_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#e8eaf6")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(viol_table)

    # HP Competency Scores
    if bf:
        story.append(Paragraph("HP Competency Model", h2_style))
        comp_data = [["Dimension", "Score", "Level", "Flags"]] + [
            [
                dim.capitalize(),
                f"{d.get('score', 100)}/100",
                d.get("level", "N/A"),
                str(d.get("flags", 0)),
            ]
            for dim, d in bf.items()
        ]
        comp_table = Table(comp_data, colWidths=[5*cm, 4*cm, 4*cm, 3*cm])
        comp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eceff1")]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(comp_table)

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        story.append(Paragraph("Recommendations", h2_style))
        for rec in recs:
            story.append(Paragraph(f"• {rec}", body_style))
            story.append(Spacer(1, 0.1*cm))

    doc.build(story)
    return buf.getvalue()


def save_report_pdf(report: Dict[str, Any], output_dir: str = "static/reports") -> Optional[str]:
    """
    Generate and save PDF report to disk.
    Returns file path or None.
    """
    pdf_bytes = generate_report_pdf(report)
    if pdf_bytes is None:
        return None

    os.makedirs(output_dir, exist_ok=True)
    session_id = report.get("session_id", "unknown")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{session_id}_{ts}.pdf"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "wb") as f:
        f.write(pdf_bytes)

    print(f"[risk_engine] PDF report saved: {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# Cloudinary Upload
# ---------------------------------------------------------------------------

def upload_report_to_cloudinary(
    file_path: str,
    public_id: str = None,
) -> Optional[Dict[str, Any]]:
    """
    Upload a report file (PDF/JSON) to Cloudinary.
    Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET env vars.
    Returns Cloudinary response dict or None.
    """
    try:
        import cloudinary
        import cloudinary.uploader
        # Removed: from core.config import get_settings / settings = get_settings() — never used

        cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        api_key = os.getenv("CLOUDINARY_API_KEY", "")
        api_secret = os.getenv("CLOUDINARY_API_SECRET", "")

        if not all([cloud_name, api_key, api_secret]):
            print("[cloudinary] Credentials not set — skipping upload")
            return None

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
        )

        resp = cloudinary.uploader.upload(
            file_path,
            resource_type="raw",
            public_id=public_id or f"hp_proctoring/reports/{os.path.basename(file_path)}",
            overwrite=True,
        )
        return {
            "url": resp.get("secure_url"),
            "public_id": resp.get("public_id"),
            "bytes": resp.get("bytes"),
        }
    except ImportError:
        print("[cloudinary] cloudinary package not installed")
        return None
    except Exception as e:
        print(f"[cloudinary] upload failed: {e}")
        return None


def upload_screenshot_to_cloudinary(
    file_path: str,
    session_id: str = "unknown",
    monitor_id: int = 1,
) -> Optional[Dict[str, Any]]:
    """Upload a screenshot to Cloudinary and return the result."""
    return upload_report_to_cloudinary(
        file_path,
        public_id=f"hp_proctoring/screenshots/{session_id}/monitor_{monitor_id}_{os.path.basename(file_path)}",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_recommendations(
    risk_score: int, focus_score: int, violations: List
) -> List[str]:
    recommendations = []
    if risk_score >= _HIGH_RISK_THRESHOLD:
        recommendations.append("High risk detected — manual review recommended")
    if focus_score < 50:
        recommendations.append("Low focus score — possible distraction issues")

    violation_types = [
        v if isinstance(v, str) else v.get("type", "") for v in violations
    ]
    if "TAB_SWITCH" in violation_types:
        recommendations.append("Multiple tab switches detected — may indicate cheating")
    if "MULTIPLE_PERSONS" in violation_types or "multiple_persons" in violation_types:
        recommendations.append("Multiple persons detected — possible assistance")
    if "PHONE_DETECTED" in violation_types or "phone_detected" in violation_types:
        recommendations.append("Phone detected — potential communication device")
    if "LOOKING_AWAY" in violation_types or "looking_away" in violation_types:
        recommendations.append("Frequent look-aways detected — monitor attention")

    if not recommendations:
        recommendations.append("Session appears clean — no major concerns")

    return recommendations


def _generate_summary_text(
    risk_score: int, focus_score: int, verdict: str, violations: List
) -> str:
    risk_level = _get_risk_level(risk_score)
    if verdict == "PASS":
        return (
            f"Session completed with {risk_level} risk. "
            f"Focus maintained at {focus_score}%. No significant violations detected."
        )
    elif verdict == "REVIEW":
        return (
            f"Session completed with {risk_level} risk. "
            f"{len(violations)} violation(s) detected. Manual review recommended."
        )
    elif verdict == "FAIL":
        return (
            f"Session completed with HIGH risk. "
            f"{len(violations)} significant violation(s) detected. Proctor intervention required."
        )
    else:
        return (
            f"Session completed. Risk: {risk_score}/100, "
            f"Focus: {focus_score}%. Verdict: {verdict}"
        )
