"""
api/events/consumer.py
======================
Event consumer — subscribes to Redis Streams consumer group.

Reads from the ``hp:events`` Redis Stream and dispatches to registered
handlers. Falls back to in-memory dispatch when Redis is unavailable.
"""

import json
import os
import threading
from typing import Callable, Dict, Any


class EventConsumer:
    """Reads from Redis Streams consumer group and dispatches events."""

    def __init__(self):
        self._handlers: Dict[str, list] = {}
        self._redis = None
        self._redis_available = False
        self._consumer_name = "hp-api-consumer"
        self._group_name = "hp-event-group"
        self._running = False
        self._thread: threading.Thread | None = None

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

    def on(self, event: str):
        def decorator(fn: Callable[[Dict[str, Any]], None]):
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    def _dispatch(self, event: str, payload: Dict[str, Any]):
        for fn in self._handlers.get(event, []):
            try:
                fn(payload)
            except Exception:
                pass

    def _process_message(self, message_id: bytes, payload_bytes: bytes):
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
            event = data.get("event")
            if event:
                self._dispatch(event, data)
        except Exception:
            pass

    def _read_loop(self):
        while self._running:
            if not self._ensure_redis():
                import time
                time.sleep(1)
                continue
            try:
                self._redis.xgroup_create("hp:events", self._group_name, id="0", mkstream=True)
            except Exception:
                pass
            try:
                results = self._redis.xreadgroup(
                    group_name=self._group_name,
                    consumer_name=self._consumer_name,
                    streams={"hp:events": ">"},
                    count=10,
                    block=1000,
                )
                for stream, messages in results:
                    for message_id, payload in messages:
                        if payload.get(b"payload"):
                            self._process_message(message_id, payload[b"payload"])
                        self._redis.xack("hp:events", self._group_name, message_id)
                        try:
                            self._redis.xdel("hp:events", message_id)
                        except Exception:
                            pass
            except Exception:
                import time
                time.sleep(0.5)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False


consumer = EventConsumer()
