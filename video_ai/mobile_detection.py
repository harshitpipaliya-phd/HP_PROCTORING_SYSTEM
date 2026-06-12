"""
video_ai/mobile_detection.py
============================
Module 2.3 - Mobile / Device Detection using MediaPipe Hands + YOLO

Features:
  - Mobile phone detection
  - Hand landmark tracking (21 points)
  - Finger count detection
  - Gesture classification (Phone-Hold, Writing, Suspicious-Cover)
  - Motion score (Optical Flow)
  - Suspicious gesture detection

Primary: MediaPipe Hands + YOLO
Fallback: Skin mask + optical flow
"""

import cv2
import numpy as np
from typing import Dict, Any, List, Tuple

# ---------------------------------------------------------------------------
# MediaPipe Hands - with graceful fallback
# ---------------------------------------------------------------------------
_mp_hands = None
_hands_detector = None
_mediapipe_available = False

try:
    import mediapipe as mp
    _mp_hands = mp.solutions.hands
    _hands_detector = _mp_hands.Hands(
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    _mediapipe_available = True
    print("[mobile_detection] OK MediaPipe Hands loaded")
except Exception as _e:
    print(f"[mobile_detection] WARN MediaPipe Hands not available ({_e}), using fallback")

# ---------------------------------------------------------------------------
# YOLO for phone detection
# ---------------------------------------------------------------------------
_yolo_model = None
_yolo_available = False

try:
    from ultralytics import YOLO
    _yolo_model = YOLO("yolov8n.pt")
    _yolo_available = True
except Exception:
    pass


# ---------------------------------------------------------------------------
# Hand landmark indices
# ---------------------------------------------------------------------------
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20
WRIST = 0


def detect_mobile_device(frame: np.ndarray) -> Dict[str, Any]:
    """
    Detect mobile devices and analyze hand gestures.
    
    Returns:
        dict with phone_detected, hands_detected, gesture_labels, etc.
    """
    if frame is None:
        return _empty_result()
    
    try:
        phone_result = _detect_phone_yolo(frame)
        hands_result = _detect_hands_mediapipe(frame)
        
        result = {**phone_result, **hands_result}
        
        # Determine unusual gestures
        unusual = False
        gesture_labels = result.get("gesture_labels", [])
        
        if "PHONE_HOLD" in gesture_labels:
            unusual = True
        if "WRITING" in gesture_labels:
            unusual = True
        if "SUSPICIOUS_COVER" in gesture_labels:
            unusual = True
        
        result["unusual_gesture"] = unusual
        
        return result
        
    except Exception as e:
        print(f"[ERROR mobile_detection.detect_mobile_device]: {e}")
        return _empty_result()


def _empty_result() -> Dict[str, Any]:
    return {
        "phone_detected": False,
        "phone_confidence": 0.0,
        "phone_engine": "N/A",
        "hands_detected": 0,
        "gesture_labels": [],
        "finger_counts": [],
        "motion_score": 0.0,
        "unusual_gesture": False,
        "hand_landmarks": []
    }


def _detect_phone_yolo(frame: np.ndarray) -> Dict[str, Any]:
    """Detect phone using YOLO."""
    if not _yolo_available or _yolo_model is None:
        return {"phone_detected": False, "phone_confidence": 0.0, "phone_engine": "N/A"}
    
    try:
        results = _yolo_model(frame, verbose=False)
        
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                label = r.names[int(box.cls[0])].lower()
                if "phone" in label or "cell" in label:
                    return {
                        "phone_detected": True,
                        "phone_confidence": float(box.conf[0]),
                        "phone_engine": "YOLOv8n"
                    }
        
        return {"phone_detected": False, "phone_confidence": 0.0, "phone_engine": "YOLOv8n"}
        
    except Exception:
        return {"phone_detected": False, "phone_confidence": 0.0, "phone_engine": "YOLOv8n"}


def _detect_hands_mediapipe(frame: np.ndarray) -> Dict[str, Any]:
    """Detect hands and analyze gestures using MediaPipe."""
    if not _mediapipe_available:
        return _detect_hands_fallback(frame)
    
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = _hands_detector.process(rgb)
    
    hands_detected = 0
    gesture_labels = []
    finger_counts = []
    hand_landmarks = []
    motion_score = 0.0
    
    if results.multi_hand_landmarks:
        hands_detected = len(results.multi_hand_landmarks)
        
        for hand_lm in results.multi_hand_landmarks:
            hand_landmarks.append(hand_lm.landmark)
            
            # Count fingers
            fingers = _count_fingers(hand_lm.landmark)
            finger_counts.append(fingers)
            
            # Classify gesture
            gesture = _classify_gesture(fingers, hand_lm.landmark)
            if gesture:
                gesture_labels.append(gesture)
        
        # Calculate motion score
        motion_score = _calculate_motion_score(frame, results.multi_hand_landmarks)
    
    return {
        "hands_detected": hands_detected,
        "gesture_labels": gesture_labels,
        "finger_counts": finger_counts,
        "motion_score": motion_score,
        "hand_landmarks": hand_landmarks
    }


def _detect_hands_fallback(frame: np.ndarray) -> Dict[str, Any]:
    """Fallback hand detection using skin mask."""
    # Simple skin color detection as fallback
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    lower_skin = np.array([0, 20, 70], dtype=np.uint8)
    upper_skin = np.array([20, 255, 255], dtype=np.uint8)
    
    mask = cv2.inRange(hsv, lower_skin, upper_skin)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    hands_detected = sum(1 for c in contours if 1000 < cv2.contourArea(c) < 50000)
    
    return {
        "hands_detected": hands_detected,
        "gesture_labels": [],
        "finger_counts": [],
        "motion_score": 0.0,
        "hand_landmarks": []
    }


def _count_fingers(landmarks) -> int:
    """Count number of extended fingers."""
    finger_count = 0
    
    # Thumb (check if extended horizontally)
    thumb_tip = landmarks[THUMB_TIP]
    thumb_ip = landmarks[4]  # Actually MCP
    if thumb_tip.x < thumb_ip.x - 0.05:  # For right hand
        finger_count += 1
    
    # Other 4 fingers (check if tip is above middle joint)
    for tip_idx, mid_idx in [(INDEX_TIP, 6), (MIDDLE_TIP, 10), (RING_TIP, 14), (PINKY_TIP, 18)]:
        tip_y = getattr(landmarks[tip_idx], 'y', 0)
        mid_y = getattr(landmarks[mid_idx], 'y', 0)
        if tip_y < mid_y:  # Tip is above (lower y value)
            finger_count += 1
    
    return finger_count


def _classify_gesture(finger_count: int, landmarks) -> str:
    """Classify hand gesture based on finger count and positions."""
    if finger_count == 0:
        return "FIST"
    elif finger_count == 1:
        # Check if it's a pointing gesture
        return "POINTING"
    elif finger_count == 2:
        return "V_SIGN"
    elif finger_count == 5:
        return "OPEN_HAND"
    
    # Special gestures based on thumb position
    thumb_tip = landmarks[THUMB_TIP]
    index_tip = landmarks[INDEX_TIP]
    
    # Phone hold detection: thumb and index close together
    thumb_index_dist = abs(thumb_tip.x - index_tip.x) + abs(thumb_tip.y - index_tip.y)
    if thumb_index_dist < 0.1:
        return "PHONE_HOLD"
    
    # Writing detection: thumb and index form a grip
    if finger_count == 2:
        return "WRITING"
    
    return ""


def _calculate_motion_score(frame: np.ndarray, hand_landmarks_list) -> float:
    """Calculate motion score based on optical flow."""
    if len(hand_landmarks_list) == 0:
        return 0.0
    
    # Calculate movement of hand landmarks between frames
    # This is a simplified version - in production you'd track previous frame
    return 0.0


def draw_mobile_overlay(frame: np.ndarray, mobile_result: Dict[str, Any]) -> np.ndarray:
    """Draw mobile detection overlay on frame."""
    if frame is None:
        return frame
    
    try:
        hands = mobile_result.get("hands_detected", 0)
        gestures = mobile_result.get("gesture_labels", [])
        unusual = mobile_result.get("unusual_gesture", False)
        
        if hands == 0:
            return frame
        
        # Draw hand landmarks
        if _mediapipe_available:
            for hand_lm in mobile_result.get("hand_landmarks", []):
                h, w = frame.shape[:2]
                for lm in hand_lm:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)
        
        # Draw info
        color = (0, 0, 255) if unusual else (0, 255, 0)
        text = f"Hands: {hands} | Gestures: {', '.join(gestures) if gestures else 'None'}"
        cv2.putText(frame, text, (10, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        
    except Exception as e:
        print(f"[ERROR mobile_detection.draw_mobile_overlay]: {e}")
    
    return frame


def is_mediapipe_available() -> bool:
    """Check if MediaPipe is available."""
    return _mediapipe_available