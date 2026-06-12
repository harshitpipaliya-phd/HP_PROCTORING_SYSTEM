"""
video_ai/object_detection.py
============================
Module 2.2 - Object Detection (Phone, Book, Notes, Laptop)
Uses YOLOv8n for detection with fallback to contour heuristic.

Features:
  - Prohibited object detection
  - Multi-object class detection
  - Confidence scoring
  - Screen state detection
"""

import cv2
import numpy as np
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# YOLOv8n - with graceful fallback
# ---------------------------------------------------------------------------
_yolo_model = None
_yolo_available = False

# COCO class indices for relevant objects
_COCO_CLASSES = {
    0: "person",
    63: "laptop",   # COCO v5/YOLOv8 index
    67: "cell phone",  # BUG FIX: was missing — phone never detected by class ID
    72: "laptop",      # alternate COCO index
    73: "remote",
    74: "keyboard",
    84: "book",        # BUG FIX: was missing — book never detected by class ID
}

try:
    from ultralytics import YOLO
    _yolo_model = YOLO("yolov8n.pt")
    _yolo_available = True
    print("[object_detection] OK YOLOv8n loaded")
except Exception as _e:
    print(f"[object_detection] WARN YOLOv8n not available ({_e}), using heuristic fallback")


# Prohibited objects to detect
_PROHIBITED_LABELS = ["cell phone", "phone", "book", "laptop", "remote", "keyboard"]
_PROHIBITED_CLASSES = {63, 67, 72, 73, 74, 84}  # BUG FIX: added cell phone (67) and book (84)


def detect_objects(frame: np.ndarray) -> Dict[str, Any]:
    """
    Detect prohibited objects in the frame.
    
    Returns:
        dict with prohibited_objects, phone_detected, book_detected, etc.
    """
    if frame is None:
        return _empty_result()
    
    try:
        if _yolo_available:
            return _detect_with_yolo(frame)
        else:
            return _detect_with_heuristic(frame)
    except Exception as e:
        print(f"[ERROR object_detection.detect_objects]: {e}")
        return _empty_result()


def _empty_result() -> Dict[str, Any]:
    return {
        "prohibited_objects": [],
        "phone_detected": False,
        "book_detected": False,
        "notes_detected": False,
        "laptop_detected": False,
        "detection_engine": "N/A",
        "object_details": [],
        "bboxes": []
    }


def _detect_with_yolo(frame: np.ndarray) -> Dict[str, Any]:
    """Detect objects using YOLOv8n."""
    results = _yolo_model(frame, verbose=False)
    
    prohibited = []
    details = []
    phone_detected = False
    book_detected = False
    notes_detected = False
    laptop_detected = False
    
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label = r.names[cls_id].lower()
            
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            obj_detail = {
                "class_id": cls_id,
                "label": label,
                "confidence": conf,
                "bbox": (x1, y1, x2, y2)
            }
            details.append(obj_detail)
            
            # Check prohibited objects
            if label in _PROHIBITED_LABELS or cls_id in _PROHIBITED_CLASSES:
                prohibited.append(label)
                
                if "phone" in label or "cell" in label:
                    phone_detected = True
                elif "book" in label:
                    book_detected = True
                elif "laptop" in label:
                    laptop_detected = True
                elif "notes" in label or "paper" in label:
                    notes_detected = True
    
    # Deduplicate
    prohibited = list(set(prohibited))
    
    return {
        "prohibited_objects": prohibited,
        "phone_detected": phone_detected,
        "book_detected": book_detected,
        "notes_detected": notes_detected,
        "laptop_detected": laptop_detected,
        "detection_engine": "YOLOv8n",
        "object_details": details,
        "bboxes": [d["bbox"] for d in details]
    }


def _detect_with_heuristic(frame: np.ndarray) -> Dict[str, Any]:
    """Detect objects using contour heuristic fallback."""
    prohibited = []
    details = []
    phone_detected = False
    book_detected = False
    laptop_detected = False
    
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Simple heuristic: detect rectangular objects
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 127, 255, cv2.THRESH_BINARY)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 1000:  # Skip small contours
            continue
        
        x, y, w_cnt, h_cnt = cv2.boundingRect(cnt)
        aspect = w_cnt / h_cnt if h_cnt > 0 else 0
        
        # Phone-like rectangle (taller than wide)
        if 0.4 < aspect < 0.8 and area < 50000:
            prohibited.append("phone")
            phone_detected = True
            details.append({
                "class_id": -1,
                "label": "phone",
                "confidence": 0.5,
                "bbox": (x, y, x + w_cnt, y + h_cnt)
            })
        
        # Book-like rectangle (nearly square)
        elif 0.7 < aspect < 1.4 and area > 5000:
            prohibited.append("book")
            book_detected = True
            details.append({
                "class_id": -1,
                "label": "book",
                "confidence": 0.4,
                "bbox": (x, y, x + w_cnt, y + h_cnt)
            })
    
    prohibited = list(set(prohibited))
    
    return {
        "prohibited_objects": prohibited,
        "phone_detected": phone_detected,
        "book_detected": book_detected,
        "notes_detected": False,
        "laptop_detected": laptop_detected,
        "detection_engine": "Heuristic",
        "object_details": details,
        "bboxes": [d["bbox"] for d in details]
    }


def draw_object_overlay(frame: np.ndarray, objects_result: Dict[str, Any]) -> np.ndarray:
    """Draw object detection overlay on frame."""
    if frame is None:
        return frame
    
    try:
        details = objects_result.get("object_details", [])
        
        if not details:
            return frame
        
        for obj in details:
            x1, y1, x2, y2 = obj["bbox"]
            label = obj["label"]
            conf = obj["confidence"]
            
            color = (0, 165, 255)  # Orange for objects
            if "phone" in label:
                color = (0, 0, 255)  # Red for phone
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label} {conf:.0%}"
            cv2.putText(frame, text, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
    except Exception as e:
        print(f"[ERROR object_detection.draw_object_overlay]: {e}")
    
    return frame


def is_yolo_available() -> bool:
    """Check if YOLOv8n is available."""
    return _yolo_available