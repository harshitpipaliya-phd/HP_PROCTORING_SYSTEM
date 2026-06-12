"""
workers/celery_app.py
=====================
Celery application configuration.
Falls back to an in-memory CeleryMock when Celery/Redis is unavailable
so tasks still execute synchronously.
"""

import os

try:
    from celery import Celery  # type: ignore

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    app = Celery(
        "hp_proctoring",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,
        task_soft_time_limit=280,
    )

    _HAS_CELERY = True
except Exception:
    _HAS_CELERY = False

    class CeleryMock:
        """Minimal stand-in when Celery/Redis unavailable."""

        def __init__(self):
            self.tasks = {}

        def task(self, *args, **kwargs):
            def register(fn):
                name = kwargs.get("name") or fn.__name__

                class FakeTask:
                    def __init__(inner, fn=fn):
                        inner.fn = fn
                        inner.name = name

                    def delay(inner, *a, **kw):
                        try:
                            return inner.fn(*a, **kw)
                        except Exception as exc:
                            return {"success": False, "error": str(exc)}

                    def apply_async(inner, args=(), kwargs=None):
                        return inner.delay(*args, **(kwargs or {}))

                self.tasks[name] = fn
                return FakeTask()
            return register

        def autodiscover_tasks(self, modules):
            for mod in modules:
                try:
                    __import__(mod)
                except ImportError:
                    pass

    app = CeleryMock()


def task(*args, **kwargs):
    """Compatibility shim so both Celery and CeleryMock use the same decorator."""
    if _HAS_CELERY:
        return app.task(*args, **kwargs)
    # CeleryMock.task is not a classmethod, so call it
    return app.task(*args, **kwargs)


def autodiscover_tasks(modules):
    app.autodiscover_tasks(modules)
