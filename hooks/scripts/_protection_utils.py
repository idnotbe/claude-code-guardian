#!/usr/bin/env python3
"""Protection utilities for Claude Code Guardian Plugin.

This module provides shared utilities for all protection hooks:
- Configuration loading from protection.json
- Pattern matching (regex for bash commands)
- Path matching (glob for file paths)
- Dry-run mode support
- Logging

# PLUGIN MIGRATION: Config resolution chain (3-step):
#   1. $CLAUDE_PROJECT_DIR/.claude/guardian/protection.json (user custom)
#   2. $CLAUDE_PLUGIN_ROOT/assets/protection.default.json (plugin default)
#   3. Hardcoded _FALLBACK_PROTECTION (emergency fallback)
#
# PLUGIN MIGRATION: Log location changed to .claude/guardian/guardian.log
# PLUGIN MIGRATION: Circuit breaker changed to .claude/guardian/.circuit_open
# PLUGIN MIGRATION: Self-protection reduced to config file only (dynamic path)

Usage:
    from _protection_utils import (
        load_protection_config,
        match_block_patterns,
        match_zero_access,
        is_dry_run,
        log_protection,
        evaluate_protection,  # Orchestration function
        git_is_tracked,       # Git integration
    )

Note on log_protection():
    - Silent fail if CLAUDE_PROJECT_DIR not set
    - Silent fail on file write errors
    - This is intentional to avoid breaking hooks on logging issues

Design Principles:
    1. Security-First: Fail-close on security-critical errors (malformed input, import failure)
       Fail-open on non-critical errors (logging, path normalization)
    2. Windows Compatibility: Use normpath/abspath for all path comparisons
    3. Robust Exception Handling: Never crash the hook lifecycle
"""

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================
# ReDoS Protection: Optional regex module for timeout support
# ============================================================

try:
    import regex as _regex_module

    _HAS_REGEX_TIMEOUT = True
except ImportError:
    _regex_module = None
    _HAS_REGEX_TIMEOUT = False

# Note: Python 3.11+ does NOT have native regex timeout support.
# The `timeout` parameter for re.search() was proposed but never implemented.
# Only the `regex` package provides timeout functionality.

# ============================================================
# Constants
# ============================================================

DRY_RUN_ENV = "CLAUDE_HOOK_DRY_RUN"
"""Environment variable to enable dry-run mode.
Set to "1", "true", or "yes" to enable."""

MAX_COMMAND_LENGTH = 100_000
"""Maximum command length in bytes before logging warning.
Commands exceeding this are still processed (fail-open) but logged."""

MAX_PATH_PREVIEW_LENGTH = 60
"""Maximum path length for log display. Paths longer than this are truncated."""

MAX_COMMAND_PREVIEW_LENGTH = 80
"""Maximum command length for log display. Commands longer than this are truncated."""

MAX_LOG_SIZE_BYTES = 1_000_000
"""Maximum log file size before rotation (1 MB)."""

REGEX_TIMEOUT_SECONDS = 0.5
"""Default timeout for regex operations to prevent ReDoS."""

COMMIT_MESSAGE_MAX_LENGTH = 72
"""Maximum commit message length (Git convention)."""

COMMIT_PREFIX_MAX_LENGTH = 30
"""Maximum commit message prefix length (m3 FIX: centralized validation)."""

HOOK_DEFAULT_TIMEOUT_SECONDS = 10
"""Default timeout for hook execution (Phase 5)."""


# ============================================================
# Hook Timeout Handling (Phase 5)
# ============================================================


class HookTimeoutError(Exception):
    """Hook execution timed out (Phase 5)."""

    pass


def with_timeout(func, timeout_seconds: int = HOOK_DEFAULT_TIMEOUT_SECONDS):
    """Execute function with timeout protection (Phase 5).

    Platform-specific implementation:
    - Windows: threading-based timeout
    - Unix: signal-based timeout (SIGALRM)

    Args:
        func: Function to execute (no arguments).
        timeout_seconds: Timeout in seconds (default: HOOK_DEFAULT_TIMEOUT_SECONDS).

    Returns:
        func() return value.

    Raises:
        HookTimeoutError: If execution exceeds timeout.
    """
    import threading

    if sys.platform == "win32":
        # Windows: threading-based timeout
        result = [None]
        exception = [None]

        def wrapper():
            try:
                result[0] = func()
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=wrapper)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            raise HookTimeoutError(f"Hook execution timed out after {timeout_seconds}s")
        if exception[0]:
            raise exception[0]
        return result[0]
    else:
        # Unix: signal-based timeout
        import signal

        def timeout_handler(signum, frame):
            raise HookTimeoutError(f"Hook execution timed out after {timeout_seconds}s")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        try:
            return func()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


def validate_commit_prefix(prefix: str, default: str = "auto-checkpoint") -> str:
    """Validate and truncate commit message prefix if needed (m3 FIX).

    Centralizes prefix validation that was duplicated in auto_commit.py
    and bash_protection.py.

    Args:
        prefix: The prefix to validate.
        default: Default prefix if input is empty.

    Returns:
        Validated prefix, truncated to COMMIT_PREFIX_MAX_LENGTH if needed.
    """
    if not prefix:
        return default

    if len(prefix) > COMMIT_PREFIX_MAX_LENGTH:
        log_protection(
            "WARN",
            f"Commit prefix too long ({len(prefix)} > {COMMIT_PREFIX_MAX_LENGTH}), truncating",
        )
        return prefix[:COMMIT_PREFIX_MAX_LENGTH]

    return prefix


# ============================================================
# Git Availability Check (Phase 4 Fix)
# ============================================================

_git_available_cache: bool | None = None
"""Cached result of git availability check (per-process)."""


def is_git_available() -> bool:
    """Check if git is available in PATH.

    Result is cached for the lifetime of the process to avoid
    repeated PATH lookups (~6 calls per hook execution).

    Returns:
        True if git is available, False otherwise.
    """
    global _git_available_cache
    if _git_available_cache is None:
        _git_available_cache = shutil.which("git") is not None
    return _git_available_cache


# ============================================================
# Circuit Breaker Pattern (Phase 4 Fix)
# ============================================================

CIRCUIT_BREAKER_FILE = ".circuit_open"
# PLUGIN MIGRATION: Circuit breaker now in .claude/guardian/
"""Flag file name for circuit breaker. Located in .claude/guardian/"""

CIRCUIT_TIMEOUT_SECONDS = 3600  # 1 hour auto-recovery
"""Time in seconds after which the circuit breaker auto-expires."""


def get_circuit_file_path() -> Path:
    """Get the path to the circuit breaker file.

    # PLUGIN MIGRATION: Changed from .claude/hooks/ to .claude/guardian/

    Returns:
        Path object for circuit breaker file.
    """
    project_dir = get_project_dir()
    if not project_dir:
        # PLUGIN MIGRATION: Updated fallback path
        return Path(".claude/guardian") / CIRCUIT_BREAKER_FILE
    return Path(project_dir) / ".claude" / "guardian" / CIRCUIT_BREAKER_FILE


def set_circuit_open(reason: str) -> None:
    """Open the circuit breaker, preventing auto-commit.

    Call this when a critical error occurs that should prevent
    automatic commits until manually reviewed.

    Args:
        reason: Human-readable reason for opening the circuit.
    """
    circuit_file = get_circuit_file_path()
    try:
        circuit_file.parent.mkdir(parents=True, exist_ok=True)
        with open(circuit_file, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}|{reason}\n")
        log_protection("WARN", f"Circuit breaker OPEN: {reason}")
    except Exception as e:
        log_protection("ERROR", f"Failed to set circuit open: {e}")


