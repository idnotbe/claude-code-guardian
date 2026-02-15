#!/usr/bin/env python3
"""Tests for advisory fail-closed security fixes.

Tests that advisory fixes (ADVISORY-1, ADVISORY-2, ADVISORY-3) produce correct
fail-closed behavior: normalization errors cause deny (not allow), variable
shadowing is eliminated, and TOCTOU races in noDelete checks fail-closed.

Run: python -m pytest tests/security/test_advisory_failclosed.py -v
  or: python3 tests/security/test_advisory_failclosed.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from _guardian_utils import (
    expand_path,
    normalize_path_for_matching,
    match_path_pattern,
    match_zero_access,
    match_read_only,
    match_no_delete,
    match_allowed_external_path,
    is_self_guardian_path,
    resolve_tool_path,
    deny_response,
)

# Constants
REPO_ROOT = _bootstrap._REPO_ROOT
BASH_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")
WRITE_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "write_guardian.py")
READ_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "read_guardian.py")
EDIT_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "edit_guardian.py")
GUARDIAN_UTILS_PATH = str(REPO_ROOT / "hooks" / "scripts" / "_guardian_utils.py")
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


def _run_hook_subprocess(script_path, stdin_data, env_override=None):
    """Run a guardian hook script as a subprocess."""
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
    """Parse hook response JSON from stdout."""
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _get_permission_decision(stdout):
    """Extract permissionDecision from hook response."""
    resp = _parse_hook_response(stdout)
    if resp is None:
        return None
    return resp.get("hookSpecificOutput", {}).get("permissionDecision")


def _setup_project_with_config(tmpdir, files=None):
    """Create a minimal project with guardian config and optional files."""
    project = Path(tmpdir)
    (project / ".git").mkdir(exist_ok=True)
    config_dir = project / ".claude" / "guardian"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(GUARDIAN_CONFIG_PATH) as f:
        config = json.load(f)
    with open(config_dir / "config.json", "w") as f:
        json.dump(config, f)
    if files:
        for name in files:
            fpath = project / name
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(f"content of {name}\n")
    return str(project)


# ============================================================
# ADVISORY-1: Variable Shadowing (nodelete_resolved)
# ============================================================


class TestAdvisory1_VariableShadowing(unittest.TestCase):
    """ADVISORY-1: The noDelete check block must use `nodelete_resolved`,
    not `resolved`, to avoid shadowing the outer resolve_tool_path result."""

    def test_nodelete_variable_not_shadowed(self):
        """Verify source code uses nodelete_resolved (not resolved) in noDelete check."""
        with open(GUARDIAN_UTILS_PATH) as f:
            source = f.read()

        # Find the noDelete check block by looking for the comment marker
        # and the expand_path call within it
        nodelete_block_start = source.find("No Delete (Write tool")
        self.assertNotEqual(nodelete_block_start, -1,
                            "Could not find noDelete check block in source")

        # Extract the noDelete block (from the comment to the next "Allow" section)
        allow_marker = source.find("========== Allow ==========", nodelete_block_start)
        self.assertNotEqual(allow_marker, -1,
                            "Could not find Allow marker after noDelete block")

        nodelete_block = source[nodelete_block_start:allow_marker]

        # The block should use nodelete_resolved, NOT bare resolved = expand_path(...)
        self.assertIn("nodelete_resolved", nodelete_block,
                       "noDelete block must use 'nodelete_resolved' variable name")

        # The variable assignment should specifically be nodelete_resolved = expand_path(...)
        self.assertIn("nodelete_resolved = expand_path(", nodelete_block,
                       "noDelete block must assign to 'nodelete_resolved'")

        # The .exists() call should be on nodelete_resolved
        self.assertIn("nodelete_resolved.exists()", nodelete_block,
                       "noDelete block must call .exists() on 'nodelete_resolved'")

        # There should NOT be a bare `resolved = expand_path(` in this block
        # (which would shadow the outer resolved variable)
        lines = nodelete_block.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("resolved = expand_path("):
                self.fail(
                    "Found 'resolved = expand_path(' in noDelete block -- "
                    "this shadows the outer 'resolved' variable. "
                    "Should be 'nodelete_resolved = expand_path('"
                )


# ============================================================
# ADVISORY-2: TOCTOU Fail-Closed in noDelete Check
# ============================================================


class TestAdvisory2_TOCTOU_FailClosed(unittest.TestCase):
    """ADVISORY-2: noDelete exists() check must fail-closed on errors."""

    def setUp(self):
        _clear_config_cache()

    def test_exists_error_blocks_write(self):
        """When expand_path raises OSError in noDelete check, write must be BLOCKED (fail-closed).

        Uses subprocess with monkeypatch to inject the error into the noDelete block's
        expand_path call. The file does NOT physically exist, so the ONLY reason
        for deny is the fail-closed error handling (file_exists = True on exception).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project WITHOUT the file -- so exists() would return False normally
            project_dir = _setup_project_with_config(tmpdir, files=[])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            scripts_dir = str(REPO_ROOT / "hooks" / "scripts")

            # Strategy: Pre-load config (so Path.exists on config path is cached),
            # then patch Path.exists to raise ONLY for CLAUDE.md paths.
            # In the check chain, only the noDelete block (L2392) calls .exists() on
            # the target path. Other checks use .is_symlink(), .resolve(), .relative_to(),
            # and string matching -- never .exists() on the file path.
            wrapper_code = f'''
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path("{scripts_dir}")))
import _guardian_utils

# Pre-load config so it's cached (prevents Path.exists on config path later)
_guardian_utils.load_guardian_config()

# Save original
_orig_exists = Path.exists

def _selective_failing_exists(self):
    if "CLAUDE.md" in str(self):
        raise OSError("simulated disk I/O error during exists() check")
    return _orig_exists(self)

# Patch Path.exists -- only raises for CLAUDE.md paths
Path.exists = _selective_failing_exists

try:
    _guardian_utils.run_path_guardian_hook("Write")
except SystemExit:
    pass
'''
            stdin_data = _make_hook_input("Write", file_path)
            env = dict(os.environ)
            env["CLAUDE_PROJECT_DIR"] = project_dir
            result = subprocess.run(
                [sys.executable, "-c", wrapper_code],
                input=stdin_data,
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Write must be denied when exists() raises (fail-closed). Got: {decision}. "
                f"stdout={result.stdout!r}, stderr={result.stderr!r}"
            )

    def test_existing_nodelete_file_blocked(self):
        """Write to existing noDelete file must be BLOCKED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir, files=["CLAUDE.md"])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            stdin_data = _make_hook_input("Write", file_path)
            result = _run_hook_subprocess(
                WRITE_GUARDIAN_PATH, stdin_data,
                env_override={"CLAUDE_PROJECT_DIR": project_dir}
            )
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(decision, "deny",
                             f"Existing noDelete file must be denied. Got: {decision}")

    def test_new_nodelete_file_allowed(self):
        """Write to new (non-existing) noDelete file must be ALLOWED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir, files=[])
            file_path = str(Path(project_dir) / "CLAUDE.md")
            stdin_data = _make_hook_input("Write", file_path)
            result = _run_hook_subprocess(
                WRITE_GUARDIAN_PATH, stdin_data,
                env_override={"CLAUDE_PROJECT_DIR": project_dir}
            )
            decision = _get_permission_decision(result.stdout)
            self.assertIn(
                decision, ("allow", None),
                f"New noDelete file creation must be allowed. Got: {decision}"
            )

    def test_exists_returns_false_allows_write(self):
        """When file does not exist, noDelete check allows write."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir, files=[])
            # README.md is in noDeletePaths but does not exist
            file_path = str(Path(project_dir) / "README.md")
            stdin_data = _make_hook_input("Write", file_path)
            result = _run_hook_subprocess(
                WRITE_GUARDIAN_PATH, stdin_data,
                env_override={"CLAUDE_PROJECT_DIR": project_dir}
            )
            decision = _get_permission_decision(result.stdout)
            self.assertIn(
                decision, ("allow", None),
                f"Non-existing noDelete file must be allowed. Got: {decision}"
            )


# ============================================================
# ADVISORY-3a: expand_path() Fail-Closed
# ============================================================


class TestAdvisory3_ExpandPath_FailClosed(unittest.TestCase):
    """ADVISORY-3a: expand_path() must propagate exceptions, not return raw path."""

    def setUp(self):
        _clear_config_cache()

    def test_expand_path_raises_on_oserror(self):
        """expand_path with a path triggering OSError should raise, not return raw path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Mock Path.resolve to raise OSError
                with patch.object(Path, "resolve", side_effect=OSError("no such device")):
                    with self.assertRaises(OSError):
                        expand_path("/some/bad/path")

    def test_expand_path_raises_on_permission_error(self):
        """PermissionError during expansion should propagate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch.object(Path, "resolve", side_effect=PermissionError("access denied")):
                    with self.assertRaises(PermissionError):
                        expand_path("/restricted/path")

    def test_expand_path_normal_operation(self):
        """Normal path expansion still works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = expand_path(str(test_file))
                self.assertIsInstance(result, Path)
                self.assertTrue(result.is_absolute())


