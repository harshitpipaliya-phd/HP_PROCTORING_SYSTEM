"""
video_ai/person_detection.py
=============================
Module 2.2 - Person Detection using YOLOv8n

Features:
  - Real-time person detection
  - Multiple person tracking
  - Confidence scoring
  - Detection engine status

Primary: YOLOv8n (Ultralytics)
Fallback: OpenCV Haar cascade + contour heuristic
"""

import cv2
import numpy as np
from typing import Dict, Any, List, Tuple

# ---------------------------------------------------------------------------
# YOLOv8n - with graceful fallback
# ---------------------------------------------------------------------------
_yolo_model = None
_yolo_available = False

try:
    from ultralytics import YOLO
    _yolo_model = YOLO("yolov8n.pt")
    _yolo_available = True
    print("[person_detection] OK YOLOv8n loaded")
except Exception as _e:
    print(f"[person_detection] WARN YOLOv8n not available ({_e}), using fallback")

# Fallback cascade
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def detect_persons(frame: np.ndarray) -> Dict[str, Any]:
    """
    Detect persons in the frame.
    
    Returns:
        dict with person_count, multiple_persons, confidence_scores, etc.
    """
    if frame is None:
        return {
            "person_count": 0,
            "multiple_persons": False,
            "unauthorized": False,
            "detection_engine": "N/A",
            "confidence_scores": [],
            "bboxes": []
        }
    
    try:
        if _yolo_available:
            return _detect_with_yolo(frame)
        else:
            return _detect_with_cascade(frame)
    except Exception as e:
        print(f"[ERROR person_detection.detect_persons]: {e}")
        return {
            "person_count": 0,
            "multiple_persons": False,
            "unauthorized": False,
            "detection_engine": "error",
            "confidence_scores": [],
            "bboxes": []
        }


def _detect_with_yolo(frame: np.ndarray) -> Dict[str, Any]:
    """Detect persons using YOLOv8n."""
    results = _yolo_model(frame, verbose=False)
    
    persons = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            # Person class in COCO is 0
            if cls_id == 0:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                persons.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": conf
                })
    
    count = len(persons)
    confs = [p["confidence"] for p in persons]
    
    return {
        "person_count": count,
        "multiple_persons": count > 1,
        "unauthorized": count > 1,
        "detection_engine": "YOLOv8n",
        "confidence_scores": confs,
        "bboxes": [p["bbox"] for p in persons],
        "details": persons
    }


def _detect_with_cascade(frame: np.ndarray) -> Dict[str, Any]:
    """Detect persons using Haar cascade fallback."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    
    faces = _face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    
    count = len(faces)
    
    return {
        "person_count": count,
        "multiple_persons": count > 1,
        "unauthorized": count > 1,
        "detection_engine": "Haar+Cascade",
        "confidence_scores": [0.6] * count if count > 0 else [],
        "bboxes": [tuple(f) for f in faces],
        "details": [{"bbox": tuple(f), "confidence": 0.6} for f in faces]
    }


def draw_person_overlay(frame: np.ndarray, persons_result: Dict[str, Any]) -> np.ndarray:
    """Draw person detection overlay on frame."""
    if frame is None:
        return frame
    
    try:
        bboxes = persons_result.get("bboxes", [])
        count = persons_result.get("person_count", 0)
        
        if count == 0:
            return frame
        
        color = (0, 0, 255) if count > 1 else (0, 255, 0)
        
        for bbox in bboxes:
            x1, y1, x2, y2 = bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, "PERSON", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Label
        label = f"Persons: {count}"
        cv2.putText(frame, label, (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
    except Exception as e:
        print(f"[ERROR person_detection.draw_person_overlay]: {e}")
    
    return frame


def is_yolo_available() -> bool:
    """Check if YOLOv8n is available."""
    return _yolo_available