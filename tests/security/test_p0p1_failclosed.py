#!/usr/bin/env python3
"""Tests for P0/P1 fail-closed security fixes.

Tests that guardian functions fail-closed (deny) on errors/missing config,
rather than fail-open (allow).

Run: python -m pytest tests/security/test_p0p1_failclosed.py -v
  or: python3 tests/security/test_p0p1_failclosed.py
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
    match_no_delete,
    run_path_guardian_hook,
    deny_response,
)

# Constants
REPO_ROOT = _bootstrap._REPO_ROOT
BASH_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")
WRITE_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "write_guardian.py")
READ_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "read_guardian.py")
EDIT_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "edit_guardian.py")
GUARDIAN_CONFIG_PATH = str(REPO_ROOT / "assets" / "guardian.default.json")


def _clear_config_cache():
    """Clear _guardian_utils config cache so tests start fresh."""
    import _guardian_utils
    _guardian_utils._config_cache = None
    _guardian_utils._using_fallback_config = False
    _guardian_utils._active_config_path = None


def _make_hook_input(tool_name, file_path):
    """Create JSON hook input for a tool call."""
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    })


def _make_bash_hook_input(command):
    """Create JSON hook input for a Bash tool call."""
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
    })


def _run_hook_subprocess(script_path, stdin_data, env_override=None):
    """Run a guardian hook script as a subprocess.

    Args:
        script_path: Path to the hook script.
        stdin_data: JSON string to pipe to stdin.
        env_override: Dict of env vars to set. If None, uses current env.

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


def _parse_hook_response(stdout):
    """Parse hook response JSON from stdout.

    Returns:
        Parsed dict, or None if no valid JSON.
    """
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _get_permission_decision(stdout):
    """Extract permissionDecision from hook response.

    Returns:
        'deny', 'allow', 'ask', or None if not found.
    """
    resp = _parse_hook_response(stdout)
    if resp is None:
        return None
    return resp.get("hookSpecificOutput", {}).get("permissionDecision")


# ============================================================
# P0-A: is_path_within_project() Fail-Closed
# ============================================================


class TestP0A_IsPathWithinProject_FailClosed(unittest.TestCase):
    """P0-A: is_path_within_project() must fail-closed (return False)
    when project dir is unset or when exceptions occur."""

    def setUp(self):
        _clear_config_cache()

    def test_no_project_dir_returns_false(self):
        """With CLAUDE_PROJECT_DIR unset, is_path_within_project must return False."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            result = is_path_within_project("/some/path")
        self.assertFalse(result, "Must fail-closed (False) when CLAUDE_PROJECT_DIR is unset")

    def test_no_project_dir_stderr_warning(self):
        """Verify stderr warning is emitted when CLAUDE_PROJECT_DIR is unset."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        captured = StringIO()
        with patch.dict(os.environ, env, clear=True), \
             patch("sys.stderr", captured):
            is_path_within_project("/some/path")
        self.assertIn("GUARDIAN WARN", captured.getvalue())
        self.assertIn("No project dir", captured.getvalue())

    def test_exception_during_resolution_returns_false(self):
        """If expand_path raises an exception, must return False (fail-closed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.expand_path", side_effect=OSError("mock resolution error")):
                    result = is_path_within_project("/some/path")
        self.assertFalse(result, "Must fail-closed (False) when expand_path raises")

    def test_normal_path_inside_project_returns_true(self):
        """Sanity check: path inside project dir returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = is_path_within_project(str(test_file))
            self.assertTrue(result, "Path inside project should return True")

    def test_normal_path_outside_project_returns_false(self):
        """Sanity check: path outside project dir returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = is_path_within_project("/etc/passwd")
            self.assertFalse(result, "Path outside project should return False")

    def test_empty_string_with_no_project_dir_returns_false(self):
        """Edge case: empty path with no project dir returns False."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            result = is_path_within_project("")
        self.assertFalse(result)


# ============================================================
# P0-B: is_symlink_escape() Fail-Closed
# ============================================================


