#!/usr/bin/env python3
"""Read Guardian Hook.

Protects files from unauthorized reading by:
1. Blocking zeroAccess paths (secrets, credentials)
2. Blocking symlink escapes (security)
3. Blocking paths outside project (security)
4. Blocking self-guarded paths (guardian system files)

Note: Does NOT block readOnly paths — reading read-only files is allowed.

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
    run_path_guardian_hook("Read")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Fail-close: on unexpected errors, deny for safety
        log_guardian("ERROR", f"Read guardian error: {type(e).__name__}: {e}")
        # Set circuit open to prevent auto-commit of potentially corrupted state
        set_circuit_open(f"read_guardian crashed: {type(e).__name__}")
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
