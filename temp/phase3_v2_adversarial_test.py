#!/usr/bin/env python3
"""Phase 3 V2 Adversarial Test Probes.

Tests the V1 fixes to _is_interpreter_heredoc():
1. Dot command (.) added to _INTERPRETER_COMMANDS
2. _VERSIONED_INTERPRETER_RE for versioned interpreters (python3.10, etc.)

Also tests bypass attempts, edge cases, and accepted limitations.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Bootstrap
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import _bootstrap  # noqa: F401

from bash_guardian import (
    _is_interpreter_heredoc,
    _INTERPRETER_COMMANDS,
    _VERSIONED_INTERPRETER_RE,
    _extract_base_command,
    split_commands,
)

REPO_ROOT = _bootstrap._REPO_ROOT
BASH_GUARDIAN_PATH = str(REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")


def _make_bash_hook_input(command):
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": command},
    })


def _run_hook_subprocess(command, tmpdir):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = tmpdir
    return subprocess.run(
        [sys.executable, BASH_GUARDIAN_PATH],
        input=_make_bash_hook_input(command),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def _get_decision(stdout):
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        resp = json.loads(stdout)
        return resp.get("hookSpecificOutput", {}).get("permissionDecision")
    except json.JSONDecodeError:
        return None


def _get_reason(stdout):
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        resp = json.loads(stdout)
        return resp.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    except json.JSONDecodeError:
        return None


# ============================================================
# Category 1: V1 Fix Validation
# ============================================================

class TestV1FixValidation(unittest.TestCase):
    """Verify the V1 fixes actually work."""

    def test_dot_command_in_frozenset(self):
        """'.' should be in _INTERPRETER_COMMANDS."""
        self.assertIn('.', _INTERPRETER_COMMANDS)

    def test_source_command_in_frozenset(self):
        """'source' should be in _INTERPRETER_COMMANDS."""
        self.assertIn('source', _INTERPRETER_COMMANDS)

    def test_dot_devstdin_heredoc(self):
        """. /dev/stdin << EOF -> should trigger."""
        self.assertTrue(_is_interpreter_heredoc(". /dev/stdin << EOF\necho hello\nEOF"))

    def test_dot_bare_heredoc(self):
        """. << EOF -> should trigger."""
        self.assertTrue(_is_interpreter_heredoc(". << EOF\necho hello\nEOF"))

    def test_python3_10_heredoc(self):
        """python3.10 << EOF -> should trigger via regex."""
        self.assertTrue(_is_interpreter_heredoc("python3.10 << EOF\nprint('hi')\nEOF"))

    def test_python3_12_absolute_path(self):
        """/usr/bin/python3.12 << EOF -> should trigger."""
        self.assertTrue(_is_interpreter_heredoc(
            "/usr/bin/python3.12 << EOF\nprint('hi')\nEOF"
        ))

    def test_nodemon_no_trigger(self):
        """nodemon << EOF -> should NOT trigger (regression check)."""
        self.assertFalse(_is_interpreter_heredoc(
            "nodemon << EOF\nconsole.log('hi')\nEOF"
        ))


# ============================================================
# Category 2: Accepted Limitations Verification
# ============================================================

class TestAcceptedLimitations(unittest.TestCase):
    """Verify accepted limitations and Phase 1 retention behavior."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_nice_n5_bash_heredoc_phase3_misses(self):
        """nice -n 5 bash << EOF -> Phase 3 _is_interpreter_heredoc check.

        _extract_base_command should handle 'nice' as a prefix and find 'bash'.
        Let's verify what _extract_base_command returns for 'nice -n 5 bash'.
        """
        # First check what _extract_base_command returns
        base = _extract_base_command("nice -n 5 bash")
        # nice is in skip_prefixes, but -n 5 is a flag+arg pair
        # nice doesn't have special flag handling like sudo does
        # So after 'nice' is skipped, '-n' is next - it starts with '-'
        # but nice isn't sudo, so no flag handling. '-n' would be treated as...
        # Let's just test it:
        print(f"  _extract_base_command('nice -n 5 bash') = '{base}'")

        # Now test the full detection
        result = _is_interpreter_heredoc("nice -n 5 bash << EOF\necho hello\nEOF")
        print(f"  _is_interpreter_heredoc('nice -n 5 bash << EOF') = {result}")

        # Document the actual behavior - don't assert pass/fail yet
        if not result:
            print("  [LIMITATION] nice -n 5 bash << EOF is NOT caught by Phase 3")
            # But verify the FULL pipeline still catches it via subprocess
            proc = _run_hook_subprocess(
                "nice -n 5 bash << EOF\necho hello\nEOF", self.tmpdir
            )
            decision = _get_decision(proc.stdout)
            reason = _get_reason(proc.stdout)
            print(f"  Full pipeline decision: {decision}, reason: {reason}")
        else:
            print("  [OK] nice -n 5 bash << EOF IS caught by Phase 3")

    def test_subshell_grouping_bypass(self):
        """(python << EOF\\nbody\\nEOF) -> subshell grouping bypass.

        The parentheses create a subshell. Does split_commands handle this?
        """
        cmd = "(python << EOF\nprint('pwned')\nEOF)"
        result = _is_interpreter_heredoc(cmd)
        print(f"  _is_interpreter_heredoc('(python << EOF...)') = {result}")

        # What does _extract_base_command get from '(python'?
        base = _extract_base_command("(python")
        print(f"  _extract_base_command('(python') = '{base}'")

        # What about split_commands?
        parts = split_commands(cmd)
        print(f"  split_commands('{cmd[:40]}...') = {parts}")

        # Test via full subprocess
        proc = _run_hook_subprocess(cmd, self.tmpdir)
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  Full pipeline decision: {decision}, reason: {reason}")

    def test_curly_brace_grouping(self):
        """{ python << EOF\\nbody\\nEOF; } -> brace grouping."""
        cmd = "{ python << EOF\nprint('pwned')\nEOF\n; }"
        result = _is_interpreter_heredoc(cmd)
        print(f"  _is_interpreter_heredoc('{{python << EOF...}}') = {result}")

        base = _extract_base_command("{ python")
        print(f"  _extract_base_command('{{ python') = '{base}'")

    def test_backtick_wrapped(self):
        """`bash << EOF\\nid\\nEOF` -> backtick command substitution."""
        cmd = "`bash << EOF\nid\nEOF`"
        result = _is_interpreter_heredoc(cmd)
        print(f"  _is_interpreter_heredoc('`bash << EOF...`') = {result}")

    def test_dollar_paren_substitution(self):
        """$(bash << EOF\\nid\\nEOF) -> $() substitution."""
        cmd = "$(bash << EOF\nid\nEOF)"
        result = _is_interpreter_heredoc(cmd)
        print(f"  _is_interpreter_heredoc('$(bash << EOF...)') = {result}")


