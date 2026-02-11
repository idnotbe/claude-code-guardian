#!/usr/bin/env python3
# PLUGIN MIGRATION: Migrated from ops/.claude/hooks/_protection/
# Import paths unchanged - scripts are colocated in hooks/scripts/

"""Bash Protection Hook - Full Implementation.

Protects against dangerous bash commands by:
1. Blocking catastrophic patterns (rm -rf /, .git deletion, etc.)
2. Asking confirmation for dangerous patterns (recursive delete, etc.)
3. Protecting paths based on zeroAccess/readOnly/noDelete rules
4. Archiving untracked files before deletion

Phase: 2 (Full Bash Protection)
"""

import glob
import json
import re
import secrets
import shlex
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from _protection_utils import (
        COMMIT_MESSAGE_MAX_LENGTH,  # Import constant for message length
        ask_response,
        deny_response,
        get_project_dir,
        git_add_tracked,
        git_commit,
        git_has_changes,
        git_has_staged_changes,  # FIX: Check staged changes before commit
        git_is_tracked,
        is_dry_run,
        is_rebase_or_merge_in_progress,  # Phase 5: Fragile state check
        is_symlink_escape,
        load_protection_config,
        log_protection,
        match_ask_patterns,
        match_block_patterns,
        match_no_delete,
        match_read_only,
        match_zero_access,
        set_circuit_open,  # Phase 4 Fix: Circuit Breaker
        truncate_command,
        validate_commit_prefix,  # m3 FIX: centralized prefix validation
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


# ============================================================
# Command Analysis
# ============================================================


def is_delete_command(command: str) -> bool:
    """Check if command is a delete operation.

    Args:
        command: The bash command to check.

    Returns:
        True if command appears to be a delete operation.
    """
    delete_patterns = [
        r"(?:^|[;&|]\s*)rm\s+",
        r"(?:^|[;&|]\s*)del\s+",
        r"(?:^|[;&|]\s*)rmdir\s+",
        r"(?:^|[;&|]\s*)Remove-Item\s+",
        r"(?:^|[;&|]\s*)ri\s+",
    ]
    return any(re.search(p, command, re.IGNORECASE) for p in delete_patterns)


def is_write_command(command: str) -> bool:
    """Check if command is a write/modify operation.

    Args:
        command: The bash command to check.

    Returns:
        True if command appears to write or modify files.
    """
    write_patterns = [
        r">\s*['\"]?[^|&;]+",  # Redirection
        r"tee\s+",
        r"mv\s+",
    ]
    return any(re.search(p, command, re.IGNORECASE) for p in write_patterns)


def extract_paths(command: str, project_dir: Path) -> list[Path]:
    """Extract file paths from command.

    Args:
        command: The bash command to parse.
        project_dir: Project directory for resolving relative paths.

    Returns:
        List of Path objects found in the command.
    """
    try:
        # Use posix=False on Windows to treat backslash as path separator, not escape
        parts = shlex.split(command, posix=(sys.platform != "win32"))
    except ValueError as e:
        # FIX: Log shlex parsing failure for debugging
        log_protection("DEBUG", f"shlex.split failed ({e}), falling back to simple split")
        parts = command.split()

    if not parts:
        return []

    paths = []
    for part in parts[1:]:  # Skip command name
        if part.startswith("-"):
            continue

        path = Path(part)
        if not path.is_absolute():
            path = project_dir / path

        # Expand wildcards
        if "*" in str(path) or "?" in str(path):
            expanded = glob.glob(str(path))
            for exp in expanded:
                p = Path(exp)
                if p.exists() and is_within_project(p, project_dir):
                    paths.append(p)
        else:
            if path.exists() and is_within_project(path, project_dir):
                paths.append(path)

    return paths


def is_within_project(path: Path, project_dir: Path) -> bool:
    """Check if path is within project directory.

    Args:
        path: Path to check.
        project_dir: Project directory boundary.

    Returns:
        True if path is within project_dir.
    """
    try:
        path.resolve().relative_to(project_dir.resolve())
        return True
    except ValueError:
        return False


# ============================================================
# Archive Functions
# ============================================================


def generate_archive_title(files: list[Path]) -> str:
    """Generate descriptive title for archive folder.

    Args:
        files: List of files being archived.

    Returns:
        Sanitized title string for the archive folder name.
    """
    if not files:
        return "empty"

    first_name = files[0].name
    # Sanitize filename
    sanitized = re.sub(r'[<>:"/\\|?*\s]', "_", first_name)
    sanitized = re.sub(r"_+", "_", sanitized)
    if len(sanitized) > 50:
        sanitized = sanitized[:47] + "..."
    sanitized = sanitized.strip("_") or "unnamed"

    if len(files) == 1:
        return sanitized
    else:
        return f"{sanitized}_and_{len(files) - 1}_more"


# Archive constraints
ARCHIVE_MAX_FILE_SIZE_MB = 100  # Skip files larger than this
ARCHIVE_MAX_TOTAL_SIZE_MB = 500  # Stop archiving if total exceeds this
ARCHIVE_MAX_FILES = 50  # Maximum number of files to archive


def archive_files(
    files: list[Path], project_dir: Path
) -> tuple[Path | None, list[tuple[Path, Path]]]:
    """Archive files before deletion.

    Applies safety limits:
    - Max file size: 100MB per file
    - Max total size: 500MB total
    - Max files: 50 files

    Files exceeding limits are logged and skipped.
    """
    if not files:
        return None, []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = generate_archive_title(files)
    archive_dir = project_dir / "_archive" / f"{timestamp}_{title}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived = []
    total_size = 0
    skipped_count = 0
    start_time = datetime.now()

    for file_path in files:
        # Check file count limit
        if len(archived) >= ARCHIVE_MAX_FILES:
            log_protection(
                "WARN", f"Archive file limit reached ({ARCHIVE_MAX_FILES}), skipping rest"
            )
            skipped_count += len(files) - len(archived)
            break

        try:
            # Check file size
            file_size = 0
            if file_path.is_file():
                file_size = file_path.stat().st_size
            elif file_path.is_dir():
                file_size = sum(f.stat().st_size for f in file_path.rglob("*") if f.is_file())

            file_size_mb = file_size / (1024 * 1024)

            # Skip large files
            if file_size_mb > ARCHIVE_MAX_FILE_SIZE_MB:
                max_mb = ARCHIVE_MAX_FILE_SIZE_MB
                log_protection(
                    "WARN",
                    f"Skipping large file {file_path.name} ({file_size_mb:.1f}MB > {max_mb}MB)",
                )
                skipped_count += 1
                continue

            # Check total size limit
            if (total_size + file_size) / (1024 * 1024) > ARCHIVE_MAX_TOTAL_SIZE_MB:
                limit_mb = ARCHIVE_MAX_TOTAL_SIZE_MB
                log_protection(
                    "WARN",
                    f"Archive total size limit reached ({limit_mb}MB), skipping rest",
                )
                skipped_count += len(files) - len(archived)
                break

            rel_path = file_path.relative_to(project_dir)
            target_dir = archive_dir / rel_path.parent
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / file_path.name
            if target_path.exists():
                suffix = secrets.token_hex(3)
                stem = file_path.stem
                ext = file_path.suffix
                target_path = target_dir / f"{stem}_{suffix}{ext}"

            if file_path.is_file():
                shutil.copy2(file_path, target_path)
            elif file_path.is_dir():
                shutil.copytree(file_path, target_path, dirs_exist_ok=True)

            archived.append((file_path, target_path))
            total_size += file_size

        except PermissionError as e:
            # M3 FIX: Categorize archive failures
            log_protection(
                "WARN",
                f"Archive PERMISSION DENIED for {file_path.name}: {e}\n"
                "  Check file permissions or run with elevated privileges.",
            )
            skipped_count += 1
        except OSError as e:
            # M3 FIX: Filesystem errors (disk full, path too long, etc.)
            error_type = "DISK FULL" if e.errno == 28 else "FILESYSTEM ERROR"
            log_protection(
                "WARN",
                f"Archive {error_type} for {file_path.name}: {e}\n  errno={e.errno}",
            )
            skipped_count += 1
        except Exception as e:
            # M3 FIX: Unexpected errors with type info
            log_protection(
                "WARN",
                f"Archive UNEXPECTED ERROR for {file_path.name}: {type(e).__name__}: {e}",
            )
            skipped_count += 1

    elapsed = (datetime.now() - start_time).total_seconds()
    if elapsed > 5:
        log_protection("INFO", f"Archive completed in {elapsed:.1f}s ({len(archived)} files)")

    if skipped_count > 0:
        log_protection("WARN", f"Skipped {skipped_count} file(s) during archive")

    return archive_dir, archived


def create_deletion_log(archive_dir: Path, archived: list[tuple[Path, Path]], command: str):
    """Create metadata JSON in archive directory."""
    # L2 FIX: Truncate command for security (prevent sensitive data in logs)
    truncated_command = command[:200] + "..." if len(command) > 200 else command
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": truncated_command,  # L2 FIX: Use truncated command
        "files": [{"original": str(orig), "archived": str(arch)} for orig, arch in archived],
    }
    log_file = archive_dir / "_deletion_log.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# ============================================================
