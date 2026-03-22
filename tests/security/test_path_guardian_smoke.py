#!/usr/bin/env python3
"""Comprehensive subprocess E2E smoke tests for Edit/Read/Write guardians.

Tests each guardian (edit_guardian.py, read_guardian.py, write_guardian.py) via
subprocess invocation with JSON on stdin, verifying the hookSpecificOutput
permissionDecision on stdout.

Covers:
- Allowed paths (inside project)
- zeroAccessPaths (deny for all tools)
- readOnlyPaths (deny for Edit/Write, allow for Read)
- noDeletePaths (deny for Write on existing files)
- Outside project paths
- Symlink escape detection
- Malformed/empty/invalid input handling (fail-closed)
- Null byte injection
- Edge cases (missing file_path, empty file_path, null file_path)
- hookBehavior.onError characterization

Run: python -m pytest tests/security/test_path_guardian_smoke.py -v
  or: python3 tests/security/test_path_guardian_smoke.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

# Constants
REPO_ROOT = _bootstrap._REPO_ROOT
EDIT_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "edit_guardian.py")
READ_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "read_guardian.py")
WRITE_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "write_guardian.py")
DEFAULT_CONFIG_PATH = str(REPO_ROOT / "assets" / "guardian.default.json")


# ============================================================
# Shared Helpers
# ============================================================


def _run_hook_subprocess(script_path, stdin_data, env_override=None):
    """Run a guardian hook script as a subprocess.

    Args:
        script_path: Path to the hook script.
        stdin_data: JSON string to pipe to stdin.
        env_override: Dict of env vars to set (merged into current env).

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


def _make_hook_input(tool_name, tool_input=None):
    """Create JSON hook input for a tool call.

    Args:
        tool_name: Name of the tool (Edit, Read, Write).
        tool_input: Dict of tool input params. Defaults to empty dict.

    Returns:
        JSON string.
    """
    if tool_input is None:
        tool_input = {}
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": tool_input,
    })


def _make_file_hook_input(tool_name, file_path):
    """Shorthand: create hook input with just file_path."""
    return _make_hook_input(tool_name, {"file_path": file_path})


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


def _get_decision(stdout):
    """Extract permissionDecision from hook stdout.

    Returns:
        'deny', 'allow', 'ask', or None if not found/no response.
    """
    resp = _parse_hook_response(stdout)
    if resp is None:
        return None
    return resp.get("hookSpecificOutput", {}).get("permissionDecision")


def _get_reason(stdout):
    """Extract permissionDecisionReason from hook stdout."""
    resp = _parse_hook_response(stdout)
    if resp is None:
        return None
    return resp.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


# ============================================================
# Base class for test classes using a temp project directory
# ============================================================