# ============================================================
# ADVISORY-3b: normalize_path_for_matching() Fail-Closed
# ============================================================


class TestAdvisory3_NormalizePathForMatching_FailClosed(unittest.TestCase):
    """ADVISORY-3b: normalize_path_for_matching() must propagate exceptions."""

    def setUp(self):
        _clear_config_cache()

    def test_normalize_raises_when_expand_path_fails(self):
        """When expand_path raises, normalize_path_for_matching should also raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.expand_path", side_effect=OSError("disk error")):
                    with self.assertRaises(OSError):
                        normalize_path_for_matching("/some/path")

    def test_normalize_normal_operation(self):
        """Normal normalization still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = normalize_path_for_matching(str(test_file))
                self.assertIsInstance(result, str)
                self.assertIn("/", result)  # Forward slashes


# ============================================================
# ADVISORY-3d: match_path_pattern() default_on_error
# ============================================================


class TestAdvisory3_MatchPathPattern_DefaultOnError(unittest.TestCase):
    """ADVISORY-3d: match_path_pattern default_on_error controls error behavior."""

    def setUp(self):
        _clear_config_cache()

    def test_default_on_error_true_returns_true_on_exception(self):
        """With default_on_error=True, exception in matching returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("disk error")):
                    result = match_path_pattern("/any/path", "*.txt", default_on_error=True)
                    self.assertTrue(result, "default_on_error=True must return True on exception")

    def test_default_on_error_false_returns_false_on_exception(self):
        """With default_on_error=False, exception in matching returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("disk error")):
                    result = match_path_pattern("/any/path", "*.txt", default_on_error=False)
                    self.assertFalse(result, "default_on_error=False must return False on exception")

    def test_default_on_error_default_is_false(self):
        """Without kwarg, default_on_error defaults to False on exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("disk error")):
                    result = match_path_pattern("/any/path", "*.txt")
                    self.assertFalse(result, "Default (no kwarg) must return False on exception")

    def test_normal_matching_unaffected(self):
        """Normal matching still works correctly with default_on_error parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Should match regardless of default_on_error value
                result_true = match_path_pattern(str(test_file), "*.txt", default_on_error=True)
                result_false = match_path_pattern(str(test_file), "*.txt", default_on_error=False)
                self.assertTrue(result_true, "Normal *.txt match should work with default_on_error=True")
                self.assertTrue(result_false, "Normal *.txt match should work with default_on_error=False")


