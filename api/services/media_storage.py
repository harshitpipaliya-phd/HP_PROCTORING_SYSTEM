"""
api/services/media_storage.py
==============================
Canonical media storage service — merged from media_storage.py + media_store.py.

Provides:
  1. MediaStorageService  — Cloudinary upload helpers (screenshots, reports, clips)
  2. MediaStore           — Global thread-safe in-memory artifact cache
  3. ArtifactStore        — Per-session isolation over MediaStore
  4. Module-level helpers — upload_screenshot(), upload_report(), store_frame(), etc.

Usage:
    from api.services.media_storage import upload_screenshot, upload_report
    from api.services.media_storage import get_artifact, get_media_store
"""

import os
import threading
import time
from typing import Optional, Dict, Any, List


# ─────────────────────────────────────────────────────────────────────────────
# Cloudinary upload helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cloudinary_config() -> bool:
    """Configure cloudinary from env. Returns True if credentials available."""
    try:
        import cloudinary
        cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        api_key = os.getenv("CLOUDINARY_API_KEY", "")
        api_secret = os.getenv("CLOUDINARY_API_SECRET", "")
        if not all([cloud_name, api_key, api_secret]):
            return False
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
        return True
    except ImportError:
        return False


class MediaStorageService:
    """Cloudinary-backed media storage. Degrades gracefully when credentials missing."""

    def upload_file(
        self,
        file_path: str,
        public_id: str = None,
        resource_type: str = "raw",
        sign_url: bool = False,
        expiry_seconds: int = 3600,
    ) -> Optional[Dict[str, Any]]:
        """Upload a file to Cloudinary. Returns {url, public_id, bytes} or None."""
        try:
            import cloudinary.uploader
            if not _cloudinary_config():
                return None

            kwargs: Dict[str, Any] = dict(
                resource_type=resource_type,
                public_id=public_id or f"hp_proctoring/{os.path.basename(file_path)}",
                overwrite=True,
            )
            # Signed URLs for evidence (1 h expiry); permanent for reports
            if sign_url:
                kwargs["sign_url"] = True
                kwargs["expires_at"] = int(time.time()) + expiry_seconds

            resp = cloudinary.uploader.upload(file_path, **kwargs)
            return {
                "url": resp.get("secure_url"),
                "public_id": resp.get("public_id"),
                "bytes": resp.get("bytes"),
            }
        except Exception:
            return None

    def upload_report(self, file_path: str, session_id: str = "unknown") -> Optional[Dict[str, Any]]:
        """Upload PDF report (permanent URL)."""
        pid = f"hp_proctoring/reports/{session_id}/{os.path.basename(file_path)}"
        return self.upload_file(file_path, public_id=pid, resource_type="raw")

    def upload_screenshot(
        self,
        file_path: str,
        session_id: str,
        label: str = "screenshot",
        monitor_id: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """Upload a screenshot. Evidence = signed URL (1 h)."""
        pid = f"hp_proctoring/screenshots/{session_id}/{monitor_id}_{label}_{os.path.basename(file_path)}"
        return self.upload_file(file_path, public_id=pid, resource_type="image",
                                sign_url=True, expiry_seconds=3600)

    def upload_video_clip(
        self,
        file_path: str,
        session_id: str,
        event_id: str = "clip",
    ) -> Optional[Dict[str, Any]]:
        """Upload a violation video clip. Evidence = signed URL (1 h)."""
        pid = f"hp_proctoring/clips/{session_id}/{event_id}_{os.path.basename(file_path)}"
        return self.upload_file(file_path, public_id=pid, resource_type="video",
                                sign_url=True, expiry_seconds=3600)

    def upload_image(self, file_path: str, public_id: str = None) -> Optional[Dict[str, Any]]:
        return self.upload_file(file_path, public_id=public_id, resource_type="image")


# Module-level singleton
_media_storage_service = MediaStorageService()


def upload_screenshot(
    file_path: str,
    session_id: str = "unknown",
    label: str = "screenshot",
    monitor_id: int = 1,
) -> Optional[str]:
    """Convenience wrapper. Returns Cloudinary URL string or None."""
    result = _media_storage_service.upload_screenshot(
        file_path, session_id=session_id, label=label, monitor_id=monitor_id
    )
    return result["url"] if result else None


def upload_report(file_path: str, session_id: str = "unknown") -> Optional[str]:
    result = _media_storage_service.upload_report(file_path, session_id=session_id)
    return result["url"] if result else None


def upload_video_clip(
    file_path: str,
    session_id: str = "unknown",
    event_id: str = "clip",
) -> Optional[str]:
    result = _media_storage_service.upload_video_clip(file_path, session_id, event_id)
    return result["url"] if result else None


# ─────────────────────────────────────────────────────────────────────────────
# MediaStore — global in-memory artifact cache  (merged from media_store.py)
# ─────────────────────────────────────────────────────────────────────────────

class MediaStore:
    """Thread-safe global in-memory artifact store with TTL."""

    def __init__(self, ttl_seconds: int = 1800):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def _key(self, session_id: str, artifact_type: str, subkey: str = "default") -> str:
        return f"{session_id}:{artifact_type}:{subkey}"

    def put(self, session_id: str, artifact_type: str, value: Any, subkey: str = "default") -> str:
        key = self._key(session_id, artifact_type, subkey)
        with self._lock:
            self._data[key] = {
                "value": value,
                "ts": time.time(),
                "session_id": session_id,
                "type": artifact_type,
            }
        return key

    def get(self, session_id: str, artifact_type: str, subkey: str = "default") -> Optional[Any]:
        key = self._key(session_id, artifact_type, subkey)
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if time.time() - entry["ts"] > self._ttl:
                del self._data[key]
                return None
            return entry["value"]

    def list_session(self, session_id: str) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        prefix = f"{session_id}:"
        with self._lock:
            for key, entry in list(self._data.items()):
                if key.startswith(prefix):
                    result.setdefault(entry["type"], []).append(key)
        return result

    def clear_session(self, session_id: str):
        prefix = f"{session_id}:"
        with self._lock:
            for key in [k for k in self._data if k.startswith(prefix)]:
                del self._data[key]


_media_store = MediaStore()

# Public alias so `from api.services.media_storage import media_store` works
media_store = _media_store


def get_media_store() -> MediaStore:
    return _media_store


# ─────────────────────────────────────────────────────────────────────────────
# ArtifactStore — per-session scoped view
# ─────────────────────────────────────────────────────────────────────────────

class ArtifactStore:
    """Session-scoped artifact isolation. Discarded on session stop / TTL."""

    def __init__(self, session_id: str, store: Optional[MediaStore] = None):
        self.session_id = session_id
        self.store = store or _media_store

    def save(self, artifact_type: str, value: Any, subkey: str = "default") -> str:
        return self.store.put(self.session_id, artifact_type, value, subkey)

    def load(self, artifact_type: str, subkey: str = "default") -> Optional[Any]:
        return self.store.get(self.session_id, artifact_type, subkey)

    def list_all(self) -> Dict[str, List[str]]:
        return self.store.list_session(self.session_id)

    def clear(self):
        self.store.clear_session(self.session_id)


def get_artifact(session_id: str) -> ArtifactStore:
    return ArtifactStore(session_id=session_id)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers used by routers / workers
# ─────────────────────────────────────────────────────────────────────────────

def store_frame(session_id: str, frame_b64: str, label: str = "frame") -> str:
    return get_artifact(session_id).save("frames", frame_b64, subkey=label)


def store_report(session_id: str, report: Dict[str, Any]) -> str:
    return get_artifact(session_id).save("reports", report, subkey="latest")


def load_report(session_id: str) -> Optional[Dict[str, Any]]:
    return get_artifact(session_id).load("reports", subkey="latest")


def store_screenshot(session_id: str, monitor_id: int, image_b64: str) -> str:
    return get_artifact(session_id).save("screenshots", image_b64, subkey=str(monitor_id))


def clear_session_artifacts(session_id: str):
    get_artifact(session_id).clear()
