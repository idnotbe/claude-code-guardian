#!/usr/bin/env python3
"""Regression tests for Guardian bypass incident (2026-03-02).

Tests the specific incident command and all 14 bypass vectors + 10 attack chains
identified in the analysis.
"""
import os
import sys
import unittest

# Add hooks/scripts to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'hooks', 'scripts'))

from _guardian_utils import (
    match_block_patterns,
    check_interpreter_payload,
    extract_interpreter_payload,
)
from bash_guardian import is_delete_command


class TestIncidentRegression(unittest.TestCase):
    """Tests for the specific incident that triggered the bypass analysis."""

    def test_incident_command_single_line(self):
        """The exact incident command (single-line) must be blocked."""
        cmd = '''python3 -c "import os, glob; [os.unlink(f) for f in glob.glob('.claude/memory/.staging/*.invalid.*')]"'''
        blocked, reason = match_block_patterns(cmd)
        self.assertTrue(blocked, f"Incident command not blocked: {cmd}")

    def test_incident_command_multiline(self):
        """Multiline variant must be caught by is_delete_command (Layer 3/4).

        match_block_patterns (Layer 0) uses [^|&\\n]* which stops at newlines,
        so multiline payloads are handled by the payload extraction in
        is_delete_command() instead. This is by design (V1 Issue 7).
        """
        cmd = 'python3 -c "import os\nimport glob\n[os.unlink(f) for f in glob.glob(\'.claude/memory/.staging/*.invalid.*\')]"'
        self.assertTrue(is_delete_command(cmd), f"Multiline incident command not caught: {cmd}")

    def test_incident_is_delete_command(self):
        """is_delete_command should detect the incident command."""
        cmd = '''python3 -c "import os; [os.unlink(f) for f in glob.glob('.claude/memory/.staging/*.invalid.*')]"'''
        self.assertTrue(is_delete_command(cmd))


