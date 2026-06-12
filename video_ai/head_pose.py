"""
video_ai/head_pose.py
=====================
Module 2.1 - Eye and Head Movement Tracking (Head Pose Part)
MediaPipe Face Mesh + SolvePnP for accurate yaw/pitch/roll

Features:
  - Head direction detection (Center / Left / Right / Up / Down / No Face)
  - Yaw, Pitch, Roll angle estimation
  - Real-time head movement monitoring

Primary: MediaPipe Face Mesh 3D landmarks + SolvePnP
Fallback: OpenCV Haar + SolvePnP heuristic
"""

import cv2
import numpy as np
from typing import Dict, Any, Tuple

# ---------------------------------------------------------------------------
# MediaPipe - with graceful fallback
# ---------------------------------------------------------------------------
_mp_face_mesh = None
_face_mesh_hp = None
_mediapipe_available = False

try:
    import mediapipe as mp
    _mp_face_mesh = mp.solutions.face_mesh
    _face_mesh_hp = _mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    _mediapipe_available = True
    print("[head_pose] OK MediaPipe Face Mesh loaded for head pose")
except Exception as _e:
    print(f"[head_pose] WARN MediaPipe not available ({_e}), using OpenCV fallback")

# ---------------------------------------------------------------------------
# Cascade classifiers (fallback)
# ---------------------------------------------------------------------------
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
_profile_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_profileface.xml"
)
_eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_eye.xml"
)
_smile_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_smile.xml"
)

# 3D model points for head pose estimation
_MP_SELECTED_IDX = [1, 152, 263, 33, 287, 57]
_MODEL_POINTS_3D = np.array([
    (0.0, 0.0, 0.0),
    (0.0, -63.6, -12.5),
    (-43.3, 32.7, -26.0),
    (43.3, 32.7, -26.0),
    (-28.9, -28.9, -24.1),
    (28.9, -28.9, -24.1),
], dtype=np.float64)

# Thresholds for direction determination
_YAW_THRESH = 15
_PITCH_THRESH = 12
_ROLL_THRESH = 20


def _build_camera_matrix(frame) -> np.ndarray:
    h, w = frame.shape[:2]
    focal = w
    return np.array([
        [focal, 0, w / 2],
        [0, focal, h / 2],
        [0, 0, 1]
    ], dtype=np.float64)


def _angles_to_direction(yaw: float, pitch: float) -> str:
    if abs(yaw) > _YAW_THRESH:
        return "Right" if yaw > 0 else "Left"
    if abs(pitch) > _PITCH_THRESH:
        return "Up" if pitch > 0 else "Down"
    return "Center"


# ---------------------------------------------------------------------------
# MediaPipe-based head pose
# ---------------------------------------------------------------------------
def _mediapipe_head_pose(frame) -> Dict[str, Any]:
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = _face_mesh_hp.process(rgb)
    
    if not results.multi_face_landmarks:
        return {
            "direction": "No Face",
            "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
            "face_detected": False,
            "nose_tip": None
        }
    
    landmarks = results.multi_face_landmarks[0].landmark
    
    image_points_2d = np.array([
        (landmarks[idx].x * w, landmarks[idx].y * h)
        for idx in _MP_SELECTED_IDX
    ], dtype=np.float64)
    
    cam_matrix = _build_camera_matrix(frame)
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)
    
    success, rvec, tvec = cv2.solvePnP(
        _MODEL_POINTS_3D, image_points_2d,
        cam_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE
    )
    
    if not success:
        return {
            "direction": "Center",
            "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
            "face_detected": True,
            "nose_tip": (int(landmarks[1].x * w), int(landmarks[1].y * h))
        }
    
    rmat, _ = cv2.Rodrigues(rvec)
    angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
    pitch = angles[0]
    yaw = angles[1]
    roll = angles[2]
    
    direction = _angles_to_direction(yaw, pitch)
    nose_tip = (int(landmarks[1].x * w), int(landmarks[1].y * h))
    
    return {
        "direction": direction,
        "yaw": round(float(yaw), 2),
        "pitch": round(float(pitch), 2),
        "roll": round(float(roll), 2),
        "face_detected": True,
        "nose_tip": nose_tip,
        "rvec": rvec,
        "tvec": tvec,
        "landmarks": landmarks,
        "img_w": w, "img_h": h
    }


# ---------------------------------------------------------------------------
# Haar cascade fallback
# ---------------------------------------------------------------------------
def _face_centre_head_pose(frame, face_rect) -> str:
    x, y, w, h = face_rect
    face_cx = x + w // 2
    face_cy = y + h // 2
    frame_cx = frame.shape[1] // 2
    frame_cy = frame.shape[0] // 2
    dx = face_cx - frame_cx
    dy = face_cy - frame_cy
    h_thresh = frame.shape[1] * 0.15
    v_thresh = frame.shape[0] * 0.12
    if abs(dx) > h_thresh:
        return "Right" if dx > 0 else "Left"
    if dy < -v_thresh:
        return "Up"
    if dy > v_thresh:
        return "Down"
    return "Center"


