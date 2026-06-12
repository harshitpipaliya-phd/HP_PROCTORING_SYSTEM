"""
tests/conftest.py
=================
Shared pytest fixtures and configuration.
"""

import sys
import os

# Ensure project root is on path (parent of tests/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
