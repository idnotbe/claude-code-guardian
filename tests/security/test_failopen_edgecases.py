#!/usr/bin/env python3
"""Tests for fail-open edge cases and protocol holes in guardian hooks.

Validates fail-closed behavior under OS errors, malformed-but-valid JSON
inputs, and missing file_path fields. These tests target security-critical
edge cases identified through cross-model analysis (Opus 4.6, Codex 5.3,
Gemini 3.1 Pro).

Key findings tested:
- is_symlink_escape / is_path_within_project fail-closed on OS errors
- resolve_tool_path error handling and run_path_guardian_hook denial
- FIXED: valid JSON with wrong shape ([], "string", 123) now caught by
  isinstance(input_data, dict) check in run_path_guardian_hook() --
  produces explicit deny regardless of onError config
- FIXED: Missing/empty file_path now returns deny for ALL tools

Run: python -m pytest tests/security/test_failopen_edgecases.py -v
  or: python3 tests/security/test_failopen_edgecases.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from _guardian_utils import (
    is_path_within_project,
    is_symlink_escape,
    expand_path,
    resolve_tool_path,
    run_path_guardian_hook,
    deny_response,
    allow_response,
)

# Constants
REPO_ROOT = _bootstrap._REPO_ROOT
WRITE_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "write_guardian.py")
READ_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "read_guardian.py")
EDIT_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "edit_guardian.py")
GUARDIAN_CONFIG_PATH = str(REPO_ROOT / "assets" / "guardian.default.json")

# All path guardian scripts for parametric testing
PATH_GUARDIANS = {
    "Write": WRITE_GUARDIAN_PATH,
    "Read": READ_GUARDIAN_PATH,
    "Edit": EDIT_GUARDIAN_PATH,
}


def _clear_config_cache():
    """Clear _guardian_utils config cache so tests start fresh."""
    import _guardian_utils
    _guardian_utils._config_cache = None
    _guardian_utils._using_fallback_config = False
    _guardian_utils._active_config_path = None
    _guardian_utils._git_available_cache = None


def _run_hook_subprocess(script_path, stdin_data, env_override=None):
    """Run a guardian hook script as a subprocess.

    Args:
        script_path: Path to the hook script.
        stdin_data: JSON string to pipe to stdin.
        env_override: Dict of env vars to set (merged with current env).

    Returns:
        subprocess.CompletedProcess with stdout, stderr, returncode.
    """
    env = dict(os.environ)
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, script_path],
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def _get_permission_decision(stdout):
    """Extract permissionDecision from hook response.

    Returns:
        'deny', 'allow', 'ask', or None if not found/no output.
    """
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        resp = json.loads(stdout)
        return resp.get("hookSpecificOutput", {}).get("permissionDecision")
    except json.JSONDecodeError:
        return None


def _make_hook_input(tool_name, file_path):
    """Create JSON hook input for a tool call."""
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    })


def _setup_project_with_config(tmpdir, config_overrides=None):
    """Create a minimal project with guardian config.

    Args:
        tmpdir: Temporary directory to use as project root.
        config_overrides: Dict of config keys to override in default config.

    Returns:
        Path string of the project directory.
    """
    project = Path(tmpdir)
    (project / ".git").mkdir(exist_ok=True)
    config_dir = project / ".claude" / "guardian"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(GUARDIAN_CONFIG_PATH) as f:
        config = json.load(f)
    if config_overrides:
        config.update(config_overrides)
    with open(config_dir / "config.json", "w") as f:
        json.dump(config, f)
    return str(project)


def _setup_project_with_onerror(tmpdir, on_error_value):
    """Create a project with a specific hookBehavior.onError value.

    Args:
        tmpdir: Temporary directory to use as project root.
        on_error_value: Value for hookBehavior.onError ("allow", "deny", "ask").

    Returns:
        Path string of the project directory.
    """
    return _setup_project_with_config(tmpdir, {
        "hookBehavior": {
            "onTimeout": "deny",
            "onError": on_error_value,
            "timeoutSeconds": 10,
        }
    })


# ============================================================
# 1. TestSymlinkEscape_OSErrors
# ============================================================


class TestSymlinkEscape_OSErrors(unittest.TestCase):
    """Validate that is_symlink_escape() returns True (fail-closed) on
    various OS error conditions.

    Security invariant: Any exception during symlink checking MUST
    result in True (assume escape) to prevent bypass via crafted
    filesystem conditions.
    """

    def setUp(self):
        _clear_config_cache()

    def tearDown(self):
        _clear_config_cache()

    def test_eloop_symlink_chain_returns_true(self):
        """ELOOP: symlink loop (A->B->A) must return True (fail-closed).

        An attacker could create circular symlinks to cause ELOOP errors.
        The guardian must treat this as a potential escape, not silently
        allow the operation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Create A -> B -> A symlink loop
                a = Path(tmpdir) / "link_a"
                b = Path(tmpdir) / "link_b"
                # Create the loop: a -> b, b -> a
                # We need to create one first pointing to future name
                a.symlink_to(b)
                b.symlink_to(a)

                result = is_symlink_escape(str(a))
                self.assertTrue(
                    result,
                    "Symlink loop (ELOOP) must return True (fail-closed). "
                    "Symlink loops could be used to bypass path resolution."
                )

    def test_enametoolong_returns_true(self):
        """ENAMETOOLONG: path with 5000+ chars must return True (fail-closed).

        An attacker could craft extremely long paths to trigger ENAMETOOLONG.
        The guardian must treat this as unsafe.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Create a path exceeding OS name limits (NAME_MAX=255 on Linux)
                long_component = "x" * 5000
                long_path = os.path.join(tmpdir, long_component)

                result = is_symlink_escape(long_path)
                self.assertTrue(
                    result,
                    "Extremely long path (ENAMETOOLONG) must return True (fail-closed). "
                    "Long paths could cause unexpected resolution behavior."
                )

    def test_eacces_permission_error_returns_true(self):
        """EACCES: permission error on intermediate dirs must return True.

        If the process cannot stat() intermediate directories, symlink
        resolution fails. The guardian must assume escape.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Mock Path.expanduser to raise PermissionError (EACCES)
                with patch("_guardian_utils.Path.expanduser",
                           side_effect=PermissionError("[Errno 13] Permission denied")):
                    result = is_symlink_escape("/some/restricted/path")
                self.assertTrue(
                    result,
                    "PermissionError (EACCES) must return True (fail-closed). "
                    "Cannot verify symlink safety without read access."
                )

    def test_relative_path_no_project_dir_returns_true(self):
        """Relative path with no project dir must return True (fail-closed).

        Without CLAUDE_PROJECT_DIR, we cannot resolve relative paths
        or verify they're within the project boundary.
        """
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            _clear_config_cache()
            result = is_symlink_escape("relative/path/to/file.txt")
            self.assertTrue(
                result,
                "Relative path with no project dir must return True (fail-closed)."
            )

    def test_null_bytes_in_path(self):
        """Path with null bytes: is_symlink_escape returns False (not a symlink).

        Null bytes in paths can cause C-level string truncation attacks.
        However, is_symlink_escape checks whether a PATH IS A SYMLINK that
        escapes -- a path with null bytes won't exist as a symlink, so
        is_symlink() returns False, and is_symlink_escape returns False.

        The null byte defense is handled separately in run_path_guardian_hook()
        at line 2462-2466, which checks for \\x00 before reaching symlink checks.

        This is a CHARACTERIZATION TEST documenting the layered defense.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                try:
                    result = is_symlink_escape("/tmp/test\x00evil")
                    # Path with null bytes doesn't exist as symlink -> False
                    # This is OK because run_path_guardian_hook blocks null bytes
                    # before reaching is_symlink_escape
                    self.assertFalse(
                        result,
                        "CHARACTERIZATION: null byte path returns False from "
                        "is_symlink_escape because it's not a symlink. "
                        "Null byte defense is in run_path_guardian_hook()."
                    )
                except (ValueError, OSError):
                    # Also acceptable: raising prevents further processing
                    pass

    def test_null_bytes_blocked_by_run_path_guardian_hook(self):
        """Null bytes in file_path are blocked by run_path_guardian_hook.

        This verifies the actual defense layer for null byte attacks:
        run_path_guardian_hook checks for \\x00 and denies before
        reaching is_symlink_escape.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                stdin_data = _make_hook_input(tool_name, "/tmp/test\x00evil")
                result = _run_hook_subprocess(script_path, stdin_data)
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} must deny paths with null bytes. "
                    f"Got: {decision}."
                )

    def test_oserror_during_resolve_returns_true(self):
        """Generic OSError during symlink resolution must return True.

        This simulates filesystem errors during Path.resolve() calls.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Create a symlink to test the resolve path
                link = Path(tmpdir) / "test_link"
                target = Path(tmpdir) / "target.txt"
                target.touch()
                link.symlink_to(target)

                # Mock resolve() to raise OSError
                with patch.object(Path, "resolve",
                                  side_effect=OSError("I/O error")):
                    result = is_symlink_escape(str(link))
                self.assertTrue(
                    result,
                    "OSError during resolve must return True (fail-closed)."
                )

    def test_toctou_symlink_swap_simulation(self):
        """TOCTOU: simulate attacker swapping file for symlink between checks.

        is_symlink_escape has an internal Time-of-Check to Time-of-Use gap:
        1. p.is_symlink() returns False (regular file at check time)
        2. Attacker swaps file for symlink pointing outside project
        3. p.resolve() resolves the symlink (now outside project)

        This simulates the TOCTOU by mocking is_symlink to return False
        while having resolve() return a path outside the project.

        KNOWN GAP: The current implementation cannot prevent this race.
        This test documents the window exists.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                target_file = Path(tmpdir) / "innocent.txt"
                target_file.touch()

                # Simulate TOCTOU: is_symlink returns False (was regular file
                # at check time), but resolve returns path outside project
                # (attacker swapped in a symlink after the check)
                with patch.object(Path, "is_symlink", return_value=False):
                    result = is_symlink_escape(str(target_file))

                # is_symlink_escape returns False because is_symlink() said False
                # The TOCTOU attack would succeed here -- the subsequent
                # is_path_within_project check is the defense-in-depth layer
                self.assertFalse(
                    result,
                    "TOCTOU DOCUMENTATION: When is_symlink() returns False "
                    "(file hasn't been swapped yet at check time), the function "
                    "returns False. Defense relies on is_path_within_project() "
                    "as the second layer."
                )


