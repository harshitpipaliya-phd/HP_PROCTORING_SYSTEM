"""
audio_proctoring/vad.py
========================
Voice Activity Detection (VAD) with SpeechBrain as primary backend
and a robust scikit-learn / signal-processing fallback.

Spec fix: SpeechBrain VAD not implemented — scikit-learn used instead.
This module provides:
  1. SpeechBrainVAD   — SpeechBrain silero-vad (production quality)
  2. SignalVAD        — scipy/numpy spectral VAD (always available)
  3. get_vad()        — returns the best available backend automatically

Usage:
    vad = get_vad()
    segments = vad.detect(audio_array, sample_rate=16000)
    # segments: list of {"start": float, "end": float, "confidence": float}
"""

from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

def _make_segment(start: float, end: float, confidence: float = 1.0) -> Dict[str, Any]:
    return {"start": round(start, 3), "end": round(end, 3), "confidence": round(confidence, 3)}


# ---------------------------------------------------------------------------
# Backend 1: SpeechBrain VAD (silero-based)
# ---------------------------------------------------------------------------

class SpeechBrainVAD:
    """
    SpeechBrain VAD using the Silero model via speechbrain.pretrained.
    Downloads the model on first use (~2 MB).
    """

    _model = None
    _loaded = False

    def __init__(self, activation_threshold: float = 0.5, deactivation_threshold: float = 0.25):
        self.activation_threshold = activation_threshold
        self.deactivation_threshold = deactivation_threshold
        self._try_load()

    def _try_load(self):
        if SpeechBrainVAD._loaded:
            return
        try:
            from speechbrain.pretrained import VAD  # type: ignore
            SpeechBrainVAD._model = VAD.from_hparams(
                source="speechbrain/vad-crdnn-libriparty",
                savedir=os.path.join(os.path.expanduser("~"), ".cache", "speechbrain_vad"),
            )
            SpeechBrainVAD._loaded = True
            logger.info("[VAD] SpeechBrain VAD loaded successfully")
        except ImportError:
            logger.warning("[VAD] speechbrain not installed — pip install speechbrain")
        except Exception as exc:
            logger.warning(f"[VAD] SpeechBrain load failed: {exc}")

    @property
    def available(self) -> bool:
        return SpeechBrainVAD._model is not None

    def detect(self, audio: np.ndarray, sample_rate: int = 16000) -> List[Dict[str, Any]]:
        """
        Run SpeechBrain VAD on a 1-D float32 audio array.
        Returns list of speech segments.
        """
        if not self.available:
            raise RuntimeError("SpeechBrain VAD not available")

        try:
            import torch
            # SpeechBrain expects a 2-D tensor [batch, samples]
            tensor = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
            # get_speech_segments returns a tensor of [start_sample, end_sample] pairs
            boundaries = SpeechBrainVAD._model.get_speech_segments(
                tensor,
                large_chunk_size=10,
                small_chunk_size=0.625,
                overlap_small_chunk=True,
                apply_energy_VAD=True,
                double_check=True,
                close_th=0.333,
                len_th=0.25,
            )
            segments = []
            if boundaries is not None and len(boundaries) > 0:
                for row in boundaries:
                    start_sec = float(row[0]) / sample_rate
                    end_sec = float(row[1]) / sample_rate
                    segments.append(_make_segment(start_sec, end_sec, confidence=0.9))
            return segments
        except Exception as exc:
            logger.warning(f"[VAD] SpeechBrain inference failed: {exc}")
            raise


# ---------------------------------------------------------------------------
# Backend 2: Signal-based VAD (always available)
# ---------------------------------------------------------------------------