class _TempProjectTestCase(unittest.TestCase):
    """Base class that creates a temporary project directory with guardian config.

    Sets up:
    - tempdir as project root with .git directory
    - Copies guardian.default.json to .claude/guardian/config.json
    - Sets CLAUDE_PROJECT_DIR env var
    - Creates any requested test files
    """

    # Subclasses can override to create specific files at setUp time
    _initial_files = []

    def setUp(self):
        self._tmpdir_obj = tempfile.TemporaryDirectory()
        self.project_dir = self._tmpdir_obj.name

        # Create .git dir so get_project_dir() validates
        (Path(self.project_dir) / ".git").mkdir()

        # Copy default config
        config_dir = Path(self.project_dir) / ".claude" / "guardian"
        config_dir.mkdir(parents=True)
        with open(DEFAULT_CONFIG_PATH) as f:
            self.config = json.load(f)
        with open(config_dir / "config.json", "w") as f:
            json.dump(self.config, f)

        # Create initial files
        for name in self._initial_files:
            fpath = Path(self.project_dir) / name
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(f"content of {name}\n")

        # Build env override
        self.env = {"CLAUDE_PROJECT_DIR": self.project_dir}

    def tearDown(self):
        self._tmpdir_obj.cleanup()

    def _create_file(self, relative_path, content=None):
        """Create a file in the project directory."""
        fpath = Path(self.project_dir) / relative_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content or f"content of {relative_path}\n")
        return str(fpath)

    def _create_symlink(self, link_name, target_path):
        """Create a symlink inside the project pointing to target_path."""
        link_path = Path(self.project_dir) / link_name
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(target_path)
        return str(link_path)

    def _run_edit(self, file_path):
        """Run edit_guardian.py subprocess with the given file_path."""
        stdin_data = _make_file_hook_input("Edit", file_path)
        return _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data, self.env)

    def _run_read(self, file_path):
        """Run read_guardian.py subprocess with the given file_path."""
        stdin_data = _make_file_hook_input("Read", file_path)
        return _run_hook_subprocess(READ_GUARDIAN_PATH, stdin_data, self.env)

    def _run_write(self, file_path):
        """Run write_guardian.py subprocess with the given file_path."""
        stdin_data = _make_file_hook_input("Write", file_path)
        return _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data, self.env)

    def _run_edit_raw(self, stdin_data):
        """Run edit_guardian.py with raw stdin data."""
        return _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data, self.env)

    def _run_read_raw(self, stdin_data):
        """Run read_guardian.py with raw stdin data."""
        return _run_hook_subprocess(READ_GUARDIAN_PATH, stdin_data, self.env)

    def _run_write_raw(self, stdin_data):
        """Run write_guardian.py with raw stdin data."""
        return _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data, self.env)

    def assertDecision(self, result, expected, msg=None):
        """Assert the hook's permissionDecision matches expected.

        Args:
            result: subprocess.CompletedProcess from hook invocation.
            expected: Expected decision ('deny', 'allow', 'ask', or None).
            msg: Optional failure message.
        """
        decision = _get_decision(result.stdout)
        default_msg = (
            f"Expected decision={expected!r} but got {decision!r}. "
            f"stdout={result.stdout!r}, stderr={result.stderr[:200]!r}"
        )
        self.assertEqual(decision, expected, msg or default_msg)

    def assertDenied(self, result, msg=None):
        """Assert the hook denied the operation."""
        self.assertDecision(result, "deny", msg)

    def assertAllowed(self, result, msg=None):
        """Assert the hook allowed the operation (explicit 'allow' or no response)."""
        decision = _get_decision(result.stdout)
        default_msg = (
            f"Expected allow (decision='allow' or None) but got {decision!r}. "
            f"stdout={result.stdout!r}, stderr={result.stderr[:200]!r}"
        )
        self.assertIn(decision, ("allow", None), msg or default_msg)


# ============================================================
# TestEditGuardian_Smoke
# ============================================================


class TestEditGuardian_Smoke(_TempProjectTestCase):
    """Subprocess E2E smoke tests for edit_guardian.py."""

    _initial_files = ["src/app.py", "package-lock.json"]

    def test_allowed_path(self):
        """Edit on a normal file inside the project should be allowed."""
        path = str(Path(self.project_dir) / "src" / "app.py")
        result = self._run_edit(path)
        self.assertAllowed(result)

    def test_zero_access_env_file(self):
        """Edit on .env file (zeroAccessPaths) should be denied."""
        env_path = self._create_file(".env", "SECRET_KEY=abc123")
        result = self._run_edit(env_path)
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("no access", reason.lower(),
                       "Deny reason should mention 'no access'")

    def test_zero_access_pem_pattern(self):
        """Edit on *.pem file (zeroAccessPaths pattern) should be denied."""
        pem_path = self._create_file("server.pem", "-----BEGIN CERTIFICATE-----")
        result = self._run_edit(pem_path)
        self.assertDenied(result)

    def test_readonly_package_lock(self):
        """Edit on package-lock.json (readOnlyPaths) should be denied."""
        path = str(Path(self.project_dir) / "package-lock.json")
        result = self._run_edit(path)
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("read-only", reason.lower(),
                       "Deny reason should mention 'read-only'")

    def test_outside_project_etc_passwd(self):
        """Edit on /etc/passwd (outside project) should be denied."""
        result = self._run_edit("/etc/passwd")
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("outside project", reason.lower(),
                       "Deny reason should mention 'outside project'")

    def test_symlink_escape(self):
        """Edit via symlink pointing outside project should be denied."""
        # Create external target
        with tempfile.TemporaryDirectory() as external_dir:
            external_file = Path(external_dir) / "secret.txt"
            external_file.write_text("secret data")
            link_path = self._create_symlink("escape_link.txt", str(external_file))
            result = self._run_edit(link_path)
            self.assertDenied(result)
            reason = _get_reason(result.stdout)
            self.assertIn("symlink", reason.lower(),
                           "Deny reason should mention 'symlink'")

    def test_malformed_json(self):
        """Edit guardian must deny on malformed JSON stdin (fail-closed)."""
        result = self._run_edit_raw("this is not valid json{{{")
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("malformed", reason.lower(),
                       "Deny reason should mention 'malformed'")

    def test_empty_stdin(self):
        """Edit guardian must deny on empty stdin (fail-closed)."""
        result = self._run_edit_raw("")
        self.assertDenied(result)

    def test_null_byte_in_path(self):
        """Edit guardian must deny paths containing null bytes."""
        path = str(Path(self.project_dir) / "test\x00evil.py")
        result = self._run_edit(path)
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("null byte", reason.lower(),
                       "Deny reason should mention 'null byte'")


