"""
core/__init__.py
================
Core module for HP Proctoring Backend.
Contains configuration, session management, and shared utilities.
"""

from core.config import Settings, get_settings, reload_settings
from core.session import (
    ProctoringSession,
    get_current_session,
    start_session,
    stop_session,
    get_session_status,
    update_session_risk,
    record_tab_switch,
    record_attention_break,
    reset_session,
)

__all__ = [
    "Settings", "get_settings", "reload_settings",
    "ProctoringSession", "get_current_session",
    "start_session", "stop_session", "get_session_status",
    "update_session_risk", "record_tab_switch", "record_attention_break",
    "reset_session",
]