"""
video_ai/processor.py
======================
Unified Video AI Processor - Combines all video analysis modules.

Integrates:
  - Eye tracking (MediaPipe Face Mesh + Iris)
  - Head pose (MediaPipe + SolvePnP yaw/pitch/roll)
  - Person detection (YOLOv8n)
  - Object detection (YOLOv8n – phone, book, notes, laptop)
  - Mobile / phone detection (YOLO + contour heuristic)
  - Hand gesture detection (MediaPipe Hands)
  - Evidence screenshot capture on violation
  - Database logging with full behavior data
  - Professional HUD overlay
"""

import cv2
import numpy as np
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

from video_ai.eye_tracking import analyze_eyes, draw_eye_tracking_overlay
from video_ai.head_pose import analyze_head_pose, draw_head_pose_overlay
from video_ai.attention import calculate_attention, get_attention_label
from video_ai.person_detection import detect_persons, draw_person_overlay
from video_ai.object_detection import detect_objects, draw_object_overlay
from video_ai.mobile_detection import detect_mobile_device, draw_mobile_overlay
from video_ai.frame_utils import capture_evidence_frame
from database import log_behavior_event


# ============================================================================
# Risk Scoring Configuration — delegates to single authoritative source
# ============================================================================
from video_ai.risk_engine import get_active_weights as _get_active_weights

def _BASE_RISK_GETTER():
    """Return current active risk weights (per-exam/org configurable)."""
    return _get_active_weights()

# Backward-compat alias (used as dict in _compute_risk)
class _BaseRiskProxy:
    def get(self, key, default=0):
        return _BASE_RISK_GETTER().get(key, default)
    def __getitem__(self, key):
        return _BASE_RISK_GETTER()[key]

_BASE_RISK = _BaseRiskProxy()

# Event audit trail
_event_log: List[Dict[str, Any]] = []
_MAX_EVENT_LOG = 500

# Behavior history for trends
_behavior_history: List[Dict[str, Any]] = []
_HISTORY_WINDOW = 300


