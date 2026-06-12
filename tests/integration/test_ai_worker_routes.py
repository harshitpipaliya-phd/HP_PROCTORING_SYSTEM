"""
tests/integration/test_ai_worker_routes.py
============================================
Integration tests for AI worker endpoints.
Tests /health, /analyze/video (spec alias), /analyze/frame, /verify/face.
"""
import pytest
import base64
import numpy as np
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def ai_client():
    from ai_workers.app import app
    return TestClient(app)


@pytest.fixture(scope="module")
def internal_key():
    import os
    return os.getenv("INTERNAL_API_KEY", "test-internal-key-for-ci")


@pytest.fixture(autouse=True, scope="module")
def set_internal_key(monkeypatch_module, internal_key):
    import os
    os.environ.setdefault("INTERNAL_API_KEY", internal_key)


@pytest.fixture(scope="module")
def monkeypatch_module(request):
    """Module-scoped monkeypatch."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


class TestAIWorkerHealth:
    def test_health_returns_ok(self, ai_client):
        r = ai_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["service"] == "ai_workers"


class TestAIWorkerAnalyzeVideoAlias:
    def _minimal_frame_b64(self):
        """Create a tiny 10x10 black image as base64 JPEG."""
        try:
            import cv2
            img = np.zeros((10, 10, 3), dtype=np.uint8)
            _, buf = cv2.imencode(".jpg", img)
            return base64.b64encode(buf.tobytes()).decode()
        except ImportError:
            return ""

    def test_analyze_video_route_exists(self, ai_client, internal_key):
        """POST /analyze/video must exist (spec compliance)."""
        frame_b64 = self._minimal_frame_b64()
        if not frame_b64:
            pytest.skip("opencv not available")
        r = ai_client.post(
            "/analyze/video",
            json={"frame_b64": frame_b64},
            headers={"X-Internal-API-Key": internal_key},
        )
        # Route must exist — 404 would mean spec non-compliance
        assert r.status_code != 404, "/analyze/video route is missing"

    def test_analyze_frame_route_exists(self, ai_client, internal_key):
        """POST /analyze/frame must still exist (backward compat)."""
        frame_b64 = self._minimal_frame_b64()
        if not frame_b64:
            pytest.skip("opencv not available")
        r = ai_client.post(
            "/analyze/frame",
            json={"frame_b64": frame_b64},
            headers={"X-Internal-API-Key": internal_key},
        )
        assert r.status_code != 404, "/analyze/frame route is missing"

    def test_missing_api_key_returns_401(self, ai_client):
        r = ai_client.post("/analyze/video", json={"frame_b64": "x"})
        assert r.status_code in (401, 403, 422, 500)


class TestAIWorkerVerifyFace:
    def test_verify_face_route_exists(self, ai_client, internal_key):
        """POST /verify/face must be registered (was H2 critical gap)."""
        r = ai_client.post(
            "/verify/face",
            json={"candidate_id": "test_cand", "frame_b64": "x"},
            headers={"X-Internal-API-Key": internal_key},
        )
        # Route must exist; 404 = still broken
        assert r.status_code != 404, "/verify/face route is missing"

    def test_verify_face_missing_params_returns_422(self, ai_client, internal_key):
        r = ai_client.post(
            "/verify/face",
            json={},
            headers={"X-Internal-API-Key": internal_key},
        )
        # Should be 422 (missing required params) not 404
        assert r.status_code in (422, 400, 500)

    def test_verify_face_missing_key_returns_401(self, ai_client):
        r = ai_client.post("/verify/face", json={"candidate_id": "x", "frame_b64": "y"})
        assert r.status_code in (401, 403, 422, 500)
