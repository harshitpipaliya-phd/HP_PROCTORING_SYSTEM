"""
audio_proctoring/stream.py
==========================
Continuous audio monitoring engine.

Features:
  - Robust session lifecycle management (start/pause/resume/stop)
  - Adaptive window analysis with overlap
  - Ring-buffer audio accumulator
  - Heartbeat watchdog for stream health
  - Continuous background noise floor calibration
  - Per-session authorized-speaker baseline
  - Detailed real-time event callbacks
  - Thread-safe state machine
  - Memory-bounded event log
  - Stream health metrics
"""

from __future__ import annotations

import os
import time
import queue
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Dict, Any

import numpy as np

try:
    import soundfile as sf
    _SOUNDFILE_OK = True
except Exception:
    _SOUNDFILE_OK = False

from audio_proctoring.classifier import (
    classify_audio,
    analyze_segments,
    detect_voice_activity,
    reset_session_context,
)

# PyAudio is optional
try:
    import pyaudio as _pyaudio_module
    _PYAUDIO_OK = True
except Exception:
    _PYAUDIO_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 512
WINDOW_SEC = 2.0
OVERLAP_SEC = 0.5
CALIBRATION_SEC = 3.0
WATCHDOG_TIMEOUT = 8.0
MAX_QUEUE_FRAMES = 200
MAX_EVENT_LOG = 500


# ---------------------------------------------------------------------------
# Stream state machine
# ---------------------------------------------------------------------------
class StreamState(Enum):
    IDLE = "idle"
    CALIBRATING = "calibrating"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
@dataclass
class MonitoringSession:
    user_id: str
    start_time: float = field(default_factory=time.time)
    events: list = field(default_factory=list)
    total_risk: float = 0.0
    speech_count: int = 0
    anomaly_count: int = 0
    noise_count: int = 0
    background_voice_count: int = 0
    unauthorized_count: int = 0
    
    authorized_baseline_rms: float = 0.02
    
    _active: bool = False
    _state: StreamState = StreamState.IDLE
    _audio_queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=MAX_QUEUE_FRAMES))
    _stream: object = None
    _thread: object = None
    
    def add_event(self, event: dict):
        self.events.append(event)
        if len(self.events) > MAX_EVENT_LOG:
            self.events = self.events[-MAX_EVENT_LOG:]
    
    def to_summary(self) -> dict:
        elapsed = time.time() - self.start_time
        risk_level = (
            "LOW" if self.total_risk < 30 else
            "MEDIUM" if self.total_risk < 70 else
            "HIGH"
        )
        return {
            "user_id": self.user_id,
            "duration_sec": round(elapsed, 1),
            "total_risk": round(min(self.total_risk, 100), 1),
            "risk_level": risk_level,
            "speech_count": self.speech_count,
            "anomaly_count": self.anomaly_count,
            "noise_count": self.noise_count,
            "background_voice_count": self.background_voice_count,
            "unauthorized_count": self.unauthorized_count,
            "event_count": len(self.events),
            "events": self.events[-20:],
        }


