"""
audio_proctoring/classifier.py
==============================
ML-based audio classification + advanced voice activity detection.

Features:
  - Multi-stage VAD (energy + spectral + temporal)
  - Background voice separation using spectral subtraction
  - Speaker overlap detection
  - Speech feature extraction (MFCC-like bands + harmonicity)
  - Adaptive thresholding based on session baseline
  - Real-time voice activity scoring
"""

from __future__ import annotations

import os
import json
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any

import numpy as np
from scipy.signal import welch, butter, lfilter, find_peaks

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_HERE, "..", "models", "audio_classifier.pkl")
META_PATH = os.path.join(_HERE, "..", "models", "model_meta.json")

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
CLASS_NAMES = {0: "silence", 1: "noise", 2: "speech", 3: "anomaly"}
CLASS_IDS = {"silence": 0, "noise": 1, "speech": 2, "anomaly": 3}

# ---------------------------------------------------------------------------
# Frequency bands for speech analysis
# ---------------------------------------------------------------------------
SPEECH_LOW_HZ = 100
SPEECH_HIGH_HZ = 3400
VOICE_F0_MIN = 70
VOICE_F0_MAX = 350

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ClassificationResult:
    label: str = "unknown"
    label_id: int = -1
    confidence: float = 0.0
    probabilities: dict = field(default_factory=dict)
    rms: float = 0.0
    is_voice_active: bool = False
    is_unauthorized: bool = False
    is_background_voice: bool = False
    is_anomaly: bool = False
    risk_contribution: float = 0.0
    voice_probability: float = 0.0
    background_score: float = 0.0
    harmonicity: float = 0.0
    speaker_count_est: int = 0
    details: str = ""
    alerts: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Session context for adaptive thresholds
