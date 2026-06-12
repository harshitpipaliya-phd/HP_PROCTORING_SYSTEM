"""
api/services/hp_mapper.py
=========================
HP competency model mapper service.

Maps internal violation flags to HP competency model dimensions:
  - integrity  : anti-cheating signals
  - focus      : attention / engagement
  - discipline : rule-following / procedural
"""

from typing import Dict, Any, List


INTEGRITY_FLAGS = {
    "MULTIPLE_PERSONS", "PHONE_DETECTED", "PHONE_HOLD_GESTURE",
    "unauthorized_speaker", "background_voice", "LOOKING_AWAY",
    "TAB_SWITCH",
}
FOCUS_FLAGS = {
    "ATTENTION_BREAK", "FREQUENT_LOOK_AWAY", "LOW_BLINK_RATE",
    "head_not_center",
}
DISCIPLINE_FLAGS = {
    "BOOK_DETECTED", "NOTES_DETECTED", "LAPTOP_DETECTED",
    "WRITING_GESTURE", "UNUSUAL_HAND_GESTURE",
}


class HPMapper:
    """Service that maps behavior flags to HP competency model."""

    def map_flags(self, violations: List[Any]) -> Dict[str, Any]:
        integrity = focus = discipline = 0
        for v in violations:
            vtype = v if isinstance(v, str) else v.get("type", "")
            if vtype in INTEGRITY_FLAGS:
                integrity += 1
            if vtype in FOCUS_FLAGS:
                focus += 1
            if vtype in DISCIPLINE_FLAGS:
                discipline += 1

        total = max(integrity + focus + discipline, 1)
        return {
            "integrity": {
                "score": max(0, 100 - integrity * 15),
                "flags": integrity,
                "level": _level(integrity, 3, 1),
            },
            "focus": {
                "score": max(0, 100 - focus * 10),
                "flags": focus,
                "level": _level(focus, 5, 2),
            },
            "discipline": {
                "score": max(0, 100 - discipline * 12),
                "flags": discipline,
                "level": _level(discipline, 3, 1),
            },
            "total_flags": total,
        }

    def build_webhook_payload(self, report: Dict[str, Any]) -> Dict[str, Any]:
        ra = report.get("risk_assessment", {})
        metrics = report.get("metrics", {})
        violations = report.get("violations", {})
        bf = report.get("behavior_flags", {})

        return {
            "hp_schema_version": "1.0",
            "session_id": report.get("session_id"),
            "candidate_id": report.get("user_id"),
            "exam_id": report.get("exam_id"),
            "timestamp": report.get("timestamp"),
            "proctoring_result": {
                "verdict": ra.get("ai_verdict", "INCONCLUSIVE"),
                "risk_score": ra.get("risk_score", 0),
                "focus_score": ra.get("focus_score", 100),
                "risk_level": ra.get("risk_level", "MINIMAL"),
            },
            "competency_scores": {
                "integrity": bf.get("integrity", {}).get("score", 100),
                "focus": bf.get("focus", {}).get("score", 100),
                "discipline": bf.get("discipline", {}).get("score", 100),
            },
            "metrics": {
                "total_frames": metrics.get("total_frames", 0),
                "tab_switches": metrics.get("tab_switches", 0),
                "attention_breaks": metrics.get("attention_breaks", 0),
                "total_violations": violations.get("total", 0),
            },
            "violation_types": list(violations.get("by_type", {}).keys()),
            "recommendations": report.get("recommendations", []),
        }


def _level(count: int, high: int, med: int) -> str:
    if count >= high:
        return "LOW"
    if count >= med:
        return "MEDIUM"
    return "HIGH"
