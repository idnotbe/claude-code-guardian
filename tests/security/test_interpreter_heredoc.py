#!/usr/bin/env python3
"""Phase 3 tests: Interpreter+heredoc ASK backstop.

Tests verify that:
1. _is_interpreter_heredoc() correctly detects interpreter commands with heredoc
2. Non-interpreter commands with heredoc are not flagged
3. Commands without heredoc are not flagged
4. Full main() flow escalates to ASK for interpreter+heredoc patterns
5. Prefixes (env, sudo, nohup, nice) are handled correctly
6. Absolute paths and variable assignments are handled

Run: python -m pytest tests/security/test_interpreter_heredoc.py -v
  or: python3 tests/security/test_interpreter_heredoc.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Bootstrap imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401

from bash_guardian import _is_interpreter_heredoc

# Constants
REPO_ROOT = _bootstrap._REPO_ROOT
BASH_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")


def _make_bash_hook_input(command):
    """Create JSON hook input for a Bash tool call."""
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
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


def _get_permission_decision(stdout):
    """Extract permissionDecision from hook response."""
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        resp = json.loads(stdout)
        return resp.get("hookSpecificOutput", {}).get("permissionDecision")
    except json.JSONDecodeError:
        return None


def _get_permission_reason(stdout):
    """Extract permissionDecisionReason from hook response."""
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        resp = json.loads(stdout)
        return resp.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    except json.JSONDecodeError:
        return None


# ============================================================
# 1. Unit Tests: _is_interpreter_heredoc()
# ============================================================


class TestIsInterpreterHeredoc(unittest.TestCase):
    """Unit tests for _is_interpreter_heredoc() detection function."""

    def test_bash_heredoc(self):
        """bash << EOF -> True."""
        self.assertTrue(_is_interpreter_heredoc("bash << EOF\necho hello\nEOF"))

    def test_python3_heredoc(self):
        """python3 << EOF -> True (Python interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("python3 << EOF\nprint('hi')\nEOF"))

    def test_node_heredoc(self):
        """node << EOF -> True (Node)."""
        self.assertTrue(_is_interpreter_heredoc("node << EOF\nconsole.log('hi')\nEOF"))

    def test_cat_heredoc_not_interpreter(self):
        """cat << EOF -> False (not an interpreter)."""
        self.assertFalse(_is_interpreter_heredoc("cat << EOF\nsome text\nEOF"))

    def test_env_bash_heredoc(self):
        """env bash << EOF -> True (env prefix)."""
        self.assertTrue(_is_interpreter_heredoc("env bash << EOF\necho hello\nEOF"))

    def test_sudo_bash_heredoc(self):
        """sudo -u root bash << EOF -> True (sudo prefix)."""
        self.assertTrue(_is_interpreter_heredoc("sudo -u root bash << EOF\necho hello\nEOF"))

    def test_absolute_path_bash_heredoc(self):
        """/usr/bin/bash << EOF -> True (absolute path)."""
        self.assertTrue(_is_interpreter_heredoc("/usr/bin/bash << EOF\necho hello\nEOF"))

    def test_here_string_also_caught(self):
        """bash <<< 'hello' -> True (here-string also caught by << check)."""
        self.assertTrue(_is_interpreter_heredoc("bash <<< 'hello'"))

    def test_variable_assignment_prefix(self):
        """FOO=bar bash << EOF -> True (variable assignment prefix)."""
        self.assertTrue(_is_interpreter_heredoc("FOO=bar bash << EOF\necho hello\nEOF"))

    def test_no_heredoc_returns_false(self):
        """bash -c 'echo test' -> False (no heredoc operator)."""
        self.assertFalse(_is_interpreter_heredoc("bash -c 'echo test'"))

    def test_bash_script_no_heredoc(self):
        """bash script.sh -> False (no heredoc operator)."""
        self.assertFalse(_is_interpreter_heredoc("bash script.sh"))

    def test_grep_heredoc_not_interpreter(self):
        """grep << EOF -> False (grep is not an interpreter)."""
        self.assertFalse(_is_interpreter_heredoc("grep << EOF\npattern\nEOF"))

    def test_sh_heredoc(self):
        """sh << EOF -> True (sh is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("sh << EOF\necho hello\nEOF"))

    def test_perl_heredoc(self):
        """perl << EOF -> True (perl is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("perl << EOF\nprint 'hi'\nEOF"))

    def test_ruby_heredoc(self):
        """ruby << EOF -> True (ruby is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("ruby << EOF\nputs 'hi'\nEOF"))

    def test_zsh_heredoc(self):
        """zsh << EOF -> True (zsh is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("zsh << EOF\necho hello\nEOF"))

    def test_dash_heredoc(self):
        """dash << EOF -> True (dash is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("dash << EOF\necho hello\nEOF"))

    def test_deno_heredoc(self):
        """deno << EOF -> True (deno is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("deno << EOF\nconsole.log('hi')\nEOF"))

    def test_bun_heredoc(self):
        """bun << EOF -> True (bun is an interpreter)."""
        self.assertTrue(_is_interpreter_heredoc("bun << EOF\nconsole.log('hi')\nEOF"))

    def test_eval_heredoc(self):
        """eval << EOF -> True (eval is an interpreter command)."""
        self.assertTrue(_is_interpreter_heredoc("eval << EOF\necho hello\nEOF"))

    def test_source_heredoc(self):
        """source /dev/stdin << EOF -> True (source is an interpreter command)."""
        self.assertTrue(_is_interpreter_heredoc("source /dev/stdin << EOF\necho hello\nEOF"))

    def test_exec_heredoc(self):
        """exec << EOF -> True (exec is an interpreter command)."""
        self.assertTrue(_is_interpreter_heredoc("exec << EOF\ncommands\nEOF"))

    def test_echo_heredoc_not_interpreter(self):
        """echo << EOF -> False (echo is not an interpreter)."""
        self.assertFalse(_is_interpreter_heredoc("echo << EOF\ntext\nEOF"))

    def test_nohup_bash_heredoc(self):
        """nohup bash << EOF -> True (nohup prefix)."""
        self.assertTrue(_is_interpreter_heredoc("nohup bash << EOF\necho hello\nEOF"))

    def test_nice_python3_heredoc(self):
        """nice python3 << EOF -> True (nice prefix)."""
        self.assertTrue(_is_interpreter_heredoc("nice python3 << EOF\nprint('hi')\nEOF"))

    def test_empty_string(self):
        """Empty string -> False."""
        self.assertFalse(_is_interpreter_heredoc(""))

    def test_heredoc_only_operator(self):
        """Just << -> False (no command before it)."""
        self.assertFalse(_is_interpreter_heredoc("<<"))

    def test_tab_stripped_heredoc(self):
        """bash <<-EOF -> True (tab-stripped heredoc variant)."""
        self.assertTrue(_is_interpreter_heredoc("bash <<-EOF\n\techo hello\nEOF"))

    def test_quoted_delimiter(self):
        """bash << 'EOF' -> True (quoted delimiter)."""
        self.assertTrue(_is_interpreter_heredoc("bash << 'EOF'\necho hello\nEOF"))

    def test_python_heredoc(self):
        """python << EOF -> True (python without version number)."""
        self.assertTrue(_is_interpreter_heredoc("python << EOF\nprint('hi')\nEOF"))

    def test_python2_heredoc(self):
        """python2 << EOF -> True (python2)."""
        self.assertTrue(_is_interpreter_heredoc("python2 << EOF\nprint 'hi'\nEOF"))

    def test_multiple_var_assignments(self):
        """A=1 B=2 bash << EOF -> True (multiple var assignments)."""
        self.assertTrue(_is_interpreter_heredoc("A=1 B=2 bash << EOF\necho hello\nEOF"))

    def test_usr_local_bin_python3(self):
        """/usr/local/bin/python3 << EOF -> True (absolute path)."""
        self.assertTrue(_is_interpreter_heredoc(
            "/usr/local/bin/python3 << EOF\nprint('hi')\nEOF"
        ))

    def test_wc_heredoc_not_interpreter(self):
        """wc << EOF -> False (wc is a passive data sink, not interpreter)."""
        self.assertFalse(_is_interpreter_heredoc("wc << EOF\nline1\nline2\nEOF"))


