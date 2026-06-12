"""
tests/unit/test_risk_engine.py
==============================
Unit tests for video_ai.risk_engine module.
"""

import pytest
from video_ai.risk_engine import (
    get_ai_verdict, map_behavior_flags_to_hp,
    build_hp_webhook_payload, _get_risk_level,
    DEFAULT_RISK_WEIGHTS, get_active_weights, set_active_weights,
    generate_report,
)


@pytest.fixture(autouse=True)
def reset_weights():
    set_active_weights(dict(DEFAULT_RISK_WEIGHTS))
    yield


def test_risk_levels():
    assert _get_risk_level(80) == "HIGH"
    assert _get_risk_level(50) == "MEDIUM"
    assert _get_risk_level(30) == "LOW"
    assert _get_risk_level(5) == "MINIMAL"


def test_ai_verdict():
    assert get_ai_verdict(risk_score=80, focus_score=100) in ("FAIL", "REVIEW")
    assert get_ai_verdict(risk_score=10, focus_score=90) == "PASS"


def test_hp_mapper():
    violations = [
        {"type": "PHONE_DETECTED"},
        {"type": "TAB_SWITCH"},
        {"type": "LOOKING_AWAY"},
    ]
    result = map_behavior_flags_to_hp(violations)
    assert "integrity" in result
    assert "focus" in result
    assert "discipline" in result
    assert result["integrity"]["flags"] == 2
    assert result["focus"]["flags"] == 0
    assert result["discipline"]["flags"] == 1


def test_generate_report():
    status = {
        "session_id": "s1", "user_id": "u1",
        "risk_score": 25, "focus_score": 90,
        "violations": [{"type": "TAB_SWITCH"}],
        "tab_switches": 1, "attention_breaks": 0,
        "total_frames": 10, "exam_id": None,
        "organization_id": None, "candidate_id": None,
    }
    report = generate_report(status)
    assert "risk_assessment" in report
    assert "behavior_flags" in report
    assert report["risk_assessment"]["risk_score"] == 25
