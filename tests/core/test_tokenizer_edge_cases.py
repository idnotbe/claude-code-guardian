#!/usr/bin/env python3
"""Tests for tokenizer boundary conditions and depth tracking.

These edge cases had ZERO test coverage in the organized test suite.
Covers: split_commands() boundary inputs, nested construct depth tracking,
feature interactions, and is_delete_command wrapper bypass patterns.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    split_commands,
    is_delete_command,
    is_write_command,
    scan_protected_paths,
)


# Standard scan config for Layer 1 tests
SCAN_CONFIG = {
    "zeroAccessPaths": [
        ".env",
        ".env.*",
        ".env*.local",
        "*.pem",
        "id_rsa",
        "id_rsa.*",
        "id_ed25519",
        "id_ed25519.*",
        "~/.ssh/**",
    ],
    "bashPathScan": {
        "enabled": True,
        "exactMatchAction": "ask",
        "patternMatchAction": "ask",
    },
}


# ============================================================
# 1. Tokenizer Boundary Conditions
# ============================================================

class TestTokenizerBoundaries(unittest.TestCase):
    """Test split_commands() with edge case inputs."""

    def test_empty_string(self):
        """Empty input should return an empty list."""
        result = split_commands("")
        self.assertEqual(result, [])

    def test_whitespace_only(self):
        """Whitespace-only input should return an empty list."""
        result = split_commands("   ")
        self.assertEqual(result, [])

    def test_tab_only(self):
        """Tab-only input should return an empty list."""
        result = split_commands("\t\t")
        self.assertEqual(result, [])

    def test_newline_only(self):
        """Newline-only input should return an empty list."""
        result = split_commands("\n\n")
        self.assertEqual(result, [])

    def test_lone_semicolon(self):
        """Lone semicolon should produce an empty list (no non-empty commands)."""
        result = split_commands(";")
        self.assertEqual(result, [])

    def test_lone_ampersand(self):
        """Lone & should produce an empty list (no non-empty commands)."""
        result = split_commands("&")
        self.assertEqual(result, [])

    def test_lone_pipe(self):
        """Lone | should produce an empty list (no non-empty commands)."""
        result = split_commands("|")
        self.assertEqual(result, [])

    def test_lone_double_ampersand(self):
        """Lone && should produce an empty list."""
        result = split_commands("&&")
        self.assertEqual(result, [])

    def test_lone_double_pipe(self):
        """Lone || should produce an empty list."""
        result = split_commands("||")
        self.assertEqual(result, [])

    def test_multiple_semicolons(self):
        """Multiple semicolons should produce an empty list."""
        result = split_commands(";;;")
        self.assertEqual(result, [])

    def test_very_long_input(self):
        """Very long input (10K+ chars) should not crash or hang."""
        long_cmd = "echo " + "a" * 10000
        result = split_commands(long_cmd)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].startswith("echo "))

    def test_very_long_input_with_separators(self):
        """Long input with separators should split correctly."""
        cmd = "; ".join([f"echo {i}" for i in range(100)])
        result = split_commands(cmd)
        self.assertEqual(len(result), 100)

    def test_single_command_no_separator(self):
        """A plain command with no separator should return as-is."""
        result = split_commands("echo hello")
        self.assertEqual(result, ["echo hello"])

    def test_trailing_semicolon(self):
        """Trailing semicolon should not produce an empty trailing element."""
        result = split_commands("echo hello;")
        self.assertEqual(result, ["echo hello"])

    def test_leading_semicolon(self):
        """Leading semicolon should not produce an empty leading element."""
        result = split_commands("; echo hello")
        self.assertEqual(result, ["echo hello"])

    def test_backslash_at_end_of_string(self):
        """Trailing backslash should not crash (boundary: no char after \\)."""
        result = split_commands("echo hello\\")
        self.assertEqual(len(result), 1)


# ============================================================
# 2. Nested Construct Depth Tracking
# ============================================================

class TestNestedConstructDepth(unittest.TestCase):
    """Test that split_commands correctly handles nested constructs."""

    def test_command_subst_inside_param_expansion(self):
        """Semicolon inside $() inside ${} should NOT split.

        echo ${VAR:-$(echo;echo)} is a single command because ; is inside
        nested $() within ${}.
        """
        result = split_commands("echo ${VAR:-$(echo;echo)}")
        self.assertEqual(len(result), 1)

    def test_arithmetic_inside_param_expansion(self):
        """Arithmetic inside parameter expansion should be 1 command."""
        result = split_commands("echo ${arr[$((i+1))]}")
        self.assertEqual(len(result), 1)

    def test_nested_param_expansion(self):
        """Nested ${} should be tracked correctly."""
        result = split_commands("echo ${A:-${B:-default}}")
        self.assertEqual(len(result), 1)

    def test_depth_desync_attack(self):
        """Depth desync: } inside $() should not close ${}.

        echo ${x:-$(echo })}; rm .env
        The } inside $() has depth > 0 (inside command substitution), so
        param_expansion_depth is NOT decremented. After $() closes, the
        final } correctly closes ${}. The ; then splits into 2 commands.

        SECURITY: This correctly splits, so 'rm .env' is visible as a
        separate command for security scanning.
        """
        cmd = "echo ${x:-$(echo })}; rm .env"
        result = split_commands(cmd)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "echo ${x:-$(echo })}")
        self.assertEqual(result[1], "rm .env")

    def test_brace_group_keeps_semicolons_together(self):
        """Brace group { ...; } should NOT split on internal semicolons."""
        result = split_commands("{ rm -rf /tmp/x; echo done; }")
        self.assertEqual(len(result), 1)

    def test_subshell_keeps_semicolons_together(self):
        """Subshell (...) should NOT split on internal semicolons."""
        result = split_commands("(rm -rf /tmp/x; echo done)")
        self.assertEqual(len(result), 1)

    def test_command_substitution_semicolons(self):
        """$() should NOT split on internal semicolons."""
        result = split_commands("echo $(echo a; echo b)")
        self.assertEqual(len(result), 1)

    def test_backtick_substitution_semicolons(self):
        """Backtick substitution should NOT split on internal semicolons."""
        result = split_commands("echo `echo a; echo b`")
        self.assertEqual(len(result), 1)

    def test_double_bracket_pipes(self):
        """[[ ... ]] should NOT split on internal | or ||."""
        result = split_commands("[[ a == b || c == d ]]")
        self.assertEqual(len(result), 1)

    def test_arithmetic_plus_pipe(self):
        """(( ... )) should NOT split on internal operators."""
        result = split_commands("(( x = 1 | 2 ))")
        self.assertEqual(len(result), 1)

    def test_extglob_pipe(self):
        """Extglob +(...|...) should NOT split on internal |."""
        result = split_commands("echo +(a|b)")
        self.assertEqual(len(result), 1)

    def test_nested_command_subst_in_double_quotes(self):
        """Semicolons inside $() inside double quotes should NOT split."""
        result = split_commands('echo "$(echo a; echo b)"')
        # The $() depth tracking works inside double quotes, keeping the
        # semicolon from splitting. The entire "$(..." is one token.
        self.assertEqual(len(result), 1)

    def test_process_substitution_semicolons(self):
        """Process substitution <(...) should NOT split on internal semicolons."""
        result = split_commands("diff <(echo a; echo b) <(echo c; echo d)")
        self.assertEqual(len(result), 1)


# ============================================================
# 3. Feature Interactions
# ============================================================

class TestFeatureInteractions(unittest.TestCase):
    """Test complex interactions between tokenizer features."""

    def test_brace_group_with_param_expansion(self):
        """Brace group with ${VAR:-default} inside should be 1 command."""
        result = split_commands("{ echo ${VAR:-default}; }")
        self.assertEqual(len(result), 1)

    def test_extglob_in_conditional(self):
        """Extglob inside [[ ]] should be 1 command."""
        result = split_commands("[[ file == +(*.txt|*.md) ]]")
        self.assertEqual(len(result), 1)

    def test_heredoc_followed_by_command(self):
        """Heredoc followed by another command via newline should split."""
        cmd = "cat <<EOF\nbody\nEOF\necho done"
        result = split_commands(cmd)
        # After heredoc body is consumed, 'echo done' follows on new line
        self.assertIn("echo done", result)

    def test_heredoc_followed_by_brace_group(self):
        """Heredoc body consumed, then brace group on next line."""
        cmd = "cat <<EOF\nbody\nEOF\n{ echo done; }"
        result = split_commands(cmd)
        self.assertIn("{ echo done; }", result)

    def test_nested_heredoc_in_command_substitution(self):
        """Heredoc inside $() is a complex interaction -- stays as 1 command."""
        cmd = "echo $(cat <<EOF\nhello\nEOF\n)"
        result = split_commands(cmd)
        self.assertEqual(len(result), 1)

    def test_complex_nesting_heredoc_param_expansion(self):
        """Heredoc inside $() with ${VAR:-$(nested)} should be 1 command."""
        cmd = "echo $(cat <<EOF\n${VAR:-$(echo nested)}\nEOF\n)"
        result = split_commands(cmd)
        self.assertEqual(len(result), 1)

    def test_backslash_escaped_semicolon(self):
        """Backslash-escaped semicolon should NOT split."""
        result = split_commands("echo hello\\; echo world")
        # \; is escaped, so this is one command (the ; is literal)
        # Actually: \; makes ; literal, but "echo world" after the space
        # is part of the same command since ; didn't split.
        self.assertEqual(len(result), 1)

    def test_semicolon_inside_single_quotes(self):
        """Semicolons inside single quotes should NOT split."""
        result = split_commands("echo 'hello; world'")
        self.assertEqual(len(result), 1)

    def test_semicolon_inside_double_quotes(self):
        """Semicolons inside double quotes should NOT split."""
        result = split_commands('echo "hello; world"')
        self.assertEqual(len(result), 1)

    def test_pipe_then_semicolon(self):
        """pipe then semicolon should produce two entries."""
        result = split_commands("echo a | grep b; echo c")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "echo a")
        self.assertEqual(result[1], "grep b")
        self.assertEqual(result[2], "echo c")

    def test_background_then_command(self):
        """& then another command should split."""
        result = split_commands("sleep 10 & echo done")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "sleep 10")
        self.assertEqual(result[1], "echo done")

    def test_fd_redirection_not_separator(self):
        """2>&1 should NOT split on &."""
        result = split_commands("echo error 2>&1")
        self.assertEqual(len(result), 1)

    def test_ampersand_redirect_not_separator(self):
        """&> should NOT split on &."""
        result = split_commands("echo hello &>/dev/null")
        self.assertEqual(len(result), 1)


# ============================================================
# 4. Wrapper/Eval Bypass Detection
# ============================================================

class TestWrapperBypass(unittest.TestCase):
    """Test is_delete_command with shell wrapper patterns.

    CRITICAL GAP: bash -c, sh -c, eval wrappers had zero test coverage.
    """

    def test_bash_c_rm_rf(self):
        """bash -c 'rm -rf .git' -- is_delete_command checks the whole string.

        NOTE: is_delete_command uses regex patterns that look for rm preceded
        by separators or start-of-string. bash -c "rm ..." has rm after a
        quote char, so the regex may or may not match.
        """
        result = is_delete_command('bash -c "rm -rf .git"')
        # The regex pattern is r"(?:^|[;&|({]\s*)rm\s+"
        # "rm -rf .git" has rm after a " which is not in the alternation.
        # So this will NOT match. This is a known gap.
        # Document actual behavior:
        self.assertFalse(result)  # GAP: wrapper bypass not detected

    def test_sh_c_rm_rf(self):
        """sh -c 'rm -rf /tmp' -- same wrapper bypass gap."""
        result = is_delete_command('sh -c "rm -rf /tmp"')
        self.assertFalse(result)  # GAP: wrapper bypass not detected

    def test_eval_rm_rf(self):
        """eval 'rm -rf .git' -- eval is not a tracked wrapper."""
        result = is_delete_command('eval "rm -rf .git"')
        self.assertFalse(result)  # GAP: eval bypass not detected

    def test_direct_rm_rf(self):
        """Direct rm -rf should be detected (baseline sanity check)."""
        self.assertTrue(is_delete_command("rm -rf .git"))

    def test_rm_after_semicolon(self):
        """rm after semicolon should be detected."""
        self.assertTrue(is_delete_command("echo hello; rm -rf .git"))

    def test_rm_after_pipe(self):
        """rm after pipe should be detected."""
        self.assertTrue(is_delete_command("echo hello | rm -rf .git"))

    def test_rm_after_ampersand(self):
        """rm after & should be detected."""
        self.assertTrue(is_delete_command("echo hello & rm -rf .git"))

    def test_rm_inside_brace_group(self):
        """rm inside { } should be detected (V1 fix)."""
        self.assertTrue(is_delete_command("{ rm -rf .git; }"))

    def test_rm_inside_subshell(self):
        """rm inside ( ) should be detected (V1 fix)."""
        self.assertTrue(is_delete_command("(rm -rf .git)"))

    def test_git_rm(self):
        """git rm should be detected."""
        self.assertTrue(is_delete_command("git rm file.txt"))

    def test_rmdir(self):
        """rmdir should be detected."""
        self.assertTrue(is_delete_command("rmdir emptydir"))

    def test_truncation_redirect(self):
        """Standalone redirect truncation should be detected as delete."""
        self.assertTrue(is_delete_command("> file.txt"))

    def test_python_os_remove(self):
        """python os.remove should be detected."""
        self.assertTrue(is_delete_command("python -c 'import os; os.remove(\"f\")'"))

    def test_is_write_command_basic(self):
        """Sanity check: is_write_command detects basic writes."""
        self.assertTrue(is_write_command("echo hello > file.txt"))
        self.assertTrue(is_write_command("cp a.txt b.txt"))
        self.assertTrue(is_write_command("mv a.txt b.txt"))
        self.assertFalse(is_write_command("echo hello"))


# ============================================================
# 5. scan_protected_paths integration
# ============================================================

class TestScanProtectedPathsEdgeCases(unittest.TestCase):
    """Edge cases for scan_protected_paths Layer 1 scanning."""

    def test_env_file_detected(self):
        """Direct .env reference should be detected."""
        verdict, reason = scan_protected_paths("cat .env", SCAN_CONFIG)
        self.assertIn(verdict, ("deny", "ask"))

    def test_env_in_path_detected(self):
        """./.env reference should be detected (I-4 fix)."""
        verdict, reason = scan_protected_paths("cat ./.env", SCAN_CONFIG)
        self.assertIn(verdict, ("deny", "ask"))

    def test_no_protected_path(self):
        """Command without protected paths should be allowed."""
        verdict, reason = scan_protected_paths("echo hello", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    def test_scan_disabled(self):
        """When bashPathScan is disabled, should allow."""
        config = {
            "zeroAccessPaths": [".env"],
            "bashPathScan": {"enabled": False},
        }
        verdict, reason = scan_protected_paths("cat .env", config)
        self.assertEqual(verdict, "allow")


if __name__ == "__main__":
    unittest.main()
