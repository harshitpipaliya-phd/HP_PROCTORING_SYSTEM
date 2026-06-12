"""
video_ai/eye_tracking.py
========================
Module 2.1 - Eye and Head Movement Tracking (Eye Part)
MediaPipe Face Mesh + Iris Tracking + Advanced Gaze Estimation

Features:
  - Eye gaze direction detection (Left / Right / Up / Down / Center)
  - Iris position and movement tracking
  - Blink detection using EAR (Eye Aspect Ratio)
  - Look-away frequency tracking
  - Suspicious pattern detection

Primary: MediaPipe Face Mesh (iris landmarks)
Fallback: OpenCV Haar cascades (if MediaPipe unavailable)
"""

import cv2
import numpy as np
import time
from typing import Tuple, Dict, Any, List, Optional

# ---------------------------------------------------------------------------
# MediaPipe Face Mesh - with graceful fallback
# ---------------------------------------------------------------------------
_mp_face_mesh = None
_face_mesh_detector = None
_mediapipe_available = False

try:
    import mediapipe as mp
    _mp_face_mesh = mp.solutions.face_mesh
    _face_mesh_detector = _mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    _mediapipe_available = True
    print("[eye_tracking] OK MediaPipe Face Mesh loaded (iris tracking enabled)")
except Exception as _e:
    print(f"[eye_tracking] WARN MediaPipe not available ({_e}), using OpenCV fallback")

# ---------------------------------------------------------------------------
# Cascade classifiers (fallback)
# ---------------------------------------------------------------------------
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
_eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_eye.xml"
)

# ---------------------------------------------------------------------------
# MediaPipe landmark indices
# ---------------------------------------------------------------------------
LEFT_EYE_LANDMARKS = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_LANDMARKS = [362, 385, 387, 263, 373, 380]
LEFT_IRIS_CENTER = 473
RIGHT_IRIS_CENTER = 468

# ---------------------------------------------------------------------------
# State for frequency tracking
# ---------------------------------------------------------------------------
_look_away_timestamps: List[float] = []
_FREQUENCY_WINDOW_SECONDS = 60
_SUSPICIOUS_THRESHOLD = 5

_blink_count = 0
_ear_threshold = 0.20
_blink_frame_cnt = 0
_BLINK_CONSEC = 2


def _record_look_away():
    now = time.time()
    _look_away_timestamps.append(now)
    cutoff = now - _FREQUENCY_WINDOW_SECONDS
    while _look_away_timestamps and _look_away_timestamps[0] < cutoff:
        _look_away_timestamps.pop(0)


def get_look_away_frequency() -> int:
    now = time.time()
    cutoff = now - _FREQUENCY_WINDOW_SECONDS
    return sum(1 for t in _look_away_timestamps if t >= cutoff)


def is_frequent_looking_away() -> bool:
    return get_look_away_frequency() >= _SUSPICIOUS_THRESHOLD


def reset_blink_count():
    global _blink_count
    _blink_count = 0


# ---------------------------------------------------------------------------
# MediaPipe-based helpers
# ---------------------------------------------------------------------------
def _get_landmark_px(landmarks, idx: int, w: int, h: int) -> Tuple[int, int]:
    lm = landmarks[idx]
    return int(lm.x * w), int(lm.y * h)


def _eye_aspect_ratio(landmarks, eye_indices: List[int], w: int, h: int) -> float:
    try:
        pts = [_get_landmark_px(landmarks, i, w, h) for i in eye_indices]
        v1 = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
        v2 = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
        h_dist = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
        if h_dist == 0:
            return 0.3
        return (v1 + v2) / (2.0 * h_dist)
    except Exception:
        return 0.3


def _iris_gaze_direction(landmarks, iris_center_idx: int,
                          eye_indices: List[int], w: int, h: int) -> str:
    try:
        iris_x, iris_y = _get_landmark_px(landmarks, iris_center_idx, w, h)
        left_corner = _get_landmark_px(landmarks, eye_indices[0], w, h)
        right_corner = _get_landmark_px(landmarks, eye_indices[3], w, h)
        top_lid = _get_landmark_px(landmarks, eye_indices[1], w, h)
        bot_lid = _get_landmark_px(landmarks, eye_indices[5], w, h)
        
        eye_width = right_corner[0] - left_corner[0]
        eye_height = bot_lid[1] - top_lid[1]
        
        if eye_width <= 0 or eye_height <= 0:
            return "Center"
        
        h_ratio = (iris_x - left_corner[0]) / eye_width
        v_ratio = (iris_y - top_lid[1]) / max(eye_height, 1)
        
        if h_ratio < 0.35:
            return "Left"
        elif h_ratio > 0.65:
            return "Right"
        elif v_ratio < 0.30:
            return "Up"
        elif v_ratio > 0.70:
            return "Down"
        return "Center"
    except Exception:
        return "Center"