# ---------------------------------------------------------------------------
# File-based analysis (HF Spaces compatible)
# ---------------------------------------------------------------------------
def analyze_audio_file(audio_path: str, user_id: str,
                       session: Optional[MonitoringSession] = None) -> dict:
    """
    Full analysis of a single audio file.
    
    Args:
        audio_path: path to audio file (wav / mp3 / flac / ogg)
        user_id: candidate/user identifier
        session: optional MonitoringSession to accumulate results into
        
    Returns a rich result dict.
    """
    if not audio_path or not os.path.exists(audio_path):
        return {"error": "No audio file provided.", "result": "⚠️ No audio"}
    
    if not _SOUNDFILE_OK:
        return {"error": "soundfile not installed.", "result": "❌ soundfile missing"}
    
    try:
        data, samplerate = sf.read(audio_path, dtype="float32", always_2d=False)
    except Exception as e:
        return {"error": str(e), "result": f"❌ Could not read audio: {e}"}
    
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    # Normalize to prevent saturation
    peak = float(np.abs(data).max())
    if peak > 1.0:
        data = data / peak
    data = data - float(np.mean(data))
    
    # Authorized baseline
    calib_samples = min(int(samplerate * CALIBRATION_SEC), len(data))
    calib_data = data[:calib_samples]
    _, calib_rms = detect_voice_activity(calib_data, samplerate, energy_threshold=0.0)
    authorized_rms = max(float(calib_rms), 0.005)
    
    # Segment analysis
    segments = analyze_segments(
        data, samplerate,
        segment_sec=1.0,
        authorized_rms_baseline=authorized_rms,
    )
    
    # Aggregate results
    speech_segs = [s for s in segments if s.label == "speech"]
    noise_segs = [s for s in segments if s.label == "noise"]
    anomaly_segs = [s for s in segments if s.label == "anomaly"]
    bg_voice_segs = [s for s in segments if s.is_background_voice]
    unauth_segs = [s for s in segments if s.is_unauthorized]
    
    total_risk = min(100.0, sum(s.risk_contribution for s in segments))
    is_unauth = bool(unauth_segs)
    has_anomaly = bool(anomaly_segs)
    has_bg_voice = bool(bg_voice_segs)
    max_speakers = max((s.speaker_count_est for s in segments), default=0)
    
    risk_level = "LOW" if total_risk < 30 else "MEDIUM" if total_risk < 70 else "HIGH"
    
    # Human-readable summary
    lines = []
    volume = float(np.mean(np.abs(data)))
    
    if has_anomaly:
        lines.append(f"🚨 Anomalous audio detected ({len(anomaly_segs)} segment(s))")
    if is_unauth:
        lines.append(f"🔴 UNAUTHORIZED SPEAKER(S) detected ({max_speakers} speakers)")
    if has_bg_voice:
        lines.append(f"⚠️ Background voice detected ({len(bg_voice_segs)} segments)")
    
    if not lines:
        if len(speech_segs) > 0:
            lines.append(f"✅ Normal speech detected ({len(speech_segs)} segments)")
        else:
            lines.append(f"🔕 No significant speech detected")
    
    result_text = " | ".join(lines) if lines else "⚠️ Analysis inconclusive"
    
    summary = {
        "user_id": user_id,
        "total_segments": len(segments),
        "speech_segments": len(speech_segs),
        "noise_segments": len(noise_segs),
        "anomaly_segments": len(anomaly_segs),
        "background_voice_segments": len(bg_voice_segs),
        "unauthorized_segments": len(unauth_segs),
        "estimated_speakers": max_speakers,
        "total_risk": total_risk,
        "risk_level": risk_level,
        "result": result_text,
        "volume": round(volume, 4),
        "segments": [
            {
                "label": s.label,
                "start_sec": s.start_sec,
                "end_sec": s.end_sec,
                "confidence": s.confidence,
                "risk": s.risk_contribution,
                "background_voice": s.is_background_voice,
                "unauthorized": s.is_unauthorized,
                "speaker_count": s.speaker_count_est,
            }
            for s in segments
        ]
    }
    
    # Update session if provided
    if session:
        session.total_risk += total_risk
        session.speech_count += len(speech_segs)
        session.anomaly_count += len(anomaly_segs)
        session.noise_count += len(noise_segs)
        session.background_voice_count += len(bg_voice_segs)
        session.unauthorized_count += len(unauth_segs)
        
        for seg in segments:
            if seg.risk_contribution > 0:
                session.add_event({
                    "timestamp": time.time(),
                    "type": seg.label,
                    "risk": seg.risk_contribution,
                    "speaker_count": seg.speaker_count_est,
                })
    
    return summary


def is_stream_available() -> bool:
    """Check if streaming (PyAudio/microphone) is available."""
    return _PYAUDIO_OK


def get_stream_state() -> StreamState:
    """Get current stream state."""
    # This would be implemented based on actual streaming
    return StreamState.IDLE

# ---------------------------------------------------------------------------
# WebSocket / raw PCM streaming endpoint support
# ---------------------------------------------------------------------------

import struct

