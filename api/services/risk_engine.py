"""
api/services/risk_engine.py
===========================
Service-layer wrapper around video_ai.risk_engine.
Provides the RiskEngine class with Redis atomic scoring, TTL management,
and distributed lock for race-condition prevention.

Audit fixes addressed here:
  - 4.1  Redis TTL on risk_score keys  (EXPIRE after session end + 24h)
  - 6.2  Distributed lock on risk score flush
  - 6.3  Pure business logic — returns events as values, no side effects
"""

import os
import time
import threading
from typing import Dict, Any, List, Optional, Tuple

# Optional Redis — graceful fallback to in-memory when unavailable
_redis_client = None
_redis_available = False
_redis_lock = threading.Lock()


def _get_redis():
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client, _redis_available
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client, _redis_available
        try:
            import redis as _redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = _redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            _redis_client = client
            _redis_available = True
        except Exception:
            _redis_available = False
    return _redis_client, _redis_available


# Risk level thresholds
HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40

# TTL for risk score keys (session end + 24 hours)
RISK_KEY_TTL_SECONDS = 86_400  # 24 h


def _risk_key(session_id: str) -> str:
    return f"hp:risk:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"hp:lock:{session_id}"


class RiskEngine:
    """
    Atomic risk score management with Redis (in-memory fallback).

    All public methods are pure: they return the computed result and
    emit side-effect writes only to the store — never mutating caller state.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._redis, self._redis_ok = _get_redis()
        self._local_score: int = 0
        self._lock = threading.Lock()

    # ── Atomic increment ─────────────────────────────────────────────────────

    def increment(self, amount: int) -> int:
        """Atomically add *amount* to the session risk score. Returns new total."""
        if self._redis_ok and self._redis:
            try:
                key = _risk_key(self.session_id)
                new_val = int(self._redis.incrby(key, amount))
                # Refresh TTL on every write
                self._redis.expire(key, RISK_KEY_TTL_SECONDS)
                return new_val
            except Exception:
                pass
        with self._lock:
            self._local_score += amount
            return self._local_score

    def get(self) -> int:
        """Return current score."""
        if self._redis_ok and self._redis:
            try:
                val = self._redis.get(_risk_key(self.session_id))
                return int(val) if val else 0
            except Exception:
                pass
        with self._lock:
            return self._local_score

    def set(self, value: int) -> None:
        """Force-set the score (e.g. on session load)."""
        if self._redis_ok and self._redis:
            try:
                self._redis.set(_risk_key(self.session_id), value, ex=RISK_KEY_TTL_SECONDS)
                return
            except Exception:
                pass
        with self._lock:
            self._local_score = value

    def expire(self) -> None:
        """Set TTL = 24 h on the key (call at session end)."""
        if self._redis_ok and self._redis:
            try:
                self._redis.expire(_risk_key(self.session_id), RISK_KEY_TTL_SECONDS)
            except Exception:
                pass

    def delete(self) -> None:
        """Remove the key entirely (call on cleanup)."""
        if self._redis_ok and self._redis:
            try:
                self._redis.delete(_risk_key(self.session_id))
            except Exception:
                pass
        with self._lock:
            self._local_score = 0

    # ── Distributed lock ─────────────────────────────────────────────────────

    def acquire_lock(self, ttl_ms: int = 5000) -> bool:
        """Try to acquire a distributed lock. Returns True if acquired."""
        if self._redis_ok and self._redis:
            try:
                return bool(self._redis.set(
                    _lock_key(self.session_id), "1",
                    px=ttl_ms, nx=True
                ))
            except Exception:
                pass
        return True  # fallback: always grant when Redis unavailable

    def release_lock(self) -> None:
        """Release the distributed lock."""
        if self._redis_ok and self._redis:
            try:
                self._redis.delete(_lock_key(self.session_id))
            except Exception:
                pass

    # ── Risk classification ───────────────────────────────────────────────────

    @staticmethod
    def classify(score: int) -> str:
        """Return 'high', 'medium', or 'low' for a given numeric score."""
        if score >= HIGH_THRESHOLD:
            return "high"
        if score >= MEDIUM_THRESHOLD:
            return "medium"
        return "low"

    # ── Event processing ──────────────────────────────────────────────────────

    @staticmethod
    def compute_risk_delta(event_type: str) -> int:
        """
        Pure function — returns the risk increment for an event type.
        No side effects.
        """
        from video_ai.risk_engine import DEFAULT_RISK_WEIGHTS
        weights = DEFAULT_RISK_WEIGHTS
        return weights.get(event_type, 0)

    def process_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a proctoring event:
          1. Look up its risk weight
          2. Atomically add to score
          3. Return computed result (no side effects on caller)
        """
        delta = self.compute_risk_delta(event_type)
        new_score = self.increment(delta) if delta else self.get()
        level = self.classify(new_score)
        return {
            "event_type": event_type,
            "risk_delta": delta,
            "new_score": new_score,
            "risk_level": level,
            "session_id": self.session_id,
        }