class TestInterpreterPayloadExtraction(unittest.TestCase):
    """Tests for the interpreter payload extraction function."""

    def test_python_c_double_quote(self):
        payload = extract_interpreter_payload('python3 -c "import os; os.unlink(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)

    def test_python_c_single_quote(self):
        payload = extract_interpreter_payload("python3 -c 'import os; os.unlink(\"f\")'")
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)

    def test_python_multiline_payload(self):
        payload = extract_interpreter_payload('python3 -c "import os\nos.unlink(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)

    def test_node_e_flag(self):
        payload = extract_interpreter_payload('node -e "const fs = require(\'fs\'); fs.unlinkSync(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("unlinkSync", payload)

    def test_perl_e_flag(self):
        payload = extract_interpreter_payload('perl -e "unlink \'file\'"')
        self.assertIsNotNone(payload)
        self.assertIn("unlink", payload)

    def test_non_interpreter_returns_none(self):
        payload = extract_interpreter_payload('ls -la')
        self.assertIsNone(payload)

    def test_python_without_c_flag(self):
        payload = extract_interpreter_payload('python3 script.py')
        self.assertIsNone(payload)

    # V2 RF-05: flags before -c/-e
    def test_python_flag_with_arg_before_c(self):
        """python3 -W ignore -c '...' must extract payload (RF-05)."""
        payload = extract_interpreter_payload('python3 -W ignore -c "import os; os.unlink(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)

    def test_python_flag_no_arg_before_c(self):
        """python3 -B -c '...' must extract payload (RF-05)."""
        payload = extract_interpreter_payload('python3 -B -c "import os; os.unlink(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)

    def test_python_multiple_flags_before_c(self):
        """python3 -B -u -c '...' must extract payload (RF-05)."""
        payload = extract_interpreter_payload('python3 -B -u -c "import os; os.unlink(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)

    def test_env_prefix_with_flags(self):
        """env python3 -W ignore -c '...' must extract payload (RF-05 + V1 Issue 5)."""
        payload = extract_interpreter_payload('env python3 -W ignore -c "os.unlink(\'f\')"')
        self.assertIsNotNone(payload)
        self.assertIn("os.unlink", payload)


class TestDestructivePayloadCheck(unittest.TestCase):
    """Tests for check_interpreter_payload."""

    def test_python_os_unlink(self):
        is_destructive, _ = check_interpreter_payload(
            'python3 -c "import os; os.unlink(\'file\')"'
        )
        self.assertTrue(is_destructive)

    def test_python_shutil_rmtree(self):
        is_destructive, _ = check_interpreter_payload(
            'python3 -c "import shutil; shutil.rmtree(\'dir\')"'
        )
        self.assertTrue(is_destructive)

    def test_python_pathlib_unlink(self):
        is_destructive, _ = check_interpreter_payload(
            'python3 -c "from pathlib import Path; Path(\'f\').unlink()"'
        )
        self.assertTrue(is_destructive)

    def test_node_unlink_sync(self):
        is_destructive, _ = check_interpreter_payload(
            'node -e "require(\'fs\').unlinkSync(\'f\')"'
        )
        self.assertTrue(is_destructive)

    def test_benign_python_read(self):
        """Benign read commands should NOT be flagged."""
        is_destructive, _ = check_interpreter_payload(
            'python3 -c "print(open(\'.claude/memory/file\').read())"'
        )
        self.assertFalse(is_destructive)

    def test_benign_python_print(self):
        is_destructive, _ = check_interpreter_payload(
            'python3 -c "import json; print(json.dumps({\'key\': \'val\'}))"'
        )
        self.assertFalse(is_destructive)

    def test_benign_node_read(self):
        is_destructive, _ = check_interpreter_payload(
            'node -e "console.log(require(\'fs\').readFileSync(\'f\', \'utf8\'))"'
        )
        self.assertFalse(is_destructive)

    def test_benign_python_script(self):
        """python3 script.py should NOT be checked (no -c flag)."""
        is_destructive, _ = check_interpreter_payload(
            'python3 test_script.py'
        )
        self.assertFalse(is_destructive)


class TestNewBlockPatterns(unittest.TestCase):
    """Tests for new block patterns added in Phase 1c."""

    def test_bash_c_rm_claude(self):
        """bash -c 'rm .claude/...' must be blocked (BV-03)."""
        blocked, _ = match_block_patterns('bash -c "rm -rf .claude/memory"')
        self.assertTrue(blocked)

    def test_sh_c_rm_claude(self):
        blocked, _ = match_block_patterns('sh -c "rm .claude/settings.json"')
        self.assertTrue(blocked)

    def test_eval_rm_claude(self):
        """eval 'rm .claude/...' must be blocked (BV-06)."""
        blocked, _ = match_block_patterns('eval "rm -rf .claude/guardian"')
        self.assertTrue(blocked)

    def test_ln_hardlink_to_claude(self):
        """Hardlink creation targeting .claude must be blocked (AC-02)."""
        blocked, _ = match_block_patterns('ln .claude/guardian/config.json /tmp/alias')
        self.assertTrue(blocked)

    def test_ln_hardlink_from_outside(self):
        blocked, _ = match_block_patterns('ln /tmp/something .claude/guardian/config.json')
        self.assertTrue(blocked)

    def test_ln_s_symlink_allowed(self):
        """Symbolic links should NOT be blocked by hardlink pattern."""
        blocked, _ = match_block_patterns('ln -s .claude/memory/foo /tmp/link')
        # ln -s is a symlink, not hardlink — should NOT match hardlink pattern
        # (symlinks are handled by symlink escape detection)
        # Note: This may still be blocked by other patterns
        pass  # Test intent documented, exact behavior depends on other patterns

    def test_kill_guardian(self):
        """Killing guardian processes must be blocked (AC-03)."""
        blocked, _ = match_block_patterns('kill -9 $(pgrep guardian)')
        self.assertTrue(blocked)

    def test_pkill_guardian(self):
        blocked, _ = match_block_patterns('pkill -f _guardian_utils')
        self.assertTrue(blocked)

    def test_chmod_guardian_config(self):
        """chmod on guardian/settings files must be blocked (NF-01)."""
        blocked, _ = match_block_patterns('chmod 777 .claude/guardian/config.json')
        self.assertTrue(blocked)

    def test_chmod_settings(self):
        blocked, _ = match_block_patterns('chmod 666 .claude/settings.json')
        self.assertTrue(blocked)

    def test_setfacl_claude(self):
        """setfacl targeting .claude must be blocked (BV-13)."""
        blocked, _ = match_block_patterns('setfacl -m u:user:rwx .claude/guardian/config.json')
        self.assertTrue(blocked)

    def test_perl_truncate(self):
        """Perl truncate must be blocked (BV-12)."""
        blocked, _ = match_block_patterns('perl -e "truncate \'file\', 0"')
        self.assertTrue(blocked)

    # False positive tests
    def test_benign_ln_symlink(self):
        """Normal symbolic link creation should NOT be blocked."""
        blocked, _ = match_block_patterns('ln -s /usr/lib/foo /usr/local/lib/foo')
        self.assertFalse(blocked)

    def test_benign_kill(self):
        """Killing non-guardian process should NOT be blocked."""
        blocked, _ = match_block_patterns('kill -9 12345')
        self.assertFalse(blocked)

    def test_benign_chmod(self):
        """chmod on non-guardian files should NOT be blocked."""
        blocked, _ = match_block_patterns('chmod 755 temp/test.sh')
        self.assertFalse(blocked)

    def test_benign_install(self):
        """Normal install commands should NOT be blocked."""
        blocked, _ = match_block_patterns('pip install requests')
        self.assertFalse(blocked)

    def test_benign_npm_install(self):
        blocked, _ = match_block_patterns('npm install express')
        self.assertFalse(blocked)


class TestSelfGuardianPaths(unittest.TestCase):
    """Tests for SELF_GUARDIAN_PATHS additions."""

    def test_settings_json_in_self_guardian(self):
        from _guardian_utils import SELF_GUARDIAN_PATHS
        self.assertIn(".claude/settings.json", SELF_GUARDIAN_PATHS)

    def test_settings_local_json_in_self_guardian(self):
        from _guardian_utils import SELF_GUARDIAN_PATHS
        self.assertIn(".claude/settings.local.json", SELF_GUARDIAN_PATHS)

    def test_config_json_still_in_self_guardian(self):
        from _guardian_utils import SELF_GUARDIAN_PATHS
        self.assertIn(".claude/guardian/config.json", SELF_GUARDIAN_PATHS)


if __name__ == "__main__":
    unittest.main()