# ============================================================
# Category 3: Bypass Attempts Against V1 Fixes
# ============================================================

class TestBypassAttempts(unittest.TestCase):
    """Try to break the V1 fixes with adversarial inputs."""

    def test_python3_trailing_dot(self):
        """python3. << EOF -> trailing dot, no version number.

        Regex: r'^(?:python[23]?|...)\d[\d.]*$'
        'python3.' -> after 'python' prefix matches 'python[23]?', need \\d next.
        '.' is not \\d, so this should NOT match the regex.
        But 'python3' IS in the frozenset... wait, _extract_base_command
        returns the full basename. So 'python3.' would be the base_cmd.
        """
        result = _is_interpreter_heredoc("python3. << EOF\nprint('hi')\nEOF")
        base = _extract_base_command("python3.")
        print(f"  base_cmd='python3.', _extract_base_command='python3.'={base}")
        print(f"  frozenset match: {'python3.' in _INTERPRETER_COMMANDS}")
        print(f"  regex match: {bool(_VERSIONED_INTERPRETER_RE.match('python3.'))}")
        print(f"  _is_interpreter_heredoc result: {result}")
        # python3. is NOT a real command - should not trigger
        # But is it a security concern if it does? Not really.
        # The question is: does the regex falsely match?
        self.assertFalse(
            _VERSIONED_INTERPRETER_RE.match("python3."),
            "python3. should NOT match versioned regex (no digit after dot)"
        )

    def test_python3_10_2_micro_version(self):
        """python3.10.2 << EOF -> micro version (e.g., pyenv builds).

        Regex allows \\d[\\d.]* after the base, so 3.10.2 -> '3' then '10.2' -> match.
        Wait: the regex is on the full command name. Let's parse:
        'python3.10.2' -> 'python' matches 'python[23]?'... no.
        Actually 'python3' matches 'python[23]?' (with '3'), then
        remaining is '.10.2'. But regex is '^(?:python[23]?|...)\\d[\\d.]*$'.
        So after 'python3' (from python[23]? matching 'python3'), we need
        \\d[\\d.]* -> '.10.2' starts with '.', not \\d. So it WON'T match?

        Wait... 'python[23]?' matches 'python' (the '3' is left over). Then
        \\d matches '3', then [\\d.]* matches '.10.2'. So 'python3.10.2' DOES match.

        Actually let me re-read: '^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)\\d[\\d.]*$'
        For 'python3.10.2':
        - 'python[23]?' can match 'python3' (greedy) or 'python' (with '3' left)
        - If it matches 'python3', remaining is '.10.2', need \\d -> '.' fails
        - If it matches 'python' (just 'python' + skip [23]?), remaining is '3.10.2'
        - \\d matches '3', [\\d.]* matches '.10.2' -> FULL MATCH

        Regex engines try alternatives. [23]? is optional, so the engine will
        try matching without the '3' and succeed.
        """
        match = _VERSIONED_INTERPRETER_RE.match("python3.10.2")
        print(f"  regex match 'python3.10.2': {bool(match)}")
        if match:
            print(f"    matched: '{match.group()}'")
        result = _is_interpreter_heredoc("python3.10.2 << EOF\nprint('hi')\nEOF")
        print(f"  _is_interpreter_heredoc result: {result}")
        # This SHOULD match - micro versions are valid
        self.assertTrue(result, "python3.10.2 should trigger (micro version is real)")

    def test_python3a_letter_after_version(self):
        """python3a << EOF -> letter suffix, not a real version.

        'python3a': python[23]? matches 'python3' or 'python'.
        If 'python': \\d matches '3', [\\d.]* matches '' (stops at 'a').
        But then 'a' is left and $ doesn't match. So NO match.
        If 'python3': \\d needs to match 'a' -> fails.
        Neither works -> NO match. Good.
        """
        match = _VERSIONED_INTERPRETER_RE.match("python3a")
        result = _is_interpreter_heredoc("python3a << EOF\nprint('hi')\nEOF")
        print(f"  regex match 'python3a': {bool(match)}")
        print(f"  _is_interpreter_heredoc result: {result}")
        self.assertFalse(match, "python3a should NOT match versioned regex")
        self.assertFalse(result, "python3a is not a real interpreter")

    def test_bash5_1_versioned_bash(self):
        """bash5.1 << EOF -> versioned bash. Should the regex catch this?

        'bash5.1': regex prefix 'bash', then \\d matches '5', [\\d.]* matches '.1'
        -> MATCH. Is bash5.1 a real command name? On some systems, yes (e.g., brew).
        """
        match = _VERSIONED_INTERPRETER_RE.match("bash5.1")
        result = _is_interpreter_heredoc("bash5.1 << EOF\necho hello\nEOF")
        print(f"  regex match 'bash5.1': {bool(match)}")
        print(f"  _is_interpreter_heredoc result: {result}")
        self.assertTrue(match, "bash5.1 should match versioned regex")
        self.assertTrue(result, "bash5.1 should trigger")

    def test_double_dot_command(self):
        """.. /dev/stdin << EOF -> double dot is NOT source command.

        '..' is 'cd ..' parent directory, not '. .' (source .). Should NOT trigger.
        """
        result = _is_interpreter_heredoc(".. /dev/stdin << EOF\necho hello\nEOF")
        base = _extract_base_command(".. /dev/stdin")
        print(f"  _extract_base_command('.. /dev/stdin') = '{base}'")
        print(f"  _is_interpreter_heredoc result: {result}")
        self.assertFalse(result, ".. is not the dot command, should not trigger")

    def test_source_bare_heredoc(self):
        """source << EOF -> should trigger (source is in frozenset)."""
        result = _is_interpreter_heredoc("source << EOF\necho hello\nEOF")
        self.assertTrue(result, "source << EOF should trigger")

    def test_dot_vs_source_equivalence(self):
        """Both . << EOF and source << EOF should trigger."""
        dot_result = _is_interpreter_heredoc(". << EOF\necho hello\nEOF")
        source_result = _is_interpreter_heredoc("source << EOF\necho hello\nEOF")
        self.assertTrue(dot_result, ". << EOF should trigger")
        self.assertTrue(source_result, "source << EOF should trigger")
        self.assertEqual(dot_result, source_result,
                         "dot and source should behave identically")

    def test_sh1_versioned(self):
        """sh1 << EOF -> matches regex? sh + \\d(1) -> yes.

        Is sh1 a real command? Unlikely, but the regex matches it.
        This is acceptable (fail-closed for unknown versioned shells).
        """
        match = _VERSIONED_INTERPRETER_RE.match("sh1")
        result = _is_interpreter_heredoc("sh1 << EOF\necho hello\nEOF")
        print(f"  regex match 'sh1': {bool(match)}")
        print(f"  _is_interpreter_heredoc result: {result}")
        # sh1 matches the regex - this is a minor false positive but acceptable
        self.assertTrue(match, "sh1 matches the regex (expected)")

    def test_ksh93_versioned(self):
        """ksh93 << EOF -> ksh93 is a REAL versioned shell."""
        match = _VERSIONED_INTERPRETER_RE.match("ksh93")
        result = _is_interpreter_heredoc("ksh93 << EOF\necho hello\nEOF")
        print(f"  regex match 'ksh93': {bool(match)}")
        print(f"  _is_interpreter_heredoc result: {result}")
        self.assertTrue(result, "ksh93 is a real versioned shell, should trigger")


