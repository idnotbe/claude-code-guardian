#!/usr/bin/env python3
"""Guardian utilities for Claude Code Guardian Plugin.

This module provides shared utilities for all guardian hooks:
- Configuration loading from config.json
- Pattern matching (regex for bash commands)
- Path matching (glob for file paths)
- Dry-run mode support
- Logging

# PLUGIN MIGRATION: Config resolution chain (3-step):
#   1. $CLAUDE_PROJECT_DIR/.claude/guardian/config.json (user custom)
#   2. $CLAUDE_PLUGIN_ROOT/assets/guardian.default.json (plugin default)
#   3. Hardcoded _FALLBACK_CONFIG (emergency fallback)
#
# PLUGIN MIGRATION: Log location changed to .claude/guardian/guardian.log
# PLUGIN MIGRATION: Circuit breaker changed to .claude/guardian/.circuit_open
# PLUGIN MIGRATION: Self-guarding reduced to config file only (dynamic path)

Usage:
    from _guardian_utils import (
        load_guardian_config,
        match_block_patterns,
        match_zero_access,
        is_dry_run,
        log_guardian,
        evaluate_rules,  # Orchestration function
        git_is_tracked,       # Git integration
    )

Note on log_guardian():
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
# ReDoS Defense: Optional regex module for timeout support
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
"""Maximum command length in bytes before blocking.
Commands exceeding this are denied (fail-closed) for security."""

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
    """Execute function with timeout guard (Phase 5).

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
    and bash_guardian.py.

    Args:
        prefix: The prefix to validate.
        default: Default prefix if input is empty.

    Returns:
        Validated prefix, truncated to COMMIT_PREFIX_MAX_LENGTH if needed.
    """
    if not prefix:
        return default

    if len(prefix) > COMMIT_PREFIX_MAX_LENGTH:
        log_guardian(
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
        log_guardian("WARN", f"Circuit breaker OPEN: {reason}")
    except Exception as e:
        log_guardian("ERROR", f"Failed to set circuit open: {e}")


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
            log_guardian(
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
        rm_cmd = "del" if sys.platform == "win32" else "rm"
        log_guardian(
            "ERROR",
            f"Cannot read circuit breaker (permission denied): {e}\n"
            f"  Recovery: Check file permissions on {circuit_file}\n"
            f'  Or delete the file manually: {rm_cmd} "{circuit_file}"',
        )
        return True, f"Circuit breaker permission error - check {circuit_file}"
    except OSError as e:
        # M1 FIX: File system errors with recovery guidance
        rm_cmd = "del" if sys.platform == "win32" else "rm"
        log_guardian(
            "ERROR",
            f"Cannot read circuit breaker (filesystem error): {e}\n"
            f'  Recovery: Delete corrupted file: {rm_cmd} "{circuit_file}"',
        )
        return True, f"Circuit breaker filesystem error - delete {circuit_file}"
    except Exception as e:
        # SECURITY FIX: Fail-CLOSED - treat read errors as circuit open
        # This prevents guardian bypass when circuit file is corrupted/inaccessible
        rm_cmd = "del" if sys.platform == "win32" else "rm"
        log_guardian(
            "ERROR",
            f"Cannot read circuit breaker (unexpected): {e}\n"
            f'  Recovery: Delete file manually: {rm_cmd} "{circuit_file}"',
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
            log_guardian("INFO", "Circuit breaker CLOSED")
    except Exception as e:
        log_guardian("WARN", f"Failed to clear circuit: {e}")


# PLUGIN MIGRATION: Self-guarding reduced to config file only.
# In plugin context, scripts live in read-only plugin cache dir.
# Only the user's config file needs guarding from agent modification.
SELF_GUARDIAN_PATHS = (
    ".claude/guardian/config.json",
)
"""Paths that are always guarded from Edit/Write, even if not in config.
This is a security measure to prevent guardian bypass.
PLUGIN MIGRATION: Reduced from 6 script paths to config-only."""

# Hardcoded fallback config for when config.json is missing/corrupted
# This ensures critical paths are ALWAYS protected even if config fails to load
_FALLBACK_CONFIG = {
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
            {"pattern": r"git\s+push\s[^;|&\n]*(?:--force(?!-with-lease)|-f\b)", "reason": "[FALLBACK] Force push"},
            {"pattern": r"(?:py|python[23]?|python\d[\d.]*)\s[^|&\n]*(?:os\.remove|os\.unlink|shutil\.rmtree|os\.rmdir|pathlib\.Path.*\.unlink)", "reason": "[FALLBACK] Interpreter deletion"},
            {"pattern": r"(?:node|deno|bun)\s[^|&\n]*(?:unlinkSync|rmSync|rmdirSync|fs\.unlink|fs\.rm\b|promises\.unlink)", "reason": "[FALLBACK] Interpreter deletion"},
            {"pattern": r"(?:perl|ruby)\s[^|&\n]*(?:\bunlink\b|File\.delete|FileUtils\.rm)", "reason": "[FALLBACK] Interpreter deletion"},
        ],
        "ask": [
            {"pattern": r"git\s+push\s[^;|&\n]*--force-with-lease", "reason": "[FALLBACK] Force push with lease"},
            {"pattern": r"git\s+reset\s+--hard", "reason": "[FALLBACK] Hard reset"},
        ],
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
        ".claude/guardian/config.json",
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

# PLUGIN MIGRATION: Track which config file was actually loaded (for dynamic self-guarding)
_active_config_path: str | None = None
"""Path to the config file that was actually loaded. Used for dynamic self-guarding."""


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
    # Note: Cannot call log_guardian() here - would cause infinite recursion
    # because log_guardian() calls get_project_dir()
    if not os.path.isdir(project_dir):
        return ""

    # Validate it's a git repo (has .git)
    # Note: No logging here to avoid recursion - git operations will fail gracefully
    # git_dir = os.path.join(project_dir, ".git")
    # Non-git projects should still work for guardian purposes

    return project_dir


def _get_plugin_root() -> str:
    """Get the plugin root directory from environment variable.

    # PLUGIN MIGRATION: New function for plugin-aware config resolution.

    Returns:
        Plugin root directory path, or empty string if not set.
    """
    return os.environ.get("CLAUDE_PLUGIN_ROOT", "")


def load_guardian_config() -> dict[str, Any]:
    """Load config.json with caching and fallback.

    # PLUGIN MIGRATION: Config resolution chain (3-step):
    #   1. $CLAUDE_PROJECT_DIR/.claude/guardian/config.json (user custom)
    #   2. $CLAUDE_PLUGIN_ROOT/assets/guardian.default.json (plugin default)
    #   3. Hardcoded _FALLBACK_CONFIG (emergency fallback)

    The config is cached for the lifetime of the process.
    Since hooks run as separate processes, this is safe.

    If config cannot be loaded, returns _FALLBACK_CONFIG to ensure
    critical paths (.git, .claude, _archive) are always protected.

    Returns:
        Configuration dict, or fallback config on error.
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
        config_path = Path(project_dir) / ".claude" / "guardian" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    _config_cache = json.load(f)
                _using_fallback_config = False
                _active_config_path = str(config_path)
                log_guardian("INFO", f"Loaded config from {config_path}")
                # Validate config structure (warn but don't block for backwards compatibility)
                _validation_errors = validate_guardian_config(_config_cache)
                if _validation_errors:
                    for _verr in _validation_errors:
                        log_guardian("WARN", f"Config validation: {_verr}")
                return _config_cache
            except json.JSONDecodeError as e:
                log_guardian(
                    "ERROR",
                    f"[FALLBACK] Invalid JSON in {config_path}: {e}\n"
                    "  Using fallback. Fix JSON syntax to restore full guardian config.",
                )
                # Fall through to next resolution step
            except OSError as e:
                log_guardian(
                    "ERROR",
                    f"[FALLBACK] Failed to read {config_path}: {e}\n"
                    "  Check file permissions.",
                )
                # Fall through to next resolution step
            except Exception as e:
                log_guardian(
                    "ERROR",
                    f"[FALLBACK] Unexpected error loading {config_path}: {e}",
                )
                # Fall through to next resolution step

    # PLUGIN MIGRATION: Step 2 -- Plugin default config
    plugin_root = _get_plugin_root()
    if plugin_root:
        default_config_path = Path(plugin_root) / "assets" / "guardian.default.json"
        if default_config_path.exists():
            try:
                with open(default_config_path, encoding="utf-8") as f:
                    _config_cache = json.load(f)
                _using_fallback_config = False
                _active_config_path = str(default_config_path)
                log_guardian(
                    "INFO",
                    f"Using plugin default config from {default_config_path}\n"
                    "  Run /guardian:init to create a custom config for this project.",
                )
                # Validate config structure (warn but don't block)
                _validation_errors = validate_guardian_config(_config_cache)
                if _validation_errors:
                    for _verr in _validation_errors:
                        log_guardian("WARN", f"Config validation: {_verr}")
                return _config_cache
            except Exception as e:
                log_guardian(
                    "ERROR",
                    f"[FALLBACK] Failed to load plugin default config: {e}",
                )
                # Fall through to hardcoded fallback

    # PLUGIN MIGRATION: Step 3 -- Hardcoded fallback
    if not project_dir:
        log_guardian(
            "WARN",
            "[FALLBACK] CLAUDE_PROJECT_DIR not set - using minimal fallback config.\n"
            "  Custom guardian rules from config.json are NOT active.",
        )
    else:
        log_guardian(
            "WARN",
            "[FALLBACK] No config.json found in any location.\n"
            "  Searched: .claude/guardian/config.json"
            + (f", plugin default" if plugin_root else "")
            + "\n  Using minimal fallback config. Run /guardian:init to set up.",
        )

    _config_cache = _FALLBACK_CONFIG
    _using_fallback_config = True
    _active_config_path = None
    return _config_cache