def is_circuit_open() -> tuple[bool, str]:
    """Check if the circuit breaker is open.

    M2 FIX: Uses atomic operations to prevent race conditions.

    Returns:
        (is_open, reason) tuple. If open, reason contains the cause.
        Auto-expires after CIRCUIT_TIMEOUT_SECONDS (1 hour).
    """
    circuit_file = get_circuit_file_path()
    try:
        if not circuit_file.exists():
            return False, ""

        # M2 FIX: Read file info with race condition handling
        try:
            stat_info = circuit_file.stat()
            age_seconds = time.time() - stat_info.st_mtime
        except FileNotFoundError:
            # File was deleted between exists() and stat() - race condition handled
            return False, ""

        if age_seconds > CIRCUIT_TIMEOUT_SECONDS:
            log_protection(
                "INFO", f"Circuit breaker auto-expired after {age_seconds / 3600:.1f} hours"
            )
            # M2 FIX: Use missing_ok to handle race condition
            try:
                circuit_file.unlink(missing_ok=True)
            except Exception:
                pass  # Best effort cleanup
            return False, ""

        # M2 FIX: Handle race condition between stat() and open()
        try:
            with open(circuit_file, encoding="utf-8") as f:
                content = f.read().strip()
        except FileNotFoundError:
            # File was deleted between stat() and open() - race condition handled
            return False, ""

        if "|" in content:
            _, reason = content.split("|", 1)
            return True, reason
        return True, "Unknown reason"
    except PermissionError as e:
        # M1 FIX: Specific handling for permission errors with recovery guidance
        log_protection(
            "ERROR",
            f"Cannot read circuit breaker (permission denied): {e}\n"
            f"  Recovery: Check file permissions on {circuit_file}\n"
            f'  Or delete the file manually: del "{circuit_file}"',
        )
        return True, f"Circuit breaker permission error - check {circuit_file}"
    except OSError as e:
        # M1 FIX: File system errors with recovery guidance
        log_protection(
            "ERROR",
            f"Cannot read circuit breaker (filesystem error): {e}\n"
            f'  Recovery: Delete corrupted file: del "{circuit_file}"',
        )
        return True, f"Circuit breaker filesystem error - delete {circuit_file}"
    except Exception as e:
        # SECURITY FIX: Fail-CLOSED - treat read errors as circuit open
        # This prevents protection bypass when circuit file is corrupted/inaccessible
        log_protection(
            "ERROR",
            f"Cannot read circuit breaker (unexpected): {e}\n"
            f'  Recovery: Delete file manually: del "{circuit_file}"',
        )
        return True, f"Circuit breaker error: {e}"


def clear_circuit() -> None:
    """Close the circuit breaker, allowing auto-commit.

    Call this after the issue has been resolved.
    """
    circuit_file = get_circuit_file_path()
    try:
        if circuit_file.exists():
            circuit_file.unlink()
            log_protection("INFO", "Circuit breaker CLOSED")
    except Exception as e:
        log_protection("WARN", f"Failed to clear circuit: {e}")


# PLUGIN MIGRATION: Self-protection reduced to config file only.
# In plugin context, scripts live in read-only plugin cache dir.
# Only the user's config file needs protection from agent modification.
SELF_PROTECTION_PATHS = (
    ".claude/guardian/protection.json",
)
"""Paths that are always protected from Edit/Write, even if not in config.
This is a security measure to prevent protection bypass.
PLUGIN MIGRATION: Reduced from 6 script paths to config-only."""

# Hardcoded fallback protection for when protection.json is missing/corrupted
# This ensures critical paths are ALWAYS protected even if config fails to load
_FALLBACK_PROTECTION = {
    "bashToolPatterns": {
        "block": [
            {"pattern": r"rm\s+-[rRf]+\s+/(?:\s*$|\*)", "reason": "[FALLBACK] Root deletion"},
            {
                "pattern": r"(?i)(?:rm|rmdir|del).*\.git(?:\s|/|$)",
                "reason": "[FALLBACK] Git deletion",
            },
            {
                "pattern": r"(?i)(?:rm|rmdir|del).*\.claude(?:\s|/|$)",
                "reason": "[FALLBACK] Claude deletion",
            },
            {
                "pattern": r"(?i)(?:rm|rmdir|del).*_archive(?:\s|/|$)",
                "reason": "[FALLBACK] Archive deletion",
            },
            {"pattern": r"git\s+push\s+(?:--force|-f)", "reason": "[FALLBACK] Force push"},
        ]
    },
    "zeroAccessPaths": [
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "~/.ssh/**",
        "~/.gnupg/**",
        "~/.aws/**",
        "secrets.json",
        "secrets.yaml",
    ],
    # PLUGIN MIGRATION: Updated readOnlyPaths to protect config instead of old hook paths
    "readOnlyPaths": [
        ".claude/guardian/protection.json",
        "node_modules/**",
        "__pycache__/**",
        ".venv/**",
        "poetry.lock",
    ],
    "noDeletePaths": [".git/**", ".claude/**", "_archive/**", "CLAUDE.md"],
    "allowedExternalPaths": [],
}

# ============================================================
# Configuration
# ============================================================

_config_cache: dict | None = None
_using_fallback_config: bool = False
"""Flag indicating if fallback config is in use (M2 FIX)."""

# PLUGIN MIGRATION: Track which config file was actually loaded (for dynamic self-protection)
_active_config_path: str | None = None
"""Path to the config file that was actually loaded. Used for dynamic self-protection."""