# ============================================================
# Category 4: Regex Edge Cases
# ============================================================

class TestRegexEdgeCases(unittest.TestCase):
    """Deep-dive edge cases for _VERSIONED_INTERPRETER_RE."""

    def test_python3_matches_frozenset_not_regex(self):
        """python3 should match via frozenset, not regex.

        The regex requires at least one digit AFTER the base prefix.
        'python3': python[23]? matches 'python3'. Then \\d needs another
        char but string ends. OR python[23]? matches 'python', then \\d
        matches '3', [\\d.]* matches '' -> '^python3$' matches!

        So actually python3 DOES match the regex too. But it hits frozenset first.
        """
        self.assertIn('python3', _INTERPRETER_COMMANDS,
                       "python3 should be in frozenset")
        regex_match = _VERSIONED_INTERPRETER_RE.match("python3")
        print(f"  'python3' also matches regex: {bool(regex_match)}")
        # It matches both - frozenset is checked first (more efficient)

    def test_regex_rejects_pure_base_names(self):
        """Pure base names like 'python', 'bash', 'sh' should NOT match regex.

        These are handled by the frozenset. The regex requires \\d after base.
        'python': python[23]? matches 'python', then \\d has nothing -> no match.
        'bash': 'bash' matches, then \\d has nothing -> no match.
        """
        for name in ['python', 'bash', 'sh', 'ruby', 'perl', 'zsh', 'dash', 'ksh']:
            with self.subTest(name=name):
                self.assertIsNone(_VERSIONED_INTERPRETER_RE.match(name),
                                  f"Pure '{name}' should NOT match versioned regex")

    def test_regex_matches_versioned(self):
        """Versioned names should match: python3.10, ruby3.1, perl5.34, bash5.2."""
        cases = [
            'python3.10', 'python3.12', 'python2.7',
            'ruby3.0', 'ruby3.1',
            'perl5.34', 'perl5.36',
            'bash5.1', 'bash5.2',
            'sh5', 'zsh5.9', 'dash0.5', 'ksh93',
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertIsNotNone(
                    _VERSIONED_INTERPRETER_RE.match(name),
                    f"Versioned '{name}' should match regex"
                )

    def test_regex_rejects_non_interpreters(self):
        """Non-interpreter names should NOT match even with numbers."""
        cases = [
            'cat3', 'grep2', 'sed4', 'awk2',
            'nodemon', 'node20',  # node is not in the regex prefix list
            'npm10', 'cargo1.70',
            'gcc12', 'g++12',
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertIsNone(
                    _VERSIONED_INTERPRETER_RE.match(name),
                    f"Non-interpreter '{name}' should NOT match regex"
                )

    def test_node_not_in_versioned_regex(self):
        """node is in frozenset but NOT in the versioned regex.

        node20 << EOF should NOT be caught (node is not in regex prefix).
        This is intentional: node doesn't use versioned binary names like python.
        """
        self.assertIn('node', _INTERPRETER_COMMANDS)
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match("node20"),
                          "node20 should NOT match versioned regex")
        # node20 is not a real command and not in frozenset
        result = _is_interpreter_heredoc("node20 << EOF\nconsole.log('hi')\nEOF")
        self.assertFalse(result, "node20 should not trigger")

    def test_csh_not_in_versioned_regex(self):
        """csh/tcsh/fish are in frozenset but NOT in versioned regex.

        csh6.24 would not match. This is a minor gap but these shells
        rarely have versioned binary names.
        """
        self.assertIn('csh', _INTERPRETER_COMMANDS)
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match("csh6.24"),
                          "csh6.24 should NOT match regex (csh not in regex)")

    def test_empty_and_garbage(self):
        """Empty string and garbage should not match."""
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match(""))
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match("   "))
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match("123"))
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match("python"))
        self.assertIsNone(_VERSIONED_INTERPRETER_RE.match("..."))

    def test_unicode_digit_bypass(self):
        """python3\u0661 (Arabic-Indic digit 1) -> should NOT match.

        \\d in Python regex matches Unicode digits by default!
        This means python3\u0661 could match the regex.
        """
        # Arabic-Indic digit one: \u0661
        name = "python3\u0661"
        match = _VERSIONED_INTERPRETER_RE.match(name)
        print(f"  regex match 'python3\\u0661': {bool(match)}")
        # This is a theoretical concern - such filenames are extremely unlikely
        # but worth documenting

    def test_very_long_version_string(self):
        """python3.999999999999 -> should match (no length limit in regex)."""
        name = "python3." + "9" * 100
        match = _VERSIONED_INTERPRETER_RE.match(name)
        print(f"  regex match 'python3.{'9'*100}': {bool(match)}")
        self.assertIsNotNone(match, "Long version should still match")