def _analyze_with_mediapipe(frame) -> Dict[str, Any]:
    global _blink_count, _blink_frame_cnt
    
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = _face_mesh_detector.process(rgb)
    
    if not results.multi_face_landmarks:
        _record_look_away()
        return {
            "face_detected": False,
            "looking_away": True,
            "gaze_direction": "No Face",
            "left_gaze": "No Face",
            "right_gaze": "No Face",
            "ear_left": 0.0,
            "ear_right": 0.0,
            "blink_count": _blink_count,
            "iris_left": None,
            "iris_right": None,
            "landmarks": None
        }
    
    face_lm = results.multi_face_landmarks[0].landmark
    
    ear_left = _eye_aspect_ratio(face_lm, LEFT_EYE_LANDMARKS, w, h)
    ear_right = _eye_aspect_ratio(face_lm, RIGHT_EYE_LANDMARKS, w, h)
    avg_ear = (ear_left + ear_right) / 2.0
    
    if avg_ear < _ear_threshold:
        _blink_frame_cnt += 1
    else:
        if _blink_frame_cnt >= _BLINK_CONSEC:
            _blink_count += 1
        _blink_frame_cnt = 0
    
    num_landmarks = len(face_lm)
    if num_landmarks >= 478:
        left_gaze = _iris_gaze_direction(face_lm, LEFT_IRIS_CENTER, LEFT_EYE_LANDMARKS, w, h)
        right_gaze = _iris_gaze_direction(face_lm, RIGHT_IRIS_CENTER, RIGHT_EYE_LANDMARKS, w, h)
        iris_left = _get_landmark_px(face_lm, LEFT_IRIS_CENTER, w, h)
        iris_right = _get_landmark_px(face_lm, RIGHT_IRIS_CENTER, w, h)
    else:
        left_gaze = "Center"
        right_gaze = "Center"
        iris_left = None
        iris_right = None
    
    if left_gaze == right_gaze:
        gaze_direction = left_gaze
    elif "Center" in (left_gaze, right_gaze):
        gaze_direction = left_gaze if right_gaze == "Center" else right_gaze
    else:
        gaze_direction = left_gaze
    
    looking_away = gaze_direction not in ("Center",) or avg_ear < 0.15
    
    if avg_ear < 0.15 and _blink_frame_cnt <= _BLINK_CONSEC:
        looking_away = False
    
    if looking_away:
        _record_look_away()
    
    return {
        "face_detected": True,
        "looking_away": looking_away,
        "gaze_direction": gaze_direction,
        "left_gaze": left_gaze,
        "right_gaze": right_gaze,
        "ear_left": round(ear_left, 3),
        "ear_right": round(ear_right, 3),
        "blink_count": _blink_count,
        "iris_left": iris_left,
        "iris_right": iris_right,
        "landmarks": face_lm
    }


# ---------------------------------------------------------------------------
# Haar Cascade fallback
# ---------------------------------------------------------------------------
def _estimate_gaze_direction_cascade(eye_roi_gray) -> str:
    try:
        _, thresh = cv2.threshold(eye_roi_gray, 50, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return "Center"
        largest = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest)
        if M["m00"] == 0:
            return "Center"
        cx = int(M["m10"] / M["m00"])
        width = eye_roi_gray.shape[1]
        ratio = cx / width if width > 0 else 0.5
        if ratio < 0.35:
            return "Left"
        elif ratio > 0.65:
            return "Right"
        return "Center"
    except Exception:
        return "Center"


