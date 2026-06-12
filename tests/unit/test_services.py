"""
tests/unit/test_services.py
============================
Unit tests for service-layer classes: RiskEngine, ReportBuilder, HPMapper.
"""

import pytest


# ── RiskEngine ───────────────────────────────────────────────────────────────

class TestRiskEngine:
    def _engine(self, session_id="test-sess"):
        from api.services.risk_engine import RiskEngine
        return RiskEngine(session_id)

    def test_increment_and_get(self):
        engine = self._engine("inc-test")
        v1 = engine.increment(10)
        assert v1 == 10
        v2 = engine.increment(15)
        assert v2 == 25
        assert engine.get() == 25

    def test_set(self):
        engine = self._engine("set-test")
        engine.set(42)
        assert engine.get() == 42

    def test_classify_low(self):
        from api.services.risk_engine import RiskEngine
        assert RiskEngine.classify(0) == "low"
        assert RiskEngine.classify(39) == "low"

    def test_classify_medium(self):
        from api.services.risk_engine import RiskEngine
        assert RiskEngine.classify(40) == "medium"
        assert RiskEngine.classify(69) == "medium"

    def test_classify_high(self):
        from api.services.risk_engine import RiskEngine
        assert RiskEngine.classify(70) == "high"
        assert RiskEngine.classify(100) == "high"

    def test_process_event_returns_dict(self):
        engine = self._engine("evt-test")
        result = engine.process_event("multiple_persons", {})
        assert "event_type" in result
        assert "risk_delta" in result
        assert "new_score" in result
        assert "risk_level" in result
        assert result["risk_delta"] > 0  # multiple_persons has positive weight

    def test_process_unknown_event_no_increment(self):
        engine = self._engine("unknown-test")
        initial = engine.get()
        result = engine.process_event("totally_unknown_event_xyz", {})
        assert result["risk_delta"] == 0
        assert engine.get() == initial

    def test_compute_risk_delta_known(self):
        from api.services.risk_engine import RiskEngine
        delta = RiskEngine.compute_risk_delta("phone_detected")
        assert delta == 30

    def test_compute_risk_delta_unknown(self):
        from api.services.risk_engine import RiskEngine
        delta = RiskEngine.compute_risk_delta("not_a_real_event")
        assert delta == 0

    def test_delete_resets_score(self):
        engine = self._engine("del-test")
        engine.increment(50)
        engine.delete()
        assert engine.get() == 0


# ── ReportBuilder ────────────────────────────────────────────────────────────

class TestReportBuilder:
    def _sample_state(self):
        return {
            "session_id": "test-report-session",
            "user_id": "user-1",
            "exam_id": "exam-1",
            "risk_score": 35,
            "focus_score": 70,
            "violations": [
                {"type": "TAB_SWITCH", "timestamp": "2026-06-11T10:00:00"},
            ],
            "tab_switches": 2,
            "attention_breaks": 1,
            "total_frames": 100,
        }

    def test_build_returns_report(self):
        from api.services.report_builder import ReportBuilder
        rb = ReportBuilder()
        report = rb.build(self._sample_state())
        assert isinstance(report, dict)
        assert "session_id" in report or "risk_assessment" in report

    def test_build_pdf_bytes_or_none(self):
        from api.services.report_builder import ReportBuilder
        rb = ReportBuilder()
        report = rb.build(self._sample_state())
        result = rb.build_pdf(report)
        # ReportLab may or may not be installed
        assert result is None or isinstance(result, bytes)

    def test_build_hp_payload(self):
        from api.services.report_builder import ReportBuilder
        rb = ReportBuilder()
        report = rb.build(self._sample_state())
        payload = rb.build_hp_payload(report)
        assert isinstance(payload, dict)


# ── HPMapper ─────────────────────────────────────────────────────────────────

class TestHPMapper:
    def test_empty_violations(self):
        from api.services.hp_mapper import HPMapper
        mapper = HPMapper()
        result = mapper.map_flags([])
        assert "integrity" in result
        assert "focus" in result
        assert "discipline" in result
        assert result["integrity"]["flags"] == 0

    def test_integrity_flag(self):
        from api.services.hp_mapper import HPMapper
        mapper = HPMapper()
        result = mapper.map_flags([{"type": "MULTIPLE_PERSONS"}])
        assert result["integrity"]["flags"] >= 1
        assert result["integrity"]["score"] < 100

    def test_focus_flag(self):
        from api.services.hp_mapper import HPMapper
        mapper = HPMapper()
        result = mapper.map_flags([{"type": "ATTENTION_BREAK"}])
        assert result["focus"]["flags"] >= 1

    def test_discipline_flag(self):
        from api.services.hp_mapper import HPMapper
        mapper = HPMapper()
        result = mapper.map_flags([{"type": "BOOK_DETECTED"}])
        assert result["discipline"]["flags"] >= 1

    def test_string_violations(self):
        from api.services.hp_mapper import HPMapper
        mapper = HPMapper()
        result = mapper.map_flags(["TAB_SWITCH", "PHONE_DETECTED"])
        assert result["integrity"]["flags"] >= 1

    def test_score_decreases_with_violations(self):
        from api.services.hp_mapper import HPMapper
        mapper = HPMapper()
        few = mapper.map_flags([{"type": "MULTIPLE_PERSONS"}])
        many = mapper.map_flags([{"type": "MULTIPLE_PERSONS"}] * 10)
        assert many["integrity"]["score"] <= few["integrity"]["score"]