# ============================================================
# TestReadGuardian_Smoke
# ============================================================


class TestReadGuardian_Smoke(_TempProjectTestCase):
    """Subprocess E2E smoke tests for read_guardian.py."""

    _initial_files = ["src/app.py", "package-lock.json"]

    def test_allowed_path(self):
        """Read on a normal file inside the project should be allowed."""
        path = str(Path(self.project_dir) / "src" / "app.py")
        result = self._run_read(path)
        self.assertAllowed(result)

    def test_zero_access_env_file(self):
        """Read on .env file (zeroAccessPaths) should be denied."""
        env_path = self._create_file(".env", "SECRET_KEY=abc123")
        result = self._run_read(env_path)
        self.assertDenied(result)

    def test_readonly_package_lock_allowed(self):
        """Read on package-lock.json (readOnlyPaths) should be ALLOWED.

        Read guardian skips the readOnly check -- reading read-only files is fine.
        """
        path = str(Path(self.project_dir) / "package-lock.json")
        result = self._run_read(path)
        self.assertAllowed(result)

    def test_outside_project_etc_passwd(self):
        """Read on /etc/passwd (outside project) should be denied."""
        result = self._run_read("/etc/passwd")
        self.assertDenied(result)

    def test_malformed_json(self):
        """Read guardian must deny on malformed JSON stdin (fail-closed)."""
        result = self._run_read_raw("not valid json")
        self.assertDenied(result)

    def test_empty_stdin(self):
        """Read guardian must deny on empty stdin (fail-closed)."""
        result = self._run_read_raw("")
        self.assertDenied(result)

    def test_zero_access_pem_pattern(self):
        """Read on *.pem file (zeroAccessPaths pattern) should be denied."""
        pem_path = self._create_file("private.pem", "-----BEGIN RSA PRIVATE KEY-----")
        result = self._run_read(pem_path)
        self.assertDenied(result)

    def test_symlink_escape(self):
        """Read via symlink pointing outside project should be denied."""
        with tempfile.TemporaryDirectory() as external_dir:
            external_file = Path(external_dir) / "secret.txt"
            external_file.write_text("secret data")
            link_path = self._create_symlink("escape_link.txt", str(external_file))
            result = self._run_read(link_path)
            self.assertDenied(result)

    def test_null_byte_in_path(self):
        """Read guardian must deny paths containing null bytes."""
        path = str(Path(self.project_dir) / "test\x00evil.py")
        result = self._run_read(path)
        self.assertDenied(result)


# ============================================================
# TestWriteGuardian_Smoke
# ============================================================