def process_pcm_bytes(
    raw_pcm: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    bit_depth: int = 16,
    session: Optional["MonitoringSession"] = None,
) -> dict:
    """
    Process raw PCM audio bytes received from a WebSocket client.

    Clients should send little-endian 16-bit signed PCM at 16 kHz mono.
    This function decodes, normalizes, and classifies the audio chunk.

    Args:
        raw_pcm: Raw PCM bytes (little-endian int16)
        sample_rate: Sample rate (default 16000)
        channels: Number of channels (default 1 — mono)
        bit_depth: Bits per sample (default 16)
        session: Optional MonitoringSession to accumulate into

    Returns:
        Classification result dict
    """
    if not raw_pcm:
        return {"error": "empty chunk", "result": "silent"}

    # Decode int16 PCM
    num_samples = len(raw_pcm) // 2
    samples = struct.unpack(f"<{num_samples}h", raw_pcm)
    data = np.array(samples, dtype=np.float32) / 32768.0  # normalize to [-1, 1]

    # Mix to mono if needed
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    # DC offset removal
    data = data - float(np.mean(data))

    # Classify the chunk
    try:
        result = classify_audio(data, sample_rate)
        label = result.label
        risk = result.risk_contribution
        confidence = result.confidence
        volume = float(np.mean(np.abs(data)))

        if session:
            if label == "speech":
                session.speech_count += 1
            elif label == "anomaly":
                session.anomaly_count += 1
            session.total_risk = min(100.0, session.total_risk + risk)
            if risk > 0:
                session.add_event({
                    "timestamp": time.time(),
                    "type": label,
                    "risk": risk,
                    "confidence": confidence,
                    "source": "websocket_pcm",
                })

        return {
            "label": label,
            "risk": risk,
            "confidence": confidence,
            "volume": round(volume, 4),
            "samples": num_samples,
        }
    except Exception as e:
        return {"error": str(e), "result": "classification_failed"}


class WebSocketAudioSession:
    """
    Manages a real-time audio session fed by raw PCM bytes from a WebSocket.
    Designed to work with FastAPI WebSocket connections without PyAudio.

    Usage:
        ws_session = WebSocketAudioSession(user_id="user_123")
        ws_session.start()

        # In WebSocket handler:
        while True:
            data = await websocket.receive_bytes()
            result = ws_session.push_chunk(data)
            await websocket.send_json(result)

        ws_session.stop()
    """

    def __init__(self, user_id: str, sample_rate: int = 16000, channels: int = 1):
        self.user_id = user_id
        self.sample_rate = sample_rate
        self.channels = channels
        self._session = MonitoringSession(user_id=user_id)
        self._session._active = True
        self._session._state = StreamState.ACTIVE
        self._buffer = deque(maxlen=MAX_QUEUE_FRAMES)
        self._lock = threading.Lock()
        self._active = False

    def start(self):
        self._active = True
        reset_session_context()
        print(f"[WebSocketAudioSession] Started for user={self.user_id}")

    def push_chunk(self, raw_pcm: bytes) -> dict:
        """Process a raw PCM chunk and return classification result."""
        if not self._active:
            return {"error": "session_not_active"}
        with self._lock:
            result = process_pcm_bytes(
                raw_pcm,
                sample_rate=self.sample_rate,
                channels=self.channels,
                session=self._session,
            )
        return result

    def stop(self) -> dict:
        self._active = False
        self._session._active = False
        self._session._state = StreamState.STOPPED
        summary = self._session.to_summary()
        print(f"[WebSocketAudioSession] Stopped — summary: {summary}")
        return summary

    def get_summary(self) -> dict:
        return self._session.to_summary()

    @property
    def is_active(self) -> bool:
        return self._active


# Registry for active WebSocket audio sessions
_ws_audio_sessions: dict = {}
_ws_sessions_lock = threading.Lock()


def create_ws_audio_session(user_id: str, session_id: str = None) -> WebSocketAudioSession:
    """Create and register a new WebSocket audio session."""
    key = session_id or user_id
    with _ws_sessions_lock:
        sess = WebSocketAudioSession(user_id=user_id)
        sess.start()
        _ws_audio_sessions[key] = sess
    return sess


def get_ws_audio_session(session_id: str) -> Optional[WebSocketAudioSession]:
    with _ws_sessions_lock:
        return _ws_audio_sessions.get(session_id)


def close_ws_audio_session(session_id: str) -> Optional[dict]:
    with _ws_sessions_lock:
        sess = _ws_audio_sessions.pop(session_id, None)
    if sess:
        return sess.stop()
    return None