class SignalVAD:
    """
    Multi-stage signal-processing VAD using energy + spectral features.
    No external ML dependencies — always available.
    Uses a sliding window with adaptive thresholding.
    """

    def __init__(
        self,
        frame_duration_ms: int = 30,
        energy_threshold_percentile: int = 15,
        speech_low_hz: int = 100,
        speech_high_hz: int = 3400,
        min_speech_duration_ms: int = 200,
        min_silence_duration_ms: int = 100,
        padding_duration_ms: int = 50,
    ):
        self.frame_ms = frame_duration_ms
        self.energy_pct = energy_threshold_percentile
        self.speech_low = speech_low_hz
        self.speech_high = speech_high_hz
        self.min_speech_ms = min_speech_duration_ms
        self.min_silence_ms = min_silence_duration_ms
        self.padding_ms = padding_duration_ms

    @property
    def available(self) -> bool:
        return True

    def _compute_frame_features(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Compute per-frame energy + spectral speech band ratio."""
        frame_samples = int(sr * self.frame_ms / 1000)
        if frame_samples < 2:
            frame_samples = 2
        num_frames = len(audio) // frame_samples
        if num_frames == 0:
            return np.array([])

        scores = []
        for i in range(num_frames):
            frame = audio[i * frame_samples: (i + 1) * frame_samples]

            # RMS energy
            rms = float(np.sqrt(np.mean(frame ** 2)))

            # Spectral band energy ratio (speech band vs total)
            try:
                from scipy.signal import welch
                freqs, psd = welch(frame, fs=sr, nperseg=min(256, len(frame)))
                speech_mask = (freqs >= self.speech_low) & (freqs <= self.speech_high)
                total_power = np.sum(psd) + 1e-12
                speech_power = np.sum(psd[speech_mask])
                band_ratio = float(speech_power / total_power)
            except Exception:
                band_ratio = 0.5

            # Zero-crossing rate (inversely correlated with voice)
            zcr = float(np.mean(np.abs(np.diff(np.sign(frame)))) / 2)
            zcr_score = max(0.0, 1.0 - zcr * 2)

            scores.append(rms * band_ratio * zcr_score)

        return np.array(scores)

    def detect(self, audio: np.ndarray, sample_rate: int = 16000) -> List[Dict[str, Any]]:
        """
        Run signal-based VAD. Returns speech segment list.
        """
        if audio is None or len(audio) == 0:
            return []

        audio = audio.astype(np.float32)
        # Normalize
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak

        scores = self._compute_frame_features(audio, sample_rate)
        if len(scores) == 0:
            return []

        # Adaptive threshold at the given percentile of non-silent frames
        threshold = float(np.percentile(scores, self.energy_pct))
        is_speech = scores > max(threshold, 1e-6)

        # Convert boolean frame array to time segments
        frame_samples = int(sample_rate * self.frame_ms / 1000)
        min_speech_frames = max(1, self.min_speech_ms // self.frame_ms)
        min_silence_frames = max(1, self.min_silence_ms // self.frame_ms)
        pad_frames = max(0, self.padding_ms // self.frame_ms)

        segments = []
        in_speech = False
        seg_start = 0
        silence_count = 0

        for i, v in enumerate(is_speech):
            if not in_speech:
                if v:
                    in_speech = True
                    seg_start = max(0, i - pad_frames)
                    silence_count = 0
            else:
                if not v:
                    silence_count += 1
                    if silence_count >= min_silence_frames:
                        end_frame = i + pad_frames
                        duration_frames = end_frame - seg_start
                        if duration_frames >= min_speech_frames:
                            t_start = seg_start * frame_samples / sample_rate
                            t_end = end_frame * frame_samples / sample_rate
                            segments.append(_make_segment(t_start, t_end, confidence=0.75))
                        in_speech = False
                else:
                    silence_count = 0

        # Handle speech that continues to end of audio
        if in_speech:
            end_frame = len(is_speech)
            duration_frames = end_frame - seg_start
            if duration_frames >= min_speech_frames:
                t_start = seg_start * frame_samples / sample_rate
                t_end = end_frame * frame_samples / sample_rate
                segments.append(_make_segment(t_start, t_end, confidence=0.75))

        return segments


# ---------------------------------------------------------------------------
# Convenience: try SpeechBrain, fall back to SignalVAD
# ---------------------------------------------------------------------------

_vad_instance: Optional[object] = None


def get_vad() -> "SpeechBrainVAD | SignalVAD":
    """
    Return the best available VAD backend.
    Tries SpeechBrain first; falls back to SignalVAD.
    Result is cached after the first call.
    """
    global _vad_instance
    if _vad_instance is not None:
        return _vad_instance

    sb = SpeechBrainVAD()
    if sb.available:
        logger.info("[VAD] Using SpeechBrain backend")
        _vad_instance = sb
    else:
        logger.info("[VAD] Using SignalVAD (scipy) backend — install speechbrain for higher accuracy")
        _vad_instance = SignalVAD()

    return _vad_instance


def detect_voice_activity(
    audio: np.ndarray, sample_rate: int = 16000
) -> List[Dict[str, Any]]:
    """
    Top-level convenience function. Detect voice activity in an audio array.

    Args:
        audio: 1-D float32 numpy array of audio samples
        sample_rate: audio sample rate in Hz

    Returns:
        List of dicts: [{"start": float, "end": float, "confidence": float}, ...]
    """
    vad = get_vad()
    try:
        return vad.detect(audio, sample_rate=sample_rate)
    except Exception as exc:
        # Final fallback: basic energy VAD
        logger.warning(f"[VAD] Primary backend failed ({exc}), using basic energy VAD")
        signal_vad = SignalVAD()
        return signal_vad.detect(audio, sample_rate=sample_rate)