def get_project_dir() -> str:
    """Get and validate project directory from environment variable.

    Validates that:
    - Directory exists
    - Directory contains .git (is a git repository)

    Returns:
        Project directory path, or empty string if not set or invalid.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        return ""

    # Validate directory exists
    # Note: Cannot call log_protection() here - would cause infinite recursion
    # because log_protection() calls get_project_dir()
    if not os.path.isdir(project_dir):
        return ""

    # Validate it's a git repo (has .git)
    # Note: No logging here to avoid recursion - git operations will fail gracefully
    # git_dir = os.path.join(project_dir, ".git")
    # Non-git projects should still work for protection purposes

    return project_dir


def _get_plugin_root() -> str:
    """Get the plugin root directory from environment variable.

    # PLUGIN MIGRATION: New function for plugin-aware config resolution.

    Returns:
        Plugin root directory path, or empty string if not set.
    """
    return os.environ.get("CLAUDE_PLUGIN_ROOT", "")


def load_protection_config() -> dict[str, Any]:
    """Load protection.json with caching and fallback protection.

    # PLUGIN MIGRATION: Config resolution chain (3-step):
    #   1. $CLAUDE_PROJECT_DIR/.claude/guardian/protection.json (user custom)
    #   2. $CLAUDE_PLUGIN_ROOT/assets/protection.default.json (plugin default)
    #   3. Hardcoded _FALLBACK_PROTECTION (emergency fallback)

    The config is cached for the lifetime of the process.
    Since hooks run as separate processes, this is safe.

    If config cannot be loaded, returns _FALLBACK_PROTECTION to ensure
    critical paths (.git, .claude, _archive) are always protected.

    Returns:
        Configuration dict, or fallback protection on error.
        Never raises exceptions - returns safe default on any error.

    Note (M2 FIX):
        Use is_using_fallback_config() to check if fallback is active.
    """
    global _config_cache, _using_fallback_config, _active_config_path
    if _config_cache is not None:
        return _config_cache

    project_dir = get_project_dir()

    # PLUGIN MIGRATION: Step 1 -- User custom config in .claude/guardian/
    if project_dir:
        config_path = Path(project_dir) / ".claude" / "guardian" / "protection.json"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    _config_cache = json.load(f)
                _using_fallback_config = False
                _active_config_path = str(config_path)
                log_protection("INFO", f"Loaded config from {config_path}")
                return _config_cache
            except json.JSONDecodeError as e:
                log_protection(
                    "ERROR",
                    f"[FALLBACK] Invalid JSON in {config_path}: {e}\n"
                    "  Using fallback. Fix JSON syntax to restore full protection.",
                )
                # Fall through to next resolution step
            except OSError as e:
                log_protection(
                    "ERROR",
                    f"[FALLBACK] Failed to read {config_path}: {e}\n"
                    "  Check file permissions.",
                )
                # Fall through to next resolution step
            except Exception as e:
                log_protection(
                    "ERROR",
                    f"[FALLBACK] Unexpected error loading {config_path}: {e}",
                )
                # Fall through to next resolution step

    # PLUGIN MIGRATION: Step 2 -- Plugin default config
    plugin_root = _get_plugin_root()
    if plugin_root:
        default_config_path = Path(plugin_root) / "assets" / "protection.default.json"
        if default_config_path.exists():
            try:
                with open(default_config_path, encoding="utf-8") as f:
                    _config_cache = json.load(f)
                _using_fallback_config = False
                _active_config_path = str(default_config_path)
                log_protection(
                    "INFO",
                    f"Using plugin default config from {default_config_path}\n"
                    "  Run /guardian:init to create a custom config for this project.",
                )
                return _config_cache
            except Exception as e:
                log_protection(
                    "ERROR",
                    f"[FALLBACK] Failed to load plugin default config: {e}",
                )
                # Fall through to hardcoded fallback

    # PLUGIN MIGRATION: Step 3 -- Hardcoded fallback
    if not project_dir:
        log_protection(
            "WARN",
            "[FALLBACK] CLAUDE_PROJECT_DIR not set - using minimal fallback protection.\n"
            "  Custom protection rules from protection.json are NOT active.",
        )
    else:
        log_protection(
            "WARN",
            "[FALLBACK] No protection.json found in any location.\n"
            "  Searched: .claude/guardian/protection.json"
            + (f", plugin default" if plugin_root else "")
            + "\n  Using minimal fallback protection. Run /guardian:init to set up.",
        )

    _config_cache = _FALLBACK_PROTECTION
    _using_fallback_config = True
    _active_config_path = None
    return _config_cache


def is_using_fallback_config() -> bool:
    """Check if fallback protection config is in use (M2 FIX).

    Call this after load_protection_config() to determine if custom
    protection rules are active or if minimal fallback is being used.

    Returns:
        True if fallback config is active (custom rules NOT loaded).
        False if protection.json was loaded successfully.
    """
    # Ensure config is loaded first
    if _config_cache is None:
        load_protection_config()
    return _using_fallback_config


def get_active_config_path() -> str | None:
    """Get the path to the config file that was actually loaded.

    # PLUGIN MIGRATION: New function for dynamic self-protection.

    Returns:
        Absolute path string to the loaded config, or None if using hardcoded fallback.
    """
    if _config_cache is None:
        load_protection_config()
    return _active_config_path


def get_hook_behavior() -> dict[str, Any]:
    """Get hookBehavior section from config.

    Returns:
        hookBehavior dict with defaults applied.
    """
    config = load_protection_config()
    defaults = {
        "onTimeout": "deny",
        "onError": "deny",
        "timeoutSeconds": 10,
    }
    behavior = config.get("hookBehavior", {})
    return {**defaults, **behavior}


def validate_protection_config(config: dict) -> list[str]:
    """Validate protection.json configuration (Phase 5).

    Performs structural and semantic validation of the protection config:
    - Checks required sections exist
    - Validates hookBehavior values
    - Validates regex pattern syntax
    - Checks path pattern validity

    Args:
        config: Loaded configuration dictionary.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors = []

    # Check required sections
    required_sections = ["bashToolPatterns", "zeroAccessPaths"]
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required section: {section}")

    # Check hookBehavior
    hook_behavior = config.get("hookBehavior", {})
    valid_decisions = {"allow", "deny", "ask"}

    on_timeout = hook_behavior.get("onTimeout", "deny")
    if on_timeout not in valid_decisions:
        errors.append(f"Invalid hookBehavior.onTimeout: {on_timeout} (must be: {valid_decisions})")

    on_error = hook_behavior.get("onError", "deny")
    if on_error not in valid_decisions:
        errors.append(f"Invalid hookBehavior.onError: {on_error} (must be: {valid_decisions})")

    timeout_seconds = hook_behavior.get("timeoutSeconds", 10)
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        errors.append(
            f"Invalid hookBehavior.timeoutSeconds: {timeout_seconds} (must be positive number)"
        )

    # Check pattern syntax in bashToolPatterns
    bash_patterns = config.get("bashToolPatterns", {})
    for category in ["block", "ask"]:
        patterns = bash_patterns.get(category, [])
        if not isinstance(patterns, list):
            errors.append(f"bashToolPatterns.{category} must be a list")
            continue
        for i, p in enumerate(patterns):
            if not isinstance(p, dict):
                errors.append(f"bashToolPatterns.{category}[{i}] must be an object")
                continue
            pattern = p.get("pattern", "")
            if not pattern:
                errors.append(f"bashToolPatterns.{category}[{i}] missing 'pattern' field")
                continue
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"Invalid regex in bashToolPatterns.{category}[{i}]: {e}")

    # Check path patterns are strings/lists
    path_sections = ["zeroAccessPaths", "readOnlyPaths", "noDeletePaths", "allowedExternalPaths"]
    for section in path_sections:
        paths = config.get(section, [])
        if not isinstance(paths, list):
            errors.append(f"{section} must be a list")
            continue
        for i, path in enumerate(paths):
            if not isinstance(path, str):
                errors.append(f"{section}[{i}] must be a string, got {type(path).__name__}")

    # Check gitIntegration structure (optional but should be valid if present)
    git_integration = config.get("gitIntegration", {})
    if git_integration:
        auto_commit = git_integration.get("autoCommit", {})
        if auto_commit:
            enabled = auto_commit.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                type_name = type(enabled).__name__
                errors.append(f"gitIntegration.autoCommit.enabled must be boolean, got {type_name}")

    return errors


# ============================================================
# Dry-Run Mode
# ============================================================


def is_dry_run() -> bool:
    """Check if running in dry-run (simulation) mode.

    In dry-run mode, hooks log what they WOULD do but don't
    actually block or modify anything.

    Enable by setting environment variable:
        CLAUDE_HOOK_DRY_RUN=1

    Returns:
        True if dry-run mode is enabled.
    """
    value = os.environ.get(DRY_RUN_ENV, "").lower()
    return value in ("1", "true", "yes")


# ============================================================
# Safe Regex with Timeout Protection (ReDoS Prevention)
# ============================================================


def safe_regex_search(
    pattern: str,
    text: str,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SECONDS,
) -> "re.Match | None":
    """Regex search with timeout protection against ReDoS.

    Uses the following strategy (in order of preference):
    1. `regex` module with timeout (if installed) - RECOMMENDED
    2. Standard `re` without timeout (logs warning on first use)

    Note: Python's standard `re` module does NOT support timeout.
    Install the `regex` package for ReDoS protection: pip install regex

    Args:
        pattern: Regular expression pattern.
        text: Text to search.
        flags: Regex flags (re.IGNORECASE, etc.).
        timeout: Timeout in seconds (default: REGEX_TIMEOUT_SECONDS).

    Returns:
        Match object if found, None otherwise.
        Returns None on timeout (fail-closed for security).
    """
    try:
        # Strategy 1: Use regex module with timeout (best option)
        if _HAS_REGEX_TIMEOUT and _regex_module is not None:
            try:
                return _regex_module.search(pattern, text, flags, timeout=timeout)
            except Exception as e:
                # regex module can raise TimeoutError or regex.error with timeout message
                exc_name = type(e).__name__.lower()
                exc_msg = str(e).lower()
                if "timeout" in exc_name or "timed out" in exc_msg:
                    log_protection(
                        "WARN",
                        f"Regex timeout ({timeout}s) for pattern: {pattern[:50]}...",
                    )
                    return None  # Fail-closed: treat timeout as no match
                # Re-raise if it's not a timeout error
                raise

        # Strategy 2: Fallback - no timeout protection (standard re module)
        if not getattr(safe_regex_search, "_warned_no_timeout", False):
            log_protection(
                "WARN",
                "No regex timeout protection available. "
                "Install 'regex' package for ReDoS protection: pip install regex",
            )
            safe_regex_search._warned_no_timeout = True

        return re.search(pattern, text, flags)

    except re.error as e:
        log_protection("WARN", f"Invalid regex pattern '{pattern[:50]}...': {e}")
        return None
    except Exception as e:
        log_protection("WARN", f"Unexpected regex error: {e}")
        return None