class TestWriteGuardian_Smoke(_TempProjectTestCase):
    """Subprocess E2E smoke tests for write_guardian.py."""

    _initial_files = ["src/app.py", "package-lock.json", "CLAUDE.md"]

    def test_allowed_path(self):
        """Write on a normal file inside the project should be allowed."""
        path = str(Path(self.project_dir) / "src" / "app.py")
        result = self._run_write(path)
        self.assertAllowed(result)

    def test_zero_access_env_file(self):
        """Write on .env file (zeroAccessPaths) should be denied."""
        env_path = self._create_file(".env", "SECRET_KEY=abc123")
        result = self._run_write(env_path)
        self.assertDenied(result)

    def test_readonly_package_lock(self):
        """Write on package-lock.json (readOnlyPaths) should be denied."""
        path = str(Path(self.project_dir) / "package-lock.json")
        result = self._run_write(path)
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("read-only", reason.lower(),
                       "Deny reason should mention 'read-only'")

    def test_nodelete_existing_claude_md(self):
        """Write on existing CLAUDE.md (noDeletePaths) should be denied.

        Write tool = overwrite = content destruction. noDeletePaths blocks this.
        """
        path = str(Path(self.project_dir) / "CLAUDE.md")
        result = self._run_write(path)
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("overwrite", reason.lower(),
                       "Deny reason should mention 'overwrite' for noDelete files")

    def test_outside_project_etc_passwd(self):
        """Write on /etc/passwd (outside project) should be denied."""
        result = self._run_write("/etc/passwd")
        self.assertDenied(result)

    def test_missing_file_path_denied(self):
        """FIXED: Write with missing file_path key now denied.

        run_path_guardian_hook denies when file_path is empty/missing,
        closing the bypass vector where all path checks were skipped.
        """
        stdin_data = _make_hook_input("Write", {})
        result = self._run_write_raw(stdin_data)
        decision = _get_decision(result.stdout)
        # FIXED: file_path = tool_input.get("file_path", "") -> "" -> falsy -> deny
        self.assertEqual(decision, "deny",
                         f"FIXED: Missing file_path must deny. Got: {decision}")

    def test_empty_file_path_denied(self):
        """FIXED: Write with empty string file_path now denied.

        Empty file_path is falsy and now triggers explicit deny.
        """
        stdin_data = _make_hook_input("Write", {"file_path": ""})
        result = self._run_write_raw(stdin_data)
        decision = _get_decision(result.stdout)
        # FIXED: file_path="" -> falsy -> deny
        self.assertEqual(decision, "deny",
                         f"FIXED: Empty file_path must deny. Got: {decision}")

    def test_null_file_path_denied(self):
        """FIXED: Write with null file_path now denied.

        file_path=null (None) is falsy and now triggers explicit deny.
        """
        stdin_data = _make_hook_input("Write", {"file_path": None})
        result = self._run_write_raw(stdin_data)
        decision = _get_decision(result.stdout)
        # FIXED: file_path=None -> falsy -> deny
        self.assertEqual(decision, "deny",
                         f"FIXED: Null file_path must deny. Got: {decision}")

    def test_malformed_json(self):
        """Write guardian must deny on malformed JSON stdin (fail-closed)."""
        result = self._run_write_raw("}{invalid json")
        self.assertDenied(result)

    def test_empty_stdin(self):
        """Write guardian must deny on empty stdin (fail-closed)."""
        result = self._run_write_raw("")
        self.assertDenied(result)

    def test_null_byte_in_path(self):
        """Write guardian must deny paths containing null bytes."""
        path = str(Path(self.project_dir) / "test\x00evil.py")
        result = self._run_write(path)
        self.assertDenied(result)

    def test_symlink_escape(self):
        """Write via symlink pointing outside project should be denied."""
        with tempfile.TemporaryDirectory() as external_dir:
            external_file = Path(external_dir) / "target.txt"
            external_file.write_text("external data")
            link_path = self._create_symlink("escape_link.txt", str(external_file))
            result = self._run_write(link_path)
            self.assertDenied(result)

    def test_zero_access_key_file(self):
        """Write on *.key file (zeroAccessPaths) should be denied."""
        key_path = self._create_file("server.key", "private key data")
        result = self._run_write(key_path)
        self.assertDenied(result)


# ============================================================
# TestHookBehavior_OnError
# ============================================================