def is_using_fallback_config() -> bool:
    """Check if fallback config is in use (M2 FIX).

    Call this after load_guardian_config() to determine if custom
    guardian rules are active or if minimal fallback is being used.

    Returns:
        True if fallback config is active (custom rules NOT loaded).
        False if config.json was loaded successfully.
    """
    # Ensure config is loaded first
    if _config_cache is None:
        load_guardian_config()
    return _using_fallback_config


def get_active_config_path() -> str | None:
    """Get the path to the config file that was actually loaded.

    # PLUGIN MIGRATION: New function for dynamic self-guarding.

    Returns:
        Absolute path string to the loaded config, or None if using hardcoded fallback.
    """
    if _config_cache is None:
        load_guardian_config()
    return _active_config_path


def get_hook_behavior() -> dict[str, Any]:
    """Get hookBehavior section from config.

    Returns:
        hookBehavior dict with defaults applied.
    """
    config = load_guardian_config()
    defaults = {
        "onTimeout": "deny",
        "onError": "deny",
        "timeoutSeconds": 10,
    }
    behavior = config.get("hookBehavior", {})
    return {**defaults, **behavior}


def make_hook_behavior_response(action: str, reason: str) -> dict[str, Any] | None:
    """Create a hook response based on a hookBehavior action string.

    Used by hook error/timeout handlers to respect the configured
    hookBehavior.onError and hookBehavior.onTimeout values.

    Args:
        action: One of "deny", "ask", or "allow".
        reason: Human-readable reason for the action.

    Returns:
        Hook response dict for "deny" or "ask", None for "allow".
        Falls back to deny for unrecognized actions (fail-closed).
    """
    if action == "allow":
        return None  # No output = allow in Claude Code hook protocol
    elif action == "ask":
        return ask_response(reason)
    else:
        # Default to deny for unrecognized values (fail-closed)
        return deny_response(reason)