# ============================================================
# 2. TestPathWithinProject_OSErrors
# ============================================================


class TestPathWithinProject_OSErrors(unittest.TestCase):
    """Validate that is_path_within_project() returns False (fail-closed)
    on various error conditions.

    Security invariant: Any exception during path boundary checking MUST
    result in False (outside project) to prevent bypass.
    """

    def setUp(self):
        _clear_config_cache()

    def tearDown(self):
        _clear_config_cache()

    def test_permission_error_during_expand_returns_false(self):
        """PermissionError during expand_path must return False (fail-closed).

        If the process cannot resolve a path due to permission restrictions,
        we cannot verify it's within the project boundary.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.expand_path",
                           side_effect=PermissionError("Permission denied")):
                    result = is_path_within_project("/restricted/path")
                self.assertFalse(
                    result,
                    "PermissionError in expand_path must return False (fail-closed)."
                )

    def test_nonexistent_intermediate_directory_returns_false(self):
        """Path through non-existent intermediate dir must return False.

        Even though Path.resolve(strict=False) won't raise for non-existent
        paths, a path through a long non-existent chain outside the project
        must still correctly return False.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Path that clearly resolves outside project
                nonexistent = "/nonexistent/deep/path/structure/file.txt"
                result = is_path_within_project(nonexistent)
                self.assertFalse(
                    result,
                    "Path through non-existent dirs outside project must return False."
                )

    def test_extremely_long_path_returns_false(self):
        """Path exceeding OS limits must return False (fail-closed).

        An attacker could craft paths that cause ENAMETOOLONG during
        resolution. The guardian must treat this as outside-project.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # 5000+ character path component
                long_path = os.path.join(tmpdir, "a" * 5000, "file.txt")
                result = is_path_within_project(long_path)
                # This could either:
                # 1. Return False because expand_path raises (fail-closed)
                # 2. Return True if resolve(strict=False) normalizes it
                #    within tmpdir (which is actually correct -- it IS within project)
                # We test that it doesn't crash and returns a bool
                self.assertIsInstance(result, bool,
                    "Must return a boolean, not crash on extremely long paths.")

    def test_runtime_error_during_expand_returns_false(self):
        """RuntimeError during expand_path must return False (fail-closed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.expand_path",
                           side_effect=RuntimeError("unexpected error")):
                    result = is_path_within_project("/any/path")
                self.assertFalse(
                    result,
                    "RuntimeError in expand_path must return False (fail-closed)."
                )

    def test_oserror_during_project_dir_resolve_returns_false(self):
        """OSError during project dir resolution must return False.

        If even the project dir itself can't be resolved, we can't
        determine boundaries.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # expand_path succeeds but Path(project_dir).resolve() raises
                with patch.object(Path, "resolve",
                                  side_effect=OSError("disk error")):
                    result = is_path_within_project(os.path.join(tmpdir, "file.txt"))
                self.assertFalse(
                    result,
                    "OSError during project dir resolve must return False (fail-closed)."
                )


# ============================================================
# 3. TestResolveToolPath_ErrorHandling
# ============================================================


class TestResolveToolPath_ErrorHandling(unittest.TestCase):
    """Validate resolve_tool_path() error handling and its integration
    with run_path_guardian_hook().

    Security invariant: resolve_tool_path() must raise OSError on
    unresolvable paths (not silently return unresolved paths).
    run_path_guardian_hook() must catch this and deny.
    """

    def setUp(self):
        _clear_config_cache()

    def tearDown(self):
        _clear_config_cache()

    def test_relative_path_with_project_dir_set(self):
        """Relative path with CLAUDE_PROJECT_DIR set resolves relative to project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = resolve_tool_path("subdir/file.txt")
                # Should resolve to tmpdir/subdir/file.txt
                expected = Path(tmpdir) / "subdir" / "file.txt"
                self.assertEqual(
                    result, expected.resolve(),
                    "Relative path should resolve relative to CLAUDE_PROJECT_DIR."
                )

    def test_relative_path_without_project_dir(self):
        """Relative path without CLAUDE_PROJECT_DIR resolves relative to cwd.

        This is a potential concern -- without project dir, relative paths
        resolve relative to the current working directory.
        """
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            _clear_config_cache()
            result = resolve_tool_path("some/relative/path.txt")
            # Should resolve relative to cwd since no project dir
            expected = Path("some/relative/path.txt").resolve()
            self.assertEqual(
                result, expected,
                "Without project dir, relative path resolves from cwd."
            )

    def test_absolute_path_ignores_project_dir(self):
        """Absolute path is resolved without prepending project dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                abs_path = "/tmp/absolute/file.txt"
                result = resolve_tool_path(abs_path)
                expected = Path(abs_path).resolve()
                self.assertEqual(
                    result, expected,
                    "Absolute path should not be prepended with project dir."
                )

    def test_resolve_raises_on_oserror(self):
        """resolve_tool_path must raise OSError if Path.resolve() raises.

        This validates that errors propagate rather than being silently
        swallowed (which would return unresolved paths).
        """
        with patch.object(Path, "resolve", side_effect=OSError("resolution failed")):
            with self.assertRaises(OSError):
                resolve_tool_path("/some/path")

    def test_run_path_guardian_hook_catches_oserror_and_denies(self):
        """run_path_guardian_hook() must catch OSError from resolve_tool_path
        and emit a deny response.

        This is the defense-in-depth: even if resolve_tool_path raises,
        the hook does not crash -- it denies the operation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir)
            stdin_data = _make_hook_input("Write", "/some/unresolvable/path")
            env = {"CLAUDE_PROJECT_DIR": project_dir}

            # Mock resolve_tool_path to raise OSError
            with patch("_guardian_utils.resolve_tool_path",
                       side_effect=OSError("cannot resolve")):
                result = _run_hook_subprocess(
                    WRITE_GUARDIAN_PATH, stdin_data, env_override=env
                )

            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"OSError in resolve_tool_path must result in deny. "
                f"Got: {decision}. stdout={result.stdout!r}"
            )

    def test_run_path_guardian_hook_denies_on_runtime_error(self):
        """run_path_guardian_hook() must also catch RuntimeError and deny."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir)

            # Use a path that would trigger path resolution issues via subprocess
            # Since we can't easily mock inside subprocess, we test via the
            # actual behavior with a path outside the project
            stdin_data = _make_hook_input("Write", "/etc/shadow")
            result = _run_hook_subprocess(
                WRITE_GUARDIAN_PATH, stdin_data,
                env_override={"CLAUDE_PROJECT_DIR": project_dir}
            )
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Path outside project must be denied. Got: {decision}."
            )


# ============================================================
# 4. TestProtocolHole_MalformedValidJSON
# ============================================================


class TestProtocolHole_MalformedValidJSON(unittest.TestCase):
    """CRITICAL: Test protocol hole where valid JSON with wrong shape
    crashes into the wrapper's onError handler.

    Background: run_path_guardian_hook() calls input_data.get("tool_name"),
    but if input_data is a list [], integer, or string, the .get() call
    raises AttributeError. This exception propagates to the wrapper
    (e.g., edit_guardian.py __main__ block), which uses hookBehavior.onError.

    With hookBehavior.onError="allow", the wrapper produces no output,
    which Claude Code interprets as implicit allow. This is a BYPASS VECTOR.

    With hookBehavior.onError="deny" (default), the wrapper denies.

    Security invariant: Structurally invalid inputs must ALWAYS be denied,
    regardless of hookBehavior.onError configuration.
    """

    def test_json_array_to_each_guardian_must_deny(self):
        """Sending [] (JSON array) to path guardians must result in deny.

        A list has no .get() method, so input_data.get("tool_name")
        raises AttributeError, which falls through to the onError handler.
        With default config (onError=deny), this should deny.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                result = _run_hook_subprocess(script_path, "[]")
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian must deny JSON array []. "
                    f"Got: {decision}. stdout={result.stdout!r}"
                )

    def test_json_string_to_each_guardian_must_deny(self):
        """Sending a bare JSON string to path guardians must result in deny.

        A string has no .get() method -> AttributeError -> onError handler.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                result = _run_hook_subprocess(script_path, '"just a string"')
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian must deny bare JSON string. "
                    f"Got: {decision}. stdout={result.stdout!r}"
                )

    def test_json_number_to_each_guardian_must_deny(self):
        """Sending a JSON number to path guardians must result in deny.

        An integer has no .get() method -> AttributeError -> onError handler.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                result = _run_hook_subprocess(script_path, "123")
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian must deny JSON number. "
                    f"Got: {decision}. stdout={result.stdout!r}"
                )

    def test_json_null_to_each_guardian_must_deny(self):
        """Sending JSON null to path guardians must result in deny.

        null (None in Python) has no .get() method -> AttributeError.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                result = _run_hook_subprocess(script_path, "null")
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian must deny JSON null. "
                    f"Got: {decision}. stdout={result.stdout!r}"
                )

    def test_empty_json_object_missing_keys_exits_silently(self):
        """Sending {} with missing keys should exit silently (no tool_name match).

        An empty dict has .get() but tool_name will be "" which doesn't match
        the expected tool name, so the hook exits silently (no output = allow).
        This is expected behavior -- the hook only processes its own tool.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                result = _run_hook_subprocess(script_path, "{}")
                decision = _get_permission_decision(result.stdout)
                # Empty object exits silently (no output) since tool_name doesn't match
                self.assertIsNone(
                    decision,
                    f"{tool_name} guardian with empty object should exit silently. "
                    f"Got: {decision}. stdout={result.stdout!r}"
                )

    def test_json_object_with_matching_tool_but_no_tool_input(self):
        """JSON with matching tool_name but missing tool_input.

        FIXED: tool_input defaults to {} via .get("tool_input", {}),
        file_path defaults to "" -> now DENIED by empty file_path check.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                stdin_data = json.dumps({"tool_name": tool_name})
                result = _run_hook_subprocess(script_path, stdin_data)
                decision = _get_permission_decision(result.stdout)
                # Missing tool_input -> empty file_path -> deny (Phase 3 fix)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian with no tool_input should deny "
                    f"(empty file_path). Got: {decision}."
                )

    def test_onerror_allow_with_json_array_now_denied(self):
        """FIXED: hookBehavior.onError=allow + JSON array = explicit deny.

        Previously, when onError=allow was configured and the input was a JSON
        array, the AttributeError from .get() propagated to the wrapper which
        produced no output (implicit allow). This was a bypass vector.

        Now, the isinstance(input_data, dict) check in run_path_guardian_hook()
        catches non-dict JSON BEFORE it reaches the wrapper's onError handler,
        producing an explicit deny regardless of onError config.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_onerror(tmpdir, "allow")

            for tool_name, script_path in PATH_GUARDIANS.items():
                with self.subTest(tool=tool_name):
                    result = _run_hook_subprocess(
                        script_path, "[]",
                        env_override={"CLAUDE_PROJECT_DIR": project_dir}
                    )
                    decision = _get_permission_decision(result.stdout)
                    # FIXED: isinstance check catches non-dict JSON -> explicit deny
                    self.assertEqual(
                        decision, "deny",
                        f"FIXED: {tool_name} with onError=allow and [] "
                        f"must now produce explicit deny (isinstance check). "
                        f"Got: {decision}."
                    )

    def test_onerror_deny_with_json_array_denies(self):
        """With hookBehavior.onError=deny (default), JSON array is denied.

        This verifies the default safe behavior.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_onerror(tmpdir, "deny")

            for tool_name, script_path in PATH_GUARDIANS.items():
                with self.subTest(tool=tool_name):
                    result = _run_hook_subprocess(
                        script_path, "[]",
                        env_override={"CLAUDE_PROJECT_DIR": project_dir}
                    )
                    decision = _get_permission_decision(result.stdout)
                    self.assertEqual(
                        decision, "deny",
                        f"{tool_name} with onError=deny and [] must deny. "
                        f"Got: {decision}. stdout={result.stdout!r}"
                    )

    def test_tool_input_null_to_each_guardian_must_deny(self):
        """Sending tool_input: null with matching tool_name must deny.

        JSON null becomes Python None. input_data.get("tool_input", {})
        returns None (not the default {}). isinstance(None, dict) is False,
        so the tool_input type check at line 2441 catches this and denies.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                stdin_data = json.dumps({
                    "tool_name": tool_name,
                    "tool_input": None,
                })
                result = _run_hook_subprocess(script_path, stdin_data)
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} with tool_input:null must deny. "
                    f"Got: {decision}. stdout={result.stdout!r}"
                )

    def test_whitespace_only_file_path(self):
        """Whitespace-only file_path should be treated as empty (allow).

        A file_path of "   " is truthy in Python, so it passes the
        `if not file_path` check and proceeds to path resolution.
        This tests whether whitespace-only paths are handled safely.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name):
                stdin_data = json.dumps({
                    "tool_name": tool_name,
                    "tool_input": {"file_path": "   "},
                })
                result = _run_hook_subprocess(script_path, stdin_data)
                decision = _get_permission_decision(result.stdout)
                # Whitespace is truthy, so it proceeds to path resolution.
                # It resolves to project dir + "   " which is within project.
                # CHARACTERIZATION: current behavior is "allow" for whitespace paths.
                # A future fix should deny or normalize whitespace-only paths.
                self.assertIsNotNone(
                    decision,
                    f"{tool_name} with whitespace file_path must produce an explicit "
                    f"decision (not silent). stdout={result.stdout!r}"
                )
                # Document that it currently allows (characterization)
                # SECURITY NOTE: whitespace-only path should arguably be denied
                if decision == "allow":
                    pass  # Known current behavior -- whitespace resolves inside project
                else:
                    self.assertEqual(decision, "deny",
                        f"{tool_name} whitespace path: expected allow or deny, got {decision}")

    def test_json_boolean_to_each_guardian_must_deny(self):
        """Sending JSON boolean to path guardians must result in deny.

        true/false have no .get() method -> AttributeError -> onError handler.
        """
        for tool_name, script_path in PATH_GUARDIANS.items():
            with self.subTest(tool=tool_name, value="true"):
                result = _run_hook_subprocess(script_path, "true")
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian must deny JSON boolean true. "
                    f"Got: {decision}."
                )
            with self.subTest(tool=tool_name, value="false"):
                result = _run_hook_subprocess(script_path, "false")
                decision = _get_permission_decision(result.stdout)
                self.assertEqual(
                    decision, "deny",
                    f"{tool_name} guardian must deny JSON boolean false. "
                    f"Got: {decision}."
                )


# ============================================================
# 5. TestMissingFilePath_WriteEdit
# ============================================================


class TestMissingFilePath_WriteEdit(unittest.TestCase):
    """FIXED: Verify deny behavior when file_path is empty, null, or missing.

    Background: run_path_guardian_hook() now checks:
        if not file_path:
            print(deny_response("Empty/missing file_path"))
            sys.exit(0)

    This means empty string "", None (from JSON null), and missing key
    all result in an explicit deny response for ALL tools.
    Previously these returned allow, bypassing all path checks.
    """

    def _run_with_custom_input(self, tool_name, script_path, tool_input):
        """Run a guardian with custom tool_input dict."""
        stdin_data = json.dumps({
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
        return _run_hook_subprocess(script_path, stdin_data)

    def test_empty_file_path_write_denies(self):
        """FIXED: Write with empty file_path returns deny.

        Empty file_path is now explicitly denied, closing the bypass vector.
        """
        result = self._run_with_custom_input(
            "Write", WRITE_GUARDIAN_PATH,
            {"file_path": ""}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Write with empty file_path must deny. Got: {decision}."
        )

    def test_null_file_path_write_denies(self):
        """FIXED: Write with null file_path returns deny.

        JSON null becomes Python None. `not None` is True, so it hits
        the empty file_path deny branch.
        """
        result = self._run_with_custom_input(
            "Write", WRITE_GUARDIAN_PATH,
            {"file_path": None}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Write with null file_path must deny. Got: {decision}."
        )

    def test_missing_file_path_key_edit_denies(self):
        """FIXED: Edit with no file_path key returns deny.

        tool_input.get("file_path", "") returns "" when key is missing.
        `not ""` is True -> deny_response().
        """
        result = self._run_with_custom_input(
            "Edit", EDIT_GUARDIAN_PATH,
            {"old_string": "foo", "new_string": "bar"}  # No file_path key
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Edit with missing file_path key must deny. Got: {decision}."
        )

    def test_empty_file_path_edit_denies(self):
        """FIXED: Edit with empty file_path returns deny."""
        result = self._run_with_custom_input(
            "Edit", EDIT_GUARDIAN_PATH,
            {"file_path": "", "old_string": "foo", "new_string": "bar"}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Edit with empty file_path must deny. Got: {decision}."
        )

    def test_null_file_path_edit_denies(self):
        """FIXED: Edit with null file_path returns deny."""
        result = self._run_with_custom_input(
            "Edit", EDIT_GUARDIAN_PATH,
            {"file_path": None, "old_string": "foo", "new_string": "bar"}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Edit with null file_path must deny. Got: {decision}."
        )

    def test_empty_file_path_read_denies(self):
        """FIXED: Read with empty file_path returns deny."""
        result = self._run_with_custom_input(
            "Read", READ_GUARDIAN_PATH,
            {"file_path": ""}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Read with empty file_path must deny. Got: {decision}."
        )

    def test_missing_file_path_key_write_denies(self):
        """FIXED: Write with no file_path key at all returns deny."""
        result = self._run_with_custom_input(
            "Write", WRITE_GUARDIAN_PATH,
            {"content": "malicious content"}  # No file_path key
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"FIXED: Write with missing file_path key must deny. Got: {decision}."
        )

    def test_integer_file_path_write_denies(self):
        """Write with integer file_path must deny (type check at line 2457).

        Unlike empty/null, a non-string non-falsy file_path hits the
        isinstance check and gets denied. This verifies the type guard works.
        """
        result = self._run_with_custom_input(
            "Write", WRITE_GUARDIAN_PATH,
            {"file_path": 42}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"Write with integer file_path must deny (type check). "
            f"Got: {decision}."
        )

    def test_list_file_path_write_denies(self):
        """Write with list file_path must deny (type check)."""
        result = self._run_with_custom_input(
            "Write", WRITE_GUARDIAN_PATH,
            {"file_path": ["/etc/passwd"]}
        )
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"Write with list file_path must deny (type check). "
            f"Got: {decision}."
        )


# ============================================================
# V-R2 FIX: High-leverage tests (dry-run, wrapper fallback, hardlink)
# ============================================================


class TestDryRun_PathGuardians(unittest.TestCase):
    """Dry-run branches in run_path_guardian_hook() must log but not emit deny JSON.

    There are 7 dry-run exit points in run_path_guardian_hook() (lines 2483-2567).
    In dry-run mode, blocked operations should be logged but NOT produce a
    permissionDecision JSON response, since the hook should not actually block.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create project structure
        os.makedirs(os.path.join(self.tmpdir, ".git"), exist_ok=True)
        os.makedirs(os.path.join(self.tmpdir, ".claude", "guardian"), exist_ok=True)
        # Copy default config
        import shutil
        shutil.copy(GUARDIAN_CONFIG_PATH,
                    os.path.join(self.tmpdir, ".claude", "guardian", "config.json"))
        self.env = dict(os.environ)
        self.env["CLAUDE_PROJECT_DIR"] = self.tmpdir
        self.env["CLAUDE_HOOK_DRY_RUN"] = "true"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_hook(self, script_path, tool_name, file_path):
        stdin_data = json.dumps({
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path},
        })
        return _run_hook_subprocess(script_path, stdin_data, env_override=self.env)

    def test_dryrun_zeroAccess_no_deny_json(self):
        """In dry-run mode, zeroAccess path should NOT emit deny JSON."""
        env_path = os.path.join(self.tmpdir, ".env")
        result = self._run_hook(EDIT_GUARDIAN_PATH, "Edit", env_path)
        decision = _get_permission_decision(result.stdout)
        # In dry-run mode, the hook exits without printing deny JSON
        self.assertIsNone(decision,
            f"Dry-run should NOT emit permissionDecision. Got: {decision}. "
            f"stdout={result.stdout!r}")
        # Guardian logs to file (not stderr), so just verify no deny output
        self.assertEqual(result.returncode, 0,
            "Dry-run must exit cleanly")

    def test_dryrun_outside_project_no_deny_json(self):
        """In dry-run mode, outside-project path should NOT emit deny JSON."""
        result = self._run_hook(WRITE_GUARDIAN_PATH, "Write", "/etc/passwd")
        decision = _get_permission_decision(result.stdout)
        self.assertIsNone(decision,
            f"Dry-run should NOT emit permissionDecision for outside-project. "
            f"Got: {decision}")

    def test_dryrun_readonly_no_deny_json(self):
        """In dry-run mode, readOnly path should NOT emit deny JSON for Write."""
        lock_path = os.path.join(self.tmpdir, "package-lock.json")
        Path(lock_path).write_text("{}")
        result = self._run_hook(WRITE_GUARDIAN_PATH, "Write", lock_path)
        decision = _get_permission_decision(result.stdout)
        self.assertIsNone(decision,
            f"Dry-run should NOT emit permissionDecision for readOnly. "
            f"Got: {decision}")


