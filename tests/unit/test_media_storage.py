"""
tests/unit/test_media_storage.py
==================================
Unit tests for the merged media_storage service.
Tests MediaStore, ArtifactStore, and convenience helpers.
"""
import time
import pytest


class TestMediaStore:
    def _store(self):
        from api.services.media_storage import MediaStore
        return MediaStore(ttl_seconds=5)

    def test_put_and_get(self):
        store = self._store()
        store.put("sess1", "frames", "base64data", "frame_001")
        result = store.get("sess1", "frames", "frame_001")
        assert result == "base64data"

    def test_get_missing_returns_none(self):
        store = self._store()
        assert store.get("nosess", "notype") is None

    def test_get_expired_returns_none(self):
        from api.services.media_storage import MediaStore
        store = MediaStore(ttl_seconds=0)  # instant expiry
        store.put("sess2", "reports", {"data": 1})
        time.sleep(0.01)
        assert store.get("sess2", "reports") is None

    def test_list_session(self):
        store = self._store()
        store.put("sess3", "frames", "f1", "a")
        store.put("sess3", "frames", "f2", "b")
        store.put("sess3", "screenshots", "s1", "c")
        listing = store.list_session("sess3")
        assert "frames" in listing
        assert len(listing["frames"]) == 2

    def test_clear_session(self):
        store = self._store()
        store.put("sess4", "frames", "x")
        store.clear_session("sess4")
        assert store.get("sess4", "frames") is None

    def test_different_sessions_isolated(self):
        store = self._store()
        store.put("s_a", "reports", "report_a")
        store.put("s_b", "reports", "report_b")
        assert store.get("s_a", "reports") == "report_a"
        assert store.get("s_b", "reports") == "report_b"


class TestArtifactStore:
    def test_save_and_load(self):
        from api.services.media_storage import ArtifactStore, MediaStore
        store = MediaStore()
        art = ArtifactStore("test_session", store)
        art.save("frames", "b64_data", "key1")
        assert art.load("frames", "key1") == "b64_data"

    def test_clear(self):
        from api.services.media_storage import ArtifactStore, MediaStore
        store = MediaStore()
        art = ArtifactStore("clear_sess", store)
        art.save("screenshots", "img_data")
        art.clear()
        assert art.load("screenshots") is None


class TestConvenienceHelpers:
    def test_store_and_load_report(self):
        from api.services.media_storage import store_report, load_report
        session_id = "helper_test_sess"
        report = {"session_id": session_id, "risk_score": 42}
        store_report(session_id, report)
        loaded = load_report(session_id)
        assert loaded is not None
        assert loaded["risk_score"] == 42

    def test_load_missing_report_returns_none(self):
        from api.services.media_storage import load_report
        assert load_report("nonexistent_session_xyz") is None

    def test_store_frame(self):
        from api.services.media_storage import store_frame, get_artifact
        store_frame("frame_sess", "base64_frame_data", "label_1")
        art = get_artifact("frame_sess")
        result = art.load("frames", "label_1")
        assert result == "base64_frame_data"

    def test_clear_session_artifacts(self):
        from api.services.media_storage import store_report, load_report, clear_session_artifacts
        store_report("clear_test", {"data": "value"})
        clear_session_artifacts("clear_test")
        assert load_report("clear_test") is None


class TestMediaStoreShimImport:
    """Ensure the deprecated media_store.py shim still works."""
    def test_shim_imports(self):
        from api.services.media_store import (
            MediaStore, ArtifactStore, get_media_store,
            get_artifact, store_frame, store_report,
            load_report, clear_session_artifacts,
        )
        # All should be callable
        store = get_media_store()
        assert store is not None
        art = get_artifact("shim_test")
        assert art is not None