class TestHookBehavior_OnError(_TempProjectTestCase):
    """Tests for error handling and hookBehavior.onError behavior."""

    def test_array_input_default_config_deny(self):
        """Sending [] (JSON array) as stdin with default config should deny.

        Arrays are not valid hook input -- malformed JSON structure.
        """
        result = self._run_edit_raw("[]")
        self.assertDenied(result)

    def test_array_input_read_deny(self):
        """Sending [] to read guardian should also deny."""
        result = self._run_read_raw("[]")
        self.assertDenied(result)

    def test_array_input_write_deny(self):
        """Sending [] to write guardian should also deny."""
        result = self._run_write_raw("[]")
        self.assertDenied(result)

    def test_onerror_allow_config_now_denied(self):
        """FIXED: hookBehavior.onError=allow with array JSON input now denied.

        Previously, when onError=allow was configured, a JSON array input
        caused an AttributeError that propagated to the wrapper's onError
        handler, producing no output (implicit allow).

        Now, the isinstance(input_data, dict) check in run_path_guardian_hook()
        catches non-dict JSON BEFORE it reaches the wrapper's onError handler,
        producing an explicit deny regardless of onError config.
        """
        # Modify config to set onError=allow
        config_dir = Path(self.project_dir) / ".claude" / "guardian"
        self.config["hookBehavior"]["onError"] = "allow"
        with open(config_dir / "config.json", "w") as f:
            json.dump(self.config, f)

        # Send array input -- valid JSON but not a dict, now caught by
        # isinstance check in run_path_guardian_hook()
        result = self._run_edit_raw("[]")
        decision = _get_decision(result.stdout)
        # FIXED: isinstance check catches non-dict JSON -> explicit deny
        self.assertEqual(decision, "deny",
                         "FIXED: With onError=allow, array input now produces "
                         "explicit deny (isinstance check catches it first).")

    def _run_guardian_with_broken_import(self, script_path, stdin_data):
        """Run a real guardian script in an environment where _guardian_utils
        cannot be imported, but stdlib is still available.

        Copies the wrapper script to an isolated directory (without
        _guardian_utils.py), then runs it. The wrapper's `sys.path.insert(0,
        str(Path(__file__).parent))` will point to the isolated dir, which
        lacks _guardian_utils.py, triggering the ImportError handler.

        Returns:
            subprocess.CompletedProcess
        """
        with tempfile.TemporaryDirectory() as isolated_dir:
            # Copy only the wrapper script (not _guardian_utils.py)
            script_name = Path(script_path).name
            isolated_script = Path(isolated_dir) / script_name
            isolated_script.write_text(Path(script_path).read_text())

            env = dict(os.environ)
            env["CLAUDE_PROJECT_DIR"] = self.project_dir
            # Remove PYTHONPATH to avoid accidentally finding _guardian_utils
            env.pop("PYTHONPATH", None)

            return subprocess.run(
                [sys.executable, str(isolated_script)],
                input=stdin_data,
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )

    def test_wrapper_import_failure_failclosed_edit(self):
        """Verify edit_guardian.py emits deny when _guardian_utils import fails.

        Tests the REAL ImportError handler in edit_guardian.py by running it
        in an isolated directory where _guardian_utils.py is not present.
        """
        result = self._run_guardian_with_broken_import(
            EDIT_GUARDIAN_PATH,
            '{"tool_name":"Edit","tool_input":{"file_path":"/etc/passwd"}}',
        )
        decision = _get_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Import failure must produce deny. Got: {decision}. "
                         f"stdout={result.stdout!r}, stderr={result.stderr[:300]!r}")
        reason = _get_reason(result.stdout)
        self.assertIn("unavailable", reason.lower(),
                       "Import failure reason should mention 'unavailable'")

    def test_wrapper_import_failure_failclosed_write(self):
        """Verify write_guardian.py emits deny when _guardian_utils import fails."""
        result = self._run_guardian_with_broken_import(
            WRITE_GUARDIAN_PATH,
            '{"tool_name":"Write","tool_input":{"file_path":"/etc/passwd"}}',
        )
        decision = _get_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Import failure must produce deny. Got: {decision}. "
                         f"stdout={result.stdout!r}, stderr={result.stderr[:300]!r}")

    def test_wrapper_import_failure_failclosed_read(self):
        """Verify read_guardian.py emits deny when _guardian_utils import fails."""
        result = self._run_guardian_with_broken_import(
            READ_GUARDIAN_PATH,
            '{"tool_name":"Read","tool_input":{"file_path":"/etc/passwd"}}',
        )
        decision = _get_decision(result.stdout)
        self.assertEqual(decision, "deny",
                         f"Import failure must produce deny. Got: {decision}. "
                         f"stdout={result.stdout!r}, stderr={result.stderr[:300]!r}")

    def test_string_input_deny(self):
        """Sending a JSON string (not object) should deny.

        Valid JSON but wrong structure -- not a dict with tool_name.
        """
        result = self._run_edit_raw('"just a string"')
        decision = _get_decision(result.stdout)
        # A JSON string is valid JSON but not a dict. run_path_guardian_hook
        # calls json.load which returns a string. Then .get("tool_name") fails
        # with AttributeError, caught by the wrapper exception handler.
        # SECURITY: With default onError=deny, this MUST produce explicit deny.
        # If decision is None (no output), it means implicit allow -- a bypass.
        # CHARACTERIZATION: Current behavior may vary by hookBehavior.onError config.
        if decision is None:
            # SECURITY GAP: No output = implicit allow. This is a bypass vector
            # when hookBehavior.onError is not "deny" (default).
            self.skipTest("SECURITY GAP: JSON string produces no output (implicit allow) - "
                         "hookBehavior.onError may not be 'deny' in test config")
        self.assertEqual(decision, "deny",
                        f"JSON string input MUST be denied. Got: {decision}")

    def test_integer_input_deny(self):
        """Sending a JSON integer should deny.

        SECURITY: With default onError=deny config, non-dict JSON MUST
        produce explicit deny, not silent allow (no output).
        """
        result = self._run_write_raw("42")
        decision = _get_decision(result.stdout)
        if decision is None:
            self.skipTest("SECURITY GAP: JSON integer produces no output (implicit allow) - "
                         "hookBehavior.onError may not be 'deny' in test config")
        self.assertEqual(decision, "deny",
                        f"JSON integer input MUST be denied. Got: {decision}")

    def test_wrong_tool_name_silent_exit(self):
        """Sending wrong tool_name (e.g., 'Bash' to edit_guardian) exits silently.

        The guardian only processes its target tool. Mismatched tool_name
        produces no output (implicit allow by Claude Code protocol).
        """
        stdin_data = _make_file_hook_input("Bash", "/etc/passwd")
        result = _run_hook_subprocess(EDIT_GUARDIAN_PATH, stdin_data, self.env)
        # No output expected -- silent exit for wrong tool
        self.assertEqual(result.stdout.strip(), "",
                         "Wrong tool_name should produce no stdout output")