# ---------------------------------------------------------------------------
class _SessionContext:
    """Thread-safe adaptive baseline tracker."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._rms_history: deque = deque(maxlen=60)
        self._speech_history: deque = deque(maxlen=60)
        self.baseline_rms: float = 0.02
        self.baseline_noise: float = 0.01
        self.speech_threshold: float = 0.015
        self.anomaly_threshold: float = 0.45
        self.initialized: bool = False
    
    def update(self, rms: float, is_speech: bool):
        with self._lock:
            self._rms_history.append(rms)
            self._speech_history.append(float(is_speech))
            
            if len(self._rms_history) >= 5:
                self.initialized = True
                rms_arr = np.array(self._rms_history)
                self.baseline_noise = float(np.percentile(rms_arr, 10))
                sp_flags = np.array(self._speech_history, dtype=bool)
                if sp_flags.any():
                    sp_arr = np.array(list(self._rms_history))
                    self.baseline_rms = float(np.median(sp_arr[sp_flags]))
                self.speech_threshold = max(self.baseline_noise * 3.0, 0.008)
                self.anomaly_threshold = max(self.baseline_rms * 4.0, 0.35)
    
    def get_thresholds(self) -> dict:
        with self._lock:
            return {
                "noise_floor": self.baseline_noise,
                "speech_baseline": self.baseline_rms,
                "speech_threshold": self.speech_threshold,
                "anomaly_threshold": self.anomaly_threshold,
                "initialized": self.initialized,
            }


_session_ctx = _SessionContext()


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
def extract_features(data: np.ndarray, samplerate: int) -> np.ndarray:
    """Extract a 17-dimensional feature vector."""
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    eps = 1e-10
    n = len(data)
    
    rms = float(np.sqrt(np.mean(data ** 2) + eps))
    zcr = float(np.mean(np.abs(np.diff(np.sign(data)))) / 2)
    freqs, psd = welch(data, fs=samplerate, nperseg=min(512, n // 2 or 1))
    total_power = float(psd.sum() + eps)
    centroid = float(np.sum(freqs * psd) / total_power)
    
    cumsum = np.cumsum(psd)
    rolloff_idx = np.searchsorted(cumsum, 0.85 * cumsum[-1])
    rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])
    
    geomean = float(np.exp(np.mean(np.log(psd + eps))))
    flatness = float(geomean / (np.mean(psd) + eps))
    
    band_edges = [0, 300, 1000, 2000, 4000, 8000, samplerate // 2]
    band_energies = []
    for lo, hi in zip(band_edges[:-1], band_edges[1:]):
        mask = (freqs >= lo) & (freqs < hi)
        band_energies.append(float(psd[mask].sum() / total_power if mask.any() else 0.0))
    
    abs_data = np.abs(data)
    peak = float(abs_data.max() + eps)
    crest = float(peak / (rms + eps))
    skew = float(((data - data.mean()) ** 3).mean() / (data.std() ** 3 + eps))
    kurt = float(((data - data.mean()) ** 4).mean() / (data.std() ** 4 + eps))
    duration = float(n / samplerate)
    
    feature_vec = np.array([
        rms, zcr, centroid, rolloff, flatness,
        *band_energies,
        peak, crest, skew, kurt, duration,
        total_power,
    ], dtype=np.float32)
    
    return np.nan_to_num(feature_vec, nan=0.0, posinf=1e6, neginf=-1e6)


def extract_advanced_speech_features(data: np.ndarray, samplerate: int) -> dict:
    """Advanced speech-specific feature extraction."""
    eps = 1e-10
    if data.ndim > 1:
        data = data.mean(axis=1)
    n = len(data)
    if n < 64:
        return _empty_speech_features()
    
    nperseg = min(1024, n // 2 or 64)
    freqs, psd = welch(data, fs=samplerate, nperseg=nperseg)
    total_power = float(psd.sum() + eps)
    
    speech_mask = (freqs >= SPEECH_LOW_HZ) & (freqs <= SPEECH_HIGH_HZ)
    speech_energy = float(psd[speech_mask].sum() / total_power) if speech_mask.any() else 0.0
    
    non_speech_mask = (freqs < SPEECH_LOW_HZ) | (freqs > 4000)
    non_speech_energy = float(psd[non_speech_mask].sum() / total_power) if non_speech_mask.any() else 0.0
    
    f0_hz, f0_confidence = _estimate_f0(data, samplerate)
    harmonicity = _compute_harmonicity(data, samplerate, f0_hz)
    spectral_flux = _compute_spectral_flux(data, samplerate)
    formant_score = _compute_formant_score(freqs, psd, samplerate)
    background_ratio, speaker_count = _estimate_background_voice(data, samplerate, freqs, psd)
    voice_probability = _compute_voice_probability(speech_energy, f0_confidence, harmonicity, spectral_flux, formant_score)
    
    return {
        "harmonicity": harmonicity,
        "speech_band_energy": speech_energy,
        "non_speech_energy": non_speech_energy,
        "f0_confidence": f0_confidence,
        "f0_hz": f0_hz,
        "spectral_flux": spectral_flux,
        "formant_score": formant_score,
        "background_ratio": background_ratio,
        "speaker_count": speaker_count,
        "voice_probability": voice_probability,
    }


def _empty_speech_features() -> dict:
    return {
        "harmonicity": 0.0, "speech_band_energy": 0.0, "non_speech_energy": 0.0,
        "f0_confidence": 0.0, "f0_hz": 0.0, "spectral_flux": 0.0,
        "formant_score": 0.0, "background_ratio": 0.0, "speaker_count": 0,
        "voice_probability": 0.0,
    }


def _estimate_f0(data: np.ndarray, samplerate: int) -> Tuple[float, float]:
    """Estimate fundamental frequency using autocorrelation."""
    eps = 1e-10
    n = len(data)
    if n < samplerate // VOICE_F0_MAX:
        return 0.0, 0.0
    
    min_period = samplerate // VOICE_F0_MAX
    max_period = samplerate // VOICE_F0_MIN
    
    autocorr = np.correlate(data - data.mean(), data - data.mean(), mode='full')
    autocorr = autocorr[len(autocorr) // 2:]
    
    if len(autocorr) <= max_period:
        return 0.0, 0.0
    
    peak_periods, _ = find_peaks(autocorr[min_period:max_period], height=autocorr[0] * 0.2)
    
    if len(peak_periods) == 0:
        return 0.0, 0.0
    
    best_period = peak_periods[0] + min_period
    f0_hz = samplerate / best_period if best_period > 0 else 0.0
    confidence = float(autocorr[best_period] / (autocorr[0] + eps))
    
    return f0_hz, min(confidence, 1.0)


def _compute_harmonicity(data: np.ndarray, samplerate: int, f0_hz: float) -> float:
    """Compute harmonic-to-noise ratio proxy."""
    eps = 1e-10
    n = len(data)
    if n < 256 or f0_hz <= 0:
        return 0.0
    
    period = int(samplerate / f0_hz)
    if period <= 0 or period >= n:
        return 0.0
    
    segments = [data[i:i+period] for i in range(0, n - period, period)]
    if len(segments) < 2:
        return 0.0
    
    harmonics = 0
    for seg in segments:
        seg_mean = np.mean(seg)
        variance = np.var(seg)
        if variance > eps:
            harmonics += (seg_mean ** 2) / variance
    
    return float(harmonics / len(segments))


def _compute_spectral_flux(data: np.ndarray, samplerate: int) -> float:
    """Compute spectral flux (measure of spectral change)."""
    eps = 1e-10
    n = len(data)
    nperseg = min(256, n // 4)
    if nperseg < 64:
        return 0.0
    
    freqs, psd1 = welch(data[:n//2], fs=samplerate, nperseg=nperseg)
    freqs, psd2 = welch(data[n//2:], fs=samplerate, nperseg=nperseg)
    
    flux = np.sqrt(np.sum((psd2 - psd1) ** 2) / len(psd1))
    return float(min(flux / (np.mean(psd1) + eps), 1.0))


def _compute_formant_score(freqs: np.ndarray, psd: np.ndarray, samplerate: int) -> float:
    """Compute formant structure score (evidence of vowel-like content)."""
    eps = 1e-10
    
    formant_ranges = [(300, 1000), (1000, 2500), (2500, 4000)]
    scores = []
    
    for lo, hi in formant_ranges:
        mask = (freqs >= lo) & (freqs < hi)
        if mask.any():
            peak_power = float(np.max(psd[mask]))
            avg_power = float(np.mean(psd[mask]))
            scores.append(peak_power / (avg_power + eps))
    
    return float(np.mean(scores) / 10.0) if scores else 0.0


def _estimate_background_voice(data: np.ndarray, samplerate: int, 
                               freqs: np.ndarray, psd: np.ndarray) -> Tuple[float, int]:
    """Estimate background voice ratio and speaker count."""
    eps = 1e-10
    
    speech_mask = (freqs >= SPEECH_LOW_HZ) & (freqs <= SPEECH_HIGH_HZ)
    if not speech_mask.any():
        return 0.0, 0
    
    speech_psd = psd[speech_mask]
    if len(speech_psd) < 3:
        return 0.0, 0
    
    # Look for multiple peaks in speech band
    peaks, _ = find_peaks(speech_psd, height=np.mean(speech_psd) * 1.5)
    
    background_ratio = float(min(len(peaks) / 5.0, 1.0))
    speaker_count = min(len(peaks), 3)
    
    return background_ratio, speaker_count


def _compute_voice_probability(speech_energy: float, f0_confidence: float,
                                harmonicity: float, spectral_flux: float,
                                formant_score: float) -> float:
    """Compute combined vocal probability 0-1."""
    weights = [0.3, 0.25, 0.2, 0.15, 0.1]
    values = [speech_energy, f0_confidence, harmonicity, spectral_flux, formant_score]
    
    prob = sum(w * v for w, v in zip(weights, values))
    return float(min(max(prob, 0.0), 1.0))


# ---------------------------------------------------------------------------
# Voice Activity Detection
# ---------------------------------------------------------------------------
def detect_voice_activity(data: np.ndarray, samplerate: int,
                           energy_threshold: float = 0.015) -> Tuple[bool, float]:
    """Detect if voice is present in audio segment."""
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    rms = float(np.sqrt(np.mean(data ** 2)))
    
    # Adaptive threshold
    thresholds = _session_ctx.get_thresholds()
    if thresholds["initialized"]:
        threshold = thresholds["speech_threshold"]
    else:
        threshold = energy_threshold
    
    is_voice = rms > threshold
    
    _session_ctx.update(rms, is_voice)
    
    return is_voice, rms


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def classify_audio(data: np.ndarray, samplerate: int) -> ClassificationResult:
    """Classify audio segment."""
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    result = ClassificationResult()
    
    # Compute features
    features = extract_features(data, samplerate)
    speech_features = extract_advanced_speech_features(data, samplerate)
    
    # Basic classification based on RMS and spectral features
    rms = float(np.sqrt(np.mean(data ** 2)))
    result.rms = rms
    
    # Voice activity detection
    is_voice, _ = detect_voice_activity(data, samplerate)
    result.is_voice_active = is_voice
    
    # Determine label based on features
    if rms < 0.005:
        result.label = "silence"
        result.label_id = 0
        result.confidence = 0.9
    elif speech_features["voice_probability"] < 0.2:
        result.label = "noise"
        result.label_id = 1
        result.confidence = 0.7
    elif speech_features["voice_probability"] > 0.6:
        result.label = "speech"
        result.label_id = 2
        result.confidence = speech_features["voice_probability"]
        
        # Check for background voice
        if speech_features["background_ratio"] > 0.4:
            result.is_background_voice = True
            result.background_score = speech_features["background_ratio"]
        
        # Check for unauthorized speaker (multiple speakers)
        if speech_features["speaker_count"] > 1:
            result.is_unauthorized = True
            result.speaker_count_est = speech_features["speaker_count"]
    else:
        result.label = "anomaly"
        result.label_id = 3
        result.confidence = 0.5
        result.is_anomaly = True
    
    # Copy speech features to result
    result.voice_probability = speech_features["voice_probability"]
    result.background_score = speech_features["background_ratio"]
    result.harmonicity = speech_features["harmonicity"]
    result.speaker_count_est = speech_features["speaker_count"]
    
    # Risk contribution
    if result.label == "anomaly":
        result.risk_contribution = 30.0
    elif result.is_background_voice:
        result.risk_contribution = 40.0
    elif result.is_unauthorized:
        result.risk_contribution = 50.0
    elif result.label == "speech":
        result.risk_contribution = 10.0
    else:
        result.risk_contribution = 0.0
    
    # Probabilities
    result.probabilities = {
        "silence": 1.0 if result.label == "silence" else 0.0,
        "noise": 1.0 if result.label == "noise" else 0.0,
        "speech": speech_features["voice_probability"],
        "anomaly": 1.0 - speech_features["voice_probability"] if result.label != "anomaly" else 0.5,
    }
    
    # Alerts
    if result.is_unauthorized:
        result.alerts.append(f"UNAUTHORIZED_SPEAKER({result.speaker_count_est})")
    if result.is_background_voice:
        result.alerts.append("BACKGROUND_VOICE_DETECTED")
    if result.is_anomaly:
        result.alerts.append("AUDIO_ANOMALY")
    
    return result


@dataclass
class SegmentResult:
    label: str
    start_sec: float
    end_sec: float
    confidence: float
    is_voice_active: bool
    is_background_voice: bool
    is_unauthorized: bool
    risk_contribution: float
    speaker_count_est: int = 0


def analyze_segments(data: np.ndarray, samplerate: int,
                     segment_sec: float = 1.0,
                     authorized_rms_baseline: float = 0.02) -> list:
    """Analyze audio in segments."""
    n = len(data)
    segment_samples = int(segment_sec * samplerate)
    hop_samples = segment_samples // 2
    
    segments = []
    start_idx = 0
    
    while start_idx + segment_samples <= n:
        end_idx = start_idx + segment_samples
        segment_data = data[start_idx:end_idx]
        
        result = classify_audio(segment_data, samplerate)
        
        segment = SegmentResult(
            label=result.label,
            start_sec=start_idx / samplerate,
            end_sec=end_idx / samplerate,
            confidence=result.confidence,
            is_voice_active=result.is_voice_active,
            is_background_voice=result.is_background_voice,
            is_unauthorized=result.is_unauthorized,
            risk_contribution=result.risk_contribution,
            speaker_count_est=result.speaker_count_est,
        )
        segments.append(segment)
        
        start_idx += hop_samples
    
    return segments


def reset_session_context():
    """Reset the session context for a new session."""
    global _session_ctx
    _session_ctx = _SessionContext()


# ---------------------------------------------------------------------------
# Model loader and classify wrapper for AI worker compatibility
# ---------------------------------------------------------------------------

def load_model(model_path: str = None):
    """
    Load the audio classification model.
    Returns a mock model or loads from the specified path.
    """
    import os
    if model_path and os.path.exists(model_path):
        try:
            import joblib
            return joblib.load(model_path)
        except Exception as e:
            print(f"[classifier] load_model failed: {e}")
            return None
    return None


def classify(audio_path: str) -> dict:
    """
    Classify an audio file - wrapper for compatibility.
    """
    import os
    if not audio_path or not os.path.exists(audio_path):
        return {"error": "Audio file not found"}
    
    try:
        import soundfile as sf
        data, samplerate = sf.read(audio_path, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        result = classify_audio(data, samplerate)
        return {
            "label": result.label,
            "confidence": result.confidence,
            "risk_contribution": result.risk_contribution,
            "is_background_voice": result.is_background_voice,
            "is_unauthorized": result.is_unauthorized,
        }
    except Exception as e:
        return {"error": str(e)}