# ============================================================
# ADVISORY-3e/f/g: Deny Checks Fail-Closed
# ============================================================


class TestAdvisory3_DenyChecks_FailClosed(unittest.TestCase):
    """ADVISORY-3e/f/g: match_zero_access, match_read_only, match_no_delete
    must fail-closed (return True) when normalization errors occur."""

    def setUp(self):
        _clear_config_cache()

    def test_match_zero_access_failclosed(self):
        """match_zero_access returns True when normalization fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # Load config so patterns exist
                project = Path(tmpdir)
                (project / ".git").mkdir(exist_ok=True)
                config_dir = project / ".claude" / "guardian"
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(GUARDIAN_CONFIG_PATH) as f:
                    config = json.load(f)
                with open(config_dir / "config.json", "w") as f:
                    json.dump(config, f)
                _clear_config_cache()

                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("normalization failed")):
                    result = match_zero_access("/some/path")
                    self.assertTrue(result,
                                    "match_zero_access must return True (fail-closed) on normalization error")

    def test_match_read_only_failclosed(self):
        """match_read_only returns True when normalization fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                project = Path(tmpdir)
                (project / ".git").mkdir(exist_ok=True)
                config_dir = project / ".claude" / "guardian"
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(GUARDIAN_CONFIG_PATH) as f:
                    config = json.load(f)
                with open(config_dir / "config.json", "w") as f:
                    json.dump(config, f)
                _clear_config_cache()

                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("normalization failed")):
                    result = match_read_only("/some/path")
                    self.assertTrue(result,
                                    "match_read_only must return True (fail-closed) on normalization error")

    def test_match_no_delete_failclosed(self):
        """match_no_delete returns True when normalization fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                project = Path(tmpdir)
                (project / ".git").mkdir(exist_ok=True)
                config_dir = project / ".claude" / "guardian"
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(GUARDIAN_CONFIG_PATH) as f:
                    config = json.load(f)
                with open(config_dir / "config.json", "w") as f:
                    json.dump(config, f)
                _clear_config_cache()

                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("normalization failed")):
                    result = match_no_delete("/some/path")
                    self.assertTrue(result,
                                    "match_no_delete must return True (fail-closed) on normalization error")

    def test_match_allowed_external_failclosed(self):
        """match_allowed_external_path returns None (not matched) on normalization error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                project = Path(tmpdir)
                (project / ".git").mkdir(exist_ok=True)
                config_dir = project / ".claude" / "guardian"
                config_dir.mkdir(parents=True, exist_ok=True)
                with open(GUARDIAN_CONFIG_PATH) as f:
                    config = json.load(f)
                with open(config_dir / "config.json", "w") as f:
                    json.dump(config, f)
                _clear_config_cache()

                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("normalization failed")):
                    result = match_allowed_external_path("/some/external/path")
                    self.assertIsNone(result,
                                     "match_allowed_external_path must return None (fail-closed) "
                                     "on normalization error")