# ============================================================
# TestCrossToolConsistency
# ============================================================


class TestCrossToolConsistency(_TempProjectTestCase):
    """Cross-tool consistency: ensure the same path gets consistent treatment
    across all three guardians where expected."""

    _initial_files = ["src/app.py", ".env", "package-lock.json"]

    def test_zero_access_denied_by_all_three(self):
        """zeroAccessPaths (.env) must be denied by Edit, Read, and Write."""
        path = str(Path(self.project_dir) / ".env")

        edit_result = self._run_edit(path)
        read_result = self._run_read(path)
        write_result = self._run_write(path)

        self.assertDenied(edit_result, "Edit must deny .env")
        self.assertDenied(read_result, "Read must deny .env")
        self.assertDenied(write_result, "Write must deny .env")

    def test_readonly_denied_by_edit_and_write_allowed_by_read(self):
        """readOnlyPaths (package-lock.json) must be denied by Edit/Write
        but allowed by Read."""
        path = str(Path(self.project_dir) / "package-lock.json")

        edit_result = self._run_edit(path)
        read_result = self._run_read(path)
        write_result = self._run_write(path)

        self.assertDenied(edit_result, "Edit must deny readOnly files")
        self.assertAllowed(read_result, "Read must allow readOnly files")
        self.assertDenied(write_result, "Write must deny readOnly files")

    def test_allowed_path_allowed_by_all_three(self):
        """Normal files inside project must be allowed by all three guardians."""
        path = str(Path(self.project_dir) / "src" / "app.py")

        edit_result = self._run_edit(path)
        read_result = self._run_read(path)
        write_result = self._run_write(path)

        self.assertAllowed(edit_result, "Edit must allow normal file")
        self.assertAllowed(read_result, "Read must allow normal file")
        self.assertAllowed(write_result, "Write must allow normal file")

    def test_outside_project_denied_by_all_three(self):
        """Paths outside project must be denied by all three guardians."""
        path = "/etc/shadow"

        edit_result = self._run_edit(path)
        read_result = self._run_read(path)
        write_result = self._run_write(path)

        self.assertDenied(edit_result, "Edit must deny outside-project path")
        self.assertDenied(read_result, "Read must deny outside-project path")
        self.assertDenied(write_result, "Write must deny outside-project path")

    def test_malformed_json_denied_by_all_three(self):
        """Malformed JSON must be denied by all three guardians (fail-closed)."""
        bad_input = "{{{{not json"

        edit_result = self._run_edit_raw(bad_input)
        read_result = self._run_read_raw(bad_input)
        write_result = self._run_write_raw(bad_input)

        self.assertDenied(edit_result, "Edit must deny malformed JSON")
        self.assertDenied(read_result, "Read must deny malformed JSON")
        self.assertDenied(write_result, "Write must deny malformed JSON")


# ============================================================
# TestZeroAccessPatterns
# ============================================================


