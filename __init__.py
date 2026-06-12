"""
HP Proctoring Backend - Unified AI Proctoring Solution
=======================================================

A comprehensive AI-powered proctoring system combining:
- Video AI: Face/gaze/person/object/mobile detection
- Audio: Voice activity/speaker detection
- Screen: Multi-monitor capture and monitoring

Author: HP Proctoring Team
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "HP Proctoring Team"

from core.config import Settings, get_settings
from core.session import ProctoringSession, get_current_session

__all__ = [
    "Settings", "get_settings",
    "ProctoringSession", "get_current_session",
]