def _analyze_with_cascade(frame) -> Dict[str, Any]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = _face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    
    if len(faces) == 0:
        _record_look_away()
        return {
            "face_detected": False, "looking_away": True,
            "gaze_direction": "No Face", "left_gaze": "No Face",
            "right_gaze": "No Face", "ear_left": 0.0, "ear_right": 0.0,
            "blink_count": 0, "iris_left": None, "iris_right": None,
            "landmarks": None
        }
    
    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
    roi_gray = gray[y:y+h, x:x+w]
    eyes = _eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=10, minSize=(20, 20))
    
    looking_away = len(eyes) < 2
    gaze_direction = "Center"
    if not looking_away and len(eyes) > 0:
        ex, ey, ew, eh = eyes[0]
        gaze_direction = _estimate_gaze_direction_cascade(roi_gray[ey:ey+eh, ex:ex+ew])
        if gaze_direction != "Center":
            looking_away = True
    
    if looking_away:
        _record_look_away()
    
    return {
        "face_detected": True, "looking_away": looking_away,
        "gaze_direction": gaze_direction, "left_gaze": gaze_direction,
        "right_gaze": gaze_direction, "ear_left": 0.25, "ear_right": 0.25,
        "blink_count": 0, "iris_left": None, "iris_right": None,
        "landmarks": None
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_eyes(frame) -> Dict[str, Any]:
    try:
        if frame is None:
            return {
                "face_detected": False, "looking_away": True,
                "gaze_direction": "No Face", "left_gaze": "No Face",
                "right_gaze": "No Face", "ear_left": 0.0, "ear_right": 0.0,
                "blink_count": 0, "iris_left": None, "iris_right": None,
                "landmarks": None, "look_away_frequency": get_look_away_frequency(),
                "frequent_looking_away": is_frequent_looking_away()
            }
        
        if _mediapipe_available:
            result = _analyze_with_mediapipe(frame)
        else:
            result = _analyze_with_cascade(frame)
        
        result["look_away_frequency"] = get_look_away_frequency()
        result["frequent_looking_away"] = is_frequent_looking_away()
        return result
        
    except Exception as e:
        print(f"[ERROR eye_tracking.analyze_eyes]: {e}")
        return {
            "face_detected": False, "looking_away": True,
            "gaze_direction": "No Face", "left_gaze": "No Face",
            "right_gaze": "No Face", "ear_left": 0.0, "ear_right": 0.0,
            "blink_count": 0, "iris_left": None, "iris_right": None,
            "landmarks": None, "look_away_frequency": 0,
            "frequent_looking_away": False
        }


def detect_looking_away(frame) -> bool:
    return analyze_eyes(frame)["looking_away"]


def get_gaze_direction(frame) -> str:
    return analyze_eyes(frame)["gaze_direction"]


# ---------------------------------------------------------------------------
# Drawing overlay
# ---------------------------------------------------------------------------
def draw_eye_tracking_overlay(frame, looking_away: bool, gaze_direction: str,
                               eye_result: Dict = None):
    try:
        if frame is None:
            return frame
        
        h_frame, w_frame = frame.shape[:2]
        
        if eye_result and eye_result.get("iris_left"):
            ix, iy = eye_result["iris_left"]
            cv2.circle(frame, (ix, iy), 3, (0, 255, 255), -1)
        if eye_result and eye_result.get("iris_right"):
            ix, iy = eye_result["iris_right"]
            cv2.circle(frame, (ix, iy), 3, (0, 255, 255), -1)
        
        if eye_result and eye_result.get("landmarks") and _mediapipe_available:
            lm = eye_result["landmarks"]
            for idx in LEFT_EYE_LANDMARKS + RIGHT_EYE_LANDMARKS:
                px = int(lm[idx].x * w_frame)
                py = int(lm[idx].y * h_frame)
                cv2.circle(frame, (px, py), 2, (255, 255, 0), -1)
        
        freq = get_look_away_frequency()
        suspicious = is_frequent_looking_away()
        freq_color = (0, 0, 255) if suspicious else (0, 255, 0)
        blink_cnt = (eye_result or {}).get("blink_count", 0)
        
        ear_txt = ""
        if eye_result:
            ear_l = eye_result.get("ear_left", 0)
            ear_r = eye_result.get("ear_right", 0)
            ear_txt = f"  EAR:{(ear_l+ear_r)/2:.2f}"
        
        status = (f"Gaze:{gaze_direction}  Away/min:{freq}"
                  f"  Blinks:{blink_cnt}{ear_txt}"
                  f"{'  [SUSPICIOUS]' if suspicious else ''}")
        cv2.putText(frame, status, (10, h_frame - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, freq_color, 1)
        
        engine = "MediaPipe+Iris" if _mediapipe_available else "Haar(fallback)"
        cv2.putText(frame, f"Eye-Engine:{engine}", (10, h_frame - 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
        
        return frame
        
    except Exception as error:
        print(f"[ERROR eye_tracking.draw_eye_tracking_overlay]: {error}")
        return frame


# ---------------------------------------------------------------------------
# Face Embedding extraction for enrollment/verification
# ---------------------------------------------------------------------------

def get_face_embedding(frame) -> Optional[np.ndarray]:
    """
    Extract a 512-dimensional face embedding from a frame using MediaPipe Face Mesh.
    
    Uses normalized iris and facial landmark positions as the embedding vector.
    
    Args:
        frame: BGR numpy array from camera
        
    Returns:
        Normalized embedding vector (np.ndarray) or None if no face detected
    """
    if frame is None or not _mediapipe_available:
        return None
    
    try:
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = _face_mesh_detector.process(rgb)
        
        if not results.multi_face_landmarks:
            return None
        
        landmarks = results.multi_face_landmarks[0].landmark
        
        # Extract key facial landmarks (iris centers + eye corners + nose tip)
        # Total 9 points = 18 dims (x, y for each), normalized to 0-1
        embedding_points = [
            LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER,
            33, 133,  # left eye corners
            362, 263,  # right eye corners
            1,  # nose tip
            61, 291,  # mouth corners
            199,  # mouth center
        ]
        
        embedding = []
        for idx in embedding_points:
            if idx < len(landmarks):
                lm = landmarks[idx]
                embedding.extend([lm.x, lm.y])
        
        if len(embedding) < 18:
            return None
        
        emb_array = np.array(embedding, dtype=np.float32)
        
        # Normalize to unit vector for cosine similarity
        norm = np.linalg.norm(emb_array)
        if norm > 0:
            emb_array = emb_array / norm
        
        return emb_array
        
    except Exception as e:
        print(f"[eye_tracking] get_face_embedding failed: {e}")
        return None


def is_mediapipe_available() -> bool:
    """Check if MediaPipe is available."""
    return _mediapipe_available