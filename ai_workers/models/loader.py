"""
ai_workers/models/loader.py
============================
Singleton model loader cache.

Ensures heavy models (YOLO, MediaPipe, audio classifier) are loaded
once and shared across all worker invocations.
"""

from typing import Any, Optional, Dict
import threading


class ModelCache:
    """Thread-safe singleton for AI model instances."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache: Dict[str, Any] = {}
                    cls._instance._loading: Dict[str, bool] = {}
        return cls._instance

    def get(self, key: str, loader):
        """Return cached model or load it via ``loader``."""
        if key in self._cache:
            return self._cache[key]
        if self._loading.get(key):
            # Another thread is loading
            import time
            while self._loading.get(key):
                time.sleep(0.01)
            return self._cache.get(key)
        self._loading[key] = True
        try:
            model = loader()
            self._cache[key] = model
            return model
        finally:
            self._loading[key] = False

    def clear(self):
        self._cache.clear()
        self._loading.clear()


model_cache = ModelCache()


def get_yolo_detector():
    return model_cache.get("yolo", lambda: _load_yolo())


def get_face_analyzer():
    return model_cache.get("face_analyzer", lambda: _load_face_analyzer())


def get_audio_classifier():
    return model_cache.get("audio_classifier", lambda: _load_audio_classifier())


def _load_yolo():
    from ultralytics import YOLO
    return YOLO("yolov8n.pt")


def _load_face_analyzer():
    import mediapipe as mp
    mp_face = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5,
    )
    mp_hands = mp.solutions.hands.Hands(
        max_num_hands=2, min_detection_confidence=0.5,
    )
    return {"face_mesh": mp_face, "hands": mp_hands}


def _load_audio_classifier():
    from audio_proctoring.classifier import load_model
    return load_model()