# ============================================================
# ADVISORY-3i: is_self_guardian_path() Fail-Closed
# ============================================================


class TestAdvisory3_IsSelfGuardianPath_FailClosed(unittest.TestCase):
    """ADVISORY-3i: is_self_guardian_path() must return True when
    normalization fails (protect guardian files on error)."""

    def setUp(self):
        _clear_config_cache()

    def test_normalization_error_returns_true(self):
        """When normalize_path_for_matching raises on the input path, returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                (Path(tmpdir) / ".git").mkdir(exist_ok=True)
                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=OSError("cannot normalize")):
                    result = is_self_guardian_path("/some/path")
                    self.assertTrue(result,
                                    "Must return True (fail-closed) when normalization fails")

    def test_active_config_normalization_error_returns_true(self):
        """When active config path normalization fails, returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                (Path(tmpdir) / ".git").mkdir(exist_ok=True)

                # Set up so normalize works for input path but fails for active config
                call_count = [0]
                original_normalize = normalize_path_for_matching

                def selective_fail(p):
                    call_count[0] += 1
                    if call_count[0] > 1:
                        raise OSError("cannot normalize active config")
                    return original_normalize(p)

                with patch("_guardian_utils.normalize_path_for_matching",
                           side_effect=selective_fail):
                    # Need an active config path for the second normalize call
                    with patch("_guardian_utils.get_active_config_path",
                               return_value="/some/config.json"):
                        result = is_self_guardian_path(str(Path(tmpdir) / "somefile.txt"))
                        self.assertTrue(result,
                                        "Must return True when active config normalization fails")

    def test_normal_operation(self):
        """Normal self-guardian path detection still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / ".git").mkdir(exist_ok=True)
            config_dir = project / ".claude" / "guardian"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "config.json"
            with open(GUARDIAN_CONFIG_PATH) as f:
                config = json.load(f)
            with open(config_path, "w") as f:
                json.dump(config, f)

            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                # A path that is NOT a guardian path
                non_guardian = str(project / "src" / "app.py")
                result = is_self_guardian_path(non_guardian)
                self.assertFalse(result,
                                 "Non-guardian path should return False")


# ============================================================
# ADVISORY-3c: resolve_tool_path() Fail-Closed
# ============================================================


class TestAdvisory3_ResolveToolPath_FailClosed(unittest.TestCase):
    """ADVISORY-3c: resolve_tool_path() must raise OSError, not return raw path."""

    def setUp(self):
        _clear_config_cache()

    def test_resolve_raises_on_oserror(self):
        """resolve_tool_path should raise OSError when resolution fails."""
        with patch.object(Path, "resolve", side_effect=OSError("device not available")):
            with self.assertRaises(OSError):
                resolve_tool_path("/some/bad/path")

    def test_normal_resolution(self):
        """Normal resolution still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": tmpdir}):
                _clear_config_cache()
                result = resolve_tool_path(str(test_file))
                self.assertIsInstance(result, Path)
                self.assertTrue(result.is_absolute())


