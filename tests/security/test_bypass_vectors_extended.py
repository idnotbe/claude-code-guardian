#!/usr/bin/env python3
"""Extended bypass vector tests and heredoc edge cases.

These security-relevant edge cases were identified during root file cleanup
as having ZERO coverage in the organized test suite. Each test documents
the actual guardian behavior and flags discrepancies with real bash as
security notes.

Run: python3 -m pytest tests/security/test_bypass_vectors_extended.py -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    split_commands,
    is_write_command,
    is_delete_command,
    scan_protected_paths,
    extract_redirection_targets,
)

SCAN_CONFIG = {
    "zeroAccessPaths": [".env", ".env.*", "*.pem", "id_rsa", "id_rsa.*"],
    "readOnlyPaths": ["/etc/*"],
    "noDeletePaths": [".git"],
    "bashPathScan": {
        "enabled": True,
        "exactMatchAction": "ask",
        "patternMatchAction": "ask",
    },
}


# ============================================================
# 1. Heredoc Delimiter Edge Cases
# ============================================================
class TestHeredocDelimiterEdgeCases(unittest.TestCase):
    """Test split_commands() with exotic heredoc delimiters.

    In bash, heredoc delimiters support quote concatenation (e.g., E"O"F
    becomes EOF) and backslash escaping. The guardian's _parse_heredoc_delimiter
    uses a simplified parser that may diverge from bash. All divergences
    documented here are SAFE (guardian is more restrictive, not less).
    """

    def test_quote_concat_delimiter_literal_match(self):
        """E"O"F -- guardian treats as literal 'E"O"F', terminates on E"O"F line.

        Bash treats E"O"F as quote concatenation -> delimiter is EOF.
        Guardian diverges: delimiter is the literal string E"O"F (including quotes).
        SAFE: if body contains EOF (bash terminator), guardian still sees it as
        heredoc body, which is MORE restrictive than bash.
        """
        result = split_commands('cat << E"O"F\nhidden\nE"O"F\necho visible')
        self.assertEqual(len(result), 2)
        self.assertIn("echo visible", result[1])

    def test_quote_concat_delimiter_unterminated_is_failclosed(self):
        """E"O"F with only EOF terminator -- guardian never finds E"O"F, fails closed.

        Since guardian expects literal E"O"F as delimiter but only EOF exists,
        the heredoc is unterminated and consumes all remaining input.
        This is fail-closed: hidden commands are NOT exposed.
        """
        result = split_commands('cat << E"O"F\nhidden\nEOF\necho visible')
        # Unterminated heredoc consumes everything -- only one sub-command
        self.assertEqual(len(result), 1)

    def test_backslash_escaped_delimiter(self):
        r"""Backslash-escaped delimiter: cat << \\EOF.

        The backslash handler consumes \\ + next char as an escaped pair
        before reaching heredoc detection. Body termination requires a
        matching \\EOF line.
        """
        result = split_commands('cat << \\EOF\nhidden\n\\EOF\necho visible')
        self.assertEqual(len(result), 2)
        self.assertIn("echo visible", result[1])

    def test_empty_string_delimiter(self):
        """Empty string delimiter: cat << '' terminates on first empty line.

        Guardian parses '' as delimiter = '' (empty string). The body
        terminates when a line matches empty string exactly.
        """
        result = split_commands("cat << ''\nhidden\n\necho visible")
        # Empty line terminates the heredoc; echo visible is a separate command
        self.assertEqual(len(result), 2)
        self.assertIn("echo visible", result[1])

    def test_quote_trailing_chars_failclosed(self):
        """'EOF'Z -- guardian uses 'EOF' (strips quotes), ignores trailing Z.

        Bash concatenates: 'EOF' + Z = EOFZ as the delimiter.
        Guardian: _parse_heredoc_delimiter sees ' and enters quoted path,
        returns delimiter='EOF'. With only EOFZ as terminator, guardian's
        EOF delimiter never matches -> unterminated heredoc -> fail-closed.
        """
        result = split_commands("cat << 'EOF'Z\nhidden\nEOFZ\necho visible")
        # Guardian fails closed: unterminated heredoc consumes everything
        self.assertEqual(len(result), 1)

    def test_quote_trailing_both_terminators(self):
        """'EOF'Z with both EOF and EOFZ in body -- guardian terminates on EOF first."""
        result = split_commands(
            "cat << 'EOF'Z\nhidden1\nEOF\nhidden2\nEOFZ\necho visible"
        )
        # Guardian terminates on EOF, so hidden2, EOFZ, echo visible are separate
        self.assertEqual(len(result), 4)
        self.assertIn("echo visible", result[-1])

    def test_backslash_space_delimiter(self):
        r"""Backslash-space delimiter: cat << \\ (single backslash as delimiter).

        The backslash handler consumes \\ as escape sequence. Body terminates
        when a line contains just \\.
        """
        result = split_commands('cat << \\\\ \nhidden\n\\\\\necho visible')
        self.assertEqual(len(result), 2)
        self.assertIn("echo visible", result[1])


# ============================================================
# 2. Pipeline + Heredoc Interleaving
# ============================================================
class TestPipelineHeredocInterleave(unittest.TestCase):
    """Test heredoc behavior when combined with pipes.

    When pipe is encountered, split_commands flushes the current accumulator.
    However, pending_heredocs persists across the pipe, so heredoc bodies
    are still consumed at the next newline.
    """

    def test_piped_heredocs_split_at_pipe(self):
        """cat <<EOF | cat <<EOF2 -- pipe splits into two sub-commands.

        Each side of the pipe becomes a separate sub-command. The heredoc
        bodies are consumed after the respective newlines.
        """
        result = split_commands(
            "cat <<EOF | cat <<EOF2\nbody1\nEOF\nbody2\nEOF2"
        )
        self.assertEqual(len(result), 2)
        self.assertIn("cat <<EOF", result[0])
        self.assertIn("cat <<EOF2", result[1])

    def test_pipeline_heredoc_body_after_pipe(self):
        """cat <<EOF | grep -- heredoc body consumed after pipe."""
        result = split_commands(
            "cat <<EOF |\ngrep b\nbody\nEOF\necho visible"
        )
        self.assertIn("cat <<EOF", result[0])
        visible_present = any("echo visible" in s for s in result)
        self.assertTrue(visible_present)

    def test_pipe_then_heredoc_body_consumed(self):
        """After pipe, pending heredoc still consumes body lines."""
        result = split_commands(
            "cat <<EOF | grep x\nbody1\nEOF\necho visible"
        )
        # body1 should NOT appear as separate command (consumed as heredoc body)
        body_leaked = any(s.strip() == "body1" for s in result)
        self.assertFalse(body_leaked)

    def test_heredoc_body_pipe_chars_not_split(self):
        """Pipe characters in heredoc body should not cause splitting."""
        result = split_commands("cat <<EOF\ncmd1 | cmd2 | cmd3\nEOF")
        self.assertEqual(len(result), 1)


# ============================================================
# 3. Process Substitution + Heredoc Nesting
# ============================================================
class TestProcessSubstitutionHeredoc(unittest.TestCase):
    """Test heredoc behavior inside process substitution <().

    Inside <(), depth > 0, so newlines do NOT trigger command splitting.
    Heredoc detection still fires (only arithmetic_depth is checked),
    but heredoc body consumption only happens at depth-0 newlines.
    """

    def test_proc_sub_heredoc_single_command(self):
        """diff <(cat <<EOF...) should be one sub-command."""
        result = split_commands(
            "diff <(cat <<EOF\nbody1\nEOF\n) <(cat <<EOF2\nbody2\nEOF2\n)"
        )
        self.assertEqual(len(result), 1)
        self.assertIn("diff", result[0])

    def test_proc_sub_heredoc_dangerous_body_contained(self):
        """Dangerous commands in heredoc body inside <() stay contained."""
        result = split_commands(
            "diff <(cat <<EOF\nrm -rf /\nEOF\n) file"
        )
        self.assertEqual(len(result), 1)
        # rm -rf / IS in the combined command text (inside <()) but not separate
        self.assertIn("rm -rf /", result[0])

    def test_proc_sub_then_separate_command(self):
        """Clean heredoc body in <() correctly separates trailing command."""
        result = split_commands(
            "diff <(cat <<EOF\nclean body\nEOF\n) file\necho visible"
        )
        visible_separate = any("echo visible" == s.strip() for s in result)
        self.assertTrue(
            visible_separate,
            "echo visible should be a separate command with clean heredoc body"
        )

    def test_depth_confusion_close_paren_in_heredoc(self):
        """) in heredoc body inside <() -- depth confusion.

        NOTE: guardian does not handle this case fully. Inside <() at
        depth=1, newlines don't trigger heredoc body consumption. The ) in
        the heredoc body is parsed as closing the <() context, corrupting
        depth tracking. 'echo hidden' IS visible as a separate command.
        """
        result = split_commands(
            "diff <(cat <<EOF\n)\nEOF\n) file\necho hidden"
        )
        hidden_visible = any("echo hidden" in s for s in result)
        self.assertTrue(
            hidden_visible,
            "echo hidden should be visible (depth confusion exposes it)"
        )


# ============================================================
# 4. Depth Corruption Attacks
# ============================================================
class TestDepthCorruptionAttacks(unittest.TestCase):
    """Test attacks that corrupt the parenthesis depth counter.

    When heredoc body is NOT properly consumed (inside depth > 0 context),
    characters like ( and ) in the body affect the depth counter.
    """

    def test_multiple_parens_corrupt_depth(self):
        """Multiple ( in heredoc body inside <() corrupts depth counter.

        NOTE: guardian does not handle this case correctly. The ( characters
        in the heredoc body increment depth from 1 to 9. The closing )
        only decrements to 8, so subsequent commands are treated as still
        being inside a subshell. 'echo hidden' becomes part of the combined
        command rather than a separate sub-command.

        SECURITY NOTE: The hidden command IS in the combined text (scanned
        by Layer 1 raw string scan), but is NOT separately analyzed by
        per-sub-command checks.
        """
        result = split_commands(
            "diff <(cat <<EOF\n((((((((\nEOF\n) file\necho hidden"
        )
        # Due to depth corruption, everything is one command
        self.assertEqual(len(result), 1)
        # The hidden command IS in the combined text (still scanned by Layer 1)
        self.assertIn("echo hidden", result[0])

    def test_depth_corruption_vs_clean_heredoc(self):
        """Contrast: clean heredoc body in <() correctly separates commands."""
        result = split_commands(
            "diff <(cat <<EOF\nclean body\nEOF\n) file\necho visible"
        )
        visible_separate = any("echo visible" == s.strip() for s in result)
        self.assertTrue(
            visible_separate,
            "echo visible should be separate with clean heredoc body"
        )

    def test_dollar_paren_heredoc_body_leaks(self):
        """$() with ) in heredoc body -- body lines leak out.

        NOTE: guardian does not handle this case correctly. Inside $() at
        depth=1, the heredoc is detected but body consumption only happens
        at depth-0 newlines. The ) in the heredoc body closes $() context,
        and subsequent lines (including rm -rf /) leak out as separate
        sub-commands.

        SECURITY NOTE: rm -rf / IS visible as a separate command, so the
        guardian WILL scan and block it. Being more permissive in what it
        exposes is SAFE for blocking but may cause false positives.
        """
        result = split_commands(
            "echo $(cat <<EOF\n)\nrm -rf /\nEOF\n)\necho visible"
        )
        rm_visible = any("rm -rf /" in s for s in result)
        self.assertTrue(
            rm_visible,
            "rm -rf / should be visible (leaked from heredoc body)"
        )
        echo_visible = any("echo visible" in s for s in result)
        self.assertTrue(echo_visible)

    def test_close_brace_in_heredoc_body_safe(self):
        """} in heredoc body at depth 0 should not corrupt brace tracking."""
        result = split_commands("cat <<EOF\n}\nEOF\necho visible")
        found_echo = any("echo visible" in c for c in result)
        self.assertTrue(found_echo)

    def test_semicolons_in_heredoc_body_not_split(self):
        """Semicolons in heredoc body should NOT split commands."""
        result = split_commands(
            "cat <<EOF\necho a; echo b; rm -rf /\nEOF"
        )
        self.assertEqual(len(result), 1)


# ============================================================
# 5. <<- Tab-Strip Heredoc
# ============================================================
class TestTabStripHeredoc(unittest.TestCase):
    """Test <<- (tab-stripping heredoc) behavior.

    bash's <<- strips leading tabs from the delimiter line only.
    Spaces are NOT stripped -- only literal tab characters.
    """

    def test_tab_indented_delimiter_matches(self):
        """<<- with tab-indented delimiter should match and consume body."""
        result = split_commands("cat <<-MYEOF\n\thello\n\tMYEOF")
        self.assertEqual(len(result), 1)
        self.assertIn("<<-MYEOF", result[0])

    def test_space_indented_delimiter_no_match(self):
        """<<- with space-indented delimiter should NOT match.

        Spaces are not tabs -- <<- only strips leading tabs.
        Heredoc becomes unterminated and consumes all remaining input.
        """
        result = split_commands("cat <<-MYEOF\n  hello\n  MYEOF")
        self.assertEqual(len(result), 1)

    def test_space_indented_with_trailing_cmd_consumed(self):
        """<<- with space-indented delimiter -- trailing command consumed (fail-closed)."""
        result = split_commands(
            "cat <<-MYEOF\n  hello\n  MYEOF\necho visible"
        )
        # Unterminated heredoc consumes everything
        self.assertEqual(len(result), 1)

    def test_tab_strip_with_trailing_cmd(self):
        """<<- with tab delimiter, followed by another command."""
        result = split_commands(
            "cat <<-MYEOF\n\thello\n\tMYEOF\necho done"
        )
        self.assertEqual(len(result), 2)
        self.assertIn("echo done", result[1])

    def test_mixed_tab_space_no_match(self):
        """<<- with tab+space on delimiter line -- no match.

        After tab stripping, delimiter line is " MYEOF" != "MYEOF".
        """
        result = split_commands(
            "cat <<-MYEOF\n\t hello\n\t MYEOF\necho visible"
        )
        # Unterminated heredoc, fail-closed
        self.assertEqual(len(result), 1)


# ============================================================
# 6. Scan False Positive Prevention
# ============================================================
class TestScanFalsePositives(unittest.TestCase):
    """Test that scan_protected_paths avoids false positives.

    Layer 1 scanning should not trigger on patterns that merely
    resemble protected paths but are not actual path references.
    """

    def test_all_question_marks_no_false_positive(self):
        """echo ??? should not trigger protected path scan.

        The ??? glob could theoretically match .env but glob_to_literals
        returns [] for generic patterns, preventing false positives.
        """
        verdict, _ = scan_protected_paths("echo ???", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    def test_env_in_quoted_text_still_detected(self):
        """'.env' in single quotes IS detected by Layer 1 scan.

        Layer 1 does raw string scanning -- it does NOT skip quoted regions.
        This is by design: defense-in-depth prefers false positives over
        false negatives.
        """
        verdict, _ = scan_protected_paths(
            "echo 'references .env'", SCAN_CONFIG
        )
        self.assertEqual(verdict, "ask")

    def test_env_as_word_in_text_detected(self):
        """.env mentioned in command text IS detected (raw string scan)."""
        verdict, _ = scan_protected_paths(
            "echo this mentions .env in text", SCAN_CONFIG
        )
        self.assertEqual(verdict, "ask")

    def test_environment_word_no_false_positive(self):
        """'environment' should not trigger .env detection (word boundary)."""
        verdict, _ = scan_protected_paths("echo environment", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    def test_id_rsa_exact_match(self):
        """Exact 'id_rsa' reference should trigger scan."""
        verdict, _ = scan_protected_paths("cat id_rsa", SCAN_CONFIG)
        self.assertEqual(verdict, "ask")

    def test_pem_suffix_detected(self):
        """*.pem pattern -- .pem suffix should be detected."""
        verdict, _ = scan_protected_paths("cat server.pem", SCAN_CONFIG)
        self.assertEqual(verdict, "ask")

    def test_safe_commands_not_blocked(self):
        """Normal commands should not be blocked."""
        for cmd in ["ls -la", "echo hello world", "grep 'error' log.txt",
                     "python3 script.py", "git status"]:
            verdict, _ = scan_protected_paths(cmd, SCAN_CONFIG)
            self.assertEqual(verdict, "allow", f"False positive on: {cmd}")


# ============================================================
# 7. Quote-Aware Write Detection
# ============================================================
class TestQuoteAwareWriteDetection(unittest.TestCase):
    """Test is_write_command() with quoted redirect targets.

    is_write_command uses _is_inside_quotes to skip > characters inside
    quoted strings. Actual redirections with quoted TARGETS (the filename
    after >) are still detected because the > itself is outside quotes.
    """

    def test_single_quoted_redirect_target_detected(self):
        """echo test > '/etc/passwd' -- > is outside quotes, detected as write."""
        self.assertTrue(is_write_command("echo test > '/etc/passwd'"))

    def test_double_quoted_redirect_target_detected(self):
        """echo test > "/etc/passwd" -- > is outside quotes, detected as write."""
        self.assertTrue(is_write_command('echo test > "/etc/passwd"'))

    def test_gt_inside_single_quotes_not_write(self):
        """echo 'data > file' -- > inside single quotes is not redirection."""
        self.assertFalse(is_write_command("echo 'data > file'"))

    def test_gt_inside_double_quotes_not_write(self):
        """echo "data > file" -- > inside double quotes is not redirection."""
        self.assertFalse(is_write_command('echo "data > file"'))

    def test_redirect_after_quoted_gt(self):
        """echo "x > y" > output.txt -- first > quoted, second > real redirect."""
        self.assertTrue(is_write_command('echo "x > y" > output.txt'))

    def test_extract_targets_single_quoted(self):
        """extract_redirection_targets strips quotes from target path."""
        targets = extract_redirection_targets(
            "echo test > '/etc/passwd'", Path("/tmp/project")
        )
        self.assertTrue(len(targets) > 0)
        self.assertEqual(str(targets[0]), "/etc/passwd")

    def test_extract_targets_double_quoted(self):
        """extract_redirection_targets strips quotes from double-quoted target."""
        targets = extract_redirection_targets(
            'echo test > "/etc/passwd"', Path("/tmp/project")
        )
        self.assertTrue(len(targets) > 0)
        self.assertEqual(str(targets[0]), "/etc/passwd")

    def test_append_redirect_detected(self):
        """echo test >> file.log -- append redirect is also a write."""
        self.assertTrue(is_write_command("echo test >> file.log"))

    def test_heredoc_operator_not_write(self):
        """cat <<EOF -- heredoc operator << is NOT a write redirect."""
        self.assertFalse(is_write_command("cat <<EOF"))

    def test_here_string_not_write(self):
        """cat <<< 'hello' -- here-string is NOT a write redirect."""
        self.assertFalse(is_write_command("cat <<< 'hello'"))


# ============================================================
# 8. Combined Attack Vectors
# ============================================================
class TestCombinedAttackVectors(unittest.TestCase):
    """Test combined bypass techniques that chain multiple edge cases."""

    def test_heredoc_hides_env_from_scan(self):
        """Heredoc body containing .env should not leak to sub-commands."""
        cmd = "cat > output.json << 'EOF'\n{\"secret\": \".env\"}\nEOF"
        subs = split_commands(cmd)
        joined = " ".join(subs)
        self.assertNotIn(
            ".env", joined,
            ".env in heredoc body should not leak to sub-commands"
        )

    def test_heredoc_hides_env_but_command_part_scanned(self):
        """cat .env in command part IS visible even with heredoc present."""
        cmd = "cat .env << 'EOF'\nbody\nEOF"
        subs = split_commands(cmd)
        joined = " ".join(subs)
        self.assertIn(
            ".env", joined,
            ".env in command part must be visible for scanning"
        )

    def test_semicolon_in_heredoc_body_not_split(self):
        """Semicolons in heredoc body must not cause command splitting."""
        result = split_commands("cat <<EOF\nfoo ; rm -rf /\nEOF")
        self.assertEqual(len(result), 1)
        rm_leaked = any(s.strip() == "rm -rf /" for s in result)
        self.assertFalse(rm_leaked)

    def test_newline_in_heredoc_body_consumed(self):
        """Newlines in heredoc body are consumed, not treated as separators."""
        result = split_commands(
            "cat <<EOF\nline1\nline2\nline3\nEOF\necho done"
        )
        self.assertEqual(len(result), 2)
        self.assertIn("echo done", result[1])

    def test_background_ampersand_in_heredoc_body_contained(self):
        """& in heredoc body should not cause splitting."""
        result = split_commands("cat <<EOF\nmalicious &\nEOF")
        self.assertEqual(len(result), 1)

    def test_delete_in_heredoc_body_not_flagged(self):
        """rm in heredoc body should not trigger is_delete_command on body."""
        cmd = "cat <<EOF\nrm -rf /\nEOF"
        subs = split_commands(cmd)
        self.assertEqual(len(subs), 1)
        self.assertFalse(is_delete_command(subs[0]))

    def test_unterminated_heredoc_failclosed(self):
        """Unterminated heredoc consumes all remaining input (fail-closed)."""
        result = split_commands("cat <<NEVERENDS\nrm -rf /\necho hidden")
        self.assertEqual(len(result), 1)
        # Neither rm nor echo should leak as separate commands
        self.assertFalse(
            any(s.strip() == "rm -rf /" for s in result)
        )
        self.assertFalse(
            any(s.strip() == "echo hidden" for s in result)
        )

    def test_multiple_heredocs_on_one_line_then_command(self):
        """Multiple heredocs on one line, followed by separate command."""
        result = split_commands(
            "cmd <<A <<B\nbody A\nA\nbody B\nB\necho done"
        )
        self.assertEqual(len(result), 2)
        self.assertIn("echo done", result[1])


if __name__ == "__main__":
    unittest.main()