# ============================================================================
# Event Logging
# ============================================================================
def _append_event(event_type: str, detail: str, risk_added: int, confidence: float = 1.0):
    """Append an event to the in-memory audit trail."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "detail": detail,
        "risk_added": risk_added,
        "confidence": round(confidence, 3)
    }
    _event_log.append(entry)
    if len(_event_log) > _MAX_EVENT_LOG:
        _event_log.pop(0)


def get_event_log() -> List[Dict[str, Any]]:
    """Return a copy of the current event audit trail."""
    return list(_event_log)


def clear_event_log():
    """Clear the audit trail."""
    _event_log.clear()


def get_behavior_trends() -> Dict[str, Any]:
    """Return behavioral trend analytics for the monitoring session."""
    if not _behavior_history:
        return {"status": "no_data", "samples": 0}
    
    scores = [b.get("risk_score", 0) for b in _behavior_history]
    looks = [b for b in _behavior_history if b.get("looking_away")]
    
    return {
        "samples": len(_behavior_history),
        "avg_risk_score": round(sum(scores) / len(scores), 1),
        "max_risk_score": max(scores),
        "attention_trend": "stable" if max(scores) - min(scores) < 20 else "variable",
        "look_away_rate": round(len(looks) / len(_behavior_history) * 100, 1),
        "risk_spike_count": sum(1 for s in scores if s >= 50),
        "time_window_seconds": len(_behavior_history) / 30,
    }


def _update_behavior_history(behavior: Dict[str, Any]):
    """Track behavior trends over time."""
    global _behavior_history
    _behavior_history.append({
        "timestamp": datetime.now().isoformat(),
        "risk_score": behavior.get("risk_score", 0),
        "attention_score": behavior.get("attention", {}).get("score", 0),
        "looking_away": behavior.get("eye_head", {}).get("looking_away", False),
        "head_direction": behavior.get("head_pose", {}).get("direction", "No Face"),
    })
    if len(_behavior_history) > _HISTORY_WINDOW:
        _behavior_history.pop(0)


# ============================================================================
# Main Processor
# ============================================================================
def analyze_frame(frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Process a single frame through all AI behavior analysis modules.
    
    Args:
        frame: BGR numpy array from camera
        
    Returns:
        (annotated_frame, response_payload)
    """
    t_start = time.time()
    
    result: Dict[str, Any] = {
        "success": True,
        "eye_head": {},
        "head_pose": {},
        "persons": {},
        "objects": {},
        "mobile": {},
        "attention": {},
        "risk_score": 0,
        "risk_breakdown": {},
        "risk_flags": [],
        "events": [],
        "evidence": {},
        "annotated_frame": frame,
        "processing_ms": 0.0
    }
    
    if frame is None:
        return frame, _error_payload("Invalid frame received")
    
    try:
        # ── 2.1 Eye Analysis ──────────────────────────────────────────────
        eye_result = analyze_eyes(frame)
        looking_away = eye_result["looking_away"]
        gaze_direction = eye_result["gaze_direction"]
        freq_look_away = eye_result.get("frequent_looking_away", False)
        blink_count = eye_result.get("blink_count", 0)
        ear_avg = (eye_result.get("ear_left", 0.25) + eye_result.get("ear_right", 0.25)) / 2.0
        
        # ── 2.1 Head Pose ─────────────────────────────────────────────────
        pose_result = analyze_head_pose(frame)
        head_direction = pose_result["direction"]
        yaw = pose_result.get("yaw", 0.0)
        pitch = pose_result.get("pitch", 0.0)
        roll = pose_result.get("roll", 0.0)
        
        # ── Attention Score ───────────────────────────────────────────────
        attention_score = calculate_attention(
            looking_away=looking_away,
            head_direction=head_direction,
        )
        attention_label = get_attention_label(attention_score)
        
        result["eye_head"] = eye_result
        result["head_pose"] = pose_result
        result["attention"] = {"score": attention_score, "label": attention_label}
        
        # ── 2.2 Person + Object Detection ────────────────────────────────
        persons_result = detect_persons(frame)
        objects_result = detect_objects(frame)
        
        result["persons"] = persons_result
        result["objects"] = objects_result
        
        # ── 2.3 Mobile / Device Detection ────────────────────────────────
        mobile_result = detect_mobile_device(frame)
        result["mobile"] = mobile_result
        
        # ── Dynamic Risk Scoring ──────────────────────────────────────────
        risk, breakdown, flags, frame_events = _calculate_risk(
            eye_result, pose_result, persons_result, objects_result, mobile_result,
            looking_away, gaze_direction, freq_look_away, head_direction,
            yaw, pitch, ear_avg, blink_count
        )
        
        result["risk_score"] = min(risk, 100)
        result["risk_breakdown"] = breakdown
        result["risk_flags"] = flags
        result["events"] = frame_events
        
        # ── Evidence Capture (on high risk) ──────────────────────────────
        if risk >= 50 and flags:
            evidence = capture_evidence_frame(frame, label="_".join(flags[:2]))
            evidence["risk_score"] = min(risk, 100)
            evidence["flags"] = flags
            result["evidence"] = evidence
        
        # ── Update Behavior Trends ────────────────────────────────────────
        _update_behavior_history(result)
        
        # ── Database Logging ──────────────────────────────────────────────
        try:
            log_behavior_event(result)
        except Exception as db_err:
            print(f"[DATABASE ERROR]: {db_err}")
        
        # ── Annotate Frame ────────────────────────────────────────────────
        annotated = frame.copy()
        annotated = draw_eye_tracking_overlay(annotated, looking_away, gaze_direction, eye_result)
        annotated = draw_head_pose_overlay(annotated, head_direction, pose_result)
        annotated = draw_person_overlay(annotated, persons_result)
        annotated = draw_object_overlay(annotated, objects_result)
        annotated = draw_mobile_overlay(annotated, mobile_result)
        annotated = _draw_hud(annotated, result)
        result["annotated_frame"] = annotated
        
    except Exception as e:
        print(f"[ERROR processor.analyze_frame]: {e}")
    
    result["processing_ms"] = round((time.time() - t_start) * 1000, 2)
    return result.get("annotated_frame", frame), result


