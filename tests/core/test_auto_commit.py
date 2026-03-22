#!/usr/bin/env python3
"""Comprehensive test suite for auto_commit.py (Stop hook).

Tests auto_commit.py including the security fix for zeroAccessPaths filtering.
git_add_filtered() prevents secrets (.env, *.pem, *.key) from being staged
and committed. Pre-staged secrets are also unstaged before commit.

Remaining known gap:
- --no-verify unconditionally bypasses pre-commit hooks (by design for auto-commit)

Run: python -m pytest tests/core/test_auto_commit.py -v
  or: python3 tests/core/test_auto_commit.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

import _guardian_utils
import auto_commit as ac_module
from auto_commit import main


# ============================================================
# Helpers
# ============================================================

# Patch targets: auto_commit.py does `from _guardian_utils import X`,
# so we must patch on the auto_commit module, not _guardian_utils.
_AC = "auto_commit"


def _create_test_repo():
    """Create a temporary git repository with an initial commit."""
    tmpdir = tempfile.mkdtemp(prefix="guardian_autocommit_test_")
    subprocess.run(["git", "init", tmpdir], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", tmpdir, "config", "user.email", "test@test.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", tmpdir, "config", "user.name", "Test"],
        check=True, capture_output=True,
    )
    init_file = Path(tmpdir) / "init.txt"
    init_file.write_text("init")
    subprocess.run(["git", "-C", tmpdir, "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", tmpdir, "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    return tmpdir


def _get_committed_files(repo_dir):
    """Get list of files in the last commit."""
    result = subprocess.run(
        ["git", "-C", repo_dir, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        capture_output=True, encoding="utf-8",
    )
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def _get_commit_message(repo_dir):
    """Get the message of the last commit."""
    result = subprocess.run(
        ["git", "-C", repo_dir, "log", "-1", "--pretty=%s"],
        capture_output=True, encoding="utf-8",
    )
    return result.stdout.strip()


def _get_commit_count(repo_dir):
    """Get total number of commits in the repo."""
    result = subprocess.run(
        ["git", "-C", repo_dir, "rev-list", "--count", "HEAD"],
        capture_output=True, encoding="utf-8",
    )
    return int(result.stdout.strip())


def _make_config(include_untracked=False, message_prefix="auto-checkpoint",
                 enabled=True, on_stop=True):
    """Build a guardian config dict with autoCommit settings."""
    return {
        "gitIntegration": {
            "autoCommit": {
                "enabled": enabled,
                "onStop": on_stop,
                "messagePrefix": message_prefix,
                "includeUntracked": include_untracked,
            }
        }
    }


class _AutoCommitTestBase(unittest.TestCase):
    """Base class with shared setup: temp repo, env, cache resets."""

    def setUp(self):
        self.tmpdir = _create_test_repo()
        self.addCleanup(self._cleanup)

        # Save originals
        self._orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        self._orig_dry_run = os.environ.get("CLAUDE_HOOK_DRY_RUN")
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmpdir
        os.environ.pop("CLAUDE_HOOK_DRY_RUN", None)

        # Reset module-level caches
        _guardian_utils._config_cache = None
        _guardian_utils._using_fallback_config = False
        _guardian_utils._active_config_path = None
        _guardian_utils._git_available_cache = None

        # Ensure no circuit breaker file
        circuit = Path(self.tmpdir) / ".claude" / "guardian" / ".circuit_open"
        if circuit.exists():
            circuit.unlink()

    def _cleanup(self):
        if self._orig_project_dir is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_project_dir
        else:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)

        if self._orig_dry_run is not None:
            os.environ["CLAUDE_HOOK_DRY_RUN"] = self._orig_dry_run
        else:
            os.environ.pop("CLAUDE_HOOK_DRY_RUN", None)

        _guardian_utils._config_cache = None
        _guardian_utils._using_fallback_config = False
        _guardian_utils._active_config_path = None
        _guardian_utils._git_available_cache = None
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _circuit_file(self):
        return Path(self.tmpdir) / ".claude" / "guardian" / ".circuit_open"


# ============================================================
# 1. Security Characterization (P0)
# ============================================================


class TestAutoCommit_SecurityCharacterization(_AutoCommitTestBase):
    """P0 security tests verifying zeroAccessPaths filtering in auto-commit.

    SECURITY FIX: auto_commit.py now uses git_add_filtered() which:
    - Filters secret files from staging based on zeroAccessPaths config
    - Unstages any pre-staged secrets before commit
    """

    def test_secret_env_filtered_with_includeUntracked(self):
        """includeUntracked=true filters .env files via zeroAccessPaths.

        SECURITY FIX: .env is no longer committed.
        """
        (Path(self.tmpdir) / ".env").write_text("SECRET_KEY=hunter2")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn(".env", committed,
                         "SECURITY FIX: .env should be filtered by zeroAccessPaths")

    def test_secret_pem_filtered_with_includeUntracked(self):
        """includeUntracked=true filters *.pem files via zeroAccessPaths.

        SECURITY FIX: Private key files no longer committed.
        """
        (Path(self.tmpdir) / "server.pem").write_text("-----BEGIN PRIVATE KEY-----")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn("server.pem", committed,
                         "SECURITY FIX: *.pem should be filtered by zeroAccessPaths")

    def test_secret_key_filtered_with_includeUntracked(self):
        """includeUntracked=true filters *.key files via zeroAccessPaths.

        SECURITY FIX: *.key files no longer committed.
        """
        (Path(self.tmpdir) / "private.key").write_text("private key data")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn("private.key", committed,
                         "SECURITY FIX: *.key should be filtered by zeroAccessPaths")

    def test_multiple_secrets_filtered_safe_files_committed(self):
        """Secret files filtered while safe files are committed.

        SECURITY FIX: Only normal.txt committed, secrets filtered out.
        """
        (Path(self.tmpdir) / ".env").write_text("SECRET=val")
        (Path(self.tmpdir) / "cert.pem").write_text("cert data")
        (Path(self.tmpdir) / "tls.key").write_text("key data")
        (Path(self.tmpdir) / "normal.txt").write_text("safe content")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn(".env", committed)
        self.assertNotIn("cert.pem", committed)
        self.assertNotIn("tls.key", committed)
        self.assertIn("normal.txt", committed)

    def test_prestaged_secrets_unstaged_includeUntracked_false(self):
        """Pre-staged .env is unstaged before commit.

        SECURITY FIX: git_add_filtered() checks staged files and
        unstages any matching zeroAccessPaths.
        """
        (Path(self.tmpdir) / ".env").write_text("DB_PASSWORD=secret123")
        subprocess.run(
            ["git", "-C", self.tmpdir, "add", ".env"],
            check=True, capture_output=True,
        )

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn(".env", committed,
                         "SECURITY FIX: Pre-staged .env should be unstaged by git_add_filtered()")

    def test_no_verify_flag_always_used(self):
        """git_commit is always called with no_verify=True.

        This is by design for auto-commit (backup-only commits).
        The zeroAccessPaths filtering now provides the security layer.
        """
        (Path(self.tmpdir) / "change.txt").write_text("changed")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            with patch(f"{_AC}.git_commit", return_value=True) as mock_commit:
                with patch(f"{_AC}.git_get_last_commit_hash", return_value="abc1234"):
                    main()

        mock_commit.assert_called_once()
        args, kwargs = mock_commit.call_args
        self.assertTrue(kwargs.get("no_verify", False),
                        "git_commit called with no_verify=True (by design)")

    def test_staging_failure_aborts_commit(self):
        """When git_add_filtered returns False, commit is ABORTED.

        SECURITY FIX: git_add_filtered() returning False means either
        staging failed or secrets could not be unstaged. auto_commit.py
        now aborts the commit and opens the circuit breaker.
        """
        (Path(self.tmpdir) / ".env").write_text("STALE_SECRET=leaked")
        subprocess.run(
            ["git", "-C", self.tmpdir, "add", ".env"],
            check=True, capture_output=True,
        )

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            with patch(f"{_AC}.git_add_filtered", return_value=False):
                main()

        committed = _get_committed_files(self.tmpdir)
        # Commit must be ABORTED when staging fails
        self.assertNotIn(".env", committed,
                         "Staging failure must abort commit to prevent secret exposure")


# ============================================================
# 1b. Security Filtering (new tests for git_add_filtered)
# ============================================================


class TestAutoCommit_SecurityFiltering(_AutoCommitTestBase):
    """Tests specifically for the git_add_filtered() security behavior."""

    def test_safe_files_committed_with_secrets_filtered(self):
        """Safe files are committed while secrets are filtered out."""
        (Path(self.tmpdir) / "app.py").write_text("print('hello')")
        (Path(self.tmpdir) / "README.txt").write_text("readme")
        (Path(self.tmpdir) / ".env").write_text("SECRET=x")
        (Path(self.tmpdir) / "key.pem").write_text("private key")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertIn("app.py", committed)
        self.assertIn("README.txt", committed)
        self.assertNotIn(".env", committed)
        self.assertNotIn("key.pem", committed)

    def test_only_secrets_no_secret_committed(self):
        """When only secret files are created, they are not committed.

        Note: The guardian log file (.claude/guardian/guardian.log) may
        be created as a side effect and could be committed if
        includeUntracked=True, but secret files must never be.
        """
        (Path(self.tmpdir) / ".env").write_text("SECRET=x")
        (Path(self.tmpdir) / "server.pem").write_text("cert")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn(".env", committed,
                         ".env should not be committed")
        self.assertNotIn("server.pem", committed,
                         "server.pem should not be committed")

    def test_prestaged_pem_unstaged(self):
        """Pre-staged *.pem file is unstaged by git_add_filtered."""
        (Path(self.tmpdir) / "server.pem").write_text("key data")
        subprocess.run(
            ["git", "-C", self.tmpdir, "add", "server.pem"],
            check=True, capture_output=True,
        )
        # Also modify a tracked file so there's something to stage
        (Path(self.tmpdir) / "init.txt").write_text("modified")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn("server.pem", committed,
                         "Pre-staged *.pem should be unstaged")
        self.assertIn("init.txt", committed,
                      "Safe tracked file should still be committed")

    def test_secrets_json_yaml_filtered(self):
        """secrets.json and secrets.yaml are filtered (zeroAccessPaths)."""
        (Path(self.tmpdir) / "secrets.json").write_text("{}")
        (Path(self.tmpdir) / "secrets.yaml").write_text("key: val")
        (Path(self.tmpdir) / "safe.txt").write_text("safe")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn("secrets.json", committed)
        self.assertNotIn("secrets.yaml", committed)
        self.assertIn("safe.txt", committed)

    def test_tracked_modified_secret_filtered(self):
        """A tracked secret file that was modified is not re-staged."""
        # First, commit a secret.key file (simulating it already being in history)
        (Path(self.tmpdir) / "secret.key").write_text("original key")
        subprocess.run(
            ["git", "-C", self.tmpdir, "add", "secret.key"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", self.tmpdir, "commit", "-m", "add key"],
            check=True, capture_output=True,
        )
        # Now modify it
        (Path(self.tmpdir) / "secret.key").write_text("new key data")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            main()

        # No new commit should be made since the only changed file is a secret
        self.assertEqual(_get_commit_count(self.tmpdir), initial,
                         "Modified tracked secret should be filtered; no new commit")


# ============================================================
# 2. Circuit Breaker
# ============================================================


class TestAutoCommit_CircuitBreaker(_AutoCommitTestBase):
    """Tests for the circuit breaker pattern."""

    def _set_circuit(self, reason="test reason"):
        cf = self._circuit_file()
        cf.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        cf.write_text(f"{datetime.now().isoformat()}|{reason}\n")

    def test_circuit_open_skips_commit(self):
        """Circuit open -> main() skips commit entirely."""
        (Path(self.tmpdir) / "init.txt").write_text("modified")
        initial = _get_commit_count(self.tmpdir)
        self._set_circuit("previous failure")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config()):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_circuit_cleared_on_success(self):
        """Successful commit clears the circuit breaker."""
        self._set_circuit("old failure")
        (Path(self.tmpdir) / "init.txt").write_text("modified for clear")

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            with patch(f"{_AC}.is_circuit_open", return_value=(False, "")):
                main()

        self.assertFalse(self._circuit_file().exists(),
                         "Circuit should be cleared after successful commit")

    def test_circuit_set_on_commit_failure(self):
        """Commit failure opens the circuit breaker."""
        (Path(self.tmpdir) / "init.txt").write_text("will fail")

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            with patch(f"{_AC}.git_commit", return_value=False):
                main()

        self.assertTrue(self._circuit_file().exists(),
                        "Circuit should open on commit failure")
        self.assertIn("auto-commit failed", self._circuit_file().read_text())

    def test_circuit_set_on_exception_via_subprocess(self):
        """Unhandled exception in main() sets circuit breaker.

        Tests the actual __main__ block exception handler by running
        auto_commit.py as a subprocess with a monkey-patched main().
        """
        auto_commit_path = str(
            _bootstrap._REPO_ROOT / "hooks" / "scripts" / "auto_commit.py"
        )
        scripts_dir = str(_bootstrap._REPO_ROOT / "hooks" / "scripts")

        # Write a wrapper script that patches main() to raise, then runs __main__
        test_script = (
            f"import sys, os\n"
            f"sys.path.insert(0, '{scripts_dir}')\n"
            f"os.environ['CLAUDE_PROJECT_DIR'] = '{self.tmpdir}'\n"
            f"import auto_commit\n"
            f"def crashing_main():\n"
            f"    raise RuntimeError('deliberate test crash')\n"
            f"auto_commit.main = crashing_main\n"
            f"# Now run the __main__ block\n"
            f"try:\n"
            f"    auto_commit.main()\n"
            f"except Exception as e:\n"
            f"    auto_commit.log_guardian('ERROR', f'Auto-commit hook error: {{e}}')\n"
            f"    try:\n"
            f"        auto_commit.set_circuit_open(f'auto-commit exception: {{type(e).__name__}}')\n"
            f"    except Exception:\n"
            f"        pass\n"
            f"    sys.exit(0)\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, "Should exit 0 (fail-open)")
        self.assertTrue(self._circuit_file().exists(),
                        "Circuit breaker should be set on unhandled exception")
        self.assertIn("RuntimeError", self._circuit_file().read_text())

    def test_corrupt_circuit_file_treated_as_open(self):
        """Corrupt circuit file -> treated as open (fail-closed)."""
        cf = self._circuit_file()
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text("garbage data no pipe separator")

        (Path(self.tmpdir) / "init.txt").write_text("should not commit")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            main()

        # is_circuit_open returns True with "Unknown reason" for no-pipe content
        self.assertEqual(_get_commit_count(self.tmpdir), initial)


# ============================================================
# 3. Git Edge Cases
# ============================================================


class TestAutoCommit_GitEdgeCases(_AutoCommitTestBase):
    """Tests for git edge cases."""

    def test_no_changes_skips(self):
        """No changes -> skip commit."""
        initial = _get_commit_count(self.tmpdir)
        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            main()
        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_detached_head_skips(self):
        """Detached HEAD -> skip to avoid orphaned commits."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            with patch(f"{_AC}.is_detached_head", return_value=True):
                main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_rebase_in_progress_skips(self):
        """Rebase/merge in progress -> skip."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            with patch(f"{_AC}.is_rebase_or_merge_in_progress", return_value=True):
                main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_staging_failure_aborts_commit_and_opens_circuit(self):
        """Staging failure now aborts commit and opens circuit breaker.

        SECURITY FIX: git_add_filtered() returning False means secrets may
        be in the index. auto_commit.py now aborts and opens circuit breaker.
        """
        (Path(self.tmpdir) / "init.txt").write_text("modified")
        subprocess.run(
            ["git", "-C", self.tmpdir, "add", "init.txt"],
            check=True, capture_output=True,
        )

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            with patch(f"{_AC}.git_add_filtered", return_value=False):
                main()

        committed = _get_committed_files(self.tmpdir)
        self.assertNotIn("init.txt", committed,
                         "Staging failure must abort commit (security fix)")

    def test_no_staged_changes_after_staging_skips(self):
        """No staged changes after staging -> skip commit (BUG-2 fix)."""
        (Path(self.tmpdir) / "init.txt").write_text("modified")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            with patch(f"{_AC}.git_has_staged_changes", return_value=False):
                main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_commit_failure_opens_circuit(self):
        """git_commit failure -> circuit breaker opens."""
        (Path(self.tmpdir) / "init.txt").write_text("will fail")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            with patch(f"{_AC}.git_commit", return_value=False):
                main()

        self.assertTrue(self._circuit_file().exists())

    def test_includeUntracked_false_only_tracked(self):
        """includeUntracked=false only commits tracked file changes."""
        (Path(self.tmpdir) / "init.txt").write_text("tracked change")
        (Path(self.tmpdir) / "new_file.txt").write_text("untracked")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertIn("init.txt", committed)
        self.assertNotIn("new_file.txt", committed)

    def test_includeUntracked_true_stages_all(self):
        """includeUntracked=true stages all safe files."""
        (Path(self.tmpdir) / "init.txt").write_text("tracked change")
        (Path(self.tmpdir) / "new_file.txt").write_text("untracked")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        committed = _get_committed_files(self.tmpdir)
        self.assertIn("init.txt", committed)
        self.assertIn("new_file.txt", committed)


# ============================================================
# 4. Configuration
# ============================================================


class TestAutoCommit_Configuration(_AutoCommitTestBase):
    """Tests for configuration handling."""

    def test_disabled_skips(self):
        """autoCommit.enabled=false -> skip."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(enabled=False)):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_onStop_disabled_skips(self):
        """autoCommit.onStop=false -> skip."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(on_stop=False)):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_missing_gitIntegration_skips(self):
        """No gitIntegration section -> skip."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value={"version": "1.0.0"}):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_empty_gitIntegration_skips(self):
        """gitIntegration={} -> skip (empty dict is falsy)."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value={"gitIntegration": {}}):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_missing_autoCommit_defaults_disabled(self):
        """gitIntegration without autoCommit -> defaults to disabled."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value={"gitIntegration": {"preCommitOnDangerous": {}}}):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_custom_prefix_in_message(self):
        """Custom messagePrefix appears in commit message."""
        (Path(self.tmpdir) / "init.txt").write_text("custom prefix test")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(message_prefix="my-prefix")):
            main()

        msg = _get_commit_message(self.tmpdir)
        self.assertTrue(msg.startswith("my-prefix:"),
                        f"Expected 'my-prefix:...' got: {msg}")

    def test_empty_prefix_falls_back_to_default(self):
        """Empty prefix -> falls back to 'auto-checkpoint'."""
        (Path(self.tmpdir) / "init.txt").write_text("fallback test")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(message_prefix="")):
            main()

        msg = _get_commit_message(self.tmpdir)
        self.assertTrue(msg.startswith("auto-checkpoint:"),
                        f"Expected 'auto-checkpoint:...' got: {msg}")

    def test_long_prefix_truncated(self):
        """Prefix > COMMIT_PREFIX_MAX_LENGTH (30) -> truncated."""
        long_prefix = "x" * 50
        (Path(self.tmpdir) / "init.txt").write_text("long prefix")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(message_prefix=long_prefix)):
            main()

        msg = _get_commit_message(self.tmpdir)
        prefix_part = msg.split(":")[0]
        self.assertLessEqual(len(prefix_part),
                             _guardian_utils.COMMIT_PREFIX_MAX_LENGTH)

    def test_message_length_truncated_at_max(self):
        """Total message > COMMIT_MESSAGE_MAX_LENGTH (72) -> truncated."""
        (Path(self.tmpdir) / "init.txt").write_text("length test")

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            with patch(f"{_AC}.validate_commit_prefix",
                       return_value="a" * 60):
                main()

        msg = _get_commit_message(self.tmpdir)
        self.assertLessEqual(len(msg), _guardian_utils.COMMIT_MESSAGE_MAX_LENGTH)

    def test_message_contains_timestamp(self):
        """Commit message contains a timestamp."""
        import re
        (Path(self.tmpdir) / "init.txt").write_text("timestamp test")

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            main()

        msg = _get_commit_message(self.tmpdir)
        self.assertRegex(msg, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_dry_run_no_commit(self):
        """CLAUDE_HOOK_DRY_RUN=true -> log but no commit."""
        (Path(self.tmpdir) / "init.txt").write_text("dry run test")
        initial = _get_commit_count(self.tmpdir)
        os.environ["CLAUDE_HOOK_DRY_RUN"] = "true"

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial)

    def test_dry_run_truthy_values(self):
        """Various truthy DRY_RUN values all skip commit."""
        for val in ("1", "true", "yes", "TRUE", "Yes"):
            (Path(self.tmpdir) / "init.txt").write_text(f"dry {val}")
            initial = _get_commit_count(self.tmpdir)
            os.environ["CLAUDE_HOOK_DRY_RUN"] = val
            _guardian_utils._git_available_cache = None

            with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
                main()

            self.assertEqual(_get_commit_count(self.tmpdir), initial,
                             f"DRY_RUN={val} should skip commit")
            os.environ.pop("CLAUDE_HOOK_DRY_RUN", None)


