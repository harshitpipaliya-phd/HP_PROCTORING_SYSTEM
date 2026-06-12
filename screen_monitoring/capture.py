"""
screen_monitoring/capture.py
============================
Capture screenshots from ALL connected monitors.
Safe on HuggingFace / Docker (returns empty list, no crash).
"""

import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# MSS for multi-screen capture
_MSS_AVAILABLE = False
try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except Exception:
    pass


def capture_all_monitors(output_dir: str = "static/screenshots") -> List[Dict[str, Any]]:
    """
    Capture one PNG per physical monitor.
    
    Args:
        output_dir: Directory to save screenshots
        
    Returns:
        List of dicts: {monitor_id, filename, path, url, width, height}
        Empty list if mss is unavailable or no display is accessible.
    """
    if not _MSS_AVAILABLE:
        return []
    
    os.makedirs(output_dir, exist_ok=True)
    screenshots = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    
    try:
        with mss.mss() as sct:
            # sct.monitors[0] = virtual combined screen; [1:] = real monitors
            real_monitors = sct.monitors[1:]
            if not real_monitors:
                return []
            
            for idx, monitor in enumerate(real_monitors):
                try:
                    filename = f"monitor_{idx + 1}_{ts}.png"
                    filepath = os.path.join(output_dir, filename)
                    
                    sct_img = sct.grab(monitor)
                    mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)
                    
                    screenshots.append({
                        "monitor_id": idx + 1,
                        "filename": filename,
                        "path": filepath,
                        "url": f"/{output_dir}/{filename}",
                        "width": monitor["width"],
                        "height": monitor["height"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    print(f"[screen_monitoring] Monitor {idx + 1} capture failed: {e}")
    
    except Exception as e:
        print(f"[screen_monitoring] mss session failed: {e}")
    
    return screenshots


def capture_monitor(monitor_id: int = 1, output_dir: str = "static/screenshots") -> Optional[Dict[str, Any]]:
    """
    Capture a specific monitor.
    
    Args:
        monitor_id: Monitor number (1-based)
        output_dir: Directory to save screenshots
        
    Returns:
        Dict with screenshot info or None if capture fails
    """
    if not _MSS_AVAILABLE:
        return None
    
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    
    try:
        with mss.mss() as sct:
            monitors = sct.monitors[1:]
            if monitor_id > len(monitors):
                return None
            
            monitor = monitors[monitor_id - 1]
            filename = f"monitor_{monitor_id}_{ts}.png"
            filepath = os.path.join(output_dir, filename)
            
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)
            
            return {
                "monitor_id": monitor_id,
                "filename": filename,
                "path": filepath,
                "url": f"/{output_dir}/{filename}",
                "width": monitor["width"],
                "height": monitor["height"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        print(f"[screen_monitoring] Monitor {monitor_id} capture failed: {e}")
        return None


def capture_primary_monitor(output_dir: str = "static/screenshots") -> Optional[Dict[str, Any]]:
    """Capture the primary monitor (monitor 1)."""
    return capture_monitor(1, output_dir)


def is_screen_capture_available() -> bool:
    """Return True if multi-screen capture is possible in this environment."""
    return _MSS_AVAILABLE


def get_monitor_count() -> int:
    """Get the number of connected monitors."""
    if not _MSS_AVAILABLE:
        return 0
    
    try:
        with mss.mss() as sct:
            return len(sct.monitors) - 1  # Exclude virtual combined screen
    except Exception:
        return 0


def get_monitor_info() -> List[Dict[str, Any]]:
    """Get information about all connected monitors."""
    if not _MSS_AVAILABLE:
        return []
    
    try:
        with mss.mss() as sct:
            monitors = sct.monitors[1:]
            return [
                {
                    "monitor_id": idx + 1,
                    "width": m["width"],
                    "height": m["height"],
                    "x": m["x"],
                    "y": m["y"],
                    "is_primary": idx == 0,
                }
                for idx, m in enumerate(monitors)
            ]
    except Exception:
        return []