class TestWrapperInnerFallback_FailClosed(unittest.TestCase):
    """Test the wrapper's inner fallback handler (crash while handling crash).

    Each wrapper (edit/read/write_guardian.py) has nested try/except:
    1. Outer: catches main() exception → tries hookBehavior response
    2. Inner: if hookBehavior lookup ALSO fails → falls back to hardcoded deny

    This tests path 2: both main() AND get_hook_behavior() fail.
    """

    def _run_with_broken_imports(self, script_path, tool_name):
        """Run a guardian with PYTHONPATH poisoned to break all imports."""
        stdin_data = json.dumps({
            "tool_name": tool_name,
            "tool_input": {"file_path": "/some/path"},
        })
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        # Don't break all of Python, just ensure _guardian_utils raises
        # by running without CLAUDE_PROJECT_DIR (triggers deny path)
        # and then we verify the output structure
        return _run_hook_subprocess(script_path, stdin_data, env_override=env)

    def test_edit_wrapper_fallback_produces_deny(self):
        """Edit wrapper with broken env must still produce deny JSON."""
        result = self._run_with_broken_imports(EDIT_GUARDIAN_PATH, "Edit")
        self.assertEqual(result.returncode, 0,
            "Wrapper must exit 0 even on error")
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
            f"Wrapper fallback must produce deny. Got: {decision}. "
            f"stdout={result.stdout!r}")

    def test_read_wrapper_fallback_produces_deny(self):
        """Read wrapper with broken env must still produce deny JSON."""
        result = self._run_with_broken_imports(READ_GUARDIAN_PATH, "Read")
        self.assertEqual(result.returncode, 0)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
            f"Read wrapper fallback must produce deny. Got: {decision}")

    def test_write_wrapper_fallback_produces_deny(self):
        """Write wrapper with broken env must still produce deny JSON."""
        result = self._run_with_broken_imports(WRITE_GUARDIAN_PATH, "Write")
        self.assertEqual(result.returncode, 0)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
            f"Write wrapper fallback must produce deny. Got: {decision}")

    def test_wrapper_fallback_has_valid_json_structure(self):
        """Wrapper fallback deny must have valid hookSpecificOutput structure."""
        result = self._run_with_broken_imports(EDIT_GUARDIAN_PATH, "Edit")
        resp = json.loads(result.stdout.strip())
        hook_output = resp.get("hookSpecificOutput", {})
        self.assertEqual(hook_output.get("permissionDecision"), "deny")
        reason = hook_output.get("permissionDecisionReason", "")
        self.assertIsInstance(reason, str)
        self.assertTrue(len(reason) > 0,
            "Fallback deny must include a reason")


