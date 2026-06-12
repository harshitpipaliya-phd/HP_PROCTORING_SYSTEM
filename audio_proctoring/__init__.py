"""
audio_proctoring/__init__.py
============================
Audio Proctoring Module - Voice Activity and Speaker Detection

Features:
  - Voice activity detection
  - Background voice detection
  - Unauthorized speaker detection
  - Audio anomaly detection
  - Session monitoring
"""

from audio_proctoring.stream import (
    analyze_audio_file,
    MonitoringSession,
    StreamState,
    is_stream_available,
)
from audio_proctoring.classifier import (
    classify_audio,
    analyze_segments,
    extract_features,
    detect_voice_activity,
)
from audio_proctoring.trainer import train_audio_model

__all__ = [
    "analyze_audio_file",
    "MonitoringSession",
    "StreamState",
    "is_stream_available",
    "classify_audio",
    "analyze_segments",
    "extract_features",
    "detect_voice_activity",
    "train_audio_model",
]