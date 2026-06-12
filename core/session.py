"""
core/session.py
===============
Unified session management for HP Proctoring Backend.
Coordinates video AI, audio, and screen monitoring into a single session.

Enhancements (v2.1):
- Persistent session state in Supabase (proctoring_sessions table)
- Candidate enrollment / lookup
- Exam / organization concept
- Multi-session registry (by session_id)
- Redis-style atomic risk score via threading.Lock + DB flush every 10s
- Full lifecycle: create → active → paused → completed / terminated
"""

import threading
import uuid
import time
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


from core.config import get_settings

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProctoringSession:
    """
    Unified proctoring session combining video AI, audio, and screen monitoring.
    Now includes exam_id, organization_id, candidate_id for full normalized support.
    """
    session_id: str
    user_id: str
    exam_id: Optional[str] = None
    organization_id: Optional[str] = None
    candidate_id: Optional[str] = None

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    # Video AI state
    total_frames: int = 0
    risk_score: int = 0
    focus_score: int = 100
    attention_breaks: int = 0
    tab_switches: int = 0

    # Person/Object state
    multiple_persons_detected: int = 0
    prohibited_objects_detected: List[str] = field(default_factory=list)

    # Audio state
    audio_active: bool = False
    speech_count: int = 0
    anomaly_count: int = 0
    background_voice_count: int = 0

    # Screen state
    monitor_changes: int = 0
    screenshots_captured: int = 0

    # Violations
    violations: List[Dict[str, Any]] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)

    # Event logs
    events: List[Dict[str, Any]] = field(default_factory=list)

    # Internal
    _active: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # Pending DB flush tracking
    _last_db_flush: float = field(default_factory=time.time)
    _DB_FLUSH_INTERVAL: float = 10.0  # seconds

    def to_summary(self) -> Dict[str, Any]:
        """Generate session summary."""
        duration = (self.end_time or time.time()) - self.start_time

        if self.risk_score >= 80:       # BUG FIX: aligned with spec §6.2 (was 70)
            risk_level = "HIGH"
        elif self.risk_score >= 50:     # BUG FIX: aligned with spec §6.2 (was 40)
            risk_level = "MEDIUM"
        elif self.risk_score >= 25:
            risk_level = "LOW"
        else:
            risk_level = "MINIMAL"

        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "exam_id": self.exam_id,
            "organization_id": self.organization_id,
            "candidate_id": self.candidate_id,
            "duration_seconds": round(duration, 1),
            "risk_level": risk_level,
            "total_risk_score": self.risk_score,
            "focus_score": self.focus_score,
            "total_frames": self.total_frames,
            "violations_count": len(self.violations),
            "tab_switches": self.tab_switches,
            "attention_breaks": self.attention_breaks,
            "multiple_persons_events": self.multiple_persons_detected,
            "prohibited_objects": list(set(self.prohibited_objects_detected)),
            "audio_anomalies": self.anomaly_count,
            "background_voice_events": self.background_voice_count,
            "monitor_changes": self.monitor_changes,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
        }

    def add_violation(self, violation_type: str, details: Dict[str, Any]):
        """Add a violation to the session."""
        with self._lock:
            self.violations.append({
                "timestamp": datetime.now().isoformat(),
                "type": violation_type,
                "details": details,
            })
            self.risk_flags.append(violation_type)

    def add_event(self, event_type: str, data: Any):
        """Add an event to the session log."""
        with self._lock:
            self.events.append({
                "timestamp": datetime.now().isoformat(),
                "type": event_type,
                "data": data,
            })

    def maybe_flush_to_db(self):
        """Flush risk_score to DB every 10 seconds (replaces Redis INCRBY pattern)."""
        now = time.time()
        if now - self._last_db_flush >= self._DB_FLUSH_INTERVAL:
            self._last_db_flush = now
            _persist_session_update(self)


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------

