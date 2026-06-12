"""
ai_workers/video_analyzer.py
=============================
Video AI worker — frame-by-frame analysis offloaded from main API.
Wraps video_ai.processor.analyze_frame for queue-based execution.
"""

from typing import Dict, Any, Tuple
import numpy as np
import time


def analyze_frame_worker(frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Analyze a single frame — callable from Celery task or direct invocation.
    """
    from video_ai.processor import analyze_frame
    t0 = time.time()
    annotated, result = analyze_frame(frame)
    result["worker_ms"] = round((time.time() - t0) * 1000, 2)
    return annotated, result


def detect_violations(result: Dict[str, Any]) -> list:
    """
    Extract violation events from a frame analysis result.
    """
    violations = []
    flags = result.get("risk_flags", [])
    breakdown = result.get("risk_breakdown", {})
    for f in flags:
        risk = breakdown.get(f.lower(), 0) or breakdown.get(f, 0)
        violations.append({"type": f, "risk": risk})
    return violations
