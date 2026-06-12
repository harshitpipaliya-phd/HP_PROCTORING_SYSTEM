"""
database/queries.py
===================
Database query functions for HP Proctoring Backend.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import json

from database.client import _supabase, _db_available


def insert_log(looking_away: bool, head_direction: str, attention_score: int):
    """Legacy proctoring log insert (backward compatible)."""
    try:
        if not _db_available or _supabase is None:
            return None
        
        data = {
            "looking_away": looking_away,
            "head_direction": head_direction,
            "attention_score": attention_score,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        return _supabase.table("proctoring_logs").insert(data).execute()
    except Exception as e:
        print(f"[DB ERROR insert_log]: {e}")
        return None


def insert_behavior_log(behavior_result: dict):
    """
    Full behavior analysis log – stores all module outputs.
    Schema covers 2.1 (iris gaze, EAR, blink, yaw, pitch, roll),
    2.2 (YOLO person/object), 2.3 (MediaPipe hands + gesture).
    """
    try:
        if not _db_available or _supabase is None:
            return None
        
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
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        return _supabase.table("behavior_logs").insert(data).execute()
        
    except Exception as e:
        print(f"[DB ERROR insert_behavior_log]: {e}")
        return None


def fetch_recent_logs(table: str = "proctoring_logs", limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent logs from a table, ordered by created_at DESC."""
    try:
        if not _db_available or _supabase is None:
            return []
        
        response = (
            _supabase.table(table)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"[DB ERROR fetch_recent_logs]: {e}")
        return []


def fetch_risk_stats(hours: int = 24) -> Dict[str, Any]:
    """Fetch aggregated risk statistics for the past N hours."""
    try:
        if not _db_available or _supabase is None:
            return {}
        
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
        print(f"[DB ERROR fetch_risk_stats]: {e}")
        return {}


def fetch_sessions(user_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch proctoring sessions."""
    try:
        if not _db_available or _supabase is None:
            return []
        
        query = _supabase.table("sessions").select("*").order("timestamp", desc=True).limit(limit)
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"[DB ERROR fetch_sessions]: {e}")
        return []


def fetch_reports(session_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch session reports."""
    try:
        if not _db_available or _supabase is None:
            return []
        
        query = _supabase.table("reports").select("*").order("timestamp", desc=True).limit(limit)
        
        if session_id:
            query = query.eq("session_id", session_id)
        
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"[DB ERROR fetch_reports]: {e}")
        return []


def fetch_audio_logs(user_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch audio analysis logs."""
    try:
        if not _db_available or _supabase is None:
            return []
        
        query = _supabase.table("audio_logs").select("*").order("created_at", desc=True).limit(limit)
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"[DB ERROR fetch_audio_logs]: {e}")
        return []


def fetch_events_for_session(session_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetch events for a specific session."""
    try:
        if not _db_available or _supabase is None:
            return []
        
        query = (
            _supabase.table("events")
            .select("*")
            .eq("session_id", session_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .offset(offset)
        )
        
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"[DB ERROR fetch_events_for_session]: {e}")
        return []