# ============================================================
# ADVISORY-3j: run_path_guardian_hook() resolve failure
# ============================================================


class TestAdvisory3_RunPathGuardianHook_ResolveFailure(unittest.TestCase):
    """ADVISORY-3j: When resolve_tool_path raises in run_path_guardian_hook,
    the hook must emit deny (not crash or allow)."""

    # We use a small Python wrapper that monkeypatches resolve_tool_path
    # to raise OSError, then runs the guardian hook. This is necessary because
    # Path.resolve() on Linux rarely raises OSError for typical paths -- the
    # advisory fix is defensive against OS-level failures (disk I/O, NFS, etc).
    _WRAPPER_TEMPLATE = '''
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path("{scripts_dir}")))
import _guardian_utils
def _failing_resolve(fp):
    raise OSError("simulated disk I/O error")
_guardian_utils.resolve_tool_path = _failing_resolve
try:
    _guardian_utils.run_path_guardian_hook("{tool_name}")
except SystemExit:
    pass
'''

    def _run_with_patched_resolve(self, tool_name, file_path, project_dir):
        """Run a guardian hook with resolve_tool_path monkeypatched to raise."""
        scripts_dir = str(REPO_ROOT / "hooks" / "scripts")
        wrapper_code = self._WRAPPER_TEMPLATE.format(
            scripts_dir=scripts_dir, tool_name=tool_name
        )
        stdin_data = _make_hook_input(tool_name, file_path)
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = project_dir
        return subprocess.run(
            [sys.executable, "-c", wrapper_code],
            input=stdin_data,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

    def test_write_guardian_resolve_failure_denies(self):
        """Write guardian must DENY when resolve_tool_path raises OSError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir)
            result = self._run_with_patched_resolve(
                "Write", str(Path(project_dir) / "test.txt"), project_dir
            )
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Write with resolve failure must deny. Got: {decision}. "
                f"stdout={result.stdout!r}, stderr={result.stderr!r}"
            )

    def test_read_guardian_resolve_failure_denies(self):
        """Read guardian must DENY when resolve_tool_path raises OSError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir)
            result = self._run_with_patched_resolve(
                "Read", str(Path(project_dir) / "test.txt"), project_dir
            )
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Read with resolve failure must deny. Got: {decision}. "
                f"stdout={result.stdout!r}, stderr={result.stderr!r}"
            )

    def test_edit_guardian_resolve_failure_denies(self):
        """Edit guardian must DENY when resolve_tool_path raises OSError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = _setup_project_with_config(tmpdir)
            result = self._run_with_patched_resolve(
                "Edit", str(Path(project_dir) / "test.txt"), project_dir
            )
            decision = _get_permission_decision(result.stdout)
            self.assertEqual(
                decision, "deny",
                f"Edit with resolve failure must deny. Got: {decision}. "
                f"stdout={result.stdout!r}, stderr={result.stderr!r}"
            )


# ============================================================
# Runner
# ============================================================


if __name__ == "__main__":
    unittest.main(verbosity=2)