class TestP0B_IsSymlinkEscape_FailClosed(unittest.TestCase):
    """P0-B: is_symlink_escape() must fail-closed (return True)
    when project dir is unset or when exceptions occur."""

    def setUp(self):
        _clear_config_cache()

    def test_no_project_dir_returns_true(self):
        """With CLAUDE_PROJECT_DIR unset, is_symlink_escape must return True (assume escape)."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            result = is_symlink_escape("/some/path")
        self.assertTrue(result, "Must fail-closed (True = escape assumed) when CLAUDE_PROJECT_DIR is unset")

    def test_no_project_dir_stderr_warning(self):
        """Verify stderr warning is emitted when CLAUDE_PROJECT_DIR is unset."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        captured = StringIO()
        with patch.dict(os.environ, env, clear=True), \
             patch("sys.stderr", captured):
            is_symlink_escape("/some/path")
        self.assertIn("GUARDIAN WARN", captured.getvalue())
        self.assertIn("No project dir", captured.getvalue())

    def test_exception_returns_true(self):
        """If symlink check raises an exception, must return True (assume escape)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Mock Path.expanduser to raise inside the try block
                with patch("_guardian_utils.Path.expanduser", side_effect=OSError("mock error")):
                    result = is_symlink_escape("/some/path")
            self.assertTrue(result, "Must fail-closed (True) when exception occurs")

    def test_non_symlink_returns_false(self):
        """Sanity check: normal file (not a symlink) returns False (no escape)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = is_symlink_escape(str(test_file))
            self.assertFalse(result, "Non-symlink should return False")

    def test_internal_symlink_returns_false(self):
        """Symlink pointing within project returns False (no escape)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "real_file.txt"
            target.touch()
            link = Path(tmpdir) / "link_to_real"
            link.symlink_to(target)
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = is_symlink_escape(str(link))
            self.assertFalse(result, "Symlink within project should return False")

    def test_external_symlink_returns_true(self):
        """Symlink pointing outside project returns True (escape detected)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink pointing to /tmp (outside this project dir)
            with tempfile.TemporaryDirectory() as external_dir:
                external_file = Path(external_dir) / "outside.txt"
                external_file.touch()
                link = Path(tmpdir) / "escape_link"
                link.symlink_to(external_file)
                with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                    _clear_config_cache()
                    result = is_symlink_escape(str(link))
                self.assertTrue(result, "Symlink outside project should return True")


# ============================================================
# P0-C: bash_guardian.py Fail-Closed on Missing Project Dir
# ============================================================


class TestP0C_BashGuardian_FailClosed(unittest.TestCase):
    """P0-C: bash_guardian.py must emit deny when CLAUDE_PROJECT_DIR is missing."""

    def test_no_project_dir_emits_deny(self):
        """Bash guardian with no CLAUDE_PROJECT_DIR must deny all commands."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_bash_hook_input("echo hello")
        result = _run_hook_subprocess(BASH_GUARDIAN_PATH, stdin_data, env_override=env)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(
            decision, "deny",
            f"Expected 'deny' but got '{decision}'. stdout={result.stdout!r}, stderr={result.stderr!r}"
        )

    def test_deny_has_meaningful_message(self):
        """Deny response must include a meaningful reason about missing project dir."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_bash_hook_input("echo hello")
        result = _run_hook_subprocess(BASH_GUARDIAN_PATH, stdin_data, env_override=env)
        resp = _parse_hook_response(result.stdout)
        self.assertIsNotNone(resp, "Response must be valid JSON")
        reason = resp.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        self.assertIn("project directory", reason.lower(),
                      f"Reason should mention project directory. Got: {reason}")

    def test_no_project_dir_stderr_warning(self):
        """Stderr should contain a warning about missing project dir."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_bash_hook_input("echo hello")
        result = _run_hook_subprocess(BASH_GUARDIAN_PATH, stdin_data, env_override=env)
        self.assertIn("GUARDIAN WARN", result.stderr,
                      f"Expected GUARDIAN WARN in stderr. Got: {result.stderr!r}")

    def test_dangerous_command_also_denied(self):
        """Even dangerous commands like rm -rf / are denied (not allowed) when no project dir."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_bash_hook_input("rm -rf /")
        result = _run_hook_subprocess(BASH_GUARDIAN_PATH, stdin_data, env_override=env)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         "Dangerous commands must also be denied when project dir is missing")


# ============================================================
# P1: noDeletePaths Enforcement in Write Tool Hook
# ============================================================