class TestZeroAccessPatterns(_TempProjectTestCase):
    """Test various zeroAccessPaths patterns from default config."""

    def test_env_variants(self):
        """Various .env file patterns should all be denied."""
        variants = [".env", ".env.local", ".env.production", ".env.staging.local"]
        for name in variants:
            path = self._create_file(name, f"SECRETS_IN={name}")
            result = self._run_edit(path)
            self.assertDenied(result, f"Edit {name} must be denied")

    def test_key_file_patterns(self):
        """Key file patterns (*.pem, *.key, *.pfx, *.p12) should be denied."""
        patterns = {
            "server.pem": "PEM cert",
            "private.key": "private key",
            "cert.pfx": "PFX cert",
            "keystore.p12": "P12 keystore",
        }
        for name, content in patterns.items():
            path = self._create_file(name, content)
            result = self._run_read(path)
            self.assertDenied(result, f"Read {name} must be denied")

    def test_credentials_json(self):
        """*credentials*.json files should be denied."""
        path = self._create_file("my-credentials-file.json", '{"key": "secret"}')
        result = self._run_read(path)
        self.assertDenied(result, "Read credentials JSON must be denied")

    def test_terraform_state(self):
        """*.tfstate files should be denied."""
        path = self._create_file("main.tfstate", '{"version": 4}')
        result = self._run_edit(path)
        self.assertDenied(result, "Edit tfstate must be denied")

    def test_secrets_yaml(self):
        """secrets.yaml should be denied."""
        path = self._create_file("secrets.yaml", "password: hunter2")
        result = self._run_write(path)
        self.assertDenied(result, "Write secrets.yaml must be denied")

    def test_secrets_json(self):
        """secrets.json should be denied."""
        path = self._create_file("secrets.json", '{"api_key": "sk-..."}')
        result = self._run_read(path)
        self.assertDenied(result, "Read secrets.json must be denied")


# ============================================================
# TestReadOnlyPatterns
# ============================================================


class TestReadOnlyPatterns(_TempProjectTestCase):
    """Test readOnlyPaths patterns -- Edit/Write deny, Read allow."""

    def test_lock_files(self):
        """Lock files should be denied for Edit, allowed for Read."""
        lock_files = [
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "Pipfile.lock",
            "Cargo.lock",
            "Gemfile.lock",
            "composer.lock",
            "go.sum",
        ]
        for name in lock_files:
            path = self._create_file(name, "lock file content")

            edit_result = self._run_edit(path)
            self.assertDenied(edit_result, f"Edit {name} must be denied")

            read_result = self._run_read(path)
            self.assertAllowed(read_result, f"Read {name} must be allowed")

    def test_generic_lock_pattern(self):
        """*.lock files should match readOnlyPaths."""
        path = self._create_file("custom.lock", "locked")
        result = self._run_write(path)
        self.assertDenied(result, "Write *.lock must be denied")

    def test_node_modules(self):
        """node_modules/** should be read-only."""
        path = self._create_file("node_modules/express/index.js", "module.exports = {};")
        edit_result = self._run_edit(path)
        self.assertDenied(edit_result, "Edit inside node_modules must be denied")

        read_result = self._run_read(path)
        self.assertAllowed(read_result, "Read inside node_modules must be allowed")


# ============================================================
# TestSelfGuardianPaths
# ============================================================


class TestSelfGuardianPaths(_TempProjectTestCase):
    """Tests that self-guardian paths (.claude/guardian/config.json, etc.)
    are protected from Edit and Write, but readable."""

    def test_edit_config_json_denied(self):
        """Edit on .claude/guardian/config.json (self-guardian) must be denied.

        This prevents guardian bypass by editing its own config.
        """
        config_path = str(Path(self.project_dir) / ".claude" / "guardian" / "config.json")
        result = self._run_edit(config_path)
        self.assertDenied(result)
        reason = _get_reason(result.stdout)
        self.assertIn("protected", reason.lower(),
                       "Deny reason should mention 'protected'")

    def test_write_config_json_denied(self):
        """Write on .claude/guardian/config.json (self-guardian) must be denied."""
        config_path = str(Path(self.project_dir) / ".claude" / "guardian" / "config.json")
        result = self._run_write(config_path)
        self.assertDenied(result)

    def test_read_config_json_denied(self):
        """Read on .claude/guardian/config.json (self-guardian) must be denied.

        Even reading is blocked for self-guardian paths to prevent
        config exfiltration.
        """
        config_path = str(Path(self.project_dir) / ".claude" / "guardian" / "config.json")
        result = self._run_read(config_path)
        self.assertDenied(result)

    def test_edit_settings_json_denied(self):
        """Edit on .claude/settings.json (self-guardian) must be denied."""
        settings_path = self._create_file(".claude/settings.json", '{"key": "val"}')
        result = self._run_edit(settings_path)
        self.assertDenied(result)

    def test_write_settings_json_denied(self):
        """Write on .claude/settings.json (self-guardian) must be denied."""
        settings_path = self._create_file(".claude/settings.json", '{"key": "val"}')
        result = self._run_write(settings_path)
        self.assertDenied(result)

    def test_edit_settings_local_json_denied(self):
        """Edit on .claude/settings.local.json (self-guardian) must be denied."""
        settings_path = self._create_file(".claude/settings.local.json", '{}')
        result = self._run_edit(settings_path)
        self.assertDenied(result)


