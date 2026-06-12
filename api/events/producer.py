"""
api/events/producer.py
======================
Event producer — publishes analysis events to Redis Streams.

Uses Redis Streams (XADD) as the internal event bus between API workers,
Celery tasks, and AI processors.
"""

import json
import os
from typing import Any, Dict


class EventProducer:
    """Publishes events to Redis Streams (XADD). Falls back to in-memory
    fire-and-forget when Redis is unavailable."""

    def __init__(self):
        self._handlers: list = []
        self._redis = None
        self._redis_available = False

    def _ensure_redis(self):
        if self._redis is not None:
            return self._redis_available
        try:
            import redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.Redis.from_url(url, decode_responses=False)
            self._redis.ping()
            self._redis_available = True
        except Exception:
            self._redis = None
            self._redis_available = False
        return self._redis_available

    def register(self, handler):
        self._handlers.append(handler)

    def emit(self, event: str, data: Dict[str, Any]):
        payload = {"event": event, "data": data}
        serialized = json.dumps(payload).encode("utf-8")

        if self._ensure_redis():
            try:
                self._redis.xadd("hp:events", {"payload": serialized}, maxlen=10000, approximate=True)
            except Exception:
                pass
        for h in self._handlers:
            try:
                h(payload)
            except Exception:
                pass


producer = EventProducer()
