"""Bootstrap module for guardian tests.

Discovers the repo root and adds hooks/scripts/ to sys.path.
Also sets default environment variables needed by the guardian.

Usage at top of any test file:
    import _bootstrap  # noqa: F401 (side-effect import)
    from bash_guardian import split_commands, ...
"""
import os
import sys
from pathlib import Path

def _find_repo_root():
    """Walk up from this file to find the repo root (contains hooks/scripts/)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "hooks" / "scripts" / "bash_guardian.py").exists():
            return current
        current = current.parent
    raise RuntimeError("Cannot find claude-code-guardian repo root from tests/_bootstrap.py")

_REPO_ROOT = _find_repo_root()
_SCRIPTS_DIR = str(_REPO_ROOT / "hooks" / "scripts")

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Set default env vars that guardian expects
os.environ.setdefault("CLAUDE_PROJECT_DIR", "/tmp/test-project")
