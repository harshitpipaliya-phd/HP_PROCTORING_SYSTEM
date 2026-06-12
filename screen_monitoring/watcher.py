"""
screen_monitoring/watcher.py
============================
Stateful monitor-change tracker with:
- Automatic interval-based screenshot capture
- Cloudinary upload for screenshots
- Monitor change events integrated into session violation log
- Thread-safe singleton
"""

import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from screen_monitoring.capture import get_monitor_count, get_monitor_info, capture_all_monitors
from screen_monitoring.detector import detect_monitors, detect_browser_windows


class MonitorWatcher:
    """Thread-safe monitor state tracker with auto-screenshot support."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_count: int = -1
        self._last_state: dict = {}
        self._change_history: List[Dict[str, Any]] = []
        self._MAX_HISTORY = 100

        # Auto-screenshot state
        self._auto_thread: Optional[threading.Thread] = None
        self._auto_running: bool = False
        self._auto_interval: int = 30  # seconds
        self._screenshot_dir: str = "static/screenshots"
        self._session_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Core monitoring
    # ------------------------------------------------------------------

    def check_changes(self, browser_hint: dict = None) -> Dict[str, Any]:
        """
        Poll monitor state. Returns:
            changed      - True if monitor count changed since last call
            data         - full detect_monitors() result
            change_event - populated only when changed=True
        """
        data = detect_monitors(browser_hint=browser_hint)
        current_count = data.get("monitor_count", 1)

        with self._lock:
            prev_count = self._last_count
            changed = (prev_count != -1) and (current_count != prev_count)

            self._last_count = current_count
            self._last_state = data

            change_event = None
            if changed:
                change_event = {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "previous_count": prev_count,
                    "current_count": current_count,
                    "direction": "connected" if current_count > prev_count else "disconnected",
                    "data": data,
                }
                self._change_history.append(change_event)
                if len(self._change_history) > self._MAX_HISTORY:
                    self._change_history.pop(0)

                print(
                    f"[MONITOR ALERT] Count changed {prev_count} → {current_count} "
                    f"({change_event['direction']})"
                )

                # Inject into session violation log
                self._record_monitor_violation(change_event)

        return {
            "changed": changed,
            "data": data,
            "change_event": change_event,
        }

    def _record_monitor_violation(self, change_event: Dict[str, Any]):
        """Fire a session violation when monitor count changes."""
        try:
            from core.session import get_current_session, update_session_risk
            session = get_current_session()
            if session:
                session.add_violation("MONITOR_CHANGE", {
                    "previous": change_event["previous_count"],
                    "current": change_event["current_count"],
                    "direction": change_event["direction"],
                })
                update_session_risk(session.risk_score + 20, ["MONITOR_CHANGE"])
        except Exception as e:
            print(f"[watcher] _record_monitor_violation: {e}")

    # ------------------------------------------------------------------
    # Screenshot capture (manual + automatic)
    # ------------------------------------------------------------------

    def capture_screenshots(
        self,
        output_dir: str = None,
        upload_cloudinary: bool = False,
        session_id: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Capture screenshots from all monitors.
        Optionally upload to Cloudinary and log to DB.
        """
        out_dir = output_dir or self._screenshot_dir
        results = capture_all_monitors(out_dir)

        if not results:
            return results

        for item in results:
            # Log to DB
            try:
                from database.client import _supabase, _db_available
                if _db_available and _supabase is not None and session_id:
                    _supabase.table("recordings").insert({
                        "session_id": session_id,
                        "recording_type": "screenshot",
                        "local_path": item.get("path"),
                        "monitor_id": item.get("monitor_id", 1),
                        "metadata": str(item),
                    }).execute()
            except Exception:
                pass

            # Cloudinary upload
            if upload_cloudinary and item.get("path"):
                try:
                    from video_ai.risk_engine import upload_screenshot_to_cloudinary
                    upload_result = upload_screenshot_to_cloudinary(
                        item["path"],
                        session_id=session_id or "unknown",
                        monitor_id=item.get("monitor_id", 1),
                    )
                    if upload_result:
                        item["cloudinary_url"] = upload_result.get("url")
                        item["cloudinary_public_id"] = upload_result.get("public_id")
                        # Update DB record with URL
                        try:
                            from database.client import _supabase, _db_available
                            if _db_available and _supabase is not None:
                                _supabase.table("recordings").update({
                                    "url": upload_result.get("url"),
                                    "cloudinary_public_id": upload_result.get("public_id"),
                                }).eq("local_path", item.get("path")).execute()
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[watcher] Cloudinary upload failed: {e}")

        return results

    # ------------------------------------------------------------------
    # Auto-screenshot background thread
    # ------------------------------------------------------------------

    def start_auto_screenshots(
        self,
        interval_seconds: int = 30,
        output_dir: str = "static/screenshots",
        upload_cloudinary: bool = False,
        session_id: str = None,
    ):
        """Start background thread that captures screenshots on interval."""
        if self._auto_running:
            return

        self._auto_interval = interval_seconds
        self._screenshot_dir = output_dir
        self._session_id = session_id
        self._auto_running = True

        def _loop():
            print(f"[watcher] Auto-screenshot started (every {interval_seconds}s)")
            while self._auto_running:
                try:
                    self.capture_screenshots(
                        output_dir=output_dir,
                        upload_cloudinary=upload_cloudinary,
                        session_id=session_id,
                    )
                    # Update session screenshot count
                    try:
                        from core.session import get_current_session
                        sess = get_current_session()
                        if sess:
                            sess.screenshots_captured += 1
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[watcher] Auto-screenshot error: {e}")
                time.sleep(interval_seconds)
            print("[watcher] Auto-screenshot stopped")

        self._auto_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_thread.start()

    def stop_auto_screenshots(self):
        """Stop the background screenshot thread."""
        self._auto_running = False
        if self._auto_thread:
            self._auto_thread.join(timeout=5)
            self._auto_thread = None

    # ------------------------------------------------------------------
    # Properties / reset
    # ------------------------------------------------------------------

    @property
    def last_state(self) -> dict:
        with self._lock:
            return dict(self._last_state)

    @property
    def change_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._change_history)

    def reset(self):
        with self._lock:
            self._last_count = -1
            self._last_state = {}
            self._change_history = []


# Module-level singleton
_watcher: Optional[MonitorWatcher] = None
_watcher_lock = threading.Lock()


def get_monitor_watcher() -> MonitorWatcher:
    global _watcher
    with _watcher_lock:
        if _watcher is None:
            _watcher = MonitorWatcher()
        return _watcher