def validate_guardian_config(config: dict) -> list[str]:
    """Validate guardian configuration (Phase 5).

    Performs structural and semantic validation of the guardian config:
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

    # Check path patterns are strings/lists (excludes allowedExternalPaths which has custom validation)
    path_sections = ["zeroAccessPaths", "readOnlyPaths", "noDeletePaths"]
    for section in path_sections:
        paths = config.get(section, [])
        if not isinstance(paths, list):
            errors.append(f"{section} must be a list")
            continue
        for i, path in enumerate(paths):
            if not isinstance(path, str):
                errors.append(f"{section}[{i}] must be a string, got {type(path).__name__}")

    # Check allowedExternalPaths entries (supports string or object with path/mode)
    allowed_ext = config.get("allowedExternalPaths", [])
    if isinstance(allowed_ext, list):
        for i, entry in enumerate(allowed_ext):
            if isinstance(entry, dict):
                if "path" not in entry:
                    errors.append(f"allowedExternalPaths[{i}] object missing 'path' field")
                mode = entry.get("mode", "read")
                if mode not in ("read", "readwrite"):
                    errors.append(f"allowedExternalPaths[{i}] invalid mode: {mode} (must be 'read' or 'readwrite')")
            elif not isinstance(entry, str):
                errors.append(f"allowedExternalPaths[{i}] must be string or object, got {type(entry).__name__}")
    else:
        errors.append("allowedExternalPaths must be a list")

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
# Safe Regex with Timeout Defense (ReDoS Prevention)
# ============================================================


def safe_regex_search(
    pattern: str,
    text: str,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SECONDS,
) -> "re.Match | None":
    """Regex search with timeout defense against ReDoS.

    Uses the following strategy (in order of preference):
    1. `regex` module with timeout (if installed) - RECOMMENDED
    2. Standard `re` without timeout (logs warning on first use)

    Note: Python's standard `re` module does NOT support timeout.
    Install the `regex` package for ReDoS defense: pip install regex

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
                    log_guardian(
                        "WARN",
                        f"Regex timeout ({timeout}s) for pattern: {pattern[:50]}...",
                    )
                    return None  # Fail-closed: treat timeout as no match
                # Re-raise if it's not a timeout error
                raise

        # Strategy 2: Fallback - no timeout defense (standard re module)
        if not getattr(safe_regex_search, "_warned_no_timeout", False):
            log_guardian(
                "WARN",
                "No regex timeout defense available. "
                "Install 'regex' package for ReDoS defense: pip install regex",
            )
            safe_regex_search._warned_no_timeout = True

        return re.search(pattern, text, flags)

    except re.error as e:
        log_guardian("WARN", f"Invalid regex pattern '{pattern[:50]}...': {e}")
        return None
    except Exception as e:
        log_guardian("WARN", f"Unexpected regex error: {e}")
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
        log_guardian(
            "WARN",
            f"Command exceeds size limit ({len(command)} > {MAX_COMMAND_LENGTH} bytes), "
            "blocking (fail-close for security)",
        )
        return True, f"Command too large ({len(command)} bytes) - blocked for security"

    config = load_guardian_config()
    pattern_configs = config.get("bashToolPatterns", {}).get("block", [])

    for pattern_config in pattern_configs:
        pattern = pattern_config.get("pattern", "")
        reason = pattern_config.get("reason", "Blocked by pattern")
        # Use safe_regex_search with timeout defense
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
        log_guardian(
            "WARN",
            f"Command exceeds size limit ({len(command)} > {MAX_COMMAND_LENGTH} bytes), "
            "requesting confirmation (fail-close for security)",
        )
        return True, f"Command too large ({len(command)} bytes) - requires confirmation"

    config = load_guardian_config()
    pattern_configs = config.get("bashToolPatterns", {}).get("ask", [])

    for pattern_config in pattern_configs:
        pattern = pattern_config.get("pattern", "")
        reason = pattern_config.get("reason", "Requires confirmation")
        # Use safe_regex_search with timeout defense
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
        # Get absolute path - resolve relative paths against project dir, not CWD
        if not os.path.isabs(expanded):
            project_dir = get_project_dir()
            if project_dir:
                expanded = os.path.join(project_dir, expanded)
        absolute = os.path.abspath(expanded)
        # Normalize separators
        normalized = os.path.normpath(absolute)
        # Case-insensitive on Windows and macOS (HFS+ is case-insensitive)
        if sys.platform != "linux":
            normalized = normalized.lower()
        return normalized
    except Exception as e:
        # On any error, log warning and return original path (fail-open)
        log_guardian("WARN", f"Error normalizing path '{path}': {e}")
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
        log_guardian("WARN", f"Error expanding path '{path}': {e}")
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
            log_guardian(
                "WARN",
                f"Symlink escape detected: {path} -> {resolved} (outside {project_resolved})",
            )
            return True
    except Exception as e:
        log_guardian("WARN", f"Error checking symlink escape for {path}: {e}")
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
        log_guardian("WARN", f"Error checking if path is within project '{path}': {e}")
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

        # Case-insensitive on Windows and macOS (HFS+ is case-insensitive)
        if sys.platform != "linux":
            normalized = normalized.lower()

        return normalized
    except Exception as e:
        # On error, log warning and return original path (fail-open)
        log_guardian("WARN", f"Error normalizing path for matching '{path}': {e}")
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
        # Case-insensitive on Windows and macOS (HFS+ is case-insensitive)
        if sys.platform != "linux":
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
            # Case-insensitive on Windows and macOS (HFS+ is case-insensitive)
            if sys.platform != "linux":
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
        log_guardian("WARN", f"Error matching path {path} against {pattern}: {e}")
        return False


