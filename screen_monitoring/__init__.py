"""
screen_monitoring/__init__.py
============================
Screen Monitoring Module - Multi-monitor capture and change detection.

Features:
  - Multi-monitor screenshot capture
  - Monitor change detection
  - Browser window monitoring
  - Screen state analysis
"""

from screen_monitoring.capture import capture_all_monitors, is_screen_capture_available
from screen_monitoring.watcher import MonitorWatcher, get_monitor_watcher
from screen_monitoring.detector import detect_monitors, detect_browser_windows

__all__ = [
    "capture_all_monitors",
    "is_screen_capture_available",
    "MonitorWatcher",
    "get_monitor_watcher",
    "detect_monitors",
    "detect_browser_windows",
]