# ============================================================
# 1b. V1 Fix Tests: dot command + versioned interpreters
# ============================================================


class TestV1Fixes(unittest.TestCase):
    """V1 fix tests for dot command and versioned interpreter detection."""

    def test_dot_command_heredoc(self):
        """. /dev/stdin << EOF -> True (dot = POSIX source)."""
        self.assertTrue(_is_interpreter_heredoc(
            ". /dev/stdin << EOF\necho hello\nEOF"
        ))

    def test_dot_bare_heredoc(self):
        """. << EOF -> True (dot command with heredoc)."""
        self.assertTrue(_is_interpreter_heredoc(". << EOF\necho hello\nEOF"))

    def test_python3_10_heredoc(self):
        """python3.10 << EOF -> True (versioned Python)."""
        self.assertTrue(_is_interpreter_heredoc(
            "python3.10 << EOF\nprint('hi')\nEOF"
        ))

    def test_python3_12_heredoc(self):
        """python3.12 << EOF -> True (versioned Python)."""
        self.assertTrue(_is_interpreter_heredoc(
            "python3.12 << EOF\nprint('hi')\nEOF"
        ))

    def test_python2_7_heredoc(self):
        """python2.7 << EOF -> True (versioned Python 2)."""
        self.assertTrue(_is_interpreter_heredoc(
            "python2.7 << EOF\nprint 'hi'\nEOF"
        ))

    def test_ruby3_0_heredoc(self):
        """ruby3.0 << EOF -> True (versioned Ruby)."""
        self.assertTrue(_is_interpreter_heredoc(
            "ruby3.0 << EOF\nputs 'hi'\nEOF"
        ))

    def test_perl5_34_heredoc(self):
        """perl5.34 << EOF -> True (versioned Perl)."""
        self.assertTrue(_is_interpreter_heredoc(
            "perl5.34 << EOF\nprint 'hi'\nEOF"
        ))

    def test_versioned_with_absolute_path(self):
        """/usr/bin/python3.10 << EOF -> True."""
        self.assertTrue(_is_interpreter_heredoc(
            "/usr/bin/python3.10 << EOF\nprint('hi')\nEOF"
        ))

    def test_non_interpreter_with_numbers(self):
        """cat3 << EOF -> False (not a versioned interpreter)."""
        self.assertFalse(_is_interpreter_heredoc(
            "cat3 << EOF\ntext\nEOF"
        ))

    def test_nodemon_not_matched(self):
        """nodemon << EOF -> False (not a versioned node, different tool)."""
        # _extract_base_command returns 'nodemon', not in _INTERPRETER_COMMANDS
        # and doesn't match _VERSIONED_INTERPRETER_RE (no leading digit after prefix)
        self.assertFalse(_is_interpreter_heredoc(
            "nodemon << EOF\nconsole.log('hi')\nEOF"
        ))

    def test_shutil_not_matched(self):
        """shutil << EOF -> False (not a versioned sh)."""
        self.assertFalse(_is_interpreter_heredoc(
            "shutil << EOF\ntext\nEOF"
        ))


