"""
api/services/media_store.py
============================
DEPRECATED — kept for backward-compatibility only.
All functionality has been merged into api/services/media_storage.py.

Any code importing from this module continues to work unchanged.
"""
from api.services.media_storage import (  # noqa: F401
    MediaStore,
    ArtifactStore,
    get_media_store,
    get_artifact,
    store_frame,
    store_report,
    load_report,
    store_screenshot,
    clear_session_artifacts,
    media_store as _media_store,
)

# Legacy aliases
media_store = _media_store

__all__ = [
    "MediaStore", "ArtifactStore", "get_media_store", "get_artifact",
    "store_frame", "store_report", "load_report", "store_screenshot",
    "clear_session_artifacts", "media_store",
]