def _calculate_risk(
    eye_result: Dict, pose_result: Dict, persons_result: Dict,
    objects_result: Dict, mobile_result: Dict,
    looking_away: bool, gaze_direction: str, freq_look_away: bool,
    head_direction: str, yaw: float, pitch: float, ear_avg: float, blink_count: int
) -> Tuple[int, Dict, List[str], List[Dict]]:
    """Calculate dynamic risk score based on all detection results."""
    risk = 0
    breakdown = {}
    flags = []
    frame_events = []
    
    def add_risk(key: str, label: str, confidence: float = 1.0, detail: str = ""):
        nonlocal risk
        base = _BASE_RISK.get(key, 0)
        score = int(base * confidence)
        risk += score
        breakdown[key] = score
        flags.append(label)
        _append_event(key, detail or label, score, confidence)
        frame_events.append({"type": key, "label": label, "risk": score, "confidence": confidence})
    
    # Multiple persons
    if persons_result.get("multiple_persons"):
        cnt = persons_result.get("person_count", 2)
        confs = persons_result.get("confidence_scores", [0.8])
        avg_c = sum(confs) / len(confs) if confs else 0.8
        add_risk("multiple_persons", f"MULTIPLE_PERSONS({cnt})", avg_c, f"{cnt} persons detected")
    
    # Phone detected
    phone_det = (objects_result.get("phone_detected") or mobile_result.get("phone_detected"))
    if phone_det:
        phone_conf = mobile_result.get("phone_confidence", 0.5)
        add_risk("phone_detected", "PHONE_DETECTED", max(phone_conf, 0.5))
    
    # Book detected
    if objects_result.get("book_detected"):
        add_risk("book_detected", "BOOK_DETECTED", 0.6)
    
    # Notes detected
    if objects_result.get("notes_detected") and not objects_result.get("book_detected"):
        add_risk("notes_detected", "NOTES_DETECTED", 0.6)
    
    # Laptop detected
    if objects_result.get("laptop_detected"):
        add_risk("laptop_detected", "LAPTOP_DETECTED", 0.6)
    
    # Looking away
    if looking_away:
        add_risk("looking_away", f"LOOKING_AWAY({gaze_direction})", 1.0)
    
    # Head not center
    if head_direction not in ("Center", "No Face"):
        magnitude = min(1.0, max(abs(yaw), abs(pitch)) / 45.0)
        conf = max(0.5, magnitude)
        add_risk("head_not_center", f"HEAD_TURNED_{head_direction.upper()}", conf)
    
    # Frequent look away
    if freq_look_away:
        freq = eye_result.get("look_away_frequency", 0)
        add_risk("frequent_look_away", "FREQUENT_LOOK_AWAY", 1.0, f"{freq} look-aways in 60s")
    
    # Unusual gesture
    if mobile_result.get("unusual_gesture"):
        add_risk("unusual_gesture", "UNUSUAL_HAND_GESTURE", 0.85)
    
    # Phone hold gesture
    if "PHONE_HOLD" in mobile_result.get("gesture_labels", []):
        add_risk("phone_hold_gesture", "PHONE_HOLD_GESTURE", 0.9)
    
    # Writing gesture
    if "WRITING" in mobile_result.get("gesture_labels", []):
        add_risk("writing_gesture", "WRITING_GESTURE", 0.75)
    
    # Low blink rate
    if 0 < ear_avg < 0.18 and blink_count == 0:
        add_risk("low_blink_rate", "LOW_BLINK_RATE", 0.6)
    
    return risk, breakdown, flags, frame_events