def _persist_session_create(session: ProctoringSession):
    """Upsert session record in Supabase proctoring_sessions table."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return
        data = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "exam_id": session.exam_id,
            "organization_id": session.organization_id,
            "candidate_id": session.candidate_id,
            "status": "active",
            "risk_score": session.risk_score,
            "focus_score": session.focus_score,
            "start_time": datetime.fromtimestamp(session.start_time, tz=timezone.utc).isoformat(),
            "total_frames": session.total_frames,
            "violations_count": len(session.violations),
            "tab_switches": session.tab_switches,
            "attention_breaks": session.attention_breaks,
            "metadata": json.dumps({}),
        }
        _supabase.table("proctoring_sessions").upsert(
            data, conflict_columns=["session_id"]
        ).execute()
    except Exception as e:
        print(f"[session] persist create failed: {e}")


def _persist_session_update(session: ProctoringSession):
    """Update live risk/focus scores in DB (10-second flush)."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return
        _supabase.table("proctoring_sessions").update({
            "risk_score": session.risk_score,
            "focus_score": session.focus_score,
            "total_frames": session.total_frames,
            "violations_count": len(session.violations),
            "tab_switches": session.tab_switches,
            "attention_breaks": session.attention_breaks,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("session_id", session.session_id).execute()
    except Exception as e:
        print(f"[session] persist update failed: {e}")


def _persist_session_end(session: ProctoringSession, reason: str):
    """Mark session as completed/terminated in DB."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return
        _supabase.table("proctoring_sessions").update({
            "status": "completed" if reason == "manual" else "terminated",
            "risk_score": session.risk_score,
            "focus_score": session.focus_score,
            "total_frames": session.total_frames,
            "violations_count": len(session.violations),
            "tab_switches": session.tab_switches,
            "attention_breaks": session.attention_breaks,
            "end_time": datetime.fromtimestamp(
                session.end_time or time.time(), tz=timezone.utc).isoformat(),
            "duration_seconds": round(
                (session.end_time or time.time()) - session.start_time, 1),
            "stop_reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("session_id", session.session_id).execute()
    except Exception as e:
        print(f"[session] persist end failed: {e}")


# ---------------------------------------------------------------------------
# Candidate enrollment helpers
# ---------------------------------------------------------------------------

def enroll_candidate(
    name: str,
    email: str,
    external_id: str = None,
    organization_id: str = None,
    face_embedding: dict = None,
) -> Dict[str, Any]:
    """
    Create or update a candidate record.
    Returns candidate dict or error.
    """
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            cid = str(uuid.uuid4())
            return {
                "candidate_id": cid,
                "name": name,
                "email": email,
                "enrolled": True,
                "note": "DB unavailable — in-memory only",
            }
        data = {
            "name": name,
            "email": email,
            "external_id": external_id or str(uuid.uuid4()),
            "organization_id": organization_id,
            "enrolled": True,
            "face_embedding": json.dumps(face_embedding) if face_embedding else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = _supabase.table("candidates").upsert(
            data, on_conflict="organization_id,external_id"
        ).execute()
        if resp.data:
            return {"candidate_id": resp.data[0]["id"], **resp.data[0]}
        return {"error": "Upsert returned no data"}
    except Exception as e:
        return {"error": str(e)}


def get_candidate(candidate_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a candidate record by UUID."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return None
        resp = _supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()
        return resp.data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Multi-session registry
# ---------------------------------------------------------------------------
_session_registry: Dict[str, ProctoringSession] = {}
_registry_lock = threading.Lock()

# Legacy single-session globals (kept for backward compat)
_session_state: Dict[str, Any] = {
    "active": False,
    "session_id": None,
    "user_id": None,
    "start_time": None,
    "risk_score": 0,
    "focus_score": 100,
    "attention_breaks": 0,
    "tab_switches": 0,
    "violations": [],
    "total_frames": 0,
    "fps": 0.0,
}
_current_session: Optional[ProctoringSession] = None
_session_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Periodic background task loops (H3, H4, H5)
# ---------------------------------------------------------------------------

SCREENSHOT_INTERVAL_SECONDS: float = 30.0    # spec: every 30s unconditionally
REVERIFICATION_INTERVAL_SECONDS: float = 600.0  # spec: every 10 minutes
RISK_FLUSH_INTERVAL_SECONDS: float = 10.0    # spec: Redis→DB every 10s


def _screenshot_interval_loop(sess: "ProctoringSession") -> None:
    """
    H3 — Capture a screenshot every 30 seconds while the session is active.
    Uploads to Cloudinary and inserts a row into recordings (type=screenshot).
    Spec Section 5, Phase 2: 'Screenshots: every 30s unconditionally'.
    """
    import time as _time
    try:
        from screen_monitoring.capture import capture_screenshot
    except Exception:
        return  # screen capture unavailable in this environment

    while sess._active:
        _time.sleep(SCREENSHOT_INTERVAL_SECONDS)
        if not sess._active:
            break
        try:
            screenshot_path = capture_screenshot()
            if screenshot_path:
                sess.screenshots_captured += 1
                # Optional Cloudinary upload — non-blocking, best-effort
                try:
                    from api.services.media_storage import upload_screenshot
                    url = upload_screenshot(
                        screenshot_path,
                        session_id=sess.session_id,
                        label="periodic_screenshot",
                    )
                    # Persist to recordings table
                    try:
                        from database.client import _supabase, _db_available
                        if _db_available and _supabase:
                            _supabase.table("recordings").insert({
                                "session_id": sess.session_id,
                                "type": "screenshot",
                                "cloudinary_url": url,
                                "captured_at": datetime.now(timezone.utc).isoformat(),
                            }).execute()
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass


def _reverification_interval_loop(sess: "ProctoringSession") -> None:
    """
    H4 — Re-verify candidate identity every 10 minutes via face comparison.
    Calls /verify/face on the AI worker (or directly via face_analyzer when
    the AI worker is colocated). Fires 'face_mismatch' event on failure.
    Spec Section 8, Phase 2 (Re-verification module).
    """
    import time as _time
    import os as _os
    import httpx as _httpx

    ai_worker_url = _os.getenv("AI_WORKER_URL", "")

    while sess._active:
        _time.sleep(REVERIFICATION_INTERVAL_SECONDS)
        if not sess._active:
            break
        if not sess.candidate_id:
            continue
        try:
            # Capture a screenshot for re-verification frame
            try:
                from screen_monitoring.capture import capture_screenshot
                shot_path = capture_screenshot()
            except Exception:
                continue

            if not shot_path:
                continue

            import base64, cv2, numpy as np
            frame = cv2.imread(shot_path)
            if frame is None:
                continue
            _, buf = cv2.imencode(".jpg", frame)
            frame_b64 = base64.b64encode(buf).decode()

            # Call AI worker /verify/face
            internal_key = _os.getenv("INTERNAL_API_KEY", "")
            if ai_worker_url and internal_key:
                resp = _httpx.post(
                    f"{ai_worker_url.rstrip('/')}/verify/face",
                    json={"candidate_id": sess.candidate_id, "frame_b64": frame_b64},
                    headers={"X-Internal-API-Key": internal_key},
                    timeout=10.0,
                )
                result = resp.json() if resp.status_code == 200 else {}
            else:
                # Colocated: call directly
                from ai_workers.models.face_analyzer import FaceAnalyzer
                fa = FaceAnalyzer()
                result = fa.verify_against_db(sess.candidate_id, frame)

            match = result.get("match", True)  # default safe: don't flag if result unknown
            similarity = result.get("similarity", 1.0)

            if not match:
                sess.add_event("face_mismatch", {
                    "similarity": similarity,
                    "threshold": 0.6,
                    "source": "10min_reverification",
                })
        except Exception:
            pass


def _risk_score_flush_loop(sess: "ProctoringSession") -> None:
    """
    H5 — Flush risk_score from Redis/in-memory to PostgreSQL every 10 seconds.
    Prevents DB contention during high-frequency event bursts.
    Spec Section 7: 'flushed to PostgreSQL every 10 seconds via background worker'.
    """
    import time as _time
    while sess._active:
        _time.sleep(RISK_FLUSH_INTERVAL_SECONDS)
        if not sess._active:
            break
        try:
            sess.maybe_flush_to_db()
        except Exception:
            pass
    # Final flush on session end
    try:
        sess.maybe_flush_to_db()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_session(
    session_id: Optional[str] = None,
    user_id: str = "default_user",
    exam_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
) -> str:
    """Start a new proctoring session (persistent + in-memory)."""
    global _current_session, _session_state

    with _session_lock:
        if _session_state["active"]:
            return _session_state["session_id"]

        sid = session_id or str(uuid.uuid4())

        sess = ProctoringSession(
            session_id=sid,
            user_id=user_id,
            exam_id=exam_id,
            organization_id=organization_id,
            candidate_id=candidate_id,
        )
        sess._active = True

        _current_session = sess

        _session_state.update({
            "active": True,
            "session_id": sid,
            "user_id": user_id,
            "exam_id": exam_id,
            "organization_id": organization_id,
            "candidate_id": candidate_id,
            "start_time": time.time(),
            "risk_score": 0,
            "focus_score": 100,
            "attention_breaks": 0,
            "tab_switches": 0,
            "violations": [],
            "total_frames": 0,
            "fps": 0.0,
        })

        # Register in multi-session registry
        with _registry_lock:
            _session_registry[sid] = sess

        # Persist to DB in background
        threading.Thread(target=_persist_session_create, args=(sess,), daemon=True).start()

        # ── Periodic background tasks ────────────────────────────────────────
        # H3: Screenshot capture every 30 seconds (spec Section 5, Phase 2)
        threading.Thread(
            target=_screenshot_interval_loop,
            args=(sess,),
            daemon=True,
            name=f"screenshot-{sid[:8]}",
        ).start()

        # H4: Face re-verification every 10 minutes (spec Section 8, Phase 2)
        threading.Thread(
            target=_reverification_interval_loop,
            args=(sess,),
            daemon=True,
            name=f"reverify-{sid[:8]}",
        ).start()

        # H5: Redis→PostgreSQL risk score flush every 10 seconds
        threading.Thread(
            target=_risk_score_flush_loop,
            args=(sess,),
            daemon=True,
            name=f"riskflush-{sid[:8]}",
        ).start()

        return sid


def stop_session(reason: str = "manual") -> Dict[str, Any]:
    """Stop the current proctoring session."""
    global _current_session, _session_state

    with _session_lock:
        if not _session_state["active"]:
            return {"error": "No active session"}

        end_time = time.time()

        if _current_session:
            _current_session.end_time = end_time
            _current_session._active = False
            summary = _current_session.to_summary()
            summary["stop_reason"] = reason
            threading.Thread(
                target=_persist_session_end,
                args=(_current_session, reason),
                daemon=True,
            ).start()
        else:
            summary = {
                "session_id": _session_state["session_id"],
                "stop_reason": reason,
                "duration_seconds": end_time - (_session_state["start_time"] or end_time),
            }

        _session_state["active"] = False
        _session_state["stopped"] = True
        _session_state["stop_reason"] = reason

        return summary


def get_current_session() -> Optional[ProctoringSession]:
    return _current_session


def get_session_by_id(session_id: str) -> Optional[ProctoringSession]:
    """Look up any session (active or recently stopped) by ID."""
    with _registry_lock:
        return _session_registry.get(session_id)


def get_session_status() -> Dict[str, Any]:
    global _session_state

    with _session_lock:
        status = dict(_session_state)

        if _current_session:
            status.update({
                "risk_score": _current_session.risk_score,
                "focus_score": _current_session.focus_score,
                "attention_breaks": _current_session.attention_breaks,
                "tab_switches": _current_session.tab_switches,
                "violations": _current_session.violations,
                "total_frames": _current_session.total_frames,
                "exam_id": _current_session.exam_id,
                "organization_id": _current_session.organization_id,
                "candidate_id": _current_session.candidate_id,
            })

        return status


def update_session_risk(score: int, flags: List[str] = None):
    """Update the session risk score and flags, flush to DB and Redis every 10s."""
    global _current_session, _session_state

    with _session_lock:
        _session_state["risk_score"] = max(_session_state["risk_score"], score)

        if flags:
            for flag in flags:
                if flag not in _session_state["violations"]:
                    _session_state["violations"].append(flag)

        if _current_session:
            _current_session.risk_score = max(_current_session.risk_score, score)
            if flags:
                _current_session.risk_flags.extend(
                    [f for f in flags if f not in _current_session.risk_flags]
                )
            # Atomic Redis increment for distributed workers
            _sync_risk_to_redis(_current_session.session_id, score, flags)
            # Periodic DB flush (10s)
            _current_session.maybe_flush_to_db()


def _sync_risk_to_redis(session_id: str, score: int, flags: List[str] = None):
    """Atomically increment risk in Redis if available."""
    try:
        from video_ai.risk_engine import redis_incrby_risk, redis_set_risk
        delta = score
        redis_incrby_risk(session_id, delta)
    except Exception:
        pass


def record_tab_switch():
    global _current_session, _session_state

    with _session_lock:
        _session_state["tab_switches"] = _session_state.get("tab_switches", 0) + 1
        _session_state["risk_score"] = min(100, _session_state["risk_score"] + 15)

        if _current_session:
            _current_session.tab_switches += 1
            _current_session.risk_score = min(100, _current_session.risk_score + 15)
            _current_session.add_violation("TAB_SWITCH", {"count": _current_session.tab_switches})
            _current_session.maybe_flush_to_db()


def record_attention_break():
    global _current_session, _session_state

    with _session_lock:
        _session_state["attention_breaks"] = _session_state.get("attention_breaks", 0) + 1
        _session_state["focus_score"] = max(0, _session_state["focus_score"] - 5)

        if _current_session:
            _current_session.attention_breaks += 1
            _current_session.focus_score = max(0, _current_session.focus_score - 5)
            _current_session.add_violation(
                "ATTENTION_BREAK", {"count": _current_session.attention_breaks}
            )
            _current_session.maybe_flush_to_db()


def record_face_absent():
    """Record a face_absent event — candidate not visible in frame."""
    global _current_session, _session_state
    _WEIGHT = 20  # matches DEFAULT_RISK_WEIGHTS["face_absent"]
    with _session_lock:
        _session_state["risk_score"] = min(100, _session_state.get("risk_score", 0) + _WEIGHT)
        if _current_session:
            _current_session.risk_score = min(100, _current_session.risk_score + _WEIGHT)
            _current_session.add_violation("FACE_ABSENT", {"weight": _WEIGHT})
            _current_session.maybe_flush_to_db()


def record_window_blur():
    """Record a window_blur event — browser window lost focus."""
    global _current_session, _session_state
    _WEIGHT = 10  # matches DEFAULT_RISK_WEIGHTS["window_blur"]
    with _session_lock:
        _session_state["risk_score"] = min(100, _session_state.get("risk_score", 0) + _WEIGHT)
        _session_state["focus_score"] = max(0, _session_state.get("focus_score", 100) - 5)
        if _current_session:
            _current_session.risk_score = min(100, _current_session.risk_score + _WEIGHT)
            _current_session.focus_score = max(0, _current_session.focus_score - 5)
            _current_session.add_violation("WINDOW_BLUR", {"weight": _WEIGHT})
            _current_session.maybe_flush_to_db()


def record_fullscreen_exit():
    """Record a fullscreen_exit event — candidate exited required fullscreen."""
    global _current_session, _session_state
    _WEIGHT = 15  # matches DEFAULT_RISK_WEIGHTS["fullscreen_exit"]
    with _session_lock:
        _session_state["risk_score"] = min(100, _session_state.get("risk_score", 0) + _WEIGHT)
        if _current_session:
            _current_session.risk_score = min(100, _current_session.risk_score + _WEIGHT)
            _current_session.add_violation("FULLSCREEN_EXIT", {"weight": _WEIGHT})
            _current_session.maybe_flush_to_db()


def reset_session():
    global _current_session, _session_state

    with _session_lock:
        _current_session = None
        _session_state = {
            "active": False,
            "session_id": None,
            "user_id": None,
            "start_time": None,
            "risk_score": 0,
            "focus_score": 100,
            "attention_breaks": 0,
            "tab_switches": 0,
            "violations": [],
            "total_frames": 0,
            "fps": 0.0,
        }


# ---------------------------------------------------------------------------
# Exam / Organization helpers
# ---------------------------------------------------------------------------

def create_exam(
    name: str,
    organization_id: str = None,
    duration_minutes: int = 60,
    risk_weights: dict = None,
    proctoring_config: dict = None,
) -> Dict[str, Any]:
    """Create an exam record in Supabase."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return {"exam_id": str(uuid.uuid4()), "name": name, "note": "DB unavailable"}
        data = {
            "name": name,
            "organization_id": organization_id,
            "duration_minutes": duration_minutes,
            "risk_weights": json.dumps(risk_weights or {}),
            "proctoring_config": json.dumps(proctoring_config or {}),
        }
        resp = _supabase.table("exams").insert(data).execute()
        if resp.data:
            return {"exam_id": resp.data[0]["id"], **resp.data[0]}
        return {"error": "Insert returned no data"}
    except Exception as e:
        return {"error": str(e)}


def create_organization(name: str, slug: str, settings: dict = None) -> Dict[str, Any]:
    """Create an organization record."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return {"organization_id": str(uuid.uuid4()), "name": name, "note": "DB unavailable"}
        data = {
            "name": name,
            "slug": slug,
            "settings": json.dumps(settings or {}),
        }
        resp = _supabase.table("organizations").upsert(data, on_conflict="slug").execute()
        if resp.data:
            return {"organization_id": resp.data[0]["id"], **resp.data[0]}
        return {"error": "Insert returned no data"}
    except Exception as e:
        return {"error": str(e)}
