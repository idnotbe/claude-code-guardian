#!/usr/bin/env python3
# PLUGIN MIGRATION: Migrated from ops/.claude/hooks/ to plugin structure
# Import paths unchanged - scripts are colocated in hooks/scripts/

"""Bash Guardian Hook - Full Implementation.

Protects against dangerous bash commands by:
1. Blocking catastrophic patterns (force push, etc.)
2. Scanning raw command for protected path references (Layer 1)
3. Decomposing compound commands for per-sub-command analysis (Layer 2)
4. Enhanced path extraction with redirection and non-existent file support (Layer 3)
5. Expanded write/delete type detection (Layer 4)
6. Archiving untracked files before deletion
7. Verdict aggregation: deny > ask > allow across all layers

Phase: 3 (Bash Bypass Protection)
"""

import glob
import json
import os
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
    from _guardian_utils import (
        COMMIT_MESSAGE_MAX_LENGTH,  # Import constant for message length
        ask_response,
        deny_response,
        get_hook_behavior,  # hookBehavior config support
        get_project_dir,
        git_add_tracked,
        git_commit,
        git_has_changes,
        git_has_staged_changes,  # FIX: Check staged changes before commit
        git_is_tracked,
        is_dry_run,
        is_rebase_or_merge_in_progress,  # Phase 5: Fragile state check
        is_symlink_escape,
        load_guardian_config,
        log_guardian,
        make_hook_behavior_response,  # hookBehavior response helper
        match_allowed_external_path,
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


# ============================================================
# Layer 2: Command Decomposition
# ============================================================


def split_commands(command: str) -> list[str]:
    """Split compound command into sub-commands.

    Handles delimiters: ;  &&  ||  |  &  newline

    Does NOT split inside:
    - Single-quoted strings ('...')
    - Double-quoted strings ("...")
    - Command substitution ($(...))
    - Process substitution (<(...) or >(...))
    - Backtick substitution (backtick...backtick)
    - Backslash-escaped characters

    Critical fixes incorporated:
    - C-2: Backslash escapes and backtick substitution handling
    - M-4: Single & as command separator

    Known limitation: ANSI-C quoting ($'...') is not specially handled.

    Args:
        command: The compound bash command to split.

    Returns:
        List of individual sub-commands (stripped of whitespace).
    """
    sub_commands: list[str] = []
    current: list[str] = []
    depth = 0  # Track nesting: $(), <(), >()
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    i = 0

    while i < len(command):
        c = command[i]

        # Backslash escape handling (outside single quotes)
        # C-2 fix: \; should NOT be treated as a delimiter
        if c == "\\" and not in_single_quote:
            # Consume backslash + next character as literal
            current.append(c)
            if i + 1 < len(command):
                i += 1
                current.append(command[i])
            i += 1
            continue

        # Single quote tracking (not inside double quotes or backticks)
        if c == "'" and not in_double_quote and not in_backtick and depth == 0:
            in_single_quote = not in_single_quote
            current.append(c)
            i += 1
            continue

        # Double quote tracking (not inside single quotes or backticks)
        if c == '"' and not in_single_quote and not in_backtick and depth == 0:
            in_double_quote = not in_double_quote
            current.append(c)
            i += 1
            continue

        # Skip everything inside quotes
        if in_single_quote or in_double_quote:
            current.append(c)
            i += 1
            continue

        # C-2 fix: Backtick substitution tracking
        if c == "`" and depth == 0:
            in_backtick = not in_backtick
            current.append(c)
            i += 1
            continue

        # Skip everything inside backticks
        if in_backtick:
            current.append(c)
            i += 1
            continue

        # Track nesting depth for $(), <(), >()
        if c == "(" and i > 0 and command[i - 1] in ("$", "<", ">"):
            depth += 1
            current.append(c)
            i += 1
            continue
        if c == "(" and depth > 0:
            depth += 1
            current.append(c)
            i += 1
            continue
        if c == ")" and depth > 0:
            depth -= 1
            current.append(c)
            i += 1
            continue

        # Only split at top level (depth == 0)
        if depth == 0:
            # Semicolon
            if c == ";":
                sub_commands.append("".join(current).strip())
                current = []
                i += 1
                continue
            # && (two ampersands)
            if c == "&" and i + 1 < len(command) and command[i + 1] == "&":
                sub_commands.append("".join(current).strip())
                current = []
                i += 2
                continue
            # || (two pipes)
            if c == "|" and i + 1 < len(command) and command[i + 1] == "|":
                sub_commands.append("".join(current).strip())
                current = []
                i += 2
                continue
            # | (single pipe, not ||)
            if c == "|":
                sub_commands.append("".join(current).strip())
                current = []
                i += 1
                continue
            # M-4 fix: & (single ampersand = background, also a separator)
            # Codex review fix: skip & when part of redirection (&>, >&, <&, |&)
            if c == "&":
                next_c = command[i + 1] if i + 1 < len(command) else ""
                prev_c = command[i - 1] if i > 0 else ""
                # &> is "redirect both stdout+stderr" -- not a separator
                if next_c == ">":
                    current.append(c)
                    i += 1
                    continue
                # >& and <& are fd duplication -- not a separator
                if prev_c in (">", "<"):
                    current.append(c)
                    i += 1
                    continue
                # n>& where n is a digit (e.g., 2>&1)
                if prev_c.isdigit() and len(current) >= 2 and current[-1] == ">":
                    current.append(c)
                    i += 1
                    continue
                sub_commands.append("".join(current).strip())
                current = []
                i += 1
                continue
            # Newline
            if c == "\n":
                sub_commands.append("".join(current).strip())
                current = []
                i += 1
                continue

        current.append(c)
        i += 1

    # Don't forget the last segment
    remaining = "".join(current).strip()
    if remaining:
        sub_commands.append(remaining)

    # Filter empty strings
    return [cmd for cmd in sub_commands if cmd]


# ============================================================
# Layer 1: Protected Path Scan
# ============================================================


def glob_to_literals(pattern: str) -> list[str]:
    """Convert a glob pattern to literal search strings for raw command scanning.

    Only converts patterns where the literal is distinctive enough to be
    meaningful as a substring search. Returns empty list for patterns that
    are too generic.

    Critical fix C-3: Returns [] for generic patterns like *.env to avoid
    false positives. Only exact matches, prefix patterns, and specific
    suffix patterns are converted.

    Examples:
        ".env"       -> [".env"]       (exact match)
        ".env.*"     -> [".env."]      (prefix match)
        "id_rsa"     -> ["id_rsa"]     (exact match)
        "id_rsa.*"   -> ["id_rsa."]    (prefix match)
        "*.pem"      -> [".pem"]       (suffix match)
        "*.tfstate"  -> [".tfstate"]   (suffix match)
        "*.env"      -> []             (too generic)
        "*credentials*.json" -> []     (too generic)

    Args:
        pattern: A glob pattern from zeroAccessPaths config.

    Returns:
        List of literal strings to search for, or [] if too generic.
    """
    # Exact match (no wildcards)
    if "*" not in pattern and "?" not in pattern:
        return [pattern]

    # Prefix match: "name.*" -> search for "name."
    if pattern.endswith(".*"):
        prefix = pattern[:-1]  # "name."
        # Only if the prefix itself has no wildcards
        if "*" not in prefix and "?" not in prefix:
            return [prefix]

    # Suffix match: "*.ext" -> search for ".ext"
    # C-3 fix: Only if the extension is distinctive enough
    if pattern.startswith("*.") and "*" not in pattern[1:] and "?" not in pattern[1:]:
        suffix = pattern[1:]  # ".ext"
        # Skip short/generic suffixes that cause excessive false positives
        if len(suffix) >= 4:
            bare = suffix[1:]  # strip leading dot
            generic_words = {"env", "key", "log"}
            if bare.lower() not in generic_words:
                return [suffix]

    # Wildcard patterns like "*credentials*" -- too generic, skip
    return []


def scan_protected_paths(command: str, config: dict) -> tuple[str, str]:
    """Scan raw command string for protected path references (Layer 1).

    Defense-in-depth layer that catches bypasses which defeat structured
    parsing by scanning for literal occurrences of protected filenames.

    Scans path tiers configured in bashPathScan.scanTiers (default: ["zeroAccess"]).
    Supported tiers: "zeroAccess" -> zeroAccessPaths,
                     "readOnly" -> readOnlyPaths,
                     "noDelete" -> noDeletePaths.
    Uses word-boundary regex to reduce false matches.

    I-4 fix: Includes / in word-boundary regex so ./.env is caught.

    Args:
        command: The raw bash command string.
        config: Guardian configuration dict.

    Returns:
        Tuple of (verdict, reason) where verdict is "deny", "ask", or "allow".
    """
    scan_config = config.get("bashPathScan", {})
    if not scan_config.get("enabled", True):
        return "allow", ""

    exact_action = scan_config.get("exactMatchAction", "ask")
    pattern_action = scan_config.get("patternMatchAction", "ask")

    # Read scanTiers from config; default to ["zeroAccess"] (preserves current behavior)
    scan_tiers = scan_config.get("scanTiers", ["zeroAccess"])

    # Map tier names to config keys
    tier_to_config_key = {
        "zeroAccess": "zeroAccessPaths",
        "readOnly": "readOnlyPaths",
        "noDelete": "noDeletePaths",
    }

    # Collect all path patterns from configured tiers
    all_scan_paths: list[str] = []
    for tier in scan_tiers:
        config_key = tier_to_config_key.get(tier)
        if config_key:
            all_scan_paths.extend(config.get(config_key, []))

    strongest_verdict = "allow"
    strongest_reason = ""

    for pattern in all_scan_paths:
        # Skip directory patterns -- too noisy for raw string scan
        if "**" in pattern or pattern.endswith("/"):
            continue

        is_exact = "*" not in pattern and "?" not in pattern
        literals = glob_to_literals(pattern)

        for literal in literals:
            # I-4 fix: Include / in word-boundary character set
            # Gemini review fix: Include {, }, , for brace expansion
            # For exact matches: strict word boundaries on both sides
            # For prefix patterns (e.g. ".env." from ".env.*"): strict before, relaxed after
            # For suffix patterns (e.g. ".pem" from "*.pem"): relaxed before, strict after
            boundary_before = r"(?:^|[\s;|&<>(\"`'=/,{\[:\]])"
            boundary_after = r"(?:$|[\s;|&<>)\"`'/,}\[:\]])"

            is_prefix_pattern = pattern.endswith(".*")
            is_suffix_pattern = pattern.startswith("*.")

            if is_suffix_pattern:
                # ".pem" can be preceded by any word char (server.pem)
                regex = re.escape(literal) + boundary_after
            elif is_prefix_pattern:
                # ".env." can be followed by any word char (.env.local)
                regex = boundary_before + re.escape(literal)
            else:
                # Exact match: strict boundaries both sides
                regex = boundary_before + re.escape(literal) + boundary_after

            if re.search(regex, command):
                action = exact_action if is_exact else pattern_action
                reason = f"Protected path reference detected: {literal}"

                if action == "deny":
                    strongest_verdict = "deny"
                    strongest_reason = reason
                elif action == "ask" and strongest_verdict != "deny":
                    strongest_verdict = "ask"
                    strongest_reason = reason

    return strongest_verdict, strongest_reason


# ============================================================
# Layer 3: Enhanced Path Extraction
# ============================================================


def _is_inside_quotes(command: str, pos: int) -> bool:
    """Check if a position in a command string is inside a quoted region.

    I-5 fix: Used to make redirection extraction quote-aware.

    Args:
        command: The command string.
        pos: The character position to check.

    Returns:
        True if the position is inside single or double quotes.
    """
    in_single = False
    in_double = False
    i = 0
    while i < pos:
        c = command[i]
        if c == "\\" and not in_single:
            i += 2  # Skip escaped character
            continue
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        i += 1
    return in_single or in_double


def extract_redirection_targets(command: str, project_dir: Path) -> list[Path]:
    """Extract file paths from shell redirections (>, >>, <).

    Handles: echo x > file.txt, echo x >> file.txt, cat < input.txt,
    cmd 2> errors.log, cmd &> all.log

    I-5 fix: Quote-aware -- skips > inside quoted regions.

    Args:
        command: The bash sub-command to parse.
        project_dir: Project directory for resolving relative paths.

    Returns:
        List of Path objects found as redirection targets.
    """
    targets: list[Path] = []
    redir_pattern = r'(?:(?:\d|&)?(?:>\|?|>{2})|<(?!<))\s*([^\s;|&<>]+)'

    for match in re.finditer(redir_pattern, command):
        # I-5 fix: Skip redirections inside quoted regions
        if _is_inside_quotes(command, match.start()):
            continue

        target = match.group(1).strip("'\"")

        # F6: Skip process substitutions — >(cmd) and <(cmd) are not file paths
        if target.startswith("("):
            continue

        # Skip variable targets like $FILE
        if target.startswith("$"):
            continue

        if not _is_path_candidate(target):
            continue

        try:
            path = Path(target)
            if not path.is_absolute():
                path = project_dir / path
            targets.append(path)
        except OSError:
            continue

    return targets


def extract_paths(
    command: str, project_dir: Path, allow_nonexistent: bool = False
) -> list[Path]:
    """Extract file paths from command arguments.

    Args:
        command: The bash command to parse.
        project_dir: Project directory for resolving relative paths.
        allow_nonexistent: If True, include paths that don't exist on disk
            (for write/delete context where the target may not exist yet).

    Returns:
        List of Path objects found in the command.
    """
    try:
        parts = shlex.split(command, posix=(sys.platform != "win32"))
    except ValueError as e:
        log_guardian("DEBUG", f"shlex.split failed ({e}), falling back to simple split")
        parts = command.split()

    # COMPAT-03 FIX: shlex.split(posix=False) keeps surrounding quotes on Windows.
    if sys.platform == "win32":
        parts = [p.strip("'\"") for p in parts]
        parts = [p for p in parts if p]

    if not parts:
        return []

    paths: list[Path] = []
    for part in parts[1:]:  # Skip command name
        if part.startswith("-"):
            # P1-6: Flag-concatenated paths like -f.env
            # Short flags (-x) are skipped, but -f.env has a path suffix
            if len(part) > 2 and not part.startswith("--"):
                flag_suffix = part[2:]  # After -X, the rest is the argument
                if _is_path_candidate(flag_suffix):
                    try:
                        suffix_path = Path(flag_suffix)
                        if not suffix_path.is_absolute():
                            suffix_path = project_dir / suffix_path
                        if suffix_path.exists() and is_within_project(suffix_path, project_dir):
                            paths.append(suffix_path)
                        elif allow_nonexistent and _is_within_project_or_would_be(suffix_path, project_dir):
                            paths.append(suffix_path)
                        elif match_allowed_external_path(str(suffix_path)):
                            paths.append(suffix_path)
                    except OSError:
                        pass
            continue

        # M-3: Handle dd of= syntax
        if part.startswith("of="):
            part = part[3:]
            if not part:
                continue

        if not _is_path_candidate(part):
            continue

        try:
            # P1-5: Expand environment variables and tilde before path creation
            expanded_part = os.path.expandvars(part)
            path = Path(expanded_part)
            if str(path).startswith("~"):
                try:
                    path = path.expanduser()
                except (RuntimeError, KeyError):
                    pass  # Unknown user -- leave as-is, will be rebased
            if not path.is_absolute():
                path = project_dir / path

            # Expand wildcards (including character classes like [v])
            if "*" in str(path) or "?" in str(path) or "[" in str(path):
                expanded = glob.glob(str(path))
                for exp in expanded:
                    p = Path(exp)
                    if p.exists() and is_within_project(p, project_dir):
                        paths.append(p)
                    elif match_allowed_external_path(str(p)):
                        paths.append(p)
            else:
                if path.exists() and is_within_project(path, project_dir):
                    paths.append(path)
                elif allow_nonexistent and _is_within_project_or_would_be(path, project_dir):
                    paths.append(path)
                elif match_allowed_external_path(str(path)):
                    paths.append(path)
        except OSError:
            continue

    return paths


def _is_within_project_or_would_be(path: Path, project_dir: Path) -> bool:
    """Check if a path is or would be within the project directory.

    F7: Uses Path.resolve(strict=False) to canonicalize paths before checking,
    preventing traversal attacks like /project/../etc/passwd.

    Args:
        path: Path to check (may not exist).
        project_dir: Project directory boundary.

    Returns:
        True if path is or would be within project_dir.
    """
    try:
        # F7: Use resolve() to canonicalize, preventing ../traversal attacks
        resolved = path.resolve(strict=False)
        resolved_project = project_dir.resolve(strict=False)
        resolved.relative_to(resolved_project)
        return True
    except (OSError, ValueError):
        return False


# ============================================================
# Layer 4: Command Type Detection (Enhanced)
# ============================================================


def is_delete_command(command: str) -> bool:
    """Check if command is a delete operation.

    Detects shell delete commands and interpreter-mediated deletions.

    Args:
        command: The bash command (or sub-command) to check.

    Returns:
        True if command appears to be a delete operation.
    """
    delete_patterns = [
        # Shell delete commands
        r"(?:^|[;&|]\s*)rm\s+",
        r"(?:^|[;&|]\s*)del\s+",
        r"(?:^|[;&|]\s*)rmdir\s+",
        r"(?:^|[;&|]\s*)Remove-Item\s+",
        r"(?:^|[;&|]\s*)ri\s+",
        # P1-1: git rm (deletes files from working tree and index)
        # F8: Allow optional git global flags before subcommand (e.g., git -C dir rm)
        r"(?:^|[;&|]\s*)git\s+(?:-[A-Za-z]\s+\S+\s+|--[a-z][-a-z]*(?:=\S+|\s+(?!rm\b)\S+)?\s+)*rm\s+",
        # mv to /dev/null (effective deletion)
        r"\bmv\s+\S+\s+/dev/null\b",
        # P1-2: Standalone redirect truncation (> file, : > file, >| file)
        # Destroys content by truncating to zero bytes
        r"^\s*(?::)?\s*>(?!>)\|?\s*\S+",
        # Interpreter-mediated deletions (python/node/perl/ruby)
        # F4: Split pathlib.Path pattern to avoid ReDoS (O(N^2) backtracking)
        r"(?:py|python[23]?|python\d[\d.]*)\s[^|&\n]*(?:os\.remove|os\.unlink|shutil\.rmtree|shutil\.move|os\.rmdir)",
        r"(?:py|python[23]?|python\d[\d.]*)\s[^|&\n]*pathlib\.Path\([^)]*\)\.unlink",
        r"(?:node|deno|bun)\s[^|&\n]*(?:unlinkSync|rmSync|rmdirSync|fs\.unlink|fs\.rm\b|promises\.unlink)",
        r"(?:perl|ruby)\s[^|&\n]*(?:\bunlink\b|File\.delete|FileUtils\.rm)",
    ]
    return any(re.search(p, command, re.IGNORECASE) for p in delete_patterns)


def is_write_command(command: str) -> bool:
    """Check if command is a write/modify operation.

    Enhanced with additional write vectors: sed -i, cp, dd, rsync,
    patch, and colon truncation (: >).

    Critical fix I-2: Does NOT include 'install' to avoid breaking
    npm/pip/cargo/brew/apt commands.

    Args:
        command: The bash command (or sub-command) to check.

    Returns:
        True if command appears to write or modify files.
    """
    write_patterns = [
        r">\s*['\"]?[^|&;]+",  # Redirection (existing)
        r"\btee\s+",  # tee (with word boundary)
        r"\bmv\s+",  # mv (with word boundary)
        r"(?<![A-Za-z-])ln\s+",  # F2: ln (negative lookbehind prevents ls -ln false positive)
        r"\bsed\s+.*-[^-]*i",  # sed with -i (in-place edit)
        r"\bcp\s+",  # cp (destination is a write)
        r"\bdd\s+",  # dd
        r"\bpatch\b",  # patch
        r"\brsync\s+",  # rsync
        r":\s*>",  # Truncation via : > file
        # P1-4: Metadata-modifying commands (count as write for readOnly)
        r"\bchmod\s+",
        r"\btouch\s+",
        r"\bchown\s+",
        r"\bchgrp\s+",
    ]
    return any(re.search(p, command, re.IGNORECASE) for p in write_patterns)


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


def _is_path_candidate(s: str) -> bool:
    """Check if a string is a plausible filesystem path.

    Rejects strings that cannot be valid paths before they reach os.path calls.

    Args:
        s: String to check.

    Returns:
        True if the string could be a valid filesystem path.
    """
    if not s:
        return False
    if "\n" in s or "\r" in s:
        return False
    if "\0" in s:
        return False
    if len(s) > 4096:
        return False
    for component in s.split("/"):
        if len(component) > 255:
            return False
    return True


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
        if len(archived) >= ARCHIVE_MAX_FILES:
            log_guardian(
                "WARN", f"Archive file limit reached ({ARCHIVE_MAX_FILES}), skipping rest"
            )
            skipped_count += len(files) - len(archived)
            break

        try:
            file_size = 0
            if file_path.is_file():
                file_size = file_path.stat().st_size
            elif file_path.is_dir():
                file_size = sum(f.stat().st_size for f in file_path.rglob("*") if f.is_file())

            file_size_mb = file_size / (1024 * 1024)

            if file_size_mb > ARCHIVE_MAX_FILE_SIZE_MB:
                max_mb = ARCHIVE_MAX_FILE_SIZE_MB
                log_guardian(
                    "WARN",
                    f"Skipping large file {file_path.name} ({file_size_mb:.1f}MB > {max_mb}MB)",
                )
                skipped_count += 1
                continue

            if (total_size + file_size) / (1024 * 1024) > ARCHIVE_MAX_TOTAL_SIZE_MB:
                limit_mb = ARCHIVE_MAX_TOTAL_SIZE_MB
                log_guardian(
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
                # F5: Symlink safety — preserve symlinks instead of dereferencing
                if os.path.islink(file_path):
                    link_target = os.readlink(file_path)
                    os.symlink(link_target, target_path)
                else:
                    shutil.copy2(file_path, target_path)
            elif file_path.is_dir():
                # F5: Symlink safety — preserve symlinks as symlinks
                shutil.copytree(file_path, target_path, symlinks=True, dirs_exist_ok=True)

            archived.append((file_path, target_path))
            total_size += file_size

        except PermissionError as e:
            log_guardian(
                "WARN",
                f"Archive PERMISSION DENIED for {file_path.name}: {e}\n"
                "  Check file permissions or run with elevated privileges.",
            )
            skipped_count += 1
        except OSError as e:
            is_disk_full = e.errno == 28 or getattr(e, "winerror", None) == 112
            error_type = "DISK FULL" if is_disk_full else "FILESYSTEM ERROR"
            log_guardian(
                "WARN",
                f"Archive {error_type} for {file_path.name}: {e}\n  errno={e.errno}",
            )
            skipped_count += 1
        except Exception as e:
            log_guardian(
                "WARN",
                f"Archive UNEXPECTED ERROR for {file_path.name}: {type(e).__name__}: {e}",
            )
            skipped_count += 1

    elapsed = (datetime.now() - start_time).total_seconds()
    if elapsed > 5:
        log_guardian("INFO", f"Archive completed in {elapsed:.1f}s ({len(archived)} files)")

    if skipped_count > 0:
        log_guardian("WARN", f"Skipped {skipped_count} file(s) during archive")

    return archive_dir, archived


def create_deletion_log(archive_dir: Path, archived: list[tuple[Path, Path]], command: str):
    """Create metadata JSON in archive directory."""
    truncated_command = command[:200] + "..." if len(command) > 200 else command
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": truncated_command,
        "files": [{"original": str(orig), "archived": str(arch)} for orig, arch in archived],
    }
    log_file = archive_dir / "_deletion_log.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# ============================================================
# Pre-commit Message Helper
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
    cmd_short = command[:20].replace("\n", " ").strip()
    fixed_len = len(prefix) + len(": ") + len("... @ ") + len(timestamp)
    available = COMMIT_MESSAGE_MAX_LENGTH - fixed_len

    if available > 10:
        cmd_short = command[:available].replace("\n", " ").strip()
    else:
        cmd_short = command[:10].replace("\n", " ").strip()

    message = f"{prefix}: {cmd_short}... @ {timestamp}"

    if len(message) > COMMIT_MESSAGE_MAX_LENGTH:
        message = message[: COMMIT_MESSAGE_MAX_LENGTH - 3] + "..."

    return message


# ============================================================
# Verdict Aggregation
# ============================================================

# Verdict precedence: deny > ask > allow
_VERDICT_PRIORITY = {"deny": 2, "ask": 1, "allow": 0}
_FAIL_CLOSE_PRIORITY = max(_VERDICT_PRIORITY.values())  # Unknown verdicts fail closed


def _stronger_verdict(
    current: tuple[str, str], candidate: tuple[str, str]
) -> tuple[str, str]:
    """Return the stronger of two verdicts based on precedence.

    C-1 fix: All layers must complete before any decision is emitted.
    This helper enables verdict aggregation with deny > ask > allow.
    Unknown verdict strings default to deny priority (fail-close).

    Args:
        current: Current (verdict, reason) tuple.
        candidate: New (verdict, reason) tuple to compare.

    Returns:
        The stronger (verdict, reason) tuple.
    """
    if _VERDICT_PRIORITY.get(candidate[0], _FAIL_CLOSE_PRIORITY) > _VERDICT_PRIORITY.get(current[0], _FAIL_CLOSE_PRIORITY):
        return candidate
    return current


# ============================================================
# Main Hook Logic
# ============================================================


def main() -> None:
    """Main hook entry point.

    Execution flow (C-1 fix: all layers complete before decision):
    1. Layer 0: Block patterns (catastrophic) -- short-circuits on deny
    2. Layer 0b: Ask patterns (dangerous-but-legitimate)
    3. Layer 1: Protected path scan (raw string scan)
    4. Layer 2+3+4: Command decomposition + per-sub-command analysis
    5. Aggregate verdicts: deny > ask > allow
    6. Handle deletions with archive
    7. Pre-commit for dangerous operations
    8. Emit final verdict
    """
    # Get project directory
    project_dir_str = get_project_dir()
    if not project_dir_str:
        # SECURITY: No project dir = can't verify safety, deny by default
        print("GUARDIAN WARN: No project dir set, failing closed for bash guardian", file=sys.stderr)
        reason = "Guardian cannot verify command safety: project directory not set"
        print(json.dumps(deny_response(reason)))
        sys.exit(0)
    project_dir = Path(project_dir_str)

    # Parse input - FAIL-CLOSE on invalid JSON for security
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log_guardian("ERROR", f"Malformed JSON input: {e}")
        print(json.dumps(deny_response("Invalid hook input (malformed JSON)")))
        sys.exit(0)

    # Only process Bash commands
    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Truncate for logging
    cmd_preview = truncate_command(command)

    # Load config once for all layers
    config = load_guardian_config()

    # ========== Layer 0: Block Patterns (short-circuit on catastrophic) ==========
    blocked, reason = match_block_patterns(command)
    if blocked:
        log_guardian("BLOCK", f"{reason}: {cmd_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", "Would DENY")
            sys.exit(0)
        print(json.dumps(deny_response(reason)))
        sys.exit(0)

    # ========== Collect verdicts from all layers ==========
    # C-1 fix: ALL layers complete before any decision
    final_verdict: tuple[str, str] = ("allow", "")

    # Layer 0b: Ask patterns
    needs_ask, ask_reason = match_ask_patterns(command)
    if needs_ask:
        final_verdict = _stronger_verdict(final_verdict, ("ask", ask_reason))

    # ========== Layer 1: Protected Path Scan ==========
    scan_verdict, scan_reason = scan_protected_paths(command, config)
    if scan_verdict != "allow":
        final_verdict = _stronger_verdict(final_verdict, (scan_verdict, scan_reason))
        log_guardian("SCAN", f"Layer 1 {scan_verdict}: {scan_reason}")

    # ========== Layer 2+3+4: Command Decomposition + Path Analysis ==========
    sub_commands = split_commands(command)
    all_paths: list[Path] = []  # Collect all paths for archive step

    for sub_cmd in sub_commands:
        is_write = is_write_command(sub_cmd)
        is_delete = is_delete_command(sub_cmd)

        # Layer 3: Extract paths from arguments (enhanced with allow_nonexistent)
        paths = extract_paths(sub_cmd, project_dir, allow_nonexistent=(is_write or is_delete))

        # Layer 3: Extract paths from redirections
        redir_paths = extract_redirection_targets(sub_cmd, project_dir)

        sub_paths = paths + redir_paths
        all_paths.extend(sub_paths)

        # F1: Fail-closed safety net — if write/delete detected but no paths resolved,
        # escalate to "ask" instead of silently allowing (fail-closed)
        if (is_write or is_delete) and not sub_paths:
            op_type = "delete" if is_delete else "write"
            final_verdict = _stronger_verdict(
                final_verdict,
                ("ask", f"Detected {op_type} but could not resolve target paths"),
            )

        for path in sub_paths:
            path_str = str(path)

            # Symlink escape check
            if is_symlink_escape(path_str):
                log_guardian("BLOCK", f"Symlink escape detected: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Symlink points outside project: {path.name}")
                )
                continue

            # Zero access check (applies to ALL operations)
            if match_zero_access(path_str):
                log_guardian("BLOCK", f"Zero access path: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Protected path: {path.name}")
                )
                continue

            # Read-only check (for write commands in this sub-command)
            if is_write and match_read_only(path_str):
                log_guardian("BLOCK", f"Read-only path: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Read-only path: {path.name}")
                )
                continue

            # External read-only check (for write commands targeting allowedExternalReadPaths)
            if is_write or is_delete:
                ext_mode = match_allowed_external_path(path_str)
                if ext_mode == "read":
                    log_guardian("BLOCK", f"Read-only external path (bash write): {path.name}")
                    final_verdict = _stronger_verdict(
                        final_verdict, ("deny", f"External path is read-only: {path.name}")
                    )
                    continue

            # No-delete check (for delete commands in this sub-command)
            if is_delete and match_no_delete(path_str):
                log_guardian("BLOCK", f"No-delete path: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Protected from deletion: {path.name}")
                )
                continue

    # ========== Emit final verdict ==========
    # C-1 fix: Now ALL layers have been evaluated

    if final_verdict[0] == "deny":
        log_guardian("DENY", f"{final_verdict[1]}: {cmd_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", "Would DENY")
            sys.exit(0)
        print(json.dumps(deny_response(final_verdict[1])))
        sys.exit(0)

    # ========== Handle Deletions with Archive ==========
    if any(is_delete_command(sub) for sub in sub_commands):
        if not all_paths:
            cmd_short = truncate_command(command, 80)
            log_guardian("DEBUG", f"Delete cmd, no paths extracted: {cmd_short}")
        else:
            existing_paths = [p for p in all_paths if p.exists()]
            untracked = [p for p in existing_paths if not git_is_tracked(str(p))]

            if not untracked and existing_paths:
                log_guardian(
                    "DEBUG",
                    f"All {len(existing_paths)} path(s) are git-tracked, no archive needed",
                )

            if untracked:
                if is_dry_run():
                    log_guardian("DRY-RUN", f"Would archive: {[p.name for p in untracked]}")
                else:
                    archive_dir, archived = archive_files(untracked, project_dir)
                    if archived:
                        create_deletion_log(archive_dir, archived, command)
                        log_guardian(
                            "ARCHIVE",
                            f"Archived {len(archived)} file(s) to {archive_dir.name}",
                        )

                        file_list = ", ".join(p.name for p in existing_paths[:3])
                        if len(existing_paths) > 3:
                            file_list += f", ... (+{len(existing_paths) - 3} more)"

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
                        log_guardian(
                            "WARN",
                            f"Archive FAILED for {len(untracked)} untracked file(s)",
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

            if existing_paths:
                log_guardian("ASK", f"Delete files: {[p.name for p in existing_paths[:3]]}")
                if is_dry_run():
                    log_guardian("DRY-RUN", "Would ASK")
                    sys.exit(0)
                file_list = ", ".join(p.name for p in existing_paths[:3])
                if len(existing_paths) > 3:
                    file_list += f", ... (+{len(existing_paths) - 3} more)"
                print(
                    json.dumps(
                        ask_response(
                            f"Delete {len(existing_paths)} file(s): {file_list}?"
                        )
                    )
                )
                sys.exit(0)

    # ========== Handle ask verdict (from Layer 0b or Layer 1) ==========
    if final_verdict[0] == "ask":
        # Try pre-commit before dangerous operation
        try:
            git_config = config.get("gitIntegration", {})
            pre_commit_config = git_config.get("preCommitOnDangerous", {})

            if pre_commit_config.get("enabled", False):
                if is_rebase_or_merge_in_progress():
                    log_guardian(
                        "WARN",
                        "Rebase/merge in progress - skipping pre-commit "
                        "(would corrupt state)",
                    )
                elif git_has_changes():
                    prefix = validate_commit_prefix(
                        pre_commit_config.get(
                            "messagePrefix", "pre-danger-checkpoint"
                        ),
                        default="pre-danger-checkpoint",
                    )
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    commit_msg = create_precommit_message(
                        prefix, command, timestamp
                    )

                    if is_dry_run():
                        log_guardian(
                            "DRY-RUN",
                            f"Would pre-commit: {commit_msg[:60]}...",
                        )
                    else:
                        if git_add_tracked():
                            if git_has_staged_changes():
                                if git_commit(commit_msg, no_verify=True):
                                    log_guardian(
                                        "INFO",
                                        f"Pre-commit created before: {cmd_preview}",
                                    )
                                else:
                                    log_guardian(
                                        "WARN",
                                        "Pre-commit failed: commit unsuccessful",
                                    )
                                    set_circuit_open(
                                        "pre-commit failed during dangerous operation"
                                    )
                            else:
                                log_guardian(
                                    "INFO",
                                    "No staged changes - skipping pre-commit "
                                    "(untracked only)",
                                )
                        else:
                            log_guardian(
                                "WARN",
                                "Pre-commit failed: unable to stage changes",
                            )
                            set_circuit_open(
                                "pre-commit staging failed during dangerous "
                                "operation"
                            )
        except Exception as e:
            log_guardian("WARN", f"Pre-commit failed: {e}")

        log_guardian("ASK", f"{final_verdict[1]}: {cmd_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", "Would ASK")
            sys.exit(0)
        print(json.dumps(ask_response(final_verdict[1])))
        sys.exit(0)

    # ========== Allow ==========
    if len(command) > 10 and not command.startswith(
        ("ls", "cd", "pwd", "echo", "cat", "type")
    ):
        log_guardian("ALLOW", cmd_preview)
    sys.exit(0)


if __name__ == "__main__":
    # TODO: Consider wrapping main() with with_timeout() using hookBehavior.timeoutSeconds.
    # Currently SKIPPED because:
    # 1. SIGALRM on Unix can interrupt git subprocess calls mid-execution, risking git state corruption
    # 2. Threading timeout on Windows cannot kill the running thread (it continues in background)
    # 3. Individual subprocess calls already have their own timeouts (5-30s)
    # 4. A blanket timeout could race with archive file operations, causing partial archives
    # If implemented, the HookTimeoutError should follow hookBehavior.onTimeout (default: "deny").
    try:
        main()
    except Exception as e:
        log_guardian("ERROR", f"Unhandled exception: {e}")
        set_circuit_open(f"bash_guardian crashed: {type(e).__name__}")
        # Use hookBehavior.onError from config (default: "deny" = fail-closed)
        try:
            error_action = get_hook_behavior().get("onError", "deny")
            response = make_hook_behavior_response(
                error_action,
                f"Guardian system error: {type(e).__name__}",
            )
            if response is not None:
                print(json.dumps(response))
        except Exception:
            # If hookBehavior lookup itself fails, fall back to deny (fail-closed)
            try:
                print(
                    json.dumps(
                        deny_response(
                            f"Guardian system error: {type(e).__name__}"
                        )
                    )
                )
            except Exception:
                pass
        sys.exit(0)