class TestP1_NoDeletePaths_WriteHook(unittest.TestCase):
    """P1: Write tool on existing noDeletePaths files must be blocked.
    Edit and Read on those files must remain allowed."""

    def _run_write_hook(self, file_path, project_dir):
        """Run the write guardian hook via subprocess."""
        stdin_data = _make_hook_input("Write", file_path)
        env = {k: v for k, v in os.environ.items()}
        env["CLAUDE_PROJECT_DIR"] = project_dir
        return _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data, env_override=env)

    def _run_edit_hook(self, file_path, project_dir):
        """Run the edit guardian hook via subprocess."""
        stdin_data = _make_hook_input("Edit", file_path)
        env = {k: v for k, v in os.environ.items()}
        env["CLAUDE_PROJECT_DIR"] = project_dir
        return _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data, env_override=env)

    def _run_read_hook(self, file_path, project_dir):
        """Run the read guardian hook via subprocess."""
        stdin_data = _make_hook_input("Read", file_path)
        env = {k: v for k, v in os.environ.items()}
        env["CLAUDE_PROJECT_DIR"] = project_dir
        return _run_hook_subprocess(READ_GUARDIAN_PATH, stdin_data, env_override=env)

    def _setup_project_with_config(self, tmpdir, files=None):
        """Create a minimal project with guardian config and optional files.

        Args:
            tmpdir: Temporary directory to use as project root.
            files: List of filenames to create in the project.

        Returns:
            Path to the temporary project directory.
        """
        project = Path(tmpdir)
        # Create .git dir so get_project_dir() validates
        (project / ".git").mkdir(exist_ok=True)
        # Copy default config to the expected location
        config_dir = project / ".claude" / "guardian"
        config_dir.mkdir(parents=True, exist_ok=True)
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        with open(config_dir / "config.json", "w") as f:
            json.dump(config, f)
        # Create requested files
        if files:
            for name in files:
                fpath = project / name
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(f"content of {name}\n")
        return str(project)

    def test_write_existing_nodelete_file_blocked(self):
        """Write tool on existing noDeletePaths file must be DENIED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=["CLAUDE.md"])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            result = self._run_write_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Write on existing noDelete file must be denied. Got: {decision}. "
                f"stdout={result.stdout!r}, stderr={result.stderr!r}"
            )

    def test_write_existing_nodelete_has_overwrite_message(self):
        """Deny message should mention 'Protected from overwrite'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=["README.md"])
            file_path = str(Path(project_dir) / "README.md")
            result = self._run_write_hook(file_path, project_dir)
            resp = _parse_hook_response(result.stdout)
            self.assertIsNotNone(resp)
            reason = resp.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            self.assertIn("overwrite", reason.lower(),
                          f"Deny reason should mention overwrite. Got: {reason}")

    def test_write_new_nodelete_file_allowed(self):
        """Write tool creating a NEW file matching noDeletePaths pattern must be ALLOWED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Do NOT create CLAUDE.md -- it doesn't exist yet
            project_dir = self._setup_project_with_config(tmpdir, files=[])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            result = self._run_write_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            # Should be allow (or None = no response = implicit allow)
            self.assertIn(
                decision, ("allow", None),
                f"Write to create new noDelete file must be allowed. Got: {decision}. "
                f"stdout={result.stdout!r}"
            )

    def test_edit_nodelete_file_allowed(self):
        """Edit tool on noDeletePaths file must be ALLOWED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=["CLAUDE.md"])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            result = self._run_edit_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            # Edit should be allowed -- noDelete only blocks Write
            self.assertIn(
                decision, ("allow", None),
                f"Edit on noDelete file must be allowed. Got: {decision}. "
                f"stdout={result.stdout!r}"
            )

    def test_read_nodelete_file_allowed(self):
        """Read tool on noDeletePaths file must be ALLOWED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=["CLAUDE.md"])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            result = self._run_read_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            self.assertIn(
                decision, ("allow", None),
                f"Read on noDelete file must be allowed. Got: {decision}. "
                f"stdout={result.stdout!r}"
            )

    def test_write_non_nodelete_file_allowed(self):
        """Write tool on a file NOT in noDeletePaths must be ALLOWED (no regression)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=["src/app.py"])
            file_path = str(Path(project_dir) / "src" / "app.py")
            result = self._run_write_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            self.assertIn(
                decision, ("allow", None),
                f"Write on non-noDelete file must be allowed. Got: {decision}. "
                f"stdout={result.stdout!r}"
            )

    def test_write_existing_gitignore_blocked(self):
        """Write tool on existing .gitignore (noDeletePaths) must be DENIED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=[".gitignore"])
            file_path = str(Path(project_dir) / ".gitignore")
            result = self._run_write_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Write on existing .gitignore must be denied. Got: {decision}. "
                f"stdout={result.stdout!r}"
            )

    def test_write_existing_packagejson_blocked(self):
        """Write tool on existing package.json (noDeletePaths) must be DENIED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self._setup_project_with_config(tmpdir, files=["package.json"])
            file_path = str(Path(project_dir) / "package.json")
            result = self._run_write_hook(file_path, project_dir)
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Write on existing package.json must be denied. Got: {decision}. "
                f"stdout={result.stdout!r}"
            )


