#!/usr/bin/env python3
# PLUGIN MIGRATION: Migrated from ops/.claude/hooks/ to plugin structure
# Import paths unchanged - scripts are colocated in hooks/scripts/

"""Edit Guardian Hook.

Protects files from unauthorized editing by:
1. Blocking zeroAccess paths (secrets, credentials)
2. Blocking readOnly paths (dependencies, generated files)
3. Blocking symlink escapes (security)
4. Blocking paths outside project (security)
5. Blocking self-guarded paths (guardian system files)

Phase: 3 (Edit/Write Guardian)

Design Principles:
- Fail-Close: If guardian system fails, deny the operation
- Use shared utilities from _guardian_utils.py
- Thin wrapper: All logic in run_path_guardian_hook()
"""

import json
import sys
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from _guardian_utils import (
        log_guardian,
        run_path_guardian_hook,
        set_circuit_open,  # Phase 4 Fix: Circuit Breaker
    )
except ImportError as e:
    # Fail-close: guardian system unavailable = block all
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Guardian system unavailable: {e}",
                }
            }
        )
    )
    sys.exit(0)


def main() -> None:
    """Main hook entry point."""
    run_path_guardian_hook("Edit")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Fail-close: on unexpected errors, deny for safety
        log_guardian("ERROR", f"Edit guardian error: {type(e).__name__}: {e}")
        # Set circuit open to prevent auto-commit of potentially corrupted state
        set_circuit_open(f"edit_guardian crashed: {type(e).__name__}")
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Guardian system error: {e}",
                    }
                }
            )
        )
        sys.exit(0)
