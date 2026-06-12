"""
api/core/config.py
==================
Re-export of ``core.config`` so ``api.core`` is fully self-contained.
"""

from core.config import Settings, get_settings, reload_settings

__all__ = ["Settings", "get_settings", "reload_settings"]
