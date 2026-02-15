#!/usr/bin/env python3
"""V2 Cross-Model Validation Tests.

Tests bypass attempts identified by Codex and Gemini during red-teaming.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    extract_paths,
    is_delete_command,
    is_write_command,
    scan_protected_paths,
    split_commands,
)

GUARDIAN_CONFIG_PATH = str(_bootstrap._REPO_ROOT / "assets" / "guardian.default.json")

SCAN_CONFIG = {
    "zeroAccessPaths": [
        ".env", ".env.*", ".env*.local", "*.pem",
        "id_rsa", "id_rsa.*", "id_ed25519", "id_ed25519.*",
        "~/.ssh/**",
    ],
    "bashPathScan": {
        "enabled": True,
        "exactMatchAction": "ask",
        "patternMatchAction": "ask",
    },
}


class TestGeminiBypass_GitRmGlobalFlags(unittest.TestCase):
    """Gemini found: git -C . rm file bypasses the git rm regex.

    The regex r"(?:^|[;&|]\\s*)git\\s+rm\\s+" requires 'git' immediately
    followed by 'rm'. Global flags like -C break this adjacency.
    """

    def test_git_global_flag_c_rm(self):
        """BYPASS FOUND: git -C . rm file NOT detected as delete."""
        result = is_delete_command("git -C . rm file")
        # This IS a real bypass -- the regex misses it
        # Documenting current behavior
        if result:
            pass  # Fixed
        else:
            pass  # Known gap: git global flags before rm

    def test_git_global_flag_c_rm_scan(self):
        """Even if is_delete misses it, Layer 1 won't help (no protected path)."""
        # The file name 'file' is generic, Layer 1 won't catch it
        # But if it targets a protected file...
        v, r = scan_protected_paths("git -C . rm .env", SCAN_CONFIG)
        self.assertEqual(v, "ask")  # Layer 1 catches .env literal


class TestGeminiBypass_QuoteObfuscation(unittest.TestCase):
    """Gemini found: cat .'env' or cat .""env breaks literal matching."""

    def test_empty_quotes_in_filename(self):
        """cat .''env -- empty quotes break Layer 1 literal match."""
        # Shell interprets .''env as .env (empty string concatenation)
        # But Layer 1 sees the literal .''env, not .env
        cmd = "cat .''env"
        v, r = scan_protected_paths(cmd, SCAN_CONFIG)
        # BYPASS: .''env does NOT contain literal ".env"
        # Current behavior: allow (not caught)
        # This is a genuine Layer 1 bypass

    def test_double_empty_quotes_in_filename(self):
        """cat .""env -- double empty quotes."""
        cmd = 'cat .""env'
        v, r = scan_protected_paths(cmd, SCAN_CONFIG)
        # BYPASS: .""env does NOT contain literal ".env"

    def test_quote_split_env(self):
        """cat '.env' -- single-quoted .env."""
        cmd = "cat '.env'"
        v, r = scan_protected_paths(cmd, SCAN_CONFIG)
        # This SHOULD be caught because '.env' contains .env literal
        # The boundary regex: (?:^|[...'])  -- ' is in boundary_before
        # So '.env' should match: ' before .env, ' after .env
        self.assertEqual(v, "ask")


