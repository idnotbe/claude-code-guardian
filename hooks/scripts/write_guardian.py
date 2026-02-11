#!/usr/bin/env python3
# PLUGIN MIGRATION: Migrated from ops/.claude/hooks/_protection/
# Import paths unchanged - scripts are colocated in hooks/scripts/

"""Write Tool Protection Hook.

Protects files from unauthorized overwriting by:
1. Blocking zeroAccess paths (secrets, credentials)
2. Blocking readOnly paths (dependencies, generated files)
3. Blocking symlink escapes (security)
4. Blocking paths outside project (security)
5. Blocking self-protection paths (protection system files)

Phase: 3 (Edit/Write Protection)

Design Principles:
- Fail-Close: If protection system fails, deny the operation
- Use shared utilities from _protection_utils.py
- Thin wrapper: All logic in run_path_protection_hook()
"""

import json
import sys
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from _protection_utils import (
        log_protection,
        run_path_protection_hook,
        set_circuit_open,  # Phase 4 Fix: Circuit Breaker
    )
except ImportError as e:
    # Fail-close: protection system unavailable = block all
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Protection system unavailable: {e}",
                }
            }
        )
    )
    sys.exit(0)


def main() -> None:
    """Main hook entry point."""
    run_path_protection_hook("Write")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Fail-close: on unexpected errors, deny for safety
        log_protection("ERROR", f"Write protection error: {type(e).__name__}: {e}")
        # Set circuit open to prevent auto-commit of potentially corrupted state
        set_circuit_open(f"write_protection crashed: {type(e).__name__}")
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Protection system error: {e}",
                    }
                }
            )
        )
        sys.exit(0)