# ============================================================
# Category 5: Integration Tests (Subprocess)
# ============================================================

class TestIntegrationSubprocess(unittest.TestCase):
    """Full pipeline integration tests via subprocess."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dot_devstdin_heredoc_full_pipeline(self):
        """. /dev/stdin << EOF -> ASK via full pipeline."""
        proc = _run_hook_subprocess(
            ". /dev/stdin << EOF\necho hello\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertEqual(decision, "ask",
                         f". /dev/stdin heredoc should ASK. Got: {decision}")

    def test_python3_10_heredoc_full_pipeline(self):
        """python3.10 << EOF -> ASK via full pipeline."""
        proc = _run_hook_subprocess(
            "python3.10 << EOF\nprint('hi')\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertEqual(decision, "ask",
                         f"python3.10 heredoc should ASK. Got: {decision}")

    def test_python3_12_absolute_path_full_pipeline(self):
        """/usr/bin/python3.12 << EOF -> ASK via full pipeline."""
        proc = _run_hook_subprocess(
            "/usr/bin/python3.12 << EOF\nprint('hi')\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertEqual(decision, "ask",
                         f"/usr/bin/python3.12 heredoc should ASK. Got: {decision}")

    def test_nodemon_heredoc_not_ask(self):
        """nodemon << EOF -> should NOT get interpreter-heredoc ASK."""
        proc = _run_hook_subprocess(
            "nodemon << EOF\nconsole.log('hi')\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout) or ""
        print(f"  decision={decision}, reason={reason}")
        # nodemon is not an interpreter, should not trigger interpreter-heredoc
        # It might trigger other checks, but should not mention "interpreter" + "heredoc"
        if decision == "ask" and "interpreter" in reason.lower() and "heredoc" in reason.lower():
            self.fail("nodemon should NOT trigger interpreter-heredoc backstop")

    def test_bash5_1_heredoc_full_pipeline(self):
        """bash5.1 << EOF -> ASK via full pipeline."""
        proc = _run_hook_subprocess(
            "bash5.1 << EOF\necho hello\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertEqual(decision, "ask",
                         f"bash5.1 heredoc should ASK. Got: {decision}")

    def test_env_python3_10_heredoc_full_pipeline(self):
        """env python3.10 << EOF -> ASK (env prefix + versioned)."""
        proc = _run_hook_subprocess(
            "env python3.10 << EOF\nprint('hi')\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertEqual(decision, "ask",
                         f"env python3.10 heredoc should ASK. Got: {decision}")

    def test_sudo_python3_11_heredoc_full_pipeline(self):
        """sudo python3.11 << EOF -> ASK (sudo prefix + versioned)."""
        proc = _run_hook_subprocess(
            "sudo python3.11 << EOF\nimport os; os.system('id')\nEOF", self.tmpdir
        )
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        # Should be at least ask (might be deny due to dangerous body content)
        self.assertIn(decision, ("ask", "deny"),
                      f"sudo python3.11 heredoc should ask or deny. Got: {decision}")


# ============================================================
# Category 6: Compound Command Interaction
# ============================================================

class TestCompoundCommandInteraction(unittest.TestCase):
    """Test how _is_interpreter_heredoc interacts with split_commands."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_pipe_into_interpreter_heredoc(self):
        """echo foo | bash << EOF -> the bash part should trigger."""
        # split_commands should split on |
        parts = split_commands("echo foo | bash << EOF\necho hello\nEOF")
        print(f"  split_commands result: {parts}")
        # Check each part
        for part in parts:
            if 'bash' in part and '<<' in part:
                result = _is_interpreter_heredoc(part)
                print(f"  _is_interpreter_heredoc('{part[:40]}') = {result}")
                self.assertTrue(result, "bash << EOF part should trigger")

    def test_semicolon_separated_interpreter_heredoc(self):
        """echo foo; python3.10 << EOF\\nbody\\nEOF -> python3.10 part triggers."""
        cmd = "echo foo; python3.10 << EOF\nprint('hi')\nEOF"
        proc = _run_hook_subprocess(cmd, self.tmpdir)
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertIn(decision, ("ask", "deny"),
                      f"Should at least ask for python3.10 heredoc. Got: {decision}")

    def test_and_then_interpreter_heredoc(self):
        """true && python3.10 << EOF\\nbody\\nEOF -> python3.10 part triggers."""
        cmd = "true && python3.10 << EOF\nprint('hi')\nEOF"
        proc = _run_hook_subprocess(cmd, self.tmpdir)
        decision = _get_decision(proc.stdout)
        reason = _get_reason(proc.stdout)
        print(f"  decision={decision}, reason={reason}")
        self.assertIn(decision, ("ask", "deny"),
                      f"Should at least ask for python3.10 heredoc. Got: {decision}")


