"""
screen_monitoring/detector.py
=============================
Monitor detection and browser window monitoring.

Features:
  - Multi-monitor detection
  - Browser window identification
  - Screen state analysis
  - Process monitoring for browser instances
"""

import os
import platform
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Platform-specific imports
_PLATFORM = platform.system()

# Browser detection patterns
_BROWSER_PROCESSES = {
    "Windows": ["chrome", "firefox", "msedge", "opera", "brave"],
    "Darwin": ["Google Chrome", "Firefox", "Safari", "Opera", "Brave"],
    "Linux": ["chrome", "firefox", "chromium", "brave-browser"],
}


def detect_monitors(browser_hint: dict = None) -> Dict[str, Any]:
    """
    Detect connected monitors and their state.
    
    Args:
        browser_hint: Optional dict with browser state information
        
    Returns:
        dict with monitor_count, monitors, browser_windows, etc.
    """
    from screen_monitoring.capture import get_monitor_count, get_monitor_info, is_screen_capture_available
    
    result = {
        "monitor_count": get_monitor_count(),
        "screen_capture_available": is_screen_capture_available(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "monitors": get_monitor_info(),
    }
    
    # Browser window detection
    browser_windows = detect_browser_windows()
    result["browser_windows"] = browser_windows
    result["browser_count"] = len(browser_windows)
    
    # Apply browser hint if provided
    if browser_hint:
        result["browser_hint"] = browser_hint
        if browser_hint.get("focused"):
            result["focus_state"] = "focused"
        else:
            result["focus_state"] = "unfocused"
    
    return result


def detect_browser_windows() -> List[Dict[str, Any]]:
    """
    Detect open browser windows using platform-specific methods.
    
    Returns:
        List of dicts with browser window information
    """
    windows = []
    
    try:
        if _PLATFORM == "Windows":
            windows = _detect_browsers_windows()
        elif _PLATFORM == "Darwin":
            windows = _detect_browsers_macos()
        elif _PLATFORM == "Linux":
            windows = _detect_browsers_linux()
    except Exception as e:
        print(f"[detector] Browser detection failed: {e}")
    
    return windows


def _detect_browsers_windows() -> List[Dict[str, Any]]:
    """Detect browser windows on Windows using tasklist."""
    import subprocess
    
    windows = []
    browser_patterns = _BROWSER_PROCESSES.get("Windows", [])
    
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split(",")
                if len(parts) >= 2:
                    windows.append({
                        "process": parts[0].strip('"'),
                        "pid": parts[1].strip('"') if len(parts) > 1 else "unknown",
                        "platform": "Windows",
                        "type": "browser",
                    })
    except Exception:
        pass
    
    return windows


def _detect_browsers_macos() -> List[Dict[str, Any]]:
    """Detect browser windows on macOS using AppleScript."""
    windows = []
    
    try:
        import subprocess
        
        # Use AppleScript to get frontmost app
        script = '''
        tell application "System Events"
            set frontApp to first process whose frontmost is true
            set frontName to name of frontApp
        end tell
        return frontName
        '''
        
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            app_name = result.stdout.strip()
            if any(browser.lower() in app_name.lower() for browser in ["chrome", "firefox", "safari", "opera", "brave"]):
                windows.append({
                    "process": app_name,
                    "platform": "macOS",
                    "type": "browser",
                    "frontmost": True,
                })
    except Exception:
        pass
    
    return windows


def _detect_browsers_linux() -> List[Dict[str, Any]]:
    """Detect browser windows on Linux using xdotool or wmctrl."""
    import subprocess
    
    windows = []
    
    try:
        # Try wmctrl first
        result = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            browser_patterns = _BROWSER_PROCESSES.get("Linux", [])
            
            for line in result.stdout.strip().split("\n"):
                for browser in browser_patterns:
                    if browser.lower() in line.lower():
                        parts = line.split(None, 3)
                        if len(parts) >= 4:
                            windows.append({
                                "window_id": parts[0],
                                "hostname": parts[1] if len(parts) > 1 else "",
                                "title": parts[3] if len(parts) > 3 else "",
                                "platform": "Linux",
                                "type": "browser",
                            })
                        break
    except Exception:
        pass
    
    # Fallback to xdotool
    if not windows:
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", "chrome"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                for window_id in result.stdout.strip().split("\n"):
                    if window_id:
                        windows.append({
                            "window_id": window_id,
                            "platform": "Linux",
                            "type": "browser",
                        })
        except Exception:
            pass
    
    return windows


def is_browser_focused() -> bool:
    """Check if a browser window is currently focused."""
    try:
        if _PLATFORM == "Windows":
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", 
                 "(Get-Process -Name 'chrome' | Where-Object {$_.MainWindowTitle -ne ''}).Count"],
                capture_output=True, text=True, timeout=5
            )
            return int(result.stdout.strip() or "0") > 0
        
        elif _PLATFORM == "Darwin":
            import subprocess
            script = '''
            tell application "System Events"
                set frontApp to first process whose frontmost is true
                set frontName to name of frontApp
            end tell
            return frontName
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                app_name = result.stdout.strip().lower()
                return any(b in app_name for b in ["chrome", "firefox", "safari", "opera", "brave"])
        
        elif _PLATFORM == "Linux":
            import subprocess
            result = subprocess.run(
                ["xdotool", "getwindowfocus", "getwindowname"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                window_name = result.stdout.lower()
                return any(b in window_name for b in ["chrome", "firefox", "chromium"])
    except Exception:
        pass
    
    return True  # Assume focused if detection fails


def get_screen_resolution() -> Dict[str, int]:
    """Get primary screen resolution."""
    try:
        if _PLATFORM == "Windows":
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", 
                 "(Get-WmiObject Win32_VideoController).CurrentHorizontalResolution | Select-Object -First 1"],
                capture_output=True, text=True, timeout=5
            )
            return {"width": int(result.stdout.strip() or "1920"), "height": 1080}
        
        elif _PLATFORM == "Darwin":
            import subprocess
            result = subprocess.run(
                ["osascript", "-e", "get screen size of (info for (path to front most application))"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                size = result.stdout.strip()
                parts = size.split(",")
                if len(parts) == 2:
                    return {"width": int(parts[0]), "height": int(parts[1])}
        
        elif _PLATFORM == "Linux":
            import subprocess
            result = subprocess.run(
                ["xrandr", "--current"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "connected" in line and "primary" in line:
                        # Parse resolution from line
                        parts = line.split()
                        for p in parts:
                            if "x" in p and p[0].isdigit():
                                w, h = p.split("x")
                                return {"width": int(w), "height": int(h)}
    except Exception:
        pass
    
    return {"width": 1920, "height": 1080}  # Default