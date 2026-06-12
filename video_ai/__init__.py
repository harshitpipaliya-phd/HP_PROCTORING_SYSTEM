"""
video_ai/__init__.py
====================
Video AI Proctoring Module - Face/Gaze/Person/Object/Mobile Detection
"""

from video_ai.processor import analyze_frame, detect_all, get_event_log, get_behavior_trends
from video_ai.risk_engine import (
    generate_report, generate_report_text, get_ai_verdict, get_violation_summary
)
from video_ai.frame_utils import capture_evidence_frame

__all__ = [
    "analyze_frame",
    "detect_all",
    "get_event_log",
    "get_behavior_trends",
    "get_violation_summary",
    "generate_report",
    "generate_report_text",
    "get_ai_verdict",
    "capture_evidence_frame",
]