# ============================================================
# Pattern Matching (Bash Commands)
# ============================================================


def match_block_patterns(command: str) -> tuple[bool, str]:
    """Check if command matches any block pattern.

    Block patterns are for catastrophic/dangerous commands
    that should be unconditionally denied.

    Args:
        command: The bash command to check.

    Returns:
        (matched, reason) tuple. If matched is True, reason
        contains the block reason.
    """
    # F-02 FIX: Fail-CLOSE on oversized commands (padding attack prevention)
    # An attacker could pad a dangerous command to exceed MAX_COMMAND_LENGTH,
    # bypassing all pattern checks. Deny oversized commands unconditionally.
    if len(command) > MAX_COMMAND_LENGTH:
        log_protection(
            "WARN",
            f"Command exceeds size limit ({len(command)} > {MAX_COMMAND_LENGTH} bytes), "
            "blocking (fail-close for security)",
        )
        return True, f"Command too large ({len(command)} bytes) - blocked for security"

    config = load_protection_config()
    pattern_configs = config.get("bashToolPatterns", {}).get("block", [])

    for pattern_config in pattern_configs:
        pattern = pattern_config.get("pattern", "")
        reason = pattern_config.get("reason", "Blocked by pattern")
        # Use safe_regex_search with timeout protection
        match = safe_regex_search(pattern, command, re.IGNORECASE | re.DOTALL)
        if match:
            return True, reason

    return False, ""


def match_ask_patterns(command: str) -> tuple[bool, str]:
    """Check if command matches any ask pattern.

    Ask patterns are for dangerous but potentially legitimate
    commands that require user confirmation.

    Args:
        command: The bash command to check.

    Returns:
        (matched, reason) tuple. If matched is True, reason
        contains the ask reason.
    """
    # F-02 FIX: Fail-CLOSE on oversized commands (consistent with match_block_patterns)
    if len(command) > MAX_COMMAND_LENGTH:
        log_protection(
            "WARN",
            f"Command exceeds size limit ({len(command)} > {MAX_COMMAND_LENGTH} bytes), "
            "requesting confirmation (fail-close for security)",
        )
        return True, f"Command too large ({len(command)} bytes) - requires confirmation"

    config = load_protection_config()
    pattern_configs = config.get("bashToolPatterns", {}).get("ask", [])

    for pattern_config in pattern_configs:
        pattern = pattern_config.get("pattern", "")
        reason = pattern_config.get("reason", "Requires confirmation")
        # Use safe_regex_search with timeout protection
        match = safe_regex_search(pattern, command, re.IGNORECASE | re.DOTALL)
        if match:
            return True, reason

    return False, ""


# ============================================================
# Path Matching (File Paths)
# ============================================================


def normalize_path(path: str) -> str:
    """Normalize path for consistent comparison.

    Applies:
    - expanduser for ~ expansion
    - normpath for consistent separators
    - abspath for absolute path
    - lowercase on Windows for case-insensitivity

    Args:
        path: Path string to normalize.

    Returns:
        Normalized path string, or original path on error.
    """
    try:
        # Expand ~ first
        expanded = os.path.expanduser(path)
        # Get absolute path
        absolute = os.path.abspath(expanded)
        # Normalize separators
        normalized = os.path.normpath(absolute)
        # Case-insensitive on Windows
        if sys.platform == "win32":
            normalized = normalized.lower()
        return normalized
    except Exception as e:
        # On any error, log warning and return original path (fail-open)
        log_protection("WARN", f"Error normalizing path '{path}': {e}")
        return path


def expand_path(path: str) -> Path:
    """Expand ~ and resolve path to absolute.

    Args:
        path: Path string, may contain ~ or be relative.

    Returns:
        Resolved absolute Path object.
    """
    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            project_dir = get_project_dir()
            if project_dir:
                p = Path(project_dir) / p
        return p.resolve()
    except Exception as e:
        # On error, log warning and return Path of original (fail-open)
        log_protection("WARN", f"Error expanding path '{path}': {e}")
        return Path(path)


def is_symlink_escape(path: str) -> bool:
    """Check if path is a symlink pointing outside the project directory.

    This is a security check to prevent symlink attacks where a symlink
    inside the project points to sensitive files outside (e.g., ~/.ssh).

    Args:
        path: Path to check (absolute or relative).

    Returns:
        True if the path is a symlink that resolves outside the project.
        False if not a symlink, or if it resolves within the project.
        False on any error (fail-open, but logs warning).
    """
    project_dir = get_project_dir()
    if not project_dir:
        return False

    try:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = Path(project_dir) / p

        # Check if it's a symlink
        if not p.is_symlink():
            return False

        # Resolve the symlink target
        resolved = p.resolve()
        project_resolved = Path(project_dir).resolve()

        # Check if resolved path is within project
        try:
            resolved.relative_to(project_resolved)
            return False  # Within project, no escape
        except ValueError:
            # resolved is not relative to project = escape detected
            log_protection(
                "WARN",
                f"Symlink escape detected: {path} -> {resolved} (outside {project_resolved})",
            )
            return True
    except Exception as e:
        log_protection("WARN", f"Error checking symlink escape for {path}: {e}")
        return False  # Fail-open


def is_path_within_project(path: str) -> bool:
    """Check if a path (resolved) is within the project directory.

    Used to verify that operations stay within project boundaries.

    Args:
        path: Path to check.

    Returns:
        True if path is within project directory.
        False if outside project or on error.
    """
    project_dir = get_project_dir()
    if not project_dir:
        return True  # No project dir = can't verify, allow

    try:
        resolved = expand_path(path)
        project_resolved = Path(project_dir).resolve()

        try:
            resolved.relative_to(project_resolved)
            return True
        except ValueError:
            return False
    except Exception as e:
        # Log warning and fail-open (allow operation)
        log_protection("WARN", f"Error checking if path is within project '{path}': {e}")
        return True  # Fail-open


def normalize_path_for_matching(path: str) -> str:
    """Normalize path for pattern matching.

    - Expands ~
    - Resolves to absolute
    - Normalizes separators to /
    - Lowercases on Windows

    Args:
        path: Path to normalize.

    Returns:
        Normalized path string with forward slashes.
    """
    try:
        expanded = str(expand_path(path))
        # Always use forward slashes for pattern matching
        normalized = expanded.replace("\\", "/")

        if sys.platform == "win32":
            normalized = normalized.lower()

        return normalized
    except Exception as e:
        # On error, log warning and return original path (fail-open)
        log_protection("WARN", f"Error normalizing path for matching '{path}': {e}")
        return path


def _match_recursive_glob(path_parts: list[str], pattern_parts: list[str]) -> bool:
    """Internal function to match path parts against pattern parts with ** support.

    Args:
        path_parts: List of path components (e.g., ['src', 'main.py'])
        pattern_parts: List of pattern components (e.g., ['src', '**', '*.py'])

    Returns:
        True if path matches pattern.
    """
    if not pattern_parts:
        return not path_parts

    if not path_parts:
        # Path exhausted - pattern must be empty or all **
        return all(p == "**" for p in pattern_parts)

    if pattern_parts[0] == "**":
        # ** can match zero or more path components
        # Try matching zero components (skip **)
        if _match_recursive_glob(path_parts, pattern_parts[1:]):
            return True
        # Try matching one component and continue with same pattern
        if _match_recursive_glob(path_parts[1:], pattern_parts):
            return True
        return False

    # Regular component - must match
    if fnmatch.fnmatch(path_parts[0], pattern_parts[0]):
        return _match_recursive_glob(path_parts[1:], pattern_parts[1:])

    return False