# ============================================================
# Integration: Defense in Depth
# ============================================================


class TestIntegration_DefenseInDepth(unittest.TestCase):
    """Integration tests: verify defense-in-depth layering."""

    def setUp(self):
        _clear_config_cache()

    def test_expand_path_exception_caught_by_is_path_within_project(self):
        """expand_path raises -> outer except in is_path_within_project -> returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.expand_path", side_effect=RuntimeError("resolution failed")):
                    result = is_path_within_project("/some/crafted/path")
        self.assertFalse(result,
                         "is_path_within_project must catch expand_path exceptions and return False")

    def test_oserror_in_expand_path_caught(self):
        """OSError during expand_path -> is_path_within_project returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.expand_path", side_effect=OSError("permission denied")):
                    result = is_path_within_project("/restricted/path")
        self.assertFalse(result, "OSError in expand_path must result in False")

    def test_write_hook_no_project_dir_denies(self):
        """Write guardian with no CLAUDE_PROJECT_DIR must deny."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_hook_input("Write", "/etc/passwd")
        result = _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data, env_override=env)
        decision = _get_permission_decision(result.stdout)
        # The path check will fail-closed because no project dir
        self.assertEqual(decision, "deny",
                         f"Write with no project dir must deny. Got: {decision}")

    def test_read_hook_no_project_dir_denies(self):
        """Read guardian with no CLAUDE_PROJECT_DIR must deny."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_hook_input("Read", "/etc/passwd")
        result = _run_hook_subprocess(READ_GUARDIAN_PATH, stdin_data, env_override=env)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Read with no project dir must deny. Got: {decision}")

    def test_edit_hook_no_project_dir_denies(self):
        """Edit guardian with no CLAUDE_PROJECT_DIR must deny."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        stdin_data = _make_hook_input("Edit", "/etc/passwd")
        result = _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data, env_override=env)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Edit with no project dir must deny. Got: {decision}")

    def test_symlink_escape_plus_path_check_both_failclosed(self):
        """Both is_symlink_escape and is_path_within_project fail-closed simultaneously
        when CLAUDE_PROJECT_DIR is unset."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(is_symlink_escape("/any/path"),
                            "is_symlink_escape must be True (fail-closed)")
            self.assertFalse(is_path_within_project("/any/path"),
                             "is_path_within_project must be False (fail-closed)")


# ============================================================
# P0-C Extra: Write/Read/Edit Guardians Subprocess Tests
# (Complements bash_guardian tests with tool hook scripts)
# ============================================================


class TestP0C_ToolGuardians_FailClosed(unittest.TestCase):
    """Verify that Write/Read/Edit guardian scripts deny on malformed input."""

    def test_write_guardian_malformed_json_denies(self):
        """Write guardian must deny on malformed JSON input."""
        result = _run_hook_subprocess(WRITE_GUARDIAN_PATH, "not valid json{{{")
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Malformed JSON must be denied. Got: {decision}")

    def test_read_guardian_malformed_json_denies(self):
        """Read guardian must deny on malformed JSON input."""
        result = _run_hook_subprocess(READ_GUARDIAN_PATH, "not valid json{{{")
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Malformed JSON must be denied. Got: {decision}")

    def test_edit_guardian_malformed_json_denies(self):
        """Edit guardian must deny on malformed JSON input."""
        result = _run_hook_subprocess(EDIT_GUARDIAN_PATH, "not valid json{{{")
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Malformed JSON must be denied. Got: {decision}")

    def test_write_guardian_null_byte_in_path_denies(self):
        """Write guardian must deny paths with null bytes."""
        stdin_data = _make_hook_input("Write", "/tmp/test\x00evil")
        result = _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data)
        decision = _get_permission_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Null byte in path must be denied. Got: {decision}")


# ============================================================
# Runner
# ============================================================


if __name__ == "__main__":
    unittest.main(verbosity=2)
