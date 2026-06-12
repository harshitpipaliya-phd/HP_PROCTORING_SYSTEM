"""
ai_workers/models/audio_classifier.py
=======================================
Audio classifier loader wrapper.
Original: audio_proctoring/classifier.py
"""

from typing import Any, Dict, Optional


def load_model(model_path: str = None) -> Any:
    """Load the audio classification model (joblib / sklearn)."""
    from audio_proctoring.classifier import load_model as _load
    return _load(model_path)


def classify_audio_segments(audio_path: str) -> Dict[str, Any]:
    """Classify audio segments (speech, anomaly, background voice)."""
    from audio_proctoring.classifier import classify
    return classify(audio_path)
