#!/usr/bin/env python3
# PLUGIN MIGRATION: Migrated from ops/.claude/hooks/ to plugin structure
# Import paths unchanged - scripts are colocated in hooks/scripts/

"""Auto-Commit Hook for Session Stop.

Automatically creates a checkpoint commit when a Claude Code
session ends, ensuring all work is preserved.

Phase: 4 (Git Automation)
"""

import sys
from datetime import datetime
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from _guardian_utils import (
        COMMIT_MESSAGE_MAX_LENGTH,  # P1-1 FIX: Import for message length limit
        clear_circuit,
        git_add_all,
        git_add_tracked,
        git_commit,
        git_get_last_commit_hash,
        git_has_changes,
        git_has_staged_changes,  # BUG-2 FIX: Check staged changes before commit
        is_circuit_open,
        is_detached_head,
        is_dry_run,
        is_rebase_or_merge_in_progress,  # M3 FIX: rebase/merge detection
        load_guardian_config,
        log_guardian,
        set_circuit_open,  # E1 FIX: circuit breaker on git failure
        validate_commit_prefix,  # m3 FIX: centralized prefix validation
    )
except ImportError as e:
    # Stop Hook is fail-open (must not block session termination)
    print(f"Warning: Could not import guardian utils: {e}", file=sys.stderr)
    sys.exit(0)  # Continue session termination


def main():
    """Execute auto-commit on session stop."""
    log_guardian("INFO", "auto-commit hook triggered (Stop event)")

    # Check circuit breaker - skip commit if circuit is open
    circuit_open, reason = is_circuit_open()
    if circuit_open:
        log_guardian("WARN", f"Circuit breaker is OPEN - skipping auto-commit: {reason}")
        # PLUGIN MIGRATION: Updated path reference
        log_guardian("INFO", "To resume auto-commits, delete .claude/guardian/.circuit_open")
        return

    # Load configuration
    config = load_guardian_config()
    git_integration = config.get("gitIntegration")

    # MINOR-3 FIX: Distinguish between missing config and disabled config
    if not git_integration:
        log_guardian("WARN", "gitIntegration section missing from config.json")
        return

    git_config = git_integration.get("autoCommit", {})

    # Check if auto-commit is enabled
    if not git_config.get("enabled", False):
        log_guardian("INFO", "Auto-commit disabled (gitIntegration.autoCommit.enabled=false)")
        return

    if not git_config.get("onStop", False):
        log_guardian("INFO", "Auto-commit on stop disabled")
        return

    # Check for detached HEAD state (MAJOR-1 FIX)
    if is_detached_head():
        log_guardian(
            "WARN", "Detached HEAD state - skipping auto-commit (commits would be orphaned)"
        )
        return

    # M3 FIX: Check for rebase/merge in progress
    if is_rebase_or_merge_in_progress():
        log_guardian("WARN", "Rebase/merge in progress - skipping auto-commit")
        return

    # Check for changes
    if not git_has_changes():
        # MAJOR-2 FIX: Clarify this could also indicate git error
        log_guardian(
            "INFO", "No changes to commit (if unexpected, check earlier warnings for git errors)"
        )
        return

    # Dry-run mode
    if is_dry_run():
        log_guardian("DRY-RUN", "Would auto-commit changes")
        return

    # Stage changes
    include_untracked = git_config.get("includeUntracked", False)
    if include_untracked:
        success = git_add_all()
    else:
        success = git_add_tracked()

    # MINOR-3 DOCUMENTATION: Stage Failure Handling Strategy
    # auto_commit.py: Continues to commit even if staging fails (best-effort)
    #   Reason: There may be already staged changes that should be preserved
    # bash_guardian.py: Skips commit if staging fails
    #   Reason: pre-commit should only include what we just staged
    if not success:
        log_guardian("WARN", "Failed to stage changes, attempting commit anyway")
        # Don't return - there may be already staged changes to commit
    else:
        # MAJOR-2 FIX: Log success only after confirming stage succeeded
        mode = (
            "all changes (including untracked)"
            if include_untracked
            else "tracked file changes only"
        )
        log_guardian("INFO", f"Staged {mode}")

    # Create commit message
    # m3 FIX: Use centralized prefix validation
    prefix = validate_commit_prefix(
        git_config.get("messagePrefix", "auto-checkpoint"),
        default="auto-checkpoint",
    )
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{prefix}: {timestamp}"

    # P1-2 FIX: Enforce message length limit for consistency with bash_guardian.py
    if len(message) > COMMIT_MESSAGE_MAX_LENGTH:
        message = message[: COMMIT_MESSAGE_MAX_LENGTH - 3] + "..."

    # BUG-2 FIX: Check for staged changes before attempting commit
    # This prevents false failures when git add -u staged nothing (only untracked files)
    if not git_has_staged_changes():
        log_guardian("INFO", "No staged changes to commit - skipping (this is normal)")
        return  # Normal exit, not a failure

    # Commit with --no-verify to bypass pre-commit hooks (auto-commit is backup-only)
    if git_commit(message, no_verify=True):
        commit_hash = git_get_last_commit_hash()
        # m2 FIX: Handle empty hash (rare, but possible for first commit timing issues)
        if commit_hash:
            log_guardian("INFO", f"auto-commit success: {commit_hash} - {message}")
        else:
            log_guardian("INFO", f"auto-commit success: (hash unavailable) - {message}")
        # Clear circuit breaker on successful commit (system is healthy)
        clear_circuit()
    else:
        # MAJOR-3 FIX: Don't speculate about failure reason - check earlier warnings
        log_guardian("WARN", "Auto-commit failed - check earlier warnings for details")
        # E1 FIX: Open circuit breaker to prevent repeated failures
        set_circuit_open("auto-commit failed - manual review required")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_guardian("ERROR", f"Auto-commit hook error: {e}")
        # E1 FIX: Open circuit breaker on unhandled exception
        try:
            set_circuit_open(f"auto-commit exception: {type(e).__name__}")
        except Exception:
            pass  # Don't fail if circuit breaker itself fails
        # Don't fail the session stop on error
        sys.exit(0)