class TestGeminiBypass_VariableExpansion(unittest.TestCase):
    """Gemini found: v=.env; cat $v hides .env in a variable."""

    def test_variable_hides_path(self):
        """v=.env; cat $v -- Layer 1 catches .env in assignment."""
        cmd = "v=.env; cat $v"
        v, r = scan_protected_paths(cmd, SCAN_CONFIG)
        # Layer 1 scans the RAW command, which contains ".env" literally
        # in the assignment "v=.env"
        self.assertEqual(v, "ask")

    def test_variable_no_literal(self):
        """export v=$(echo .env); cat $v -- no literal .env in command."""
        # If .env never appears literally...
        # Actually it still does: "echo .env" contains ".env"
        cmd = "export v=$(echo .env); cat $v"
        v, r = scan_protected_paths(cmd, SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_fully_indirect_variable(self):
        """v=$(printf '\\x2eenv'); cat $v -- truly hidden."""
        # This constructs .env from hex codes -- no ".env" literal anywhere
        cmd = "v=$(printf '\\x2eenv'); cat $v"
        v, r = scan_protected_paths(cmd, SCAN_CONFIG)
        # BYPASS: No literal ".env" in the command string
        # Current behavior: allow (not caught by Layer 1)
        # Layer 2+3 would see "$v" which expands but Python doesn't execute


class TestGeminiBypass_RelativePath(unittest.TestCase):
    """Gemini found: cat ../../.ssh/id_rsa traverses out of project."""

    def test_relative_path_traversal_in_scan(self):
        """Layer 1 catches id_rsa literal regardless of path prefix."""
        v, r = scan_protected_paths("cat ../../.ssh/id_rsa", SCAN_CONFIG)
        self.assertEqual(v, "ask")

    def test_relative_path_traversal_in_extract(self):
        """Layer 3 resolves path -- outside project, not extracted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("cat ../../.ssh/id_rsa", Path(tmpdir))
            # Path resolves outside tmpdir, should NOT be extracted
            for p in paths:
                self.assertFalse(
                    str(p).endswith("id_rsa"),
                    f"Path {p} should not be extracted (outside project)"
                )


class TestCodexBypass_NoDeleteViaOverwrite(unittest.TestCase):
    """Codex found: noDelete files can be destroyed via overwrite/truncation.

    echo '' > CLAUDE.md is caught as is_write but not is_delete,
    so match_no_delete() (which only runs for is_delete) won't trigger.
    """

    def test_echo_redirect_is_write_not_delete(self):
        """echo '' > CLAUDE.md -- write, not delete. noDelete won't trigger."""
        self.assertTrue(is_write_command("echo '' > CLAUDE.md"))
        self.assertFalse(is_delete_command("echo '' > CLAUDE.md"))
        # FINDING: This is a real gap. noDeletePaths only protect against
        # is_delete_command, not destructive writes that effectively
        # destroy content.

    def test_bare_truncation_is_delete(self):
        """> CLAUDE.md -- bare truncation IS caught as delete (P1-2 fix)."""
        self.assertTrue(is_delete_command("> CLAUDE.md"))

    def test_cat_devnull_redirect_is_write(self):
        """cat /dev/null > CLAUDE.md -- is_write but not is_delete."""
        self.assertTrue(is_write_command("cat /dev/null > CLAUDE.md"))
        self.assertFalse(is_delete_command("cat /dev/null > CLAUDE.md"))


class TestCodexBypass_ExternalPaths(unittest.TestCase):
    """Codex found: zeroAccessPaths with ** (like ~/.ssh/**) are skipped
    in Layer 1 scan and not enforced in Layer 3 (outside project).
    """

    def test_ssh_path_layer1_skips_doublestar(self):
        """~/.ssh/** patterns are skipped in scan_protected_paths."""
        # But id_rsa literal is STILL caught separately
        v, r = scan_protected_paths("cat ~/.ssh/config", SCAN_CONFIG)
        # "config" is not a protected literal, and ~/.ssh/** is skipped
        # FINDING: ~/.ssh/config is NOT caught
        # Only protected if the filename itself matches a zeroAccess pattern

    def test_ssh_known_hosts_not_caught(self):
        """~/.ssh/known_hosts -- not a zeroAccess literal."""
        v, r = scan_protected_paths("cat ~/.ssh/known_hosts", SCAN_CONFIG)
        # FINDING: known_hosts not protected individually

    def test_aws_credentials_not_caught(self):
        """~/.aws/credentials -- ** pattern skipped, 'credentials' not literal."""
        v, r = scan_protected_paths("cat ~/.aws/credentials", SCAN_CONFIG)
        # FINDING: ~/.aws/credentials not caught
        # The *credentials*.json pattern wouldn't match (no .json)


class TestCodexBypass_LongFlagPaths(unittest.TestCase):
    """Codex found: --flag=value paths not parsed by extract_paths.

    Layer 3 skips all --prefixed flags entirely. Only Layer 1 can catch.
    """

    def test_long_flag_not_extracted(self):
        """--config=.env -- not extracted by Layer 3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.touch()
            paths = extract_paths("tool --config=.env", Path(tmpdir))
            # Long flags are skipped entirely
            env_found = any(p.name == ".env" for p in paths)
            # FINDING: .env not extracted from --config=.env
            # But Layer 1 catches it

    def test_long_flag_caught_by_layer1(self):
        """Layer 1 catches .env in --config=.env."""
        v, r = scan_protected_paths("tool --config=.env", SCAN_CONFIG)
        self.assertEqual(v, "ask")


class TestGeminiBypass_ExecPrefix(unittest.TestCase):
    """Gemini found: exec chmod 777 file -- exec prefix."""

    def test_exec_chmod(self):
        """exec chmod 777 file -- still caught by is_write."""
        # The pattern is r"\\bchmod\\s+" which uses word boundary
        # "exec chmod" still contains "chmod" with word boundary
        self.assertTrue(is_write_command("exec chmod 777 file"))

    def test_env_chmod(self):
        """env chmod 777 file -- env prefix."""
        self.assertTrue(is_write_command("env chmod 777 file"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