# ============================================================
# Category 7: Adversarial Encodings and Tricks
# ============================================================

class TestAdversarialEncodings(unittest.TestCase):
    """Adversarial encoding and evasion attempts."""

    def test_tab_between_command_and_heredoc(self):
        """python3.10\\t<< EOF -> tab instead of space."""
        result = _is_interpreter_heredoc("python3.10\t<< EOF\nprint('hi')\nEOF")
        print(f"  tab-separated: {result}")
        # shlex.split handles tabs, so this should work
        self.assertTrue(result, "Tab-separated should still trigger")

    def test_multiple_spaces(self):
        """python3.10    <<    EOF -> multiple spaces."""
        result = _is_interpreter_heredoc("python3.10    <<    EOF\nprint('hi')\nEOF")
        print(f"  multi-space: {result}")
        self.assertTrue(result, "Multi-space should still trigger")

    def test_heredoc_with_dash_prefix(self):
        """python3.10 <<- EOF -> tab-stripped heredoc variant."""
        result = _is_interpreter_heredoc("python3.10 <<- EOF\nprint('hi')\nEOF")
        print(f"  <<- variant: {result}")
        # '<<' is in '<<-', so the '<<' in sub_cmd check should pass
        self.assertTrue(result, "<<- variant should still trigger")

    def test_aliased_path_interpreter(self):
        """~/.pyenv/versions/3.10.0/bin/python3.10 << EOF -> pyenv path."""
        cmd = "~/.pyenv/versions/3.10.0/bin/python3.10 << EOF\nprint('hi')\nEOF"
        result = _is_interpreter_heredoc(cmd)
        base = _extract_base_command("~/.pyenv/versions/3.10.0/bin/python3.10")
        print(f"  pyenv path base_cmd: '{base}'")
        print(f"  _is_interpreter_heredoc result: {result}")
        # Path.name should extract 'python3.10' from the full path
        self.assertTrue(result, "pyenv path should still resolve to python3.10")

    def test_symlink_style_path(self):
        """/opt/homebrew/bin/python3.12 << EOF -> homebrew path."""
        result = _is_interpreter_heredoc(
            "/opt/homebrew/bin/python3.12 << EOF\nprint('hi')\nEOF"
        )
        self.assertTrue(result, "Homebrew path should trigger")

    def test_relative_path_interpreter(self):
        """./python3.10 << EOF -> relative path."""
        result = _is_interpreter_heredoc(
            "./python3.10 << EOF\nprint('hi')\nEOF"
        )
        base = _extract_base_command("./python3.10")
        print(f"  relative path base_cmd: '{base}'")
        print(f"  _is_interpreter_heredoc result: {result}")
        # Path('./python3.10').name = 'python3.10'
        self.assertTrue(result, "Relative path should trigger")


if __name__ == '__main__':
    # Run with verbose output to see all the debug prints
    unittest.main(verbosity=2)