# Pre-commit Message Helper (NEW)
# ============================================================


def create_precommit_message(prefix: str, command: str, timestamp: str) -> str:
    """Create a pre-commit message with length limit.

    Args:
        prefix: Message prefix (e.g., "pre-danger-checkpoint")
        command: The command being executed (will be truncated)
        timestamp: Timestamp string

    Returns:
        Commit message limited to COMMIT_MESSAGE_MAX_LENGTH (72 chars)
    """
    # Start with minimum info
    cmd_short = command[:20].replace("\n", " ").strip()

    # Try to fit as much as possible within 72 chars
    # Format: "{prefix}: {cmd}... @ {timestamp}"
    # Reserve space for fixed parts
    fixed_len = len(prefix) + len(": ") + len("... @ ") + len(timestamp)
    available = COMMIT_MESSAGE_MAX_LENGTH - fixed_len

    if available > 10:
        cmd_short = command[:available].replace("\n", " ").strip()
    else:
        cmd_short = command[:10].replace("\n", " ").strip()

    message = f"{prefix}: {cmd_short}... @ {timestamp}"

    # Final safety check
    if len(message) > COMMIT_MESSAGE_MAX_LENGTH:
        message = message[: COMMIT_MESSAGE_MAX_LENGTH - 3] + "..."

    return message