def match_path_pattern(path: str, pattern: str) -> bool:
    """Match a path against a glob pattern.

    Handles:
    - ~ expansion in both path and pattern
    - ** for recursive matching (proper implementation)
    - * for single-level matching
    - Case-insensitive on Windows

    Args:
        path: The path to check.
        pattern: The glob pattern to match against.

    Returns:
        True if path matches pattern.
    """
    try:
        # Normalize both path and pattern
        norm_path = normalize_path_for_matching(path)

        # Expand pattern
        norm_pattern = str(Path(pattern).expanduser()).replace("\\", "/")
        if sys.platform == "win32":
            norm_pattern = norm_pattern.lower()

        # Try direct match with fnmatch first (for simple patterns)
        if fnmatch.fnmatch(norm_path, norm_pattern):
            return True

        # Try matching filename only (for simple patterns like ".env", "*.pem")
        # Skip this for patterns containing "/" or "**" (directory patterns)
        if "/" not in pattern and "**" not in pattern:
            filename = Path(norm_path).name
            if fnmatch.fnmatch(filename, norm_pattern):
                return True

        # Try matching relative to project
        project_dir = get_project_dir()
        if project_dir:
            project_normalized = project_dir.replace("\\", "/")
            if sys.platform == "win32":
                project_normalized = project_normalized.lower()

            # Use + "/" to ensure exact prefix match
            # (avoid E:\ops matching E:\ops-2)
            if norm_path.startswith(project_normalized + "/") or norm_path == project_normalized:
                rel_path = norm_path[len(project_normalized) :].lstrip("/")

                # Use recursive glob matching for ** patterns
                if "**" in norm_pattern:
                    path_parts = rel_path.split("/") if rel_path else []
                    pattern_parts = norm_pattern.split("/")
                    if _match_recursive_glob(path_parts, pattern_parts):
                        return True
                else:
                    if fnmatch.fnmatch(rel_path, norm_pattern):
                        return True
                    # Also try with leading ./
                    if fnmatch.fnmatch("./" + rel_path, norm_pattern):
                        return True

        return False
    except Exception as e:
        log_protection("WARN", f"Error matching path {path} against {pattern}: {e}")
        return False


def match_zero_access(path: str) -> bool:
    """Check if path matches zeroAccessPaths (no read/write/delete).

    Args:
        path: The path to check.

    Returns:
        True if path is in zeroAccessPaths.
    """
    config = load_protection_config()
    patterns = config.get("zeroAccessPaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


def match_read_only(path: str) -> bool:
    """Check if path matches readOnlyPaths (read OK, no write/delete).

    Args:
        path: The path to check.

    Returns:
        True if path is in readOnlyPaths.
    """
    config = load_protection_config()
    patterns = config.get("readOnlyPaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


def match_no_delete(path: str) -> bool:
    """Check if path matches noDeletePaths (read/write OK, no delete).

    Args:
        path: The path to check.

    Returns:
        True if path is in noDeletePaths.
    """
    config = load_protection_config()
    patterns = config.get("noDeletePaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


def match_allowed_external_path(path: str) -> bool:
    """Check if path matches allowedExternalPaths (permitted outside-project writes).

    These paths bypass ONLY the 'outside project' check.
    All other checks (symlink, zeroAccess, readOnly, selfProtection) still apply.

    Args:
        path: The path to check.

    Returns:
        True if path is in allowedExternalPaths.
    """
    config = load_protection_config()
    patterns = config.get("allowedExternalPaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


# ============================================================
# Logging with Rotation
# ============================================================


def _rotate_log_if_needed(log_file: Path) -> None:
    """Rotate log file if it exceeds MAX_LOG_SIZE_BYTES.

    Rotation strategy:
    - If log exceeds size limit, rename to .log.1 (overwriting any existing .log.1)
    - This keeps exactly one backup for debugging recent issues
    - Silent fail on any error (non-critical operation)

    Args:
        log_file: Path to the log file to check/rotate.
    """
    try:
        if not log_file.exists():
            return

        # Check file size
        file_size = log_file.stat().st_size
        if file_size < MAX_LOG_SIZE_BYTES:
            return

        # Rotate: rename current to .log.1
        backup_file = log_file.with_suffix(".log.1")

        # On Windows, we need to remove the target first if it exists
        if backup_file.exists():
            backup_file.unlink()

        # Rename current log to backup
        log_file.rename(backup_file)

    except Exception:
        # Silent fail - rotation is non-critical
        pass


def log_protection(level: str, message: str) -> None:
    """Log a protection event to guardian.log.

    # PLUGIN MIGRATION: Log location changed from .claude/hooks/protection.log
    #   to .claude/guardian/guardian.log

    Log format:
        TIMESTAMP [LEVEL] [DRY-RUN] MESSAGE

    Features:
    - Automatic rotation when log exceeds MAX_LOG_SIZE_BYTES
    - Keeps one backup file (.log.1) for debugging
    - Silent fail on any error - never breaks hook execution

    Args:
        level: Log level (INFO, WARN, ERROR, BLOCK, ASK, ALLOW)
        message: Message to log.
    """
    project_dir = get_project_dir()
    if not project_dir:
        return

    # PLUGIN MIGRATION: Changed from .claude/hooks/protection.log to .claude/guardian/guardian.log
    log_file = Path(project_dir) / ".claude" / "guardian" / "guardian.log"

    try:
        timestamp = datetime.now().isoformat(timespec="seconds")
        mode = "[DRY-RUN] " if is_dry_run() else ""
        line = f"{timestamp} [{level}] {mode}{message}\n"

        # Ensure directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Rotate if needed (before writing)
        _rotate_log_if_needed(log_file)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Silent fail - don't break hook on log error
        pass


def sanitize_stderr_for_log(stderr: str, max_length: int = 500) -> str:
    """Sanitize stderr output for logging.

    L1 FIX: Remove potentially sensitive path information outside project.

    Args:
        stderr: Raw stderr output.
        max_length: Maximum length to log.

    Returns:
        Sanitized stderr string.
    """
    if not stderr:
        return ""

    # Truncate first
    sanitized = stderr[:max_length]
    if len(stderr) > max_length:
        sanitized += "..."

    # Mask home directory references (best-effort)
    home = os.path.expanduser("~")
    if home != "~":
        sanitized = sanitized.replace(home, "~")

    return sanitized


# ============================================================
# Hook Response Helpers
# ============================================================


def deny_response(reason: str) -> dict[str, Any]:
    """Generate a deny response for PreToolUse hook.

    Args:
        reason: Human-readable reason for denial.

    Returns:
        Hook response dict that will block the operation.
    """
    # Use text prefix instead of emoji for Windows cp949 compatibility
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"[BLOCKED] {reason}",
        }
    }


def ask_response(reason: str) -> dict[str, Any]:
    """Generate an ask response for PreToolUse hook.

    Args:
        reason: Human-readable reason for asking.

    Returns:
        Hook response dict that will prompt user for confirmation.
    """
    # Use text prefix instead of emoji for Windows cp949 compatibility
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"[CONFIRM] {reason}",
        }
    }


