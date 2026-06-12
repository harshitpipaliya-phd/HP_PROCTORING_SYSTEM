"""
database/__init__.py
====================
Database Module - Supabase integration for logging and data persistence.

Features:
  - Async logging to Supabase
  - Behavior event logging
  - Session logging
  - Report persistence
  - Silent failure handling (never crashes the app)
"""

from database.client import (
    init_database,
    is_available,
    is_available as db_available,
    log_event,
    log_session,
    log_report,
    log_behavior_event,
    log_audio_event,
)
from database.queries import (
    insert_log,
    insert_behavior_log,
    fetch_recent_logs,
    fetch_risk_stats,
    fetch_sessions,
    fetch_reports,
    fetch_audio_logs,
    fetch_events_for_session,
)

__all__ = [
    "init_database",
    "is_available",
    "db_available",
    "log_event",
    "log_session",
    "log_report",
    "log_behavior_event",
    "log_audio_event",
    "insert_log",
    "insert_behavior_log",
    "fetch_recent_logs",
    "fetch_risk_stats",
    "fetch_sessions",
    "fetch_reports",
    "fetch_audio_logs",
    "fetch_events_for_session",
]