def _solvepnp_cascade_head_pose(frame, face_rect) -> Dict[str, Any]:
    try:
        x, y, w, h = face_rect
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        roi = gray[y:y+h, x:x+w]
        
        eyes = _eye_cascade.detectMultiScale(roi, 1.1, 8, minSize=(20, 20))
        smiles = _smile_cascade.detectMultiScale(roi, 1.7, 22, minSize=(25, 15))
        
        if len(eyes) < 2:
            direction = _face_centre_head_pose(frame, face_rect)
            return {"direction": direction, "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                    "face_detected": True, "nose_tip": (x + w//2, y + h//2)}
        
        eyes_sorted = sorted(eyes, key=lambda e: e[0])
        le, re = eyes_sorted[0], eyes_sorted[1]
        
        def to_frame(ex, ey, ew, eh):
            return (x + ex + ew//2, y + ey + eh//2)
        
        le_pt = to_frame(*le)
        re_pt = to_frame(*re)
        nose_pt = (x + w//2, y + h//2)
        chin_pt = (x + w//2, y + h)
        
        if len(smiles) > 0:
            s = smiles[0]
            m_l = (x + s[0], y + s[1] + s[3]//2)
            m_r = (x + s[0] + s[2], y + s[1] + s[3]//2)
        else:
            m_l = (x + w//4, y + int(h * 0.8))
            m_r = (x + 3*w//4, y + int(h * 0.8))
        
        image_points = np.array([nose_pt, chin_pt, le_pt, re_pt, m_l, m_r], dtype=np.float64)
        
        cam_matrix = _build_camera_matrix(frame)
        dist_coeffs = np.zeros((4, 1))
        success, rvec, tvec = cv2.solvePnP(
            _MODEL_POINTS_3D, image_points,
            cam_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )
        
        if not success:
            direction = _face_centre_head_pose(frame, face_rect)
            return {"direction": direction, "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                    "face_detected": True, "nose_tip": nose_pt}
        
        rmat, _ = cv2.Rodrigues(rvec)
        angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
        pitch, yaw, roll = angles[0], angles[1], angles[2]
        direction = _angles_to_direction(yaw, pitch)
        
        return {
            "direction": direction,
            "yaw": round(float(yaw), 2),
            "pitch": round(float(pitch), 2),
            "roll": round(float(roll), 2),
            "face_detected": True,
            "nose_tip": nose_pt
        }
        
    except Exception:
        direction = _face_centre_head_pose(frame, face_rect)
        return {"direction": direction, "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                "face_detected": True, "nose_tip": None}


def _cascade_head_pose(frame) -> Dict[str, Any]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    
    if len(faces) == 0:
        return {"direction": "No Face", "yaw": 0.0, "pitch": 0.0, "roll": 0.0,
                "face_detected": False, "nose_tip": None}
    
    face_rect = max(faces, key=lambda r: r[2] * r[3])
    return _solvepnp_cascade_head_pose(frame, face_rect)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_head_pose(frame) -> Dict[str, Any]:
    try:
        if frame is None:
            return {"direction": "No Face", "yaw": 0.0, "pitch": 0.0,
                    "roll": 0.0, "face_detected": False, "nose_tip": None}
        
        if _mediapipe_available:
            return _mediapipe_head_pose(frame)
        else:
            return _cascade_head_pose(frame)
            
    except Exception as error:
        print(f"[ERROR head_pose.analyze_head_pose]: {error}")
        return {"direction": "No Face", "yaw": 0.0, "pitch": 0.0,
                "roll": 0.0, "face_detected": False, "nose_tip": None}


def get_head_pose(frame) -> str:
    return analyze_head_pose(frame)["direction"]


# ---------------------------------------------------------------------------
# Drawing overlay
# ---------------------------------------------------------------------------
def draw_head_pose_overlay(frame, head_direction: str, pose_result: Dict = None):
    try:
        if frame is None:
            return frame
        
        if pose_result and pose_result.get("face_detected") and \
                pose_result.get("nose_tip") and _mediapipe_available and \
                "rvec" in pose_result:
            try:
                nose_tip = pose_result["nose_tip"]
                w_img = pose_result.get("img_w", frame.shape[1])
                h_img = pose_result.get("img_h", frame.shape[0])
                
                direction_3d = np.array([[0, 0, -60]], dtype=np.float64)
                cam_matrix = _build_camera_matrix(frame)
                dist_coeffs = np.zeros((4, 1))
                proj, _ = cv2.projectPoints(
                    direction_3d,
                    pose_result["rvec"], pose_result["tvec"],
                    cam_matrix, dist_coeffs
                )
                proj_pt = (int(proj[0][0][0]), int(proj[0][0][1]))
                color = (0, 255, 0) if head_direction == "Center" else (0, 100, 255)
                cv2.arrowedLine(frame, nose_tip, proj_pt, color, 3, tipLength=0.3)
            except Exception:
                pass
        
        elif not _mediapipe_available:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
            for (x, y, w, h) in faces:
                cx, cy = x + w // 2, y + h // 2
                arrow_map = {
                    "Left": (cx - 40, cy),
                    "Right": (cx + 40, cy),
                    "Up": (cx, cy - 40),
                    "Down": (cx, cy + 40),
                    "Center": (cx, cy)
                }
                end = arrow_map.get(head_direction, (cx, cy))
                color = (0, 255, 0) if head_direction == "Center" else (0, 100, 255)
                cv2.arrowedLine(frame, (cx, cy), end, color, 3, tipLength=0.4)
        
        if pose_result:
            yaw = pose_result.get("yaw", 0.0)
            pitch = pose_result.get("pitch", 0.0)
            roll = pose_result.get("roll", 0.0)
            color = (0, 255, 0) if head_direction == "Center" else (0, 100, 255)
            cv2.putText(frame, f"Head:{head_direction}  Y:{yaw:.1f} P:{pitch:.1f} R:{roll:.1f}",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)
        else:
            color = (0, 255, 0) if head_direction == "Center" else (0, 100, 255)
            cv2.putText(frame, f"Head: {head_direction}",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        
        return frame
        
    except Exception as error:
        print(f"[ERROR head_pose.draw_head_pose_overlay]: {error}")
        return frame


def is_mediapipe_available() -> bool:
    """Check if MediaPipe is available."""
    return _mediapipe_available