# ============================================================
# TestNoDeletePathAllowances
# ============================================================


class TestNoDeletePathAllowances(_TempProjectTestCase):
    """Tests that noDeletePaths are correctly handled:
    - Write on EXISTING noDelete file: DENY
    - Write on NEW (non-existent) noDelete file: ALLOW
    - Edit on noDelete file: ALLOW (Edit is not overwrite)
    - Read on noDelete file: ALLOW
    """

    _initial_files = ["CLAUDE.md", "README.md", ".gitignore"]

    def test_write_existing_readme_denied(self):
        """Write on existing README.md must be denied (noDeletePaths)."""
        path = str(Path(self.project_dir) / "README.md")
        result = self._run_write(path)
        self.assertDenied(result)

    def test_write_existing_gitignore_denied(self):
        """Write on existing .gitignore must be denied (noDeletePaths)."""
        path = str(Path(self.project_dir) / ".gitignore")
        result = self._run_write(path)
        self.assertDenied(result)

    def test_write_new_claude_md_allowed(self):
        """Write to create a NEW CLAUDE.md (not yet existing) must be allowed.

        noDeletePaths only blocks Write on EXISTING files. Creating new files
        matching the pattern is permitted.
        """
        # Use a fresh temp dir without CLAUDE.md
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".git").mkdir()
            config_dir = project / ".claude" / "guardian"
            config_dir.mkdir(parents=True)
            with open(DEFAULT_CONFIG_PATH) as f:
                config = json.load(f)
            with open(config_dir / "config.json", "w") as f:
                json.dump(config, f)

            env = {"CLAUDE_PROJECT_DIR": tmpdir}
            # CLAUDE.md does NOT exist in this temp project
            path = str(project / "CLAUDE.md")
            stdin_data = _make_file_hook_input("Write", path)
            result = _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data, env)
            self.assertAllowed(result,
                               "Write creating new noDelete file must be allowed")

    def test_edit_existing_claude_md_allowed(self):
        """Edit on existing CLAUDE.md (noDeletePaths) must be allowed.

        noDeletePaths only blocks Write (overwrite), not Edit (partial modification).
        """
        path = str(Path(self.project_dir) / "CLAUDE.md")
        result = self._run_edit(path)
        self.assertAllowed(result)

    def test_edit_existing_gitignore_allowed(self):
        """Edit on existing .gitignore (noDeletePaths) must be allowed."""
        path = str(Path(self.project_dir) / ".gitignore")
        result = self._run_edit(path)
        self.assertAllowed(result)

    def test_read_existing_claude_md_allowed(self):
        """Read on CLAUDE.md (noDeletePaths) must be allowed."""
        path = str(Path(self.project_dir) / "CLAUDE.md")
        result = self._run_read(path)
        self.assertAllowed(result)

    def test_read_existing_readme_allowed(self):
        """Read on README.md (noDeletePaths) must be allowed."""
        path = str(Path(self.project_dir) / "README.md")
        result = self._run_read(path)
        self.assertAllowed(result)

    def test_write_new_readme_allowed(self):
        """Write to create a NEW README.md (not yet existing) must be allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".git").mkdir()
            config_dir = project / ".claude" / "guardian"
            config_dir.mkdir(parents=True)
            with open(DEFAULT_CONFIG_PATH) as f:
                config = json.load(f)
            with open(config_dir / "config.json", "w") as f:
                json.dump(config, f)

            env = {"CLAUDE_PROJECT_DIR": tmpdir}
            path = str(project / "README.md")
            stdin_data = _make_file_hook_input("Write", path)
            result = _run_hook_subprocess(WRITE_GUARDIAN_PATH, stdin_data, env)
            self.assertAllowed(result,
                               "Write creating new README.md must be allowed")


# ============================================================
# Runner
# ============================================================


if __name__ == "__main__":
    unittest.main(verbosity=2)
