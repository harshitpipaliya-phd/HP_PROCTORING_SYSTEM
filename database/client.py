"""
database/client.py
==================
Supabase client for database operations.
Fully silent on any network/DNS error — never crashes the app.
"""

import os
import json
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Import settings
from core.config import get_settings

# Supabase client
_supabase = None
_db_available = False
_init_lock = threading.Lock()


def _init_supabase():
    """Initialize Supabase client in background thread."""
    global _supabase, _db_available
    
    settings = get_settings()
    
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        print("[database] Supabase init skipped: SUPABASE_URL / SUPABASE_KEY not set")
        return
    
    try:
        from supabase import create_client
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        _db_available = True
        
        # Wrap upsert for compatibility across supabase-py versions
        _orig_upsert = client.table.upsert
        def _patched_upsert(table_name, data, on_conflict=None, **kwargs):
            try:
                return _orig_upsert(data, conflict_columns=on_conflict, **kwargs) if on_conflict else _orig_upsert(data, **kwargs)
            except TypeError:
                return _orig_upsert(data, on_conflict=on_conflict, **kwargs)
        client.table.upsert = _patched_upsert
        
        _supabase = client
        print("[database] Supabase client created successfully")
    except ModuleNotFoundError:
        print("[database] Supabase init failed: 'supabase' package not installed")
        print("[database] Run: pip install supabase>=2.3.0")
    except Exception as e:
        print(f"[database] Supabase init failed: {e}")


def init_database():
    """Initialize the database connection."""
    with _init_lock:
        _init_supabase()


