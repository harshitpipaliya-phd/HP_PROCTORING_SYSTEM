"""
ai_workers/models/yolo_detector.py
====================================
YOLOv8 object/person detection wrapper.
Wraps video_ai.object_detection and video_ai.person_detection.
Original: video_ai/object_detection.py & person_detection.py
"""

from typing import Dict, Any, List, Optional
import numpy as np


def detect_persons(frame: np.ndarray, conf: float = 0.5) -> Dict[str, Any]:
    """
    Detect persons in a frame using YOLOv8 (or Haar+HOG fallback).
    Returns dict with person_count, multiple_persons flag, etc.
    """
    from video_ai.person_detection import detect_persons as _detect
    return _detect(frame, conf=conf)


def detect_objects(frame: np.ndarray, conf: float = 0.4) -> Dict[str, Any]:
    """
    Detect prohibited objects (phone, book, notes, laptop) using YOLOv8.
    Returns dict with detected object flags.
    """
    from video_ai.object_detection import detect_objects as _detect
    return _detect(frame, conf=conf)


def detect_mobile(frame: np.ndarray, conf: float = 0.4) -> Dict[str, Any]:
    """
    Mobile phone + hand gesture detection.
    Wraps video_ai.mobile_detection.detect_mobile_device.
    """
    from video_ai.mobile_detection import detect_mobile_device as _detect
    return _detect(frame, conf=conf)