def _error_payload(msg: str) -> Dict[str, Any]:
    """BUG FIX: Return flat structure matching normal result so callers
    (app.py reads result.get('risk_score'), not result['data']['risk_score'])
    don't KeyError on error frames."""
    return {
        "success": False,
        "message": msg,
        "eye_head": {"looking_away": True, "gaze_direction": "No Face"},
        "head_pose": {"direction": "No Face", "yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        "persons": {"person_count": 0, "multiple_persons": False},
        "objects": {"prohibited_objects": [], "phone_detected": False,
                    "book_detected": False, "laptop_detected": False},
        "mobile": {"phone_detected": False, "phone_confidence": 0.0,
                   "hands_detected": 0, "unusual_gesture": False, "gesture_labels": []},
        "attention": {"score": 0, "label": "DISENGAGED"},
        "risk_score": 0,
        "risk_breakdown": {},
        "risk_flags": ["PROCESSING_ERROR"],
        "events": [],
        "evidence": {},
        "annotated_frame": None,
        "processing_ms": 0.0,
    }


def detect_all(frame: np.ndarray) -> Dict[str, Any]:
    """Legacy compatibility function."""
    _, result = analyze_frame(frame)
    return result


# ============================================================================
# Professional HUD Drawing
# ============================================================================
def _draw_hud(frame: np.ndarray, result: Dict[str, Any]) -> np.ndarray:
    """Draw a professional multi-section HUD panel on the frame."""
    GREEN = (0, 200, 0)
    RED = (0, 0, 220)
    BLUE = (220, 100, 20)
    YELLOW = (0, 220, 220)
    WHITE = (240, 240, 240)
    ORANGE = (0, 140, 255)
    GRAY = (160, 160, 160)
    TEAL = (180, 200, 0)
    
    h_frame = frame.shape[0]
    
    # Semi-transparent panel
    overlay = frame.copy()
    panel_w, panel_h = 460, 380
    cv2.rectangle(overlay, (6, 6), (panel_w, panel_h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    cv2.rectangle(frame, (6, 6), (panel_w, panel_h), WHITE, 1)
    
    # Title bar
    cv2.rectangle(frame, (6, 6), (panel_w, 30), (40, 40, 80), -1)
    cv2.putText(frame, "AI BEHAVIOR ANALYSIS MONITOR",
                (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.58, YELLOW, 2)
    
    y = 46
    
    # 2.1 Eye & Head
    cv2.putText(frame, "[ 2.1 EYE & HEAD TRACKING ]",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, TEAL, 1)
    y += 18
    
    eye_head = result.get("eye_head", {})
    looking_away = eye_head.get("looking_away", False)
    gaze_direction = eye_head.get("gaze_direction", "N/A")
    
    la_col = RED if looking_away else GREEN
    cv2.putText(frame, f"  Looking Away : {looking_away}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, la_col, 1)
    y += 16
    
    cv2.putText(frame, f"  Gaze         : {gaze_direction}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
    y += 16
    
    head_pose = result.get("head_pose", {})
    head_direction = head_pose.get("direction", "N/A")
    yaw = head_pose.get("yaw", 0.0)
    pitch = head_pose.get("pitch", 0.0)
    roll = head_pose.get("roll", 0.0)
    
    hd_col = RED if head_direction not in ("Center", "No Face") else GREEN
    cv2.putText(frame, f"  Head         : {head_direction}  Y:{yaw:.1f} P:{pitch:.1f} R:{roll:.1f}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, hd_col, 1)
    y += 16
    
    ear_l = eye_head.get("ear_left", 0.0)
    ear_r = eye_head.get("ear_right", 0.0)
    blinks = eye_head.get("blink_count", 0)
    freq = eye_head.get("look_away_frequency", 0)
    cv2.putText(frame, f"  EAR:{(ear_l+ear_r)/2:.2f}  Blinks:{blinks}  Away/min:{freq}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, GRAY, 1)
    y += 16
    
    attention = result.get("attention", {})
    att_score = attention.get("score", 0)
    att_label = attention.get("label", "N/A")
    att_col = GREEN if att_score >= 70 else (ORANGE if att_score >= 40 else RED)
    cv2.putText(frame, f"  Attention     : {att_score}/100  [{att_label}]",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, att_col, 1)
    y += 20
    
    # 2.2 Person & Object
    cv2.line(frame, (10, y), (panel_w-4, y), (60, 60, 60), 1)
    y += 8
    cv2.putText(frame, "[ 2.2 PERSON & OBJECT DETECTION ]",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, TEAL, 1)
    y += 18
    
    persons = result.get("persons", {})
    p_cnt = persons.get("person_count", 0)
    p_col = RED if persons.get("multiple_persons") else GREEN
    p_eng = persons.get("detection_engine", "?")
    cv2.putText(frame, f"  Persons: {p_cnt}  {'[UNAUTHORIZED]' if persons.get('multiple_persons') else '[OK]'}  [{p_eng}]",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, p_col, 1)
    y += 16
    
    objects = result.get("objects", {})
    objs = objects.get("prohibited_objects", [])
    o_col = RED if objs else GREEN
    o_str = ", ".join(objs[:3]) if objs else "None"
    if len(o_str) > 30:
        o_str = o_str[:27] + "..."
    cv2.putText(frame, f"  Objects: {o_str}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, o_col, 1)
    y += 16
    
    flags_det = []
    if objects.get("phone_detected"): flags_det.append("Phone")
    if objects.get("book_detected"): flags_det.append("Book")
    if objects.get("notes_detected"): flags_det.append("Notes")
    if objects.get("laptop_detected"): flags_det.append("Laptop")
    det_str = " | ".join(flags_det) if flags_det else "None"
    det_col = RED if flags_det else GREEN
    cv2.putText(frame, f"  Detected: {det_str}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, det_col, 1)
    y += 20
    
    # 2.3 Mobile / Gesture
    cv2.line(frame, (10, y), (panel_w-4, y), (60, 60, 60), 1)
    y += 8
    cv2.putText(frame, "[ 2.3 MOBILE / DEVICE DETECTION ]",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, TEAL, 1)
    y += 18
    
    mobile = result.get("mobile", {})
    ph = mobile.get("phone_detected", False)
    ph_c = mobile.get("phone_confidence", 0.0)
    ph_col = RED if ph else GREEN
    cv2.putText(frame, f"  Phone: {'DETECTED' if ph else 'None'} {ph_c:.0%}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, ph_col, 1)
    y += 16
    
    ug = mobile.get("unusual_gesture", False)
    hands = mobile.get("hands_detected", 0)
    gestures = ", ".join(mobile.get("gesture_labels", [])) or "None"
    ug_col = RED if ug else GREEN
    cv2.putText(frame, f"  Hands:{hands}  Gesture:{gestures[:25]}  {'[SUSPICIOUS]' if ug else '[OK]'}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, ug_col, 1)
    y += 16
    
    ms = mobile.get("motion_score", 0.0)
    cv2.putText(frame, f"  Motion Score: {ms:.4f}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, GRAY, 1)
    y += 20
    
    # Risk Score
    cv2.line(frame, (10, y), (panel_w-4, y), WHITE, 1)
    y += 10
    
    risk_score = result.get("risk_score", 0)
    r_col = RED if risk_score >= 50 else (ORANGE if risk_score >= 25 else GREEN)
    cv2.putText(frame, f"RISK SCORE: {risk_score}/100",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, r_col, 2)
    
    # Risk bar
    bar_x, bar_y, bar_w, bar_h = 10, y + 8, panel_w - 20, 10
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+bar_h), (40, 40, 40), -1)
    filled = int(bar_w * risk_score / 100)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x+filled, bar_y+bar_h), r_col, -1)
    y += 25
    
    # Risk flags
    risk_flags = result.get("risk_flags", [])
    flags_str = " | ".join(risk_flags) if risk_flags else "No Flags"
    if len(flags_str) > 60:
        flags_str = flags_str[:57] + "..."
    cv2.putText(frame, f"Flags: {flags_str}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.36, YELLOW, 1)
    y += 14
    
    # Processing time
    proc_ms = result.get("processing_ms", 0.0)
    cv2.putText(frame, f"Proc: {proc_ms:.1f}ms",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.34, GRAY, 1)
    
    return frame