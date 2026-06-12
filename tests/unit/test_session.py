"""
tests/unit/test_session.py
==========================
Unit tests for core.session module.
"""

import pytest
from core.session import (
    ProctoringSession, start_session, stop_session,
    get_session_status, get_current_session, record_tab_switch,
    update_session_risk, reset_session,
)


def test_proctoring_session_creation():
    session = ProctoringSession(session_id="test-001", user_id="u1")
    assert session.session_id == "test-001"
    assert session.user_id == "u1"
    assert session._active is False


def test_session_lifecycle():
    reset_session()
    sid = start_session(user_id="alice")
    sess = get_current_session()
    assert sess is not None
    assert sess._active is True
    status = get_session_status()
    assert status["active"] is True

    info = stop_session("manual")
    assert "session_id" in info
    sess_after = get_current_session()
    assert getattr(sess_after, "_active", False) is False


def test_tab_switch_records_violation():
    reset_session()
    start_session(user_id="bob")
    record_tab_switch()
    status = get_session_status()
    assert status["tab_switches"] >= 1


def test_update_risk_and_flags():
    reset_session()
    start_session(user_id="carol")
    update_session_risk(80, ["PHONE_DETECTED", "MULTIPLE_PERSONS"])
    status = get_session_status()
    assert status["risk_score"] >= 80