def allow_response() -> dict[str, Any]:
    """Generate an allow response for PreToolUse hook.

    Returns:
        Hook response dict that will allow the operation.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


# ============================================================
# Protection Evaluation (Orchestration)
# ============================================================


def evaluate_protection(command: str) -> tuple[str, str]:
    """Evaluate command against all protection rules.

    Applies precedence order:
    1. Block patterns → "deny"
    2. Ask patterns → "ask"
    3. No match → "allow"

    Note: Path-based checks (zeroAccess, readOnly, noDelete)
    are handled separately in individual hooks since they
    require file path extraction.

    Args:
        command: The bash command to evaluate.

    Returns:
        (decision, reason) tuple where decision is
        "deny", "ask", or "allow".
    """
    try:
        # 1. Check block patterns (highest priority)
        blocked, reason = match_block_patterns(command)
        if blocked:
            return "deny", reason

        # 2. Check ask patterns
        needs_ask, reason = match_ask_patterns(command)
        if needs_ask:
            return "ask", reason

        # 3. No protection triggered
        return "allow", ""
    except Exception as e:
        # Fail-open: on any error, allow and log
        log_protection("ERROR", f"Error in evaluate_protection: {e}")
        return "allow", ""


# ============================================================
# Git Integration (Basic)
# ============================================================


def git_is_tracked(path: str) -> bool:
    """Check if file is tracked by git.

    Used to determine if a file can be recovered from git
    history vs needs to be archived before deletion.

    Args:
        path: File path (string, absolute or relative).

    Returns:
        True if file is tracked by git, False otherwise.
        Returns False on any error (fail-open).
    """
    # Check git availability first
    if not is_git_available():
        log_protection("WARN", "Git not available - cannot check tracking")
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            env=_get_git_env(),
            timeout=5,  # Prevent hanging
        )
        return result.returncode == 0
    except FileNotFoundError:
        log_protection("WARN", "Git executable not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log_protection("WARN", f"Git ls-files timeout for {path} - treating as untracked (safer)")
        return False  # Fail-safe: archive will be attempted for safety
    except Exception as e:
        log_protection("WARN", f"Error checking git tracking for {path}: {e}")
        return False


# ============================================================
# Git Integration Functions (Phase 4)
# ============================================================


def _get_git_env() -> dict:
    """Get environment for git subprocess with LC_ALL=C.

    Forces git to output messages in English (POSIX locale),
    ensuring consistent parsing regardless of system locale.
    This prevents issues on Korean/Japanese/German etc. systems
    where git messages would be localized.

    Returns:
        Copy of current environment with LC_ALL=C set.
    """
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    return env


def _is_git_lock_error(stderr: str) -> bool:
    """Check if error is due to git lock file.

    Args:
        stderr: The stderr output from a git command.

    Returns:
        True if the error indicates a git lock file issue.
    """
    lock_indicators = [".git/index.lock", "Unable to create", "locked"]
    return any(indicator in stderr for indicator in lock_indicators)


def sanitize_commit_message(message: str) -> str:
    """Sanitize commit message for git safety.

    Removes only control characters (0x00-0x1F except newline/tab).
    Preserves all printable UTF-8 characters including Korean, Japanese, emojis.
    Enforces Git convention length limit.

    Args:
        message: Raw commit message.

    Returns:
        Sanitized commit message. Returns "[auto-commit]" if empty after sanitization.
    """
    # Remove only control characters (preserve newline, tab, and all printable UTF-8)
    sanitized = "".join(c for c in message if c in ("\n", "\t") or ord(c) >= 32)

    # Handle empty result - provide placeholder
    if not sanitized.strip():
        sanitized = "[auto-commit]"

    # Enforce length limit (Git convention: 72 chars for first line)
    if len(sanitized) > COMMIT_MESSAGE_MAX_LENGTH:
        sanitized = sanitized[: COMMIT_MESSAGE_MAX_LENGTH - 3] + "..."

    return sanitized


def git_has_changes() -> bool:
    """Check if there are uncommitted changes.

    Returns:
        True if there are changes (staged or unstaged), False otherwise.
        Returns False on any error (fail-open).
    """
    # Check git availability first
    if not is_git_available():
        log_protection("WARN", "Git not available - cannot check changes")
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            env=_get_git_env(),
            timeout=10,
        )
        # CRITICAL-1 FIX: Check returncode to distinguish "no changes" from "git error"
        if result.returncode != 0:
            stderr_msg = (result.stderr or "")[:500]
            log_protection("WARN", f"Git status failed (rc={result.returncode}): {stderr_msg}")
            return False
        return bool(result.stdout.strip())
    except FileNotFoundError:
        log_protection("WARN", "Git executable not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log_protection("WARN", "Git status timeout")
        return False
    except Exception as e:
        log_protection("WARN", f"Error checking git changes: {e}")
        return False


def git_has_staged_changes() -> bool:
    """Check if there are staged changes ready to commit.

    Uses `git diff --cached --quiet` which returns:
    - Exit code 0: No staged changes
    - Exit code 1: Has staged changes

    Returns:
        True if there are staged changes, False otherwise.
        Returns False on any error (fail-open).
    """
    if not is_git_available():
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            cwd=project_dir,
            env=_get_git_env(),
            timeout=10,
        )
        # Exit code 1 means there ARE staged changes
        return result.returncode == 1
    except Exception:
        return False


def git_add_all(max_retries: int = 3) -> bool:
    """Stage all changes including untracked files.

    Args:
        max_retries: Maximum retry attempts for lock file or timeout issues.

    Returns:
        True if successful, False otherwise.
    """
    # Check git availability first
    if not is_git_available():
        log_protection("WARN", "Git not available - cannot stage changes")
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=project_dir,
                env=_get_git_env(),
                timeout=30,
            )
            if result.returncode == 0:
                log_protection("INFO", "Git add -A succeeded")
                # Also log stderr if present (could contain warnings)
                if result.stderr:
                    log_protection("INFO", f"Git add -A note: {result.stderr[:500]}")
                return True

            stderr = result.stderr or ""
            if _is_git_lock_error(stderr) and attempt < max_retries - 1:
                log_protection("INFO", f"Git lock detected, retry {attempt + 1}/{max_retries}")
                time.sleep(0.5 * (attempt + 1))
                continue

            log_protection("WARN", f"Git add -A stderr: {stderr[:500]}")
            return False

        except FileNotFoundError:
            log_protection("WARN", "Git executable not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            # M4 FIX: Retry on timeout (system may be under load)
            if attempt < max_retries - 1:
                log_protection("INFO", f"Git add -A timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            log_protection("WARN", "Git add -A timeout after all retries")
            return False
        except Exception as e:
            log_protection("WARN", f"Error staging all changes: {e}")
            return False

    return False


def git_add_tracked(max_retries: int = 3) -> bool:
    """Stage only tracked file changes (no new files).

    Args:
        max_retries: Maximum retry attempts for lock file or timeout issues.

    Returns:
        True if successful, False otherwise.
    """
    # Check git availability first
    if not is_git_available():
        log_protection("WARN", "Git not available - cannot stage changes")
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["git", "add", "-u"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=project_dir,
                env=_get_git_env(),
                timeout=30,
            )
            if result.returncode == 0:
                log_protection("INFO", "Git add -u succeeded")
                # Also log stderr if present (could contain warnings)
                if result.stderr:
                    log_protection("INFO", f"Git add -u note: {result.stderr[:500]}")
                return True

            stderr = result.stderr or ""
            if _is_git_lock_error(stderr) and attempt < max_retries - 1:
                log_protection("INFO", f"Git lock detected, retry {attempt + 1}/{max_retries}")
                time.sleep(0.5 * (attempt + 1))
                continue

            log_protection("WARN", f"Git add -u stderr: {stderr[:500]}")
            return False

        except FileNotFoundError:
            log_protection("WARN", "Git executable not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            # M4 FIX: Retry on timeout (system may be under load)
            if attempt < max_retries - 1:
                log_protection("INFO", f"Git add -u timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            log_protection("WARN", "Git add -u timeout after all retries")
            return False
        except Exception as e:
            log_protection("WARN", f"Error staging tracked changes: {e}")
            return False

    return False


def ensure_git_config() -> bool:
    """Ensure git user.email and user.name are configured.

    Git requires these to be set for commits. If not set, we set
    defaults from protection.json or hardcoded fallbacks.

    MINOR-2 FIX: Now reads identity from protection.json gitIntegration.identity
    MAJOR-4 FIX: Now checks return codes from git config commands
    m4 FIX: Now verifies config values after setting

    Returns:
        True if config is valid or was set successfully, False otherwise.
    """
    if not is_git_available():
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    # MINOR-2 FIX: Get identity from config (with hardcoded fallbacks)
    config = load_protection_config()
    git_integration = config.get("gitIntegration", {})
    identity = git_integration.get("identity", {})
    default_email = identity.get("email", "auto-commit@ops.local")
    default_name = identity.get("name", "Ops Auto-Commit")

    email_ok = False
    name_ok = False

    try:
        # Check if user.email is set
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            env=_get_git_env(),
            timeout=5,
        )
        if result.stdout.strip():
            email_ok = True
        else:
            # MAJOR-4 FIX: Check return code of config set
            set_result = subprocess.run(
                ["git", "config", "--local", "user.email", default_email],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=project_dir,
                env=_get_git_env(),
                timeout=5,
            )
            if set_result.returncode == 0:
                # m4 FIX: Verify the config was actually set
                verify_result = subprocess.run(
                    ["git", "config", "user.email"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=project_dir,
                    env=_get_git_env(),
                    timeout=5,
                )
                if verify_result.stdout.strip() == default_email:
                    log_protection("INFO", f"Set and verified git user.email: {default_email}")
                    email_ok = True
                else:
                    log_protection(
                        "WARN",
                        f"Git user.email set but verification failed. "
                        f"Expected: {default_email}, Got: {verify_result.stdout.strip()}",
                    )
            else:
                log_protection("WARN", f"Failed to set git user.email: {set_result.stderr}")

        # Check if user.name is set
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            env=_get_git_env(),
            timeout=5,
        )
        if result.stdout.strip():
            name_ok = True
        else:
            # MAJOR-4 FIX: Check return code of config set
            set_result = subprocess.run(
                ["git", "config", "--local", "user.name", default_name],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=project_dir,
                env=_get_git_env(),
                timeout=5,
            )
            if set_result.returncode == 0:
                # m4 FIX: Verify the config was actually set
                verify_result = subprocess.run(
                    ["git", "config", "user.name"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=project_dir,
                    env=_get_git_env(),
                    timeout=5,
                )
                if verify_result.stdout.strip() == default_name:
                    log_protection("INFO", f"Set and verified git user.name: {default_name}")
                    name_ok = True
                else:
                    log_protection(
                        "WARN",
                        f"Git user.name set but verification failed. "
                        f"Expected: {default_name}, Got: {verify_result.stdout.strip()}",
                    )
            else:
                log_protection("WARN", f"Failed to set git user.name: {set_result.stderr}")

        # Return True only if both are OK (fail-open: let git commit try anyway)
        if not email_ok or not name_ok:
            log_protection("WARN", f"Git config incomplete: email_ok={email_ok}, name_ok={name_ok}")
        return True  # Fail-open: let git commit try anyway
    except Exception as e:
        log_protection("WARN", f"Could not verify/set git config: {e}")
        return True  # Fail-open: let git commit try anyway


def git_commit(message: str, max_retries: int = 3, no_verify: bool = False) -> bool:
    """Create a git commit with the given message.

    Args:
        message: Commit message (will be sanitized).
        max_retries: Maximum retry attempts for lock file or timeout issues.
        no_verify: Skip pre-commit hooks (--no-verify flag).

    Returns:
        True if successful, False otherwise (including when no staged changes).
    """
    # Check git availability first
    if not is_git_available():
        log_protection("WARN", "Git not available - cannot commit")
        return False

    # Ensure git config is set (user.email, user.name)
    ensure_git_config()

    project_dir = get_project_dir()
    if not project_dir:
        return False

    # Sanitize commit message
    message = sanitize_commit_message(message)

    for attempt in range(max_retries):
        try:
            cmd = ["git", "commit", "-m", message]
            if no_verify:
                cmd.append("--no-verify")
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                cwd=project_dir,
                env=_get_git_env(),
                timeout=30,
            )
            if result.returncode == 0:
                log_protection("INFO", "Git commit succeeded")
                # Also log stderr if present (could contain warnings)
                if result.stderr:
                    log_protection("INFO", f"Git commit note: {result.stderr[:500]}")
                return True

            # BUG-1 FIX: Check for "nothing to commit" case before treating as error
            # BUG-2 FIX: Also check "nothing added to commit" (untracked files only case)
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            combined_output = stdout + stderr
            if (
                "nothing to commit" in combined_output
                or "nothing added to commit" in combined_output
            ):
                log_protection("INFO", "Nothing to commit (no staged changes)")
                return True  # This is a valid success case, not an error

            if _is_git_lock_error(stderr) and attempt < max_retries - 1:
                log_protection("INFO", f"Git lock detected, retry {attempt + 1}/{max_retries}")
                time.sleep(0.5 * (attempt + 1))
                continue

            log_protection("WARN", f"Git commit stderr: {stderr[:500]}")
            return False

        except FileNotFoundError:
            log_protection("WARN", "Git executable not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            # M4 FIX: Retry on timeout (system may be under load)
            if attempt < max_retries - 1:
                log_protection("INFO", f"Git commit timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            log_protection("WARN", "Git commit timeout after all retries")
            return False
        except Exception as e:
            log_protection("WARN", f"Error creating commit: {e}")
            return False

    return False


def git_get_last_commit_hash() -> str:
    """Get the hash of the last commit.

    Works correctly in both normal and detached HEAD states.

    Returns:
        Short commit hash (7 chars) or empty string on error.
        Returns empty string for repos with no commits yet.
    """
    # Check git availability first
    if not is_git_available():
        return ""

    project_dir = get_project_dir()
    if not project_dir:
        return ""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            env=_get_git_env(),
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()

        # MINOR-1 FIX: Detect empty repo explicitly
        stderr = result.stderr or ""
        if "does not have any commits" in stderr or "no commits yet" in stderr:
            log_protection("INFO", "Repository has no commits yet")
        else:
            log_protection("WARN", f"Git rev-parse failed: {stderr[:200]}")
        return ""
    except FileNotFoundError:
        log_protection("WARN", "Git executable not found in PATH")
        return ""
    except subprocess.TimeoutExpired:
        log_protection("WARN", "Git rev-parse timeout")
        return ""
    except Exception as e:
        log_protection("WARN", f"Error getting commit hash: {e}")
        return ""


def is_detached_head() -> bool:
    """Check if repository is in detached HEAD state.

    In detached HEAD state, commits are not on any branch and may be
    garbage collected. Auto-commit should skip in this state to avoid
    creating orphaned commits.

    Returns:
        True if in detached HEAD state (no branch checked out).
        False if on a branch or on any error (fail-open for non-critical check).
    """
    if not is_git_available():
        return False

    project_dir = get_project_dir()
    if not project_dir:
        return False

    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_dir,
            env=_get_git_env(),
            timeout=5,
        )
        # Exit 0 = on a branch (symbolic-ref exists)
        # Exit 1 = detached HEAD (no symbolic-ref)
        return result.returncode != 0
    except FileNotFoundError:
        log_protection("WARN", "Git executable not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log_protection("WARN", "Git symbolic-ref timeout")
        return False
    except Exception as e:
        log_protection("WARN", f"Error checking detached HEAD: {e}")
        return False


def is_rebase_or_merge_in_progress() -> bool:
    """Check if a rebase or merge is in progress.

    During rebase/merge, auto-commit could corrupt the git state.

    Returns:
        True if rebase, merge, or cherry-pick is in progress.
    """
    project_dir = get_project_dir()
    if not project_dir:
        return False

    git_dir = Path(project_dir) / ".git"

    state_indicators = [
        git_dir / "rebase-merge",
        git_dir / "rebase-apply",
        git_dir / "MERGE_HEAD",
        git_dir / "CHERRY_PICK_HEAD",
        git_dir / "BISECT_LOG",
    ]

    for indicator in state_indicators:
        if indicator.exists():
            log_protection("INFO", f"Git operation in progress: {indicator.name}")
            return True

    return False


# ============================================================
# Path Protection Hook Runner (Shared Edit/Write Logic)
# ============================================================


def truncate_path(path: str, max_length: int = MAX_PATH_PREVIEW_LENGTH) -> str:
    """Truncate path for display in logs.

    Shows the end of the path (most relevant part) with ... prefix.

    Args:
        path: Path to truncate.
        max_length: Maximum length (default: MAX_PATH_PREVIEW_LENGTH).

    Returns:
        Truncated path string.
    """
    if len(path) <= max_length:
        return path
    # Show last (max_length - 3) characters with ... prefix
    return f"...{path[-(max_length - 3) :]}"


def truncate_command(command: str, max_length: int = MAX_COMMAND_PREVIEW_LENGTH) -> str:
    """Truncate command for display in logs.

    Shows the start of the command (most relevant part) with ... suffix.

    Args:
        command: Command to truncate.
        max_length: Maximum length (default: MAX_COMMAND_PREVIEW_LENGTH).

    Returns:
        Truncated command string.
    """
    if len(command) <= max_length:
        return command
    # Show first (max_length - 3) characters with ... suffix
    return f"{command[: max_length - 3]}..."


def is_self_protection_path(path: str) -> bool:
    """Check if path is a self-protection path (protection system itself).

    These paths are ALWAYS protected regardless of configuration.

    # PLUGIN MIGRATION: Now uses dynamic config path detection in addition
    # to static SELF_PROTECTION_PATHS. In plugin context, only the config
    # file needs protection (scripts are in read-only cache).

    Args:
        path: Path to check.

    Returns:
        True if path should be protected as part of protection system.
    """
    # Normalize path for comparison
    norm_path = normalize_path_for_matching(path)

    project_dir = get_project_dir()
    if not project_dir:
        return False

    project_normalized = project_dir.replace("\\", "/")
    if sys.platform == "win32":
        project_normalized = project_normalized.lower()

    # Check static self-protection paths
    for protected in SELF_PROTECTION_PATHS:
        protected_norm = protected.replace("\\", "/")
        if sys.platform == "win32":
            protected_norm = protected_norm.lower()

        # Check exact match against full protected path
        # Note: No endswith check - that would allow bypass via external project paths
        full_protected = f"{project_normalized}/{protected_norm}"
        if norm_path == full_protected:
            return True

    # PLUGIN MIGRATION: Also check dynamic config path (the actually-loaded config)
    active_config = get_active_config_path()
    if active_config:
        active_norm = normalize_path_for_matching(active_config)
        if norm_path == active_norm:
            return True

    return False


def resolve_tool_path(file_path: str) -> Path:
    """Resolve file path from tool input, handling relative paths.

    Args:
        file_path: The file path from tool input.

    Returns:
        Resolved absolute Path object.
    """
    path = Path(file_path)

    if not path.is_absolute():
        project_dir = get_project_dir()
        if project_dir:
            path = Path(project_dir) / path

    # Resolve symlinks to prevent bypass
    try:
        return path.resolve()
    except OSError as e:
        log_protection("WARN", f"Could not resolve path {file_path}: {e}")
        return path


def run_path_protection_hook(tool_name: str) -> None:
    """Run protection checks for Edit/Write tools.

    This is the main entry point for path-based protection hooks.
    It implements fail-close semantics for security.

    Args:
        tool_name: The tool name to check for ("Edit" or "Write").
    """
    import json as _json  # Local import to avoid circular dependency issues

    # Parse input - FAIL-CLOSE on invalid JSON
    try:
        input_data = _json.load(sys.stdin)
    except _json.JSONDecodeError as e:
        # SECURITY FIX: Fail-close on malformed input
        log_protection("ERROR", f"Malformed JSON input: {e}")
        print(_json.dumps(deny_response("Invalid hook input (malformed JSON)")))
        sys.exit(0)

    # Only process specified tool (case-insensitive)
    actual_tool = input_data.get("tool_name", "")
    if not isinstance(actual_tool, str) or actual_tool.lower() != tool_name.lower():
        # Not our target tool - exit silently (Claude Code treats no response as allow)
        sys.exit(0)

    # Validate tool_input is a dict
    tool_input = input_data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        log_protection("WARN", f"Invalid tool_input type: {type(tool_input).__name__}")
        print(_json.dumps(deny_response("Invalid tool input structure")))
        sys.exit(0)

    # Extract file path
    file_path = tool_input.get("file_path", "")

    # Validate file_path
    if not file_path:
        log_protection("WARN", f"{tool_name} called without file_path")
        # Allow - some tools might legitimately have no path
        # Note: No response = allow in Claude Code hook protocol
        print(_json.dumps(allow_response()))
        sys.exit(0)

    if not isinstance(file_path, str):
        log_protection("WARN", f"Invalid file_path type: {type(file_path).__name__}")
        print(_json.dumps(deny_response("Invalid file path type")))
        sys.exit(0)

    # Check for null bytes (path injection attack)
    if "\x00" in file_path:
        log_protection("BLOCK", f"Null byte in path rejected: {truncate_path(file_path)}")
        print(_json.dumps(deny_response("Invalid file path (contains null byte)")))
        sys.exit(0)

    # Resolve to absolute path
    resolved = resolve_tool_path(file_path)
    path_str = str(resolved)
    path_preview = truncate_path(file_path)

    log_protection("INFO", f"{tool_name} check: {path_preview}")

    # ========== Check: Symlink Escape ==========
    if is_symlink_escape(file_path):
        log_protection("BLOCK", f"Symlink escape detected ({tool_name}): {path_preview}")
        if is_dry_run():
            log_protection("DRY-RUN", f"Would DENY {tool_name} (symlink escape)")
            sys.exit(0)
        print(_json.dumps(deny_response(f"Symlink points outside project: {Path(file_path).name}")))
        sys.exit(0)

    # ========== Check: Path Within Project ==========
    if not is_path_within_project(path_str):
        # Check if path is in allowedExternalPaths before blocking
        if match_allowed_external_path(path_str):
            log_protection(
                "ALLOW",
                f"Allowed external path ({tool_name}): {path_preview}"
            )
            # Fall through to remaining checks (self-protection, zeroAccess, readOnly)
        else:
            log_protection("BLOCK", f"Path outside project ({tool_name}): {path_preview}")
            if is_dry_run():
                log_protection("DRY-RUN", f"Would DENY {tool_name} (outside project)")
                sys.exit(0)
            print(_json.dumps(deny_response("Path is outside project directory")))
            sys.exit(0)

    # ========== Check: Self Protection ==========
    if is_self_protection_path(path_str):
        log_protection("BLOCK", f"Self-protection path ({tool_name}): {path_preview}")
        if is_dry_run():
            log_protection("DRY-RUN", f"Would DENY {tool_name} (self-protection)")
            sys.exit(0)
        print(_json.dumps(deny_response(f"Protected system file: {Path(file_path).name}")))
        sys.exit(0)

    # ========== Check: Zero Access ==========
    if match_zero_access(path_str):
        log_protection("BLOCK", f"Zero access path ({tool_name}): {path_preview}")
        if is_dry_run():
            log_protection("DRY-RUN", f"Would DENY {tool_name}")
            sys.exit(0)
        print(_json.dumps(deny_response(f"Protected file (no access): {Path(file_path).name}")))
        sys.exit(0)

    # ========== Check: Read Only ==========
    if match_read_only(path_str):
        log_protection("BLOCK", f"Read-only path ({tool_name}): {path_preview}")
        if is_dry_run():
            log_protection("DRY-RUN", f"Would DENY {tool_name}")
            sys.exit(0)
        print(_json.dumps(deny_response(f"Read-only file: {Path(file_path).name}")))
        sys.exit(0)

    # ========== Allow ==========
    log_protection("ALLOW", f"{tool_name}: {path_preview}")
    sys.exit(0)


# ============================================================
# Module Self-Test (when run directly)
# ============================================================


if __name__ == "__main__":
    print("_protection_utils.py - Module loaded successfully")
    print(f"Project dir: {get_project_dir()}")
    print(f"Plugin root: {_get_plugin_root()}")
    print(f"Dry-run mode: {is_dry_run()}")
    print(f"Config loaded: {bool(load_protection_config())}")
    print(f"Active config path: {get_active_config_path()}")
    print(f"Self-protection paths: {SELF_PROTECTION_PATHS}")
    print(f"Regex timeout available: {_HAS_REGEX_TIMEOUT}")
