#!/usr/bin/env python3
"""Tests for the SessionStart auto-activate hook (session_start.sh).

Tests invoke the bash script via subprocess.run() with controlled environment
variables and temporary directory structures. The script is fail-open by design
(always exits 0), so tests verify behavior via stdout output and filesystem state.

Run: python -m pytest tests/regression/test_session_start.py -v
  or: python3 tests/regression/test_session_start.py
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

REPO_ROOT = _bootstrap._REPO_ROOT
SESSION_START_SCRIPT = str(REPO_ROOT / "hooks" / "scripts" / "session_start.sh")
RECOMMENDED_CONFIG = str(REPO_ROOT / "assets" / "guardian.recommended.json")


def _run_session_start(project_dir=None, plugin_root=None, env_extras=None,
                       unset_vars=None):
    """Run session_start.sh with controlled environment.

    Args:
        project_dir: Value for CLAUDE_PROJECT_DIR (None = unset).
        plugin_root: Value for CLAUDE_PLUGIN_ROOT (None = unset).
        env_extras: Dict of additional env vars to set.
        unset_vars: List of env var names to remove from environment.

    Returns:
        subprocess.CompletedProcess with stdout, stderr, returncode.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    if env_extras:
        env.update(env_extras)
    if unset_vars:
        for var in unset_vars:
            env.pop(var, None)

    return subprocess.run(
        ["bash", SESSION_START_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


class TestSessionStartFirstRun(unittest.TestCase):
    """Tests for first-run config creation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="guardian_session_start_")
        self.project_dir = os.path.join(self.tmpdir, "project")
        os.makedirs(self.project_dir)
        self.config_path = os.path.join(
            self.project_dir, ".claude", "guardian", "config.json"
        )

    def tearDown(self):
        # Restore permissions before cleanup (in case chmod tests)
        for root, dirs, files in os.walk(self.tmpdir):
            for d in dirs:
                p = os.path.join(root, d)
                try:
                    os.chmod(p, stat.S_IRWXU)
                except OSError:
                    pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_first_run_creates_config(self):
        """No config exists, valid source file, valid env vars -> config created."""
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.isfile(self.config_path),
                        "Config file should be created on first run")
        self.assertIn("[Guardian] Activated", result.stdout)

    def test_first_run_stdout_messages(self):
        """First run prints all 4 context lines."""
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertIn("Activated recommended security config", result.stdout)
        self.assertIn("Protecting against:", result.stdout)
        self.assertIn("Config saved to .claude/guardian/config.json", result.stdout)
        self.assertIn("/guardian:init", result.stdout)

    def test_created_config_valid_json(self):
        """Created config file is valid JSON."""
        _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        with open(self.config_path, "r") as f:
            data = json.load(f)
        self.assertIn("version", data)
        self.assertIn("bashToolPatterns", data)

    def test_created_config_matches_source(self):
        """Created config content matches source recommended config."""
        _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        with open(self.config_path, "r") as f:
            created = f.read()
        with open(RECOMMENDED_CONFIG, "r") as f:
            source = f.read()
        self.assertEqual(created, source,
                         "Created config should be identical to source")

    def test_created_config_permissions(self):
        """Created config file has 0644 permissions (not mktemp's 0600)."""
        _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        mode = os.stat(self.config_path).st_mode & 0o777
        self.assertEqual(mode, 0o644,
                         f"Config should be 0644, got {oct(mode)}")

    def test_dir_exists_no_config(self):
        """.claude/guardian/ exists but config.json doesn't -> config created."""
        os.makedirs(os.path.join(self.project_dir, ".claude", "guardian"),
                     exist_ok=True)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.isfile(self.config_path))
        self.assertIn("[Guardian] Activated", result.stdout)


class TestSessionStartExistingConfig(unittest.TestCase):
    """Tests for when config already exists."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="guardian_session_start_")
        self.project_dir = os.path.join(self.tmpdir, "project")
        self.config_dir = os.path.join(self.project_dir, ".claude", "guardian")
        os.makedirs(self.config_dir)
        self.config_path = os.path.join(self.config_dir, "config.json")
        # Create a pre-existing config
        with open(self.config_path, "w") as f:
            f.write('{"version": "existing"}')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_existing_config_silent(self):
        """Config already exists -> no stdout, no file modification."""
        with open(self.config_path) as f:
            original_content = f.read()
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", "Should produce no output")
        with open(self.config_path) as f:
            self.assertEqual(f.read(), original_content,
                             "Config should not be modified")

    def test_empty_config_file_exits_silently(self):
        """config.json exists but is empty (0 bytes) -> silent exit."""
        with open(self.config_path, "w") as f:
            pass  # Empty file
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        # File should still be empty (not overwritten)
        self.assertEqual(os.path.getsize(self.config_path), 0)

    def test_idempotent_double_run(self):
        """Run script twice: first creates, second is silent."""
        # Remove pre-existing config for first run
        os.remove(self.config_path)

        # First run creates config
        result1 = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertIn("[Guardian] Activated", result1.stdout)
        with open(self.config_path) as f:
            content_after_first = f.read()

        # Second run is silent
        result2 = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result2.returncode, 0)
        self.assertEqual(result2.stdout, "")
        with open(self.config_path) as f:
            self.assertEqual(f.read(), content_after_first,
                             "File should not change on second run")


class TestSessionStartEnvValidation(unittest.TestCase):
    """Tests for environment variable validation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="guardian_session_start_")
        self.project_dir = os.path.join(self.tmpdir, "project")
        os.makedirs(self.project_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_missing_project_dir_env(self):
        """CLAUDE_PROJECT_DIR unset -> silent exit, no file created."""
        result = _run_session_start(
            project_dir=None,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        config_path = os.path.join(self.project_dir, ".claude", "guardian", "config.json")
        self.assertFalse(os.path.exists(config_path))

    def test_empty_project_dir_env(self):
        """CLAUDE_PROJECT_DIR="" -> silent exit, no file created."""
        result = _run_session_start(
            project_dir="",
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_missing_plugin_root_env(self):
        """CLAUDE_PLUGIN_ROOT unset -> silent exit, no file created."""
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=None,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_relative_project_dir_rejected(self):
        """CLAUDE_PROJECT_DIR="relative/path" -> silent exit."""
        result = _run_session_start(
            project_dir="relative/path",
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_nonexistent_project_dir_rejected(self):
        """CLAUDE_PROJECT_DIR="/nonexistent/path" -> silent exit."""
        result = _run_session_start(
            project_dir="/nonexistent/path/that/does/not/exist",
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_missing_source_file(self):
        """guardian.recommended.json doesn't exist at source path -> silent exit."""
        # Use a valid but empty plugin root
        fake_plugin_root = os.path.join(self.tmpdir, "fake_plugin")
        os.makedirs(os.path.join(fake_plugin_root, "assets"), exist_ok=True)
        # Don't create guardian.recommended.json
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=fake_plugin_root,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


class TestSessionStartFilesystem(unittest.TestCase):
    """Tests for filesystem edge cases."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="guardian_session_start_")
        self.project_dir = os.path.join(self.tmpdir, "project")
        os.makedirs(self.project_dir)
        self.config_path = os.path.join(
            self.project_dir, ".claude", "guardian", "config.json"
        )

    def tearDown(self):
        # Restore permissions before cleanup
        for root, dirs, files in os.walk(self.tmpdir):
            for d in dirs:
                p = os.path.join(root, d)
                try:
                    os.chmod(p, stat.S_IRWXU)
                except OSError:
                    pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_readonly_filesystem(self):
        """Target directory not writable (chmod 555) -> warning, no file, exit 0."""
        # Make project dir read-only so mkdir fails
        os.chmod(self.project_dir, stat.S_IRUSR | stat.S_IXUSR)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(self.config_path))
        self.assertIn("Could not auto-activate", result.stdout)

    def test_mkdir_failure_emits_warning(self):
        """mkdir fails -> stdout contains warning, exit 0."""
        os.chmod(self.project_dir, stat.S_IRUSR | stat.S_IXUSR)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Could not auto-activate", result.stdout)
        self.assertIn("/guardian:init", result.stdout)

    def test_cp_failure_emits_warning(self):
        """Source file unreadable (cp fails) -> warning, exit 0."""
        # Create directory structure so mkdir succeeds
        config_dir = os.path.join(self.project_dir, ".claude", "guardian")
        os.makedirs(config_dir, exist_ok=True)
        # Create a fake plugin root with unreadable source
        fake_plugin = os.path.join(self.tmpdir, "fake_plugin")
        fake_assets = os.path.join(fake_plugin, "assets")
        os.makedirs(fake_assets)
        source = os.path.join(fake_assets, "guardian.recommended.json")
        with open(source, "w") as f:
            f.write("{}")
        # Make source unreadable after it passes the -f check
        os.chmod(source, 0o000)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=fake_plugin,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Could not auto-activate", result.stdout)
        # Restore permissions for cleanup
        os.chmod(source, stat.S_IRUSR | stat.S_IWUSR)


class TestSessionStartSymlinks(unittest.TestCase):
    """Tests for symlink attack mitigation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="guardian_session_start_")
        self.project_dir = os.path.join(self.tmpdir, "project")
        os.makedirs(self.project_dir)
        self.outside_dir = os.path.join(self.tmpdir, "outside")
        os.makedirs(self.outside_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_symlink_parent_rejected(self):
        """.claude is a symlink -> no file created, exit 0."""
        claude_dir = os.path.join(self.project_dir, ".claude")
        os.symlink(self.outside_dir, claude_dir)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(
            os.path.exists(os.path.join(self.outside_dir, "guardian", "config.json"))
        )

    def test_symlink_guardian_dir_rejected(self):
        """.claude/guardian is a symlink -> no file created, exit 0."""
        claude_dir = os.path.join(self.project_dir, ".claude")
        os.makedirs(claude_dir)
        guardian_dir = os.path.join(claude_dir, "guardian")
        os.symlink(self.outside_dir, guardian_dir)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse(
            os.path.exists(os.path.join(self.outside_dir, "config.json"))
        )

    def test_symlink_config_file_rejected(self):
        """config.json is a symlink (dangling) -> no overwrite, exit 0."""
        config_dir = os.path.join(self.project_dir, ".claude", "guardian")
        os.makedirs(config_dir)
        config_path = os.path.join(config_dir, "config.json")
        # Create a dangling symlink
        os.symlink("/nonexistent/target", config_path)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        # Symlink should still be there, not replaced
        self.assertTrue(os.path.islink(config_path))

    def test_symlink_config_file_valid_target_rejected(self):
        """config.json is a symlink to a valid file -> no overwrite, exit 0."""
        config_dir = os.path.join(self.project_dir, ".claude", "guardian")
        os.makedirs(config_dir)
        config_path = os.path.join(config_dir, "config.json")
        target = os.path.join(self.outside_dir, "evil.json")
        with open(target, "w") as f:
            f.write("{}")
        os.symlink(target, config_path)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        # Target file should not be modified
        with open(target) as f:
            self.assertEqual(f.read(), "{}")


class TestSessionStartExitCodes(unittest.TestCase):
    """Tests that exit code is always 0 in all scenarios."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="guardian_session_start_")
        self.project_dir = os.path.join(self.tmpdir, "project")
        os.makedirs(self.project_dir)

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir):
            for d in dirs:
                p = os.path.join(root, d)
                try:
                    os.chmod(p, stat.S_IRWXU)
                except OSError:
                    pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_exit_code_always_zero_success(self):
        """Successful config creation -> exit 0."""
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)

    def test_exit_code_always_zero_existing(self):
        """Config exists -> exit 0."""
        config_dir = os.path.join(self.project_dir, ".claude", "guardian")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "config.json"), "w") as f:
            f.write("{}")
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)

    def test_exit_code_always_zero_missing_env(self):
        """Missing env vars -> exit 0."""
        result = _run_session_start(project_dir=None, plugin_root=None)
        self.assertEqual(result.returncode, 0)

    def test_exit_code_always_zero_readonly(self):
        """Read-only filesystem -> exit 0."""
        os.chmod(self.project_dir, stat.S_IRUSR | stat.S_IXUSR)
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)
        os.chmod(self.project_dir, stat.S_IRWXU)

    def test_exit_code_always_zero_no_source(self):
        """Missing source file -> exit 0."""
        fake_root = os.path.join(self.tmpdir, "fake")
        os.makedirs(os.path.join(fake_root, "assets"))
        result = _run_session_start(
            project_dir=self.project_dir,
            plugin_root=fake_root,
        )
        self.assertEqual(result.returncode, 0)

    def test_exit_code_always_zero_relative_path(self):
        """Relative CLAUDE_PROJECT_DIR -> exit 0."""
        result = _run_session_start(
            project_dir="relative/path",
            plugin_root=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