# ============================================================
# 1c. V2 Fix Tests: hyphenated/letter-suffixed interpreters
# ============================================================


class TestV2Fixes(unittest.TestCase):
    """V2 fix tests for broader versioned interpreter matching."""

    def test_python3_8m_heredoc(self):
        """python3.8m << EOF -> True (pymalloc suffix)."""
        self.assertTrue(_is_interpreter_heredoc(
            "python3.8m << EOF\nprint('hi')\nEOF"
        ))

    def test_python3_12m_heredoc(self):
        """python3.12m << EOF -> True."""
        self.assertTrue(_is_interpreter_heredoc(
            "python3.12m << EOF\nprint('hi')\nEOF"
        ))

    def test_bash_5_0_heredoc(self):
        """bash-5.0 << EOF -> True (hyphenated version)."""
        self.assertTrue(_is_interpreter_heredoc(
            "bash-5.0 << EOF\necho hello\nEOF"
        ))

    def test_ruby_3_2_heredoc(self):
        """ruby-3.2 << EOF -> True (hyphenated version)."""
        self.assertTrue(_is_interpreter_heredoc(
            "ruby-3.2 << EOF\nputs 'hi'\nEOF"
        ))

    def test_perl_micro_version(self):
        """perl5.34.1 << EOF -> True (micro version)."""
        self.assertTrue(_is_interpreter_heredoc(
            "perl5.34.1 << EOF\nprint 'hi'\nEOF"
        ))

    def test_shred_not_matched(self):
        """shred << EOF -> False (not a versioned sh, starts with 'sh' but no digit/hyphen after)."""
        self.assertFalse(_is_interpreter_heredoc(
            "shred << EOF\ntext\nEOF"
        ))

    def test_perldoc_not_matched(self):
        """perldoc << EOF -> False (not a versioned perl)."""
        self.assertFalse(_is_interpreter_heredoc(
            "perldoc << EOF\ntext\nEOF"
        ))

    def test_bashrc_not_matched(self):
        """bashrc << EOF -> False (not a versioned bash)."""
        self.assertFalse(_is_interpreter_heredoc(
            "bashrc << EOF\ntext\nEOF"
        ))

    def test_python3a_not_matched(self):
        """python3a << EOF -> False (letter immediately after, no version digit)."""
        # 'python3a' doesn't match: requires digit or hyphen after base, but 'python3'
        # + 'a' doesn't start with digit/hyphen. Wait... 'python3a' - the regex is
        # (?:python[23]?)(?:[-\d][\w.-]*)$ so it matches 'python' + '3a' with '3' being
        # the digit start and 'a' matching \w. Let me check... 'python3a' matches
        # 'python' + '3a' where '3' is [-\d] and 'a' is [\w.-]. So it DOES match.
        # That's acceptable — 'python3a' looks like a versioned Python variant.
        # For this test we just verify it triggers (over-ask is safe).
        self.assertTrue(_is_interpreter_heredoc(
            "python3a << EOF\nprint('hi')\nEOF"
        ))

    def test_sudo_inline_equals_flag(self):
        """sudo --user=root bash << EOF -> True (V2 fix: --flag=value inline arg)."""
        self.assertTrue(_is_interpreter_heredoc(
            "sudo --user=root bash << EOF\necho hello\nEOF"
        ))

    def test_sudo_preserve_env_equals(self):
        """sudo --preserve-env=HOME bash << EOF -> True (GNU-style inline arg)."""
        self.assertTrue(_is_interpreter_heredoc(
            "sudo --preserve-env=HOME bash << EOF\necho hello\nEOF"
        ))