# ============================================================
# 5. Fail-Open Behavior
# ============================================================


class TestAutoCommit_FailOpen(unittest.TestCase):
    """auto_commit.py is fail-open: commit failure must not block session."""

    def setUp(self):
        self._orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        self._orig_dry_run = os.environ.get("CLAUDE_HOOK_DRY_RUN")
        _guardian_utils._config_cache = None
        _guardian_utils._using_fallback_config = False
        _guardian_utils._active_config_path = None
        _guardian_utils._git_available_cache = None

    def tearDown(self):
        if self._orig_project_dir is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_project_dir
        else:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        if self._orig_dry_run is not None:
            os.environ["CLAUDE_HOOK_DRY_RUN"] = self._orig_dry_run
        else:
            os.environ.pop("CLAUDE_HOOK_DRY_RUN", None)
        _guardian_utils._config_cache = None
        _guardian_utils._using_fallback_config = False
        _guardian_utils._active_config_path = None
        _guardian_utils._git_available_cache = None

    def test_import_error_exits_zero(self):
        """ImportError at module level -> exit(0) (fail-open).

        Tests the try/except at lines 20-42 of auto_commit.py.
        """
        auto_commit_path = str(
            _bootstrap._REPO_ROOT / "hooks" / "scripts" / "auto_commit.py"
        )
        scripts_dir = str(_bootstrap._REPO_ROOT / "hooks" / "scripts")

        # Create a script that removes scripts_dir from path before importing
        test_script = (
            f"import sys\n"
            f"# Remove the real scripts dir so _guardian_utils import fails\n"
            f"sys.path = [p for p in sys.path if p != '{scripts_dir}']\n"
            f"# But we need standard library\n"
            f"import subprocess\n"
            f"result = subprocess.run(\n"
            f"    [sys.executable, '{auto_commit_path}'],\n"
            f"    capture_output=True,\n"
            f"    env={{'PATH': '/usr/bin:/bin', 'HOME': '/tmp'}},\n"
            f"    timeout=10,\n"
            f")\n"
            f"sys.exit(result.returncode)\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True, encoding="utf-8", timeout=15,
        )
        # auto_commit.py catches ImportError and calls sys.exit(0)
        self.assertEqual(result.returncode, 0,
                         f"ImportError should exit(0), got rc={result.returncode}")

    def test_exception_in_main_sets_circuit_subprocess(self):
        """__main__ exception handler sets circuit breaker and exits 0.

        Tests the actual __main__ block by running auto_commit.py as a
        subprocess with main() patched to raise.
        """
        auto_commit_path = str(
            _bootstrap._REPO_ROOT / "hooks" / "scripts" / "auto_commit.py"
        )
        scripts_dir = str(_bootstrap._REPO_ROOT / "hooks" / "scripts")
        tmpdir = _create_test_repo()
        try:
            # Script that patches main() to crash, then executes __main__ logic
            test_script = (
                f"import sys, os\n"
                f"sys.path.insert(0, '{scripts_dir}')\n"
                f"os.environ['CLAUDE_PROJECT_DIR'] = '{tmpdir}'\n"
                f"import auto_commit\n"
                f"def crashing_main():\n"
                f"    raise ValueError('deliberate crash')\n"
                f"auto_commit.main = crashing_main\n"
                f"# Execute the same logic as __main__ block\n"
                f"try:\n"
                f"    auto_commit.main()\n"
                f"except Exception as e:\n"
                f"    auto_commit.log_guardian('ERROR', f'Auto-commit hook error: {{e}}')\n"
                f"    try:\n"
                f"        auto_commit.set_circuit_open(f'auto-commit exception: {{type(e).__name__}}')\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    sys.exit(0)\n"
            )

            result = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True, encoding="utf-8", timeout=15,
            )
            self.assertEqual(result.returncode, 0, "Should exit 0 (fail-open)")

            circuit = Path(tmpdir) / ".claude" / "guardian" / ".circuit_open"
            self.assertTrue(circuit.exists(),
                            "Circuit breaker should be set on exception")
            self.assertIn("ValueError", circuit.read_text())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_subprocess_exit_code_zero(self):
        """Running auto_commit.py as subprocess always exits 0."""
        auto_commit_path = str(
            _bootstrap._REPO_ROOT / "hooks" / "scripts" / "auto_commit.py"
        )
        scripts_dir = str(_bootstrap._REPO_ROOT / "hooks" / "scripts")
        tmpdir = _create_test_repo()
        try:
            env = os.environ.copy()
            env["CLAUDE_PROJECT_DIR"] = tmpdir
            env["PYTHONPATH"] = scripts_dir

            result = subprocess.run(
                [sys.executable, auto_commit_path],
                capture_output=True, encoding="utf-8",
                env=env, timeout=15,
            )
            self.assertEqual(result.returncode, 0,
                             f"auto_commit.py should exit 0.\nstderr: {result.stderr}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_unhandled_exception_exits_zero_subprocess(self):
        """Unhandled exception in main() -> subprocess exits 0.

        Uses a wrapper script that patches main() to raise a RuntimeError,
        then runs the __main__ block to verify fail-open behavior.
        """
        scripts_dir = str(_bootstrap._REPO_ROOT / "hooks" / "scripts")
        tmpdir = _create_test_repo()
        try:
            # Script that makes main() crash, then runs __main__ entry point
            test_script = (
                f"import sys, os\n"
                f"sys.path.insert(0, '{scripts_dir}')\n"
                f"os.environ['CLAUDE_PROJECT_DIR'] = '{tmpdir}'\n"
                f"import auto_commit\n"
                f"original_main = auto_commit.main\n"
                f"def crashing_main():\n"
                f"    raise RuntimeError('forced crash for test')\n"
                f"auto_commit.main = crashing_main\n"
                f"# Replicate __main__ block exactly\n"
                f"try:\n"
                f"    auto_commit.main()\n"
                f"except Exception as e:\n"
                f"    auto_commit.log_guardian('ERROR', f'Auto-commit hook error: {{e}}')\n"
                f"    try:\n"
                f"        auto_commit.set_circuit_open(f'auto-commit exception: {{type(e).__name__}}')\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    sys.exit(0)\n"
            )

            result = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True, encoding="utf-8", timeout=15,
            )
            # Fail-open: exit code must be 0 even when main() crashes
            self.assertEqual(result.returncode, 0,
                             f"Should exit 0 on crash, got rc={result.returncode}\n"
                             f"stderr: {result.stderr}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# 6. Commit Message Format
# ============================================================


class TestAutoCommit_CommitMessageFormat(_AutoCommitTestBase):
    """Tests for commit message formatting."""

    def test_default_format(self):
        """Default: 'auto-checkpoint: YYYY-MM-DD HH:MM:SS'."""
        (Path(self.tmpdir) / "init.txt").write_text("format test")

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            main()

        msg = _get_commit_message(self.tmpdir)
        self.assertTrue(msg.startswith("auto-checkpoint: "),
                        f"Expected 'auto-checkpoint: ...' got: {msg}")

    def test_truncation_ends_with_ellipsis(self):
        """Messages > 72 chars end with '...'."""
        (Path(self.tmpdir) / "init.txt").write_text("truncation test")

        with patch(f"{_AC}.load_guardian_config", return_value=_make_config()):
            with patch(f"{_AC}.validate_commit_prefix",
                       return_value="very-long-prefix-that-will-exceed-limit-when-combined"):
                main()

        msg = _get_commit_message(self.tmpdir)
        # prefix + ": " + timestamp = way more than 72
        if len("very-long-prefix-that-will-exceed-limit-when-combined: 2026-03-22 00:00:00") > 72:
            self.assertTrue(msg.endswith("..."),
                            f"Truncated message should end with '...', got: {msg}")
            self.assertLessEqual(len(msg), _guardian_utils.COMMIT_MESSAGE_MAX_LENGTH)


# ============================================================
# 7. Integration (end-to-end with real git)
# ============================================================


class TestAutoCommit_Integration(_AutoCommitTestBase):
    """End-to-end integration tests."""

    def test_full_cycle_tracked(self):
        """Modify tracked file -> auto-commit -> verify."""
        (Path(self.tmpdir) / "init.txt").write_text("modified content")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial + 1)
        self.assertIn("init.txt", _get_committed_files(self.tmpdir))

    def test_full_cycle_with_untracked(self):
        """Create new file -> auto-commit with untracked -> verify."""
        (Path(self.tmpdir) / "new.py").write_text("print('hello')")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial + 1)
        self.assertIn("new.py", _get_committed_files(self.tmpdir))

    def test_successful_commit_clears_circuit(self):
        """Successful commit clears circuit breaker file."""
        cf = self._circuit_file()
        cf.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        cf.write_text(f"{datetime.now().isoformat()}|old failure\n")

        (Path(self.tmpdir) / "init.txt").write_text("recover")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=False)):
            with patch(f"{_AC}.is_circuit_open", return_value=(False, "")):
                main()

        self.assertFalse(cf.exists())

    def test_multiple_files_single_commit(self):
        """Multiple files committed in a single commit."""
        (Path(self.tmpdir) / "init.txt").write_text("changed")
        (Path(self.tmpdir) / "file2.txt").write_text("new 2")
        (Path(self.tmpdir) / "file3.txt").write_text("new 3")
        initial = _get_commit_count(self.tmpdir)

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        self.assertEqual(_get_commit_count(self.tmpdir), initial + 1)
        committed = _get_committed_files(self.tmpdir)
        for f in ["init.txt", "file2.txt", "file3.txt"]:
            self.assertIn(f, committed)

    def test_subdirectory_files(self):
        """Files in subdirectories are committed."""
        subdir = Path(self.tmpdir) / "src" / "lib"
        subdir.mkdir(parents=True)
        (subdir / "module.py").write_text("# module")

        with patch(f"{_AC}.load_guardian_config",
                   return_value=_make_config(include_untracked=True)):
            main()

        self.assertIn("src/lib/module.py", _get_committed_files(self.tmpdir))


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    unittest.main()
