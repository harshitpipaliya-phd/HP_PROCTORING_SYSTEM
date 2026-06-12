"""
ai_workers/models/face_analyzer.py
====================================
Face and eye tracking wrapper.
Wraps video_ai.eye_tracking and video_ai.head_pose.

Fix: Added FaceAnalyzer class with analyze_faces() method that was missing,
     causing a crash in ai_workers/app.py /verify/face endpoint.
"""

from typing import Dict, Any, Optional
import numpy as np


class FaceAnalyzer:
    """
    Wrapper class for face analysis operations.
    Provides analyze_faces() method used by /verify/face endpoint.
    Falls back gracefully when face_recognition/dlib are unavailable.
    """

    def analyze_faces(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Analyze faces in a frame and return embedding + face count.

        Returns:
            {
                "faces": int,           # number of faces detected
                "embedding": list,      # face embedding vector (128-d or MediaPipe)
                "locations": list,      # face bounding boxes
                "success": bool,
            }
        """
        if frame is None:
            return {"faces": 0, "embedding": None, "locations": [], "success": False}

        # --- Strategy 1: face_recognition (dlib-based, most accurate) ---
        try:
            import face_recognition  # type: ignore
            rgb = frame[:, :, ::-1]  # BGR→RGB
            locations = face_recognition.face_locations(rgb, model="hog")
            if not locations:
                return {"faces": 0, "embedding": None, "locations": [], "success": True}
            encodings = face_recognition.face_encodings(rgb, locations)
            embedding = encodings[0].tolist() if encodings else None
            return {
                "faces": len(locations),
                "embedding": embedding,
                "locations": [
                    {"top": t, "right": r, "bottom": b, "left": l}
                    for t, r, b, l in locations
                ],
                "success": True,
                "backend": "face_recognition",
            }
        except ImportError:
            pass
        except Exception:
            pass

        # --- Strategy 2: MediaPipe FaceMesh (no dlib needed) ---
        try:
            from video_ai.eye_tracking import get_face_embedding
            embedding = get_face_embedding(frame)
            if embedding is None:
                return {"faces": 0, "embedding": None, "locations": [], "success": True}
            return {
                "faces": 1,
                "embedding": embedding.tolist() if hasattr(embedding, "tolist") else list(embedding),
                "locations": [],
                "success": True,
                "backend": "mediapipe",
            }
        except Exception:
            pass

        # --- Strategy 3: OpenCV Haar cascade (last resort) ---
        try:
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(cascade_path)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            if len(faces) == 0:
                return {"faces": 0, "embedding": None, "locations": [], "success": True}

            # Build a rough embedding from face region statistics
            x, y, w, h = faces[0]
            face_roi = gray[y:y + h, x:x + w]
            face_resized = cv2.resize(face_roi, (16, 16)).flatten().astype(float)
            face_resized = face_resized / (np.linalg.norm(face_resized) + 1e-8)
            return {
                "faces": len(faces),
                "embedding": face_resized.tolist(),
                "locations": [{"top": y, "right": x + w, "bottom": y + h, "left": x}],
                "success": True,
                "backend": "opencv_haar",
            }
        except Exception as exc:
            return {"faces": 0, "embedding": None, "locations": [], "success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Module-level helper functions (backward compat)
# ---------------------------------------------------------------------------

def analyze_face(frame: np.ndarray) -> Dict[str, Any]:
    """
    Full face analysis: eye tracking + head pose.
    Returns combined dict.
    """
    from video_ai.eye_tracking import analyze_eyes
    from video_ai.head_pose import analyze_head_pose
    eye_result = analyze_eyes(frame)
    pose_result = analyze_head_pose(frame)
    return {"eye_head": eye_result, "head_pose": pose_result}


def enroll_face(image_b64: str, candidate_id: str) -> Dict[str, Any]:
    """
    Enroll a face embedding for a candidate.
    Stores the embedding as a JSON dict for later comparison.
    """
    import base64
    import cv2

    try:
        img_bytes = base64.b64decode(image_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            return {"success": False, "error": "Image decode failed"}

        analyzer = FaceAnalyzer()
        result = analyzer.analyze_faces(image)
        embedding = result.get("embedding")
        if embedding is None:
            return {"success": False, "error": "No face detected"}

        from core.session import enroll_candidate
        enroll_candidate(
            name="",
            email="",
            external_id=candidate_id,
            face_embedding={"embedding": embedding},
        )
        return {"success": True, "candidate_id": candidate_id, "embedding": embedding}
    except Exception as e:
        return {"success": False, "error": str(e)}


def verify_face(frame: np.ndarray, candidate_id: str) -> Dict[str, Any]:
    """
    Verify a face against an enrolled candidate embedding.
    Returns match score and boolean.
    """
    from core.session import get_candidate

    cand = get_candidate(candidate_id)
    if not cand or not cand.get("face_embedding"):
        return {"success": False, "error": "Candidate not enrolled", "match": False}

    analyzer = FaceAnalyzer()
    result = analyzer.analyze_faces(frame)
    embedding = result.get("embedding")
    if embedding is None:
        return {"success": False, "error": "No face detected", "match": False}

    enrolled = np.array(cand["face_embedding"]["embedding"])
    live = np.array(embedding)
    score = float(np.dot(live, enrolled) / (
        np.linalg.norm(live) * np.linalg.norm(enrolled) + 1e-8
    ))
    match = score >= 0.85
    return {
        "success": True, "match": match, "score": score,
        "candidate_id": candidate_id, "threshold": 0.85,
    }