def match_zero_access(path: str) -> bool:
    """Check if path matches zeroAccessPaths (no read/write/delete).

    Args:
        path: The path to check.

    Returns:
        True if path is in zeroAccessPaths.
    """
    config = load_guardian_config()
    patterns = config.get("zeroAccessPaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


def match_read_only(path: str) -> bool:
    """Check if path matches readOnlyPaths (read OK, no write/delete).

    Args:
        path: The path to check.

    Returns:
        True if path is in readOnlyPaths.
    """
    config = load_guardian_config()
    patterns = config.get("readOnlyPaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


def match_no_delete(path: str) -> bool:
    """Check if path matches noDeletePaths (read/write OK, no delete).

    Args:
        path: The path to check.

    Returns:
        True if path is in noDeletePaths.
    """
    config = load_guardian_config()
    patterns = config.get("noDeletePaths", [])
    return any(match_path_pattern(path, p) for p in patterns)


def match_allowed_external_path(path: str) -> tuple:
    """Check if path matches allowedExternalPaths with mode support.

    Supports two formats:
    - String: treated as read-only (mode="read")
    - Object {"path": "...", "mode": "read"|"readwrite"}: explicit mode

    These paths bypass ONLY the 'outside project' check.
    All other checks (symlink, zeroAccess, readOnly, selfGuardian) still apply.

    First-match-wins: patterns are evaluated in config order.

    Args:
        path: The path to check.

    Returns:
        Tuple of (matched, mode). mode is "read", "readwrite", or "" if not matched.
    """
    config = load_guardian_config()
    patterns = config.get("allowedExternalPaths", [])
    for entry in patterns:
        if isinstance(entry, dict):
            pattern = entry.get("path", "")
            mode = entry.get("mode", "read")
            if mode not in ("read", "readwrite"):
                mode = "read"  # fail-safe: invalid mode defaults to read-only
        else:
            pattern = str(entry)
            mode = "read"
        if pattern and match_path_pattern(path, pattern):
            return (True, mode)
    return (False, "")


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


def log_guardian(level: str, message: str) -> None:
    """Log a guardian event to guardian.log.

    # PLUGIN MIGRATION: Log location changed from .claude/hooks/guardian.log
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

    # PLUGIN MIGRATION: Changed from .claude/hooks/ to .claude/guardian/guardian.log
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
# Rule Evaluation (Orchestration)
# ============================================================


def evaluate_rules(command: str) -> tuple[str, str]:
    """Evaluate command against all configured rules.

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

        # 3. No rule triggered
        return "allow", ""
    except Exception as e:
        # Fail-closed: on any error, deny to prevent bypass
        log_guardian("ERROR", f"Error in evaluate_rules: {e}")
        return "deny", "Guardian internal error (fail-closed)"


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
        log_guardian("WARN", "Git not available - cannot check tracking")
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
        log_guardian("WARN", "Git executable not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log_guardian("WARN", f"Git ls-files timeout for {path} - treating as untracked (safer)")
        return False  # Fail-safe: archive will be attempted for safety
    except Exception as e:
        log_guardian("WARN", f"Error checking git tracking for {path}: {e}")
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
        log_guardian("WARN", "Git not available - cannot check changes")
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
            log_guardian("WARN", f"Git status failed (rc={result.returncode}): {stderr_msg}")
            return False
        return bool(result.stdout.strip())
    except FileNotFoundError:
        log_guardian("WARN", "Git executable not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log_guardian("WARN", "Git status timeout")
        return False
    except Exception as e:
        log_guardian("WARN", f"Error checking git changes: {e}")
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
        log_guardian("WARN", "Git not available - cannot stage changes")
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
                log_guardian("INFO", "Git add -A succeeded")
                # Also log stderr if present (could contain warnings)
                if result.stderr:
                    log_guardian("INFO", f"Git add -A note: {result.stderr[:500]}")
                return True

            stderr = result.stderr or ""
            if _is_git_lock_error(stderr) and attempt < max_retries - 1:
                log_guardian("INFO", f"Git lock detected, retry {attempt + 1}/{max_retries}")
                time.sleep(0.5 * (attempt + 1))
                continue

            log_guardian("WARN", f"Git add -A stderr: {stderr[:500]}")
            return False

        except FileNotFoundError:
            log_guardian("WARN", "Git executable not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            # M4 FIX: Retry on timeout (system may be under load)
            if attempt < max_retries - 1:
                log_guardian("INFO", f"Git add -A timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            log_guardian("WARN", "Git add -A timeout after all retries")
            return False
        except Exception as e:
            log_guardian("WARN", f"Error staging all changes: {e}")
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
        log_guardian("WARN", "Git not available - cannot stage changes")
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
                log_guardian("INFO", "Git add -u succeeded")
                # Also log stderr if present (could contain warnings)
                if result.stderr:
                    log_guardian("INFO", f"Git add -u note: {result.stderr[:500]}")
                return True

            stderr = result.stderr or ""
            if _is_git_lock_error(stderr) and attempt < max_retries - 1:
                log_guardian("INFO", f"Git lock detected, retry {attempt + 1}/{max_retries}")
                time.sleep(0.5 * (attempt + 1))
                continue

            log_guardian("WARN", f"Git add -u stderr: {stderr[:500]}")
            return False

        except FileNotFoundError:
            log_guardian("WARN", "Git executable not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            # M4 FIX: Retry on timeout (system may be under load)
            if attempt < max_retries - 1:
                log_guardian("INFO", f"Git add -u timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            log_guardian("WARN", "Git add -u timeout after all retries")
            return False
        except Exception as e:
            log_guardian("WARN", f"Error staging tracked changes: {e}")
            return False

    return False


def ensure_git_config() -> bool:
    """Ensure git user.email and user.name are configured.

    Git requires these to be set for commits. If not set, we set
    defaults from config.json or hardcoded fallbacks.

    MINOR-2 FIX: Now reads identity from config.json gitIntegration.identity
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
    config = load_guardian_config()
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
                    log_guardian("INFO", f"Set and verified git user.email: {default_email}")
                    email_ok = True
                else:
                    log_guardian(
                        "WARN",
                        f"Git user.email set but verification failed. "
                        f"Expected: {default_email}, Got: {verify_result.stdout.strip()}",
                    )
            else:
                log_guardian("WARN", f"Failed to set git user.email: {set_result.stderr}")

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
                    log_guardian("INFO", f"Set and verified git user.name: {default_name}")
                    name_ok = True
                else:
                    log_guardian(
                        "WARN",
                        f"Git user.name set but verification failed. "
                        f"Expected: {default_name}, Got: {verify_result.stdout.strip()}",
                    )
            else:
                log_guardian("WARN", f"Failed to set git user.name: {set_result.stderr}")

        # Return True only if both are OK (fail-open: let git commit try anyway)
        if not email_ok or not name_ok:
            log_guardian("WARN", f"Git config incomplete: email_ok={email_ok}, name_ok={name_ok}")
        return True  # Fail-open: let git commit try anyway
    except Exception as e:
        log_guardian("WARN", f"Could not verify/set git config: {e}")
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
        log_guardian("WARN", "Git not available - cannot commit")
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
                log_guardian("INFO", "Git commit succeeded")
                # Also log stderr if present (could contain warnings)
                if result.stderr:
                    log_guardian("INFO", f"Git commit note: {result.stderr[:500]}")
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
                log_guardian("INFO", "Nothing to commit (no staged changes)")
                return True  # This is a valid success case, not an error

            if _is_git_lock_error(stderr) and attempt < max_retries - 1:
                log_guardian("INFO", f"Git lock detected, retry {attempt + 1}/{max_retries}")
                time.sleep(0.5 * (attempt + 1))
                continue

            log_guardian("WARN", f"Git commit stderr: {stderr[:500]}")
            return False

        except FileNotFoundError:
            log_guardian("WARN", "Git executable not found in PATH")
            return False
        except subprocess.TimeoutExpired:
            # M4 FIX: Retry on timeout (system may be under load)
            if attempt < max_retries - 1:
                log_guardian("INFO", f"Git commit timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(1.0 * (attempt + 1))
                continue
            log_guardian("WARN", "Git commit timeout after all retries")
            return False
        except Exception as e:
            log_guardian("WARN", f"Error creating commit: {e}")
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
            log_guardian("INFO", "Repository has no commits yet")
        else:
            log_guardian("WARN", f"Git rev-parse failed: {stderr[:200]}")
        return ""
    except FileNotFoundError:
        log_guardian("WARN", "Git executable not found in PATH")
        return ""
    except subprocess.TimeoutExpired:
        log_guardian("WARN", "Git rev-parse timeout")
        return ""
    except Exception as e:
        log_guardian("WARN", f"Error getting commit hash: {e}")
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
        log_guardian("WARN", "Git executable not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log_guardian("WARN", "Git symbolic-ref timeout")
        return False
    except Exception as e:
        log_guardian("WARN", f"Error checking detached HEAD: {e}")
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
            log_guardian("INFO", f"Git operation in progress: {indicator.name}")
            return True

    return False


# ============================================================
# Path Guardian Hook Runner (Shared Edit/Write Logic)
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


def is_self_guardian_path(path: str) -> bool:
    """Check if path is a self-guarded path (guardian system files).

    These paths are ALWAYS protected regardless of configuration.

    # PLUGIN MIGRATION: Now uses dynamic config path detection in addition
    # to static SELF_GUARDIAN_PATHS. In plugin context, only the config
    # file needs guarding (scripts are in read-only cache).

    Args:
        path: Path to check.

    Returns:
        True if path should be protected as part of guardian system.
    """
    # Normalize path for comparison
    norm_path = normalize_path_for_matching(path)

    project_dir = get_project_dir()
    if not project_dir:
        return False

    project_normalized = project_dir.replace("\\", "/")
    # Case-insensitive on Windows and macOS (HFS+ is case-insensitive)
    if sys.platform != "linux":
        project_normalized = project_normalized.lower()

    # Check static self-guardian paths
    for protected in SELF_GUARDIAN_PATHS:
        protected_norm = protected.replace("\\", "/")
        # Case-insensitive on Windows and macOS (HFS+ is case-insensitive)
        if sys.platform != "linux":
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
        log_guardian("WARN", f"Could not resolve path {file_path}: {e}")
        return path


def run_path_guardian_hook(tool_name: str) -> None:
    """Run guardian checks for Read/Edit/Write tools.

    This is the main entry point for path-based guardian hooks.
    It implements fail-close semantics for security.

    Args:
        tool_name: The tool name to check for ("Read", "Edit", or "Write").
    """
    import json as _json  # Local import to avoid circular dependency issues

    # Parse input - FAIL-CLOSE on invalid JSON
    try:
        input_data = _json.load(sys.stdin)
    except _json.JSONDecodeError as e:
        # SECURITY FIX: Fail-close on malformed input
        log_guardian("ERROR", f"Malformed JSON input: {e}")
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
        log_guardian("WARN", f"Invalid tool_input type: {type(tool_input).__name__}")
        print(_json.dumps(deny_response("Invalid tool input structure")))
        sys.exit(0)

    # Extract file path
    file_path = tool_input.get("file_path", "")

    # Validate file_path
    if not file_path:
        log_guardian("WARN", f"{tool_name} called without file_path")
        # Allow - some tools might legitimately have no path
        # Note: No response = allow in Claude Code hook protocol
        print(_json.dumps(allow_response()))
        sys.exit(0)

    if not isinstance(file_path, str):
        log_guardian("WARN", f"Invalid file_path type: {type(file_path).__name__}")
        print(_json.dumps(deny_response("Invalid file path type")))
        sys.exit(0)

    # Check for null bytes (path injection attack)
    if "\x00" in file_path:
        log_guardian("BLOCK", f"Null byte in path rejected: {truncate_path(file_path)}")
        print(_json.dumps(deny_response("Invalid file path (contains null byte)")))
        sys.exit(0)

    # Resolve to absolute path
    resolved = resolve_tool_path(file_path)
    path_str = str(resolved)
    path_preview = truncate_path(file_path)

    log_guardian("INFO", f"{tool_name} check: {path_preview}")

    # ========== Check: Symlink Escape ==========
    if is_symlink_escape(file_path):
        log_guardian("BLOCK", f"Symlink escape detected ({tool_name}): {path_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", f"Would DENY {tool_name} (symlink escape)")
            sys.exit(0)
        print(_json.dumps(deny_response(f"Symlink points outside project: {Path(file_path).name}")))
        sys.exit(0)

    # ========== Check: Path Within Project ==========
    if not is_path_within_project(path_str):
        # Check if path is in allowedExternalPaths before blocking
        matched, ext_mode = match_allowed_external_path(path_str)
        if matched:
            # Mode check: read-only external paths block Write/Edit
            if ext_mode == "read" and tool_name.lower() in ("write", "edit"):
                log_guardian("BLOCK", f"Read-only external path ({tool_name}): {path_preview}")
                if is_dry_run():
                    log_guardian("DRY-RUN", f"Would DENY {tool_name} (read-only external)")
                    sys.exit(0)
                print(_json.dumps(deny_response(
                    f"External path is read-only: {Path(file_path).name}\n"
                    "Use {\"path\": \"...\", \"mode\": \"readwrite\"} in allowedExternalPaths to allow writes."
                )))
                sys.exit(0)
            log_guardian(
                "ALLOW",
                f"Allowed external path ({tool_name}, mode={ext_mode}): {path_preview}"
            )
            # Fall through to remaining checks (self-guardian, zeroAccess, readOnly)
        else:
            log_guardian("BLOCK", f"Path outside project ({tool_name}): {path_preview}")
            if is_dry_run():
                log_guardian("DRY-RUN", f"Would DENY {tool_name} (outside project)")
                sys.exit(0)
            print(_json.dumps(deny_response("Path is outside project directory")))
            sys.exit(0)

    # ========== Check: Self Guardian ==========
    if is_self_guardian_path(path_str):
        log_guardian("BLOCK", f"Self-guardian path ({tool_name}): {path_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", f"Would DENY {tool_name} (self-guardian)")
            sys.exit(0)
        print(_json.dumps(deny_response(f"Protected system file: {Path(file_path).name}")))
        sys.exit(0)

    # ========== Check: Zero Access ==========
    if match_zero_access(path_str):
        log_guardian("BLOCK", f"Zero access path ({tool_name}): {path_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", f"Would DENY {tool_name}")
            sys.exit(0)
        reason = (
            f"Protected file (no access): {Path(file_path).name}"
            "\nBash alternatives (cat, sed, echo >, etc.) are also monitored by Guardian."
        )
        print(_json.dumps(deny_response(reason)))
        sys.exit(0)

    # ========== Check: Read Only ==========
    # Skip readOnly check for Read tool — reading read-only files is allowed
    if tool_name.lower() != "read" and match_read_only(path_str):
        log_guardian("BLOCK", f"Read-only path ({tool_name}): {path_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", f"Would DENY {tool_name}")
            sys.exit(0)
        reason = (
            f"Read-only file: {Path(file_path).name}"
            "\nBash alternatives (cat, sed, echo >, etc.) are also monitored by Guardian."
        )
        print(_json.dumps(deny_response(reason)))
        sys.exit(0)

    # ========== Allow ==========
    log_guardian("ALLOW", f"{tool_name}: {path_preview}")
    sys.exit(0)


# ============================================================
# Module Self-Test (when run directly)
# ============================================================


if __name__ == "__main__":
    print("_guardian_utils.py - Module loaded successfully")
    print(f"Project dir: {get_project_dir()}")
    print(f"Plugin root: {_get_plugin_root()}")
    print(f"Dry-run mode: {is_dry_run()}")
    print(f"Config loaded: {bool(load_guardian_config())}")
    print(f"Active config path: {get_active_config_path()}")
    print(f"Self-guardian paths: {SELF_GUARDIAN_PATHS}")
    print(f"Regex timeout available: {_HAS_REGEX_TIMEOUT}")