# ============================================================
# Main Hook Logic
# ============================================================


def main() -> None:
    """Main hook entry point."""
    # Get project directory
    project_dir_str = get_project_dir()
    if not project_dir_str:
        sys.exit(0)
    project_dir = Path(project_dir_str)

    # Parse input - FAIL-CLOSE on invalid JSON for security
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log_protection("ERROR", f"Malformed JSON input: {e}")
        print(json.dumps(deny_response("Invalid hook input (malformed JSON)")))
        sys.exit(0)

    # Only process Bash commands
    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Truncate for logging
    cmd_preview = truncate_command(command)

    # ========== Step 1: Block Patterns ==========
    blocked, reason = match_block_patterns(command)
    if blocked:
        log_protection("BLOCK", f"{reason}: {cmd_preview}")
        if is_dry_run():
            log_protection("DRY-RUN", "Would DENY")
            sys.exit(0)
        print(json.dumps(deny_response(reason)))
        sys.exit(0)

    # ========== Step 2: Ask Patterns ==========
    needs_ask, ask_reason = match_ask_patterns(command)

    # ========== Step 3: Extract and Check Paths ==========
    paths = extract_paths(command, project_dir)

    for path in paths:
        path_str = str(path)

        # Symlink escape check (prevent symlinks pointing outside project)
        if is_symlink_escape(path_str):
            log_protection("BLOCK", f"Symlink escape detected: {path.name}")
            if is_dry_run():
                log_protection("DRY-RUN", "Would DENY")
                sys.exit(0)
            print(json.dumps(deny_response(f"Symlink points outside project: {path.name}")))
            sys.exit(0)

        # Zero access check
        if match_zero_access(path_str):
            log_protection("BLOCK", f"Zero access path: {path.name}")
            if is_dry_run():
                log_protection("DRY-RUN", "Would DENY")
                sys.exit(0)
            print(json.dumps(deny_response(f"Protected path: {path.name}")))
            sys.exit(0)

        # Read-only check (for write commands)
        if is_write_command(command) and match_read_only(path_str):
            log_protection("BLOCK", f"Read-only path: {path.name}")
            if is_dry_run():
                log_protection("DRY-RUN", "Would DENY")
                sys.exit(0)
            print(json.dumps(deny_response(f"Read-only path: {path.name}")))
            sys.exit(0)

        # No-delete check (for delete commands)
        if is_delete_command(command) and match_no_delete(path_str):
            log_protection("BLOCK", f"No-delete path: {path.name}")
            if is_dry_run():
                log_protection("DRY-RUN", "Would DENY")
                sys.exit(0)
            print(json.dumps(deny_response(f"Protected from deletion: {path.name}")))
            sys.exit(0)

    # ========== Step 4: Handle Deletions with Archive ==========
    if is_delete_command(command):
        if not paths:
            # FIX: Log when deletion detected but no paths extracted
            # This helps diagnose path extraction issues
            cmd_short = truncate_command(command, 80)
            log_protection("DEBUG", f"Delete cmd, no paths extracted: {cmd_short}")
        else:
            # Archive untracked files
            untracked = [p for p in paths if not git_is_tracked(str(p))]

            # FIX: Log when all files are git-tracked (no archive needed)
            if not untracked and paths:
                log_protection(
                    "DEBUG",
                    f"All {len(paths)} path(s) are git-tracked, no archive needed",
                )

            if untracked:
                if is_dry_run():
                    log_protection("DRY-RUN", f"Would archive: {[p.name for p in untracked]}")
                else:
                    archive_dir, archived = archive_files(untracked, project_dir)
                    if archived:
                        create_deletion_log(archive_dir, archived, command)
                        log_protection(
                            "ARCHIVE", f"Archived {len(archived)} file(s) to {archive_dir.name}"
                        )

                        # Ask for confirmation
                        file_list = ", ".join(p.name for p in paths[:3])
                        if len(paths) > 3:
                            file_list += f", ... (+{len(paths) - 3} more)"

                        print(
                            json.dumps(
                                ask_response(
                                    f"Archived {len(archived)} file(s) to {archive_dir.name}/\n"
                                    f"Files: {file_list}\n"
                                    "Proceed with deletion?"
                                )
                            )
                        )
                        sys.exit(0)
                    else:
                        # Archive failed - warn user explicitly
                        log_protection(
                            "WARN", f"Archive FAILED for {len(untracked)} untracked file(s)"
                        )
                        file_list = ", ".join(p.name for p in untracked[:3])
                        if len(untracked) > 3:
                            file_list += f", ... (+{len(untracked) - 3} more)"

                        print(
                            json.dumps(
                                ask_response(
                                    f"ARCHIVE FAILED for {len(untracked)} file(s)!\n"
                                    f"Files: {file_list}\n"
                                    f"Data will be PERMANENTLY LOST if deleted.\n"
                                    "Proceed with deletion anyway?"
                                )
                            )
                        )
                        sys.exit(0)

            # Tracked files only - just ask
            if paths:
                log_protection("ASK", f"Delete files: {[p.name for p in paths[:3]]}")
                if is_dry_run():
                    log_protection("DRY-RUN", "Would ASK")
                    sys.exit(0)
                file_list = ", ".join(p.name for p in paths[:3])
                if len(paths) > 3:
                    file_list += f", ... (+{len(paths) - 3} more)"
                print(json.dumps(ask_response(f"Delete {len(paths)} file(s): {file_list}?")))
                sys.exit(0)

    # ========== Step 5: Pre-commit for Dangerous Operations ==========
    if needs_ask:
        # Try pre-commit before dangerous operation
        try:
            git_config = load_protection_config().get("gitIntegration", {})
            pre_commit_config = git_config.get("preCommitOnDangerous", {})

            if pre_commit_config.get("enabled", False):
                # Phase 5: Check for fragile git state (merge/rebase in progress)
                if is_rebase_or_merge_in_progress():
                    log_protection(
                        "WARN",
                        "Rebase/merge in progress - skipping pre-commit (would corrupt git state)",
                    )
                elif git_has_changes():
                    # m3 FIX: Use centralized prefix validation
                    prefix = validate_commit_prefix(
                        pre_commit_config.get("messagePrefix", "pre-danger-checkpoint"),
                        default="pre-danger-checkpoint",
                    )
                    timestamp = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )  # P1-3 FIX: Add seconds

                    # FIX: Use helper function for length-limited message
                    commit_msg = create_precommit_message(prefix, command, timestamp)

                    # MINOR-2 FIX: Log in dry-run mode instead of skipping silently
                    if is_dry_run():
                        log_protection("DRY-RUN", f"Would pre-commit: {commit_msg[:60]}...")
                    else:
                        # MINOR-3 DOCUMENTATION: Stage Failure Handling Strategy
                        # bash_protection.py: Skips commit if staging fails
                        #   Reason: pre-commit should only include what we just staged
                        # auto_commit.py: Continues to commit even if staging fails
                        #   Reason: There may be already staged changes that should be preserved
                        if git_add_tracked():
                            # FIX: Check for actual staged changes before attempting commit
                            # This prevents circuit breaker from opening when git_add_tracked()
                            # succeeds but stages 0 files (e.g., only untracked changes exist)
                            if git_has_staged_changes():
                                # FIX: Use no_verify=True to skip pre-commit hooks
                                # Pre-danger-checkpoint is for backup, not code verification
                                # This prevents circuit breaker from triggering on linter failures
                                if git_commit(commit_msg, no_verify=True):
                                    log_protection(
                                        "INFO", f"Pre-commit created before: {cmd_preview}"
                                    )
                                else:
                                    log_protection("WARN", "Pre-commit failed: commit unsuccessful")
                                    # P2-2 FIX: Open circuit on pre-commit failure for consistency
                                    set_circuit_open("pre-commit failed during dangerous operation")
                            else:
                                # No staged changes after git add - this is normal when
                                # only untracked files exist. Skip commit silently.
                                log_protection(
                                    "INFO",
                                    "No staged changes - skipping pre-commit (untracked only)",
                                )
                        else:
                            log_protection("WARN", "Pre-commit failed: unable to stage changes")
                            # P2-2 FIX: Open circuit on staging failure
                            set_circuit_open("pre-commit staging failed during dangerous operation")
        except Exception as e:
            log_protection("WARN", f"Pre-commit failed: {e}")

        log_protection("ASK", f"{ask_reason}: {cmd_preview}")
        if is_dry_run():
            log_protection("DRY-RUN", "Would ASK")
            sys.exit(0)
        print(json.dumps(ask_response(ask_reason)))
        sys.exit(0)

    # ========== Step 6: Allow ==========
    # Only log non-trivial commands (reduce verbosity per Phase 1B feedback)
    if len(command) > 10 and not command.startswith(("ls", "cd", "pwd", "echo", "cat", "type")):
        log_protection("ALLOW", cmd_preview)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_protection("ERROR", f"Unhandled exception: {e}")
        # Set circuit open to prevent auto-commit of potentially corrupted state
        set_circuit_open(f"bash_protection crashed: {type(e).__name__}")
        # F-01 FIX: Fail-CLOSE on unhandled exception (security hook must deny on crash)
        try:
            print(json.dumps(deny_response(f"Protection system error: {type(e).__name__}")))
        except Exception:
            pass  # If even deny_response fails, exit silently (Claude Code treats no output as allow)
        sys.exit(0)
