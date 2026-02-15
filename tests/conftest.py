"""Pytest configuration -- bootstraps sys.path for guardian imports."""
import sys
from pathlib import Path

# Ensure tests/ directory is on sys.path so _bootstrap can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401, E402