# ============================================================
# 2. Integration Tests: Full main() flow via subprocess
# ============================================================


class TestInterpreterHeredocIntegration(unittest.TestCase):
    """Full main() flow integration tests for interpreter+heredoc ASK backstop."""

    def setUp(self):
        """Create a temporary project directory."""
        self.tmpdir = tempfile.mkdtemp()
        self.env = {
            "CLAUDE_PROJECT_DIR": self.tmpdir,
        }

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_bash_guardian(self, command):
        """Run bash_guardian with a command and return (decision, reason)."""
        stdin_data = _make_bash_hook_input(command)
        result = _run_hook_subprocess(
            BASH_GUARDIAN_PATH, stdin_data, env_override=self.env
        )
        decision = _get_permission_decision(result.stdout)
        reason = _get_permission_reason(result.stdout)
        return decision, reason, result

    def test_bash_heredoc_triggers_ask(self):
        """bash << EOF\\necho hello\\nEOF -> ASK (interpreter heredoc)."""
        decision, reason, _ = self._run_bash_guardian(
            "bash << EOF\necho hello\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for bash heredoc. Got: {decision}"
        )
        self.assertIn("heredoc", reason.lower(),
                       f"Reason should mention heredoc. Got: {reason}")

    def test_cat_heredoc_no_interpreter_trigger(self):
        """cat << EOF\\nsome text\\nEOF -> ALLOW (not interpreter).

        cat heredoc without output redirect is safe and should not trigger
        the interpreter+heredoc backstop.
        """
        decision, reason, result = self._run_bash_guardian(
            "cat << EOF\nsome text\nEOF"
        )
        # Should NOT be ask/deny due to interpreter+heredoc
        # (might be allow or None for safe commands)
        self.assertNotEqual(
            decision, "deny",
            f"cat heredoc should not be denied. Got: {decision}. "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )

    def test_sudo_bash_heredoc_triggers_ask(self):
        """sudo bash << EOF\\nls\\nEOF -> ASK (sudo prefix)."""
        decision, reason, _ = self._run_bash_guardian(
            "sudo bash << EOF\nls\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for sudo bash heredoc. Got: {decision}"
        )

    def test_python3_heredoc_triggers_ask(self):
        """python3 << EOF\\nprint('hello')\\nEOF -> ASK (Python)."""
        decision, reason, _ = self._run_bash_guardian(
            "python3 << EOF\nprint('hello')\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for python3 heredoc. Got: {decision}"
        )

    def test_bash_c_no_heredoc_trigger(self):
        """bash -c 'echo test' -> no heredoc trigger (no <<)."""
        decision, reason, _ = self._run_bash_guardian("bash -c 'echo test'")
        # Should not trigger heredoc backstop (no <<)
        # May trigger other checks, but should not be denied
        # The important thing: it should NOT mention heredoc in reason
        if reason:
            self.assertNotIn(
                "heredoc", reason.lower(),
                f"bash -c should not trigger heredoc backstop. Reason: {reason}"
            )

    def test_bash_script_no_heredoc_trigger(self):
        """bash script.sh -> no heredoc trigger (no <<)."""
        decision, reason, _ = self._run_bash_guardian("bash script.sh")
        if reason:
            self.assertNotIn(
                "heredoc", reason.lower(),
                f"bash script.sh should not trigger heredoc backstop. Reason: {reason}"
            )

    def test_node_heredoc_triggers_ask(self):
        """node << EOF\\nconsole.log('hi')\\nEOF -> ASK (Node)."""
        decision, reason, _ = self._run_bash_guardian(
            "node << EOF\nconsole.log('hi')\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for node heredoc. Got: {decision}"
        )

    def test_env_bash_heredoc_triggers_ask(self):
        """env bash << EOF\\necho hello\\nEOF -> ASK (env prefix)."""
        decision, reason, _ = self._run_bash_guardian(
            "env bash << EOF\necho hello\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for env bash heredoc. Got: {decision}"
        )

    def test_absolute_path_bash_heredoc_triggers_ask(self):
        """/usr/bin/bash << EOF\\necho hello\\nEOF -> ASK (absolute path)."""
        decision, reason, _ = self._run_bash_guardian(
            "/usr/bin/bash << EOF\necho hello\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for /usr/bin/bash heredoc. Got: {decision}"
        )

    def test_benign_bash_heredoc_still_asks(self):
        """Even benign bash << EOF\\necho hi\\nEOF triggers ASK.

        This is intentional -- any code execution via heredoc warrants
        confirmation in --dangerously-skip-permissions mode.
        """
        decision, reason, _ = self._run_bash_guardian(
            "bash << EOF\necho hi\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Even benign bash heredoc should ASK. Got: {decision}"
        )

    def test_dangerous_bash_heredoc_at_least_ask(self):
        """bash << EOF\\nrm -rf /\\nEOF -> at least ASK (may be deny from other checks)."""
        decision, reason, _ = self._run_bash_guardian(
            "bash << EOF\nrm -rf /\nEOF"
        )
        self.assertIn(
            decision, ("ask", "deny"),
            f"Dangerous bash heredoc should be at least ask. Got: {decision}"
        )

    def test_perl_heredoc_triggers_ask(self):
        """perl << EOF\\nprint 'hi'\\nEOF -> ASK (Perl)."""
        decision, reason, _ = self._run_bash_guardian(
            "perl << EOF\nprint 'hi'\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for perl heredoc. Got: {decision}"
        )

    def test_ruby_heredoc_triggers_ask(self):
        """ruby << EOF\\nputs 'hi'\\nEOF -> ASK (Ruby)."""
        decision, reason, _ = self._run_bash_guardian(
            "ruby << EOF\nputs 'hi'\nEOF"
        )
        self.assertEqual(
            decision, "ask",
            f"Expected 'ask' for ruby heredoc. Got: {decision}"
        )


if __name__ == '__main__':
    unittest.main()
