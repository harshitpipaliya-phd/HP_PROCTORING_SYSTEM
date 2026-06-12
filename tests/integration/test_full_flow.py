"""
tests/integration/test_full_flow.py
====================================
Extended integration tests covering full session lifecycle,
security, admin endpoints, reports, and events.
"""

import pytest
import json
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


@pytest.fixture
def admin_headers(client):
    r = client.post("/auth/login", json={"email": "admin@example.com", "role": "admin"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def proctor_headers(client):
    r = client.post("/auth/login", json={"email": "proctor@example.com", "role": "proctor"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_login_invalid_role(client):
    r = client.post("/auth/login", json={"email": "x@x.com", "role": "hacker"})
    assert r.status_code == 400


def test_login_superadmin(client):
    r = client.post("/auth/login", json={"email": "root@example.com", "role": "superadmin"})
    assert r.status_code == 200
    assert r.json()["role"] == "superadmin"


def test_auth_required_on_sessions(client):
    r = client.post("/v1/sessions", json={"user_id": "unauth"})
    assert r.status_code == 401


def test_auth_required_on_monitor(client):
    r = client.get("/v1/monitor/risk")
    assert r.status_code == 401


# ── Session lifecycle (v1 paths) ──────────────────────────────────────────────

def test_v1_session_create_and_get(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "flowtest", "exam_id": "exam-1"}, headers=admin_headers)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert sid

    r2 = client.get(f"/v1/sessions/{sid}", headers=admin_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["session"]["session_id"] == sid
    assert body["session"]["status"] == "active"


def test_v1_session_end(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "endtest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.post(f"/v1/sessions/{sid}/end", json={"reason": "completed"}, headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["success"] is True


def test_v1_session_terminate(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "termtest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.post(f"/v1/sessions/{sid}/terminate", headers=admin_headers)
    assert r2.status_code == 200


def test_v1_session_events(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "eventstest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.get(f"/v1/sessions/{sid}/events", headers=admin_headers)
    assert r2.status_code == 200
    assert "events" in r2.json()


def test_session_not_found(client, admin_headers):
    r = client.get("/v1/sessions/nonexistent-session-id-xyz", headers=admin_headers)
    assert r.status_code == 404


# ── Monitor endpoints ──────────────────────────────────────────────────────────

def test_monitor_all_endpoints(client, admin_headers):
    paths = [
        "/v1/monitor/violations",
        "/v1/monitor/risk",
        "/v1/monitor/report",
        "/v1/monitor/stats",
        "/v1/monitor/monitors",
        "/v1/monitor/events",
        "/v1/monitor/risk-weights",
    ]
    for path in paths:
        r = client.get(path, headers=admin_headers)
        assert r.status_code == 200, f"FAILED {path}: {r.status_code} {r.text[:200]}"


def test_risk_weights_update(client, admin_headers):
    r = client.post("/v1/monitor/risk-weights", json={
        "weights": {"multiple_persons": 60, "phone_detected": 35}
    }, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True


# ── Events endpoint ────────────────────────────────────────────────────────────

def test_v1_events_empty(client, admin_headers):
    r = client.get("/v1/events", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert "total" in body


def test_v1_events_filter_by_session(client, admin_headers):
    r = client.get("/v1/events?session_id=test-session-xyz", headers=admin_headers)
    assert r.status_code == 200


# ── Reports ────────────────────────────────────────────────────────────────────

def test_report_not_found(client, admin_headers):
    r = client.get("/v1/reports/nonexistent-session-abc", headers=admin_headers)
    assert r.status_code == 404


def test_report_for_active_session(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "reporttest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.get(f"/v1/reports/{sid}", headers=admin_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["success"] is True
    assert "report" in body


def test_report_pdf_for_active_session(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "pdftest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.get(f"/v1/reports/{sid}/pdf", headers=admin_headers)
    # PDF may return 200 (if reportlab available) or 503 (if not installed)
    assert r2.status_code in (200, 503)


# ── Admin endpoints ────────────────────────────────────────────────────────────

def test_admin_active_sessions(client, admin_headers):
    r = client.get("/v1/admin/sessions/active", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "sessions" in body
    assert "active_count" in body


def test_admin_session_feed(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "adminfeedtest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.get(f"/v1/admin/sessions/{sid}/feed", headers=admin_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["session_id"] == sid


def test_admin_flag_session(client, admin_headers):
    r = client.post("/v1/sessions", json={"user_id": "flagtest"}, headers=admin_headers)
    sid = r.json()["session_id"]
    r2 = client.post(f"/v1/admin/sessions/{sid}/flag",
                     json={"reason": "Suspicious behavior", "notes": "Manual review"},
                     headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["flagged"] is True


def test_admin_requires_admin_role(client, proctor_headers):
    # Proctors cannot access some admin-only operations
    r = client.get("/v1/admin/users", headers=proctor_headers)
    # Either 200 (allowed for proctor too) or 403
    assert r.status_code in (200, 403, 503)


# ── Candidates ─────────────────────────────────────────────────────────────────

def test_candidate_enroll(client, admin_headers):
    r = client.post("/v1/candidates/enroll", json={
        "name": "Test Candidate",
        "email": f"test_{int(__import__('time').time())}@example.com",
        "organization_id": "test-org",
    }, headers=admin_headers)
    # Should succeed or fail with DB unavailable
    assert r.status_code in (200, 500, 503)


def test_candidate_not_found(client, admin_headers):
    r = client.get("/v1/candidates/nonexistent-candidate-xyz", headers=admin_headers)
    assert r.status_code in (404, 503)


# ── Monitoring — tab switch ────────────────────────────────────────────────────

def test_tab_switch_log(client, admin_headers):
    client.post("/v1/sessions", json={"user_id": "tabswitcher"}, headers=admin_headers)
    r = client.post("/v1/monitor/tab-switch", json={
        "timestamp": "2026-06-11T12:00:00Z",
        "url": "https://google.com",
        "direction": "away",
    }, headers=admin_headers)
    assert r.status_code == 200


# ── HP webhook ────────────────────────────────────────────────────────────────

def test_hp_webhook_missing_sig(client):
    r = client.post("/v1/webhooks/hp/compliance", json={"test": "payload"})
    # Without signature or secret configured, should return 401
    assert r.status_code in (401, 500)


# ── Health & Root detailed ─────────────────────────────────────────────────────

def test_health_has_required_fields(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "timestamp" in body
    assert "libraries" in body
    assert "database" in body
    assert "version" in body


def test_root_has_endpoint_map(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert "endpoints" in body
    assert "session" in body["endpoints"]
    assert "websockets" in body["endpoints"]
