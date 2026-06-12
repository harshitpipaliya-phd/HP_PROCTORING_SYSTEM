"""
tests/integration/test_api.py
=============================
Integration tests for FastAPI routers.
"""

import pytest
import os
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get JWT auth headers using the test login endpoint."""
    from api.main import app
    from core.config import get_settings
    settings = get_settings()
    client = TestClient(app)
    r = client.post("/auth/login", json={
        "email": "test@example.com",
        "role": "admin"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_and_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "service" in r.json()

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_login(client):
    r = client.post("/auth/login", json={
        "email": "admin@example.com",
        "role": "admin"
    })
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"


def test_session_lifecycle(client, auth_headers):
    r = client.post("/session/start", json={"user_id": "testuser"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    sid = body["session_id"]

    r = client.get("/session/status", headers=auth_headers)
    assert r.status_code == 200

    r = client.post("/session/stop", json={"reason": "manual"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_session_start_v2(client, auth_headers):
    r = client.post("/session/start/v2", json={
        "user_id": "u1",
        "exam_id": "e1",
        "candidate_id": "c1",
    }, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["candidate_id"] == "c1"


def test_session_start_idempotent(client, auth_headers):
    client.post("/session/start", json={"user_id": "idempotent"}, headers=auth_headers)
    r = client.post("/session/start", json={"user_id": "idempotent"}, headers=auth_headers)
    assert r.status_code == 200
    assert "already active" in r.json().get("message", "").lower()


def test_violations_empty(client, auth_headers):
    r = client.get("/monitor/violations", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body
    assert "list" in body


def test_risk_endpoint(client, auth_headers):
    r = client.get("/monitor/risk", headers=auth_headers)
    assert r.status_code == 200
    assert "risk_score" in r.json()


def test_report_text(client, auth_headers):
    r = client.get("/monitor/report/text", headers=auth_headers)
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert isinstance(r.text, str)


def test_stats_without_db(client, auth_headers):
    r = client.get("/monitor/stats", headers=auth_headers)
    assert r.status_code == 200


def test_logs_endpoints(client, auth_headers):
    for path in ("/logs/behavior", "/logs/audio", "/logs/sessions"):
        r = client.get(path, headers=auth_headers)
        assert r.status_code == 200


def test_monitors_endpoint(client, auth_headers):
    r = client.get("/monitor/monitors", headers=auth_headers)
    assert r.status_code == 200


def test_events_endpoint(client, auth_headers):
    r = client.get("/monitor/events", headers=auth_headers)
    assert r.status_code == 200


def test_risk_weights_get(client, auth_headers):
    r = client.get("/monitor/risk-weights", headers=auth_headers)
    assert r.status_code == 200
    assert "weights" in r.json()