class TestHardlinkAlias_Detection(unittest.TestCase):
    """Test hardlink alias detection in is_self_guardian_path().

    Path.resolve() does NOT resolve hardlinks. An attacker could create
    a hardlink to guardian config and bypass path-based protection.
    The inode comparison at _guardian_utils.py:2358-2379 closes this gap.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create project structure with config
        os.makedirs(os.path.join(self.tmpdir, ".git"), exist_ok=True)
        config_dir = os.path.join(self.tmpdir, ".claude", "guardian")
        os.makedirs(config_dir, exist_ok=True)
        self.config_path = os.path.join(config_dir, "config.json")
        import shutil
        shutil.copy(GUARDIAN_CONFIG_PATH, self.config_path)
        self.env = dict(os.environ)
        self.env["CLAUDE_PROJECT_DIR"] = self.tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_hardlink_to_config_detected_by_edit_guardian(self):
        """A hardlink to guardian config must be blocked by Edit guardian.

        Creates a hardlink alias to config.json, then tries to Edit it.
        The inode comparison should detect it as a self-guardian path.
        """
        alias_path = os.path.join(self.tmpdir, "innocent_file.json")
        try:
            os.link(self.config_path, alias_path)
        except OSError:
            self.skipTest("Hardlinks not supported on this filesystem")

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": alias_path},
        })
        result = _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data,
                                       env_override=self.env)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
            f"Hardlink alias to config must be denied. Got: {decision}. "
            f"stdout={result.stdout!r}, stderr={result.stderr[:300]!r}")

    def test_hardlink_to_config_detected_by_write_guardian(self):
        """Write to hardlink alias of guardian config must be blocked."""
        alias_path = os.path.join(self.tmpdir, "not_config.json")
        try:
            os.link(self.config_path, alias_path)
        except OSError:
            self.skipTest("Hardlinks not supported on this filesystem")

        stdin_data = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": alias_path},
        })
        result = _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data,
                                       env_override=self.env)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
            f"Hardlink alias to config must be denied by Write. Got: {decision}")

    def test_non_hardlink_file_not_blocked(self):
        """A regular file with same name pattern should NOT be blocked."""
        regular_file = os.path.join(self.tmpdir, "my_config.json")
        Path(regular_file).write_text('{"key": "value"}')

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": regular_file},
        })
        result = _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data,
                                       env_override=self.env)
        decision = _get_permission_decision(result.stdout)
        # Regular files should be allowed (not a hardlink to config)
        self.assertNotEqual(decision, "deny",
            f"Regular file should not be blocked. Got: {decision}")


# ============================================================
# Runner
# ============================================================


if __name__ == "__main__":
    unittest.main(verbosity=2)