def is_available() -> bool:
    """Check if database is available."""
    return _db_available


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _async_insert(table: str, data: dict):
    """Run DB insert in background thread — never blocks."""
    def _do():
        try:
            if _supabase is None:
                return
            _supabase.table(table).insert(data).execute()
        except Exception as e:
            print(f"[database] Insert failed for {table}: {e}")
    
    thread = threading.Thread(target=_do, daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def log_event(user_id: str, event: str, result: str):
    """Log a generic event to video_logs table."""
    if not _db_available:
        return
    
    _async_insert("video_logs", {
        "user_id": user_id,
        "event": event,
        "result": str(result)[:500],  # Guard against huge strings
        "timestamp": _now(),
    })


def log_session(session_id: str, user_id: str, event: str, metadata: dict = None):
    """Log session-level events with optional metadata."""
    if not _db_available:
        return
    
    _async_insert("proctoring_sessions", {
        "session_id": session_id,
        "user_id": user_id,
        "event": event,
        "metadata": json.dumps(metadata or {}),
        "timestamp": _now(),
    })


def log_report(session_id: str, report: dict):
    """Persist a complete session report."""
    if not _db_available:
        return
    
    ra = report.get("risk_assessment", {})
    _async_insert("reports", {
        "session_id": session_id,
        "risk_score": ra.get("risk_score", 0),
        "focus_score": ra.get("focus_score", 100),
        "verdict": ra.get("ai_verdict", "Low"),
        "total_violations": report.get("violations", {}).get("total", 0),
        "report_json": json.dumps(report),
        "timestamp": _now(),
    })


def log_behavior_event(behavior_result: dict):
    """
    Log full behavior analysis to behavior_logs table.
    Schema covers 2.1 (iris gaze, EAR, blink, yaw, pitch, roll),
    2.2 (YOLO person/object), 2.3 (MediaPipe hands + gesture).
    """
    if not _db_available:
        return
    
    try:
        eye_head = behavior_result.get("eye_head", {})
        pose = behavior_result.get("head_pose", {})
        persons = behavior_result.get("persons", {})
        objects = behavior_result.get("objects", {})
        mobile = behavior_result.get("mobile", {})
        attention = behavior_result.get("attention", {})
        breakdown = behavior_result.get("risk_breakdown", {})
        events = behavior_result.get("events", [])
        
        data = {
            # 2.1 Eye
            "looking_away": eye_head.get("looking_away", False),
            "gaze_direction": eye_head.get("gaze_direction", "N/A"),
            "left_gaze": eye_head.get("left_gaze", "N/A"),
            "right_gaze": eye_head.get("right_gaze", "N/A"),
            "ear_left": eye_head.get("ear_left", 0.0),
            "ear_right": eye_head.get("ear_right", 0.0),
            "blink_count": eye_head.get("blink_count", 0),
            "look_away_frequency": eye_head.get("look_away_frequency", 0),
            "frequent_look_away": eye_head.get("frequent_looking_away", False),
            # 2.1 Head
            "head_direction": pose.get("direction", "N/A"),
            "yaw": pose.get("yaw", 0.0),
            "pitch": pose.get("pitch", 0.0),
            "roll": pose.get("roll", 0.0),
            # Attention
            "attention_score": attention.get("score", 0),
            "attention_label": attention.get("label", "N/A"),
            # 2.2 Persons
            "person_count": persons.get("person_count", 0),
            "multiple_persons": persons.get("multiple_persons", False),
            "person_engine": persons.get("detection_engine", "N/A"),
            # 2.2 Objects
            "prohibited_objects": json.dumps(objects.get("prohibited_objects", [])),
            "phone_detected": objects.get("phone_detected", False),
            "book_detected": objects.get("book_detected", False),
            "notes_detected": objects.get("notes_detected", False),
            "laptop_detected": objects.get("laptop_detected", False),
            "object_engine": objects.get("detection_engine", "N/A"),
            # 2.3 Mobile
            "mobile_phone": mobile.get("phone_detected", False),
            "phone_confidence": mobile.get("phone_confidence", 0.0),
            "hands_detected": mobile.get("hands_detected", 0),
            "unusual_gesture": mobile.get("unusual_gesture", False),
            "gesture_labels": json.dumps(mobile.get("gesture_labels", [])),
            "motion_score": mobile.get("motion_score", 0.0),
            # Risk
            "risk_score": behavior_result.get("risk_score", 0),
            "risk_flags": json.dumps(behavior_result.get("risk_flags", [])),
            "risk_breakdown": json.dumps(breakdown),
            # Events
            "events_json": json.dumps(events[:10]),
            # Timestamps
            "created_at": _now()
        }
        
        _async_insert("behavior_logs", data)
        
    except Exception as e:
        print(f"[database] log_behavior_event failed: {e}")


def log_audio_event(audio_result: dict):
    """Log audio analysis event to audio_logs table."""
    if not _db_available:
        return
    
    try:
        data = {
            "user_id": audio_result.get("user_id", "unknown"),
            "total_risk": audio_result.get("total_risk", 0),
            "risk_level": audio_result.get("risk_level", "LOW"),
            "speech_segments": audio_result.get("speech_segments", 0),
            "anomaly_segments": audio_result.get("anomaly_segments", 0),
            "background_voice_segments": audio_result.get("background_voice_segments", 0),
            "unauthorized_segments": audio_result.get("unauthorized_segments", 0),
            "estimated_speakers": audio_result.get("estimated_speakers", 0),
            "result": audio_result.get("result", ""),
            "volume": audio_result.get("volume", 0.0),
            "created_at": _now()
        }
        
        _async_insert("audio_logs", data)
        
    except Exception as e:
        print(f"[database] log_audio_event failed: {e}")


def fetch_logs(table: str, limit: int = 20) -> list:
    """Fetch recent logs from a table."""
    if not _db_available or _supabase is None:
        return []
    
    try:
        response = (
            _supabase.table(table)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"[database] fetch_logs failed: {e}")
        return []


def fetch_behavior_stats(hours: int = 24) -> dict:
    """Fetch aggregated behavior statistics for the past N hours."""
    if not _db_available or _supabase is None:
        return {}
    
    try:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        
        response = (
            _supabase.table("behavior_logs")
            .select("risk_score, risk_flags, created_at")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .execute()
        )
        
        rows = response.data or []
        if not rows:
            return {}
        
        scores = [r.get("risk_score", 0) for r in rows]
        return {
            "total_frames": len(rows),
            "avg_risk": round(sum(scores) / len(scores), 1),
            "max_risk": max(scores),
            "high_risk_count": sum(1 for s in scores if s >= 50),
            "period_hours": hours
        }
    except Exception as e:
        print(f"[database] fetch_behavior_stats failed: {e}")
        return {}


# Initialize on import
init_database()