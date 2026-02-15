#!/usr/bin/env python3
"""Adversarial test suite for Guardian V2 Fixes (F1-F10) + V1 Hotfixes.

Goal: Find bypasses, edge cases, and weaknesses through creative adversarial testing.
Tests are organized by fix ID. Each test documents the attack vector and expected behavior.

Run: python3 -m unittest temp.test_guardian_v2fixes_adversarial -v
"""

import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Bootstrap test environment


# Add tests/ directory to path for _bootstrap import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

# Original path insert replaced by _bootstrap
# sys.path.insert(
#     0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts"
# )

from bash_guardian import (
    _is_within_project_or_would_be,
    _stronger_verdict,
    archive_files,
    extract_paths,
    extract_redirection_targets,
    is_delete_command,
    is_write_command,
    scan_protected_paths,
    split_commands,
)

# Constants
GUARDIAN_CONFIG_PATH = (
    str(_bootstrap._REPO_ROOT / "assets" / "guardian.default.json")
)
BASH_GUARDIAN_PATH = (
    str(_bootstrap._REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")
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
# F1: Fail-Closed Safety Net — Adversarial Tests
# ============================================================


class TestF1_Adversarial(unittest.TestCase):
    """F1: Try to bypass the fail-closed safety net for unresolvable paths."""

    def test_f1_command_substitution_bypass(self):
        """rm $(echo /etc/passwd) — command substitution hides the real target.

        shlex.split produces ['rm', '$(echo', '/etc/passwd)'] which are
        nonsensical paths. The key question: does F1 trigger because
        these resolve as bogus in-project paths, or does it miss them?
        """
        self.assertTrue(is_delete_command("rm $(echo /etc/passwd)"))
        # The command substitution is NOT expanded by Python's shlex
        # so extract_paths will get weird tokens

    def test_f1_backtick_substitution(self):
        """rm `cat targets.txt` — backtick substitution hides targets."""
        self.assertTrue(is_delete_command("rm `cat targets.txt`"))

    def test_f1_brace_expansion_bypass(self):
        """rm {a,b,c}.txt — brace expansion not handled by shlex.

        shlex.split produces ['rm', '{a,b,c}.txt'] as a single token.
        Path('{a,b,c}.txt') is not a real path, but _is_path_candidate
        returns True, and it becomes project_dir/{a,b,c}.txt which
        doesn't exist but passes _is_within_project_or_would_be.
        """
        self.assertTrue(is_delete_command("rm {a,b,c}.txt"))
        # F1 should ideally trigger but brace expansion creates a fake path

    def test_f1_tilde_expansion_other_user(self):
        """rm ~root/file — tilde expansion for other users.

        If expanduser fails for unknown user, the path stays as
        ~root/file which becomes project_dir/~root/file.
        """
        self.assertTrue(is_delete_command("rm ~root/file"))

    def test_f1_env_var_set_to_outside_path(self):
        """rm $OUTSIDE — when env var is set to a path outside project.

        expandvars resolves $OUTSIDE to /etc/passwd, which is outside
        project. extract_paths should reject it (not within project).
        Then sub_paths is empty, and F1 triggers "ask".
        """
        self.assertTrue(is_delete_command("rm $OUTSIDE"))
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"OUTSIDE": "/etc/passwd"}):
                paths = extract_paths("rm $OUTSIDE", Path(tmpdir), allow_nonexistent=True)
                # /etc/passwd is outside project, should be rejected
                self.assertEqual(len(paths), 0,
                    "Path outside project should not be returned")

    def test_f1_write_with_only_flags(self):
        """cp --version — write detected, no paths. F1 should trigger."""
        self.assertTrue(is_write_command("cp --version"))
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("cp --version", Path(tmpdir), allow_nonexistent=True)
            redir = extract_redirection_targets("cp --version", Path(tmpdir))
            sub_paths = paths + redir
            # No actual paths, just flags — F1 should trigger
            # Verify the F1 condition would be met
            is_write = is_write_command("cp --version")
            is_delete = is_delete_command("cp --version")
            self.assertTrue(is_write or is_delete)
            self.assertEqual(len(sub_paths), 0,
                "Flags-only commands should have no resolved paths")

    def test_f1_glob_pattern_in_rm(self):
        """rm *.bak — glob not expanded by shlex, becomes literal path."""
        self.assertTrue(is_delete_command("rm *.bak"))
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("rm *.bak", Path(tmpdir), allow_nonexistent=True)
            # *.bak has wildcard, extract_paths does glob.glob which may return nothing
            # F1 should trigger if no matches

    def test_f1_heredoc_write_bypass(self):
        """cat << EOF > /etc/passwd — heredoc with redirect.

        split_commands should not split at <<. The redirect > should
        be caught.
        """
        cmd = "cat << EOF > /tmp/output"
        self.assertTrue(is_write_command(cmd))

    def test_f1_process_substitution_with_write(self):
        """tee >(grep error) — tee is write, process sub is not a path.

        F6 filters process substitution targets. With only process sub
        targets, sub_paths could be empty, triggering F1.
        """
        self.assertTrue(is_write_command("tee >(grep error)"))

    def test_f1_dd_with_variable_output(self):
        """dd if=/dev/zero of=$TARGET — write command, variable target."""
        self.assertTrue(is_write_command("dd if=/dev/zero of=$TARGET"))


# ============================================================
# F2: ln Write Detection — Adversarial Tests
# ============================================================


class TestF2_Adversarial(unittest.TestCase):
    """F2: Try to bypass ln write detection."""

    def test_f2_command_wrapper_ln(self):
        """command ln -sf target link — 'command' prefix bypasses \\b.

        \\bln\\s+ looks for word boundary before ln. In 'command ln',
        the space before 'ln' creates a word boundary, so \\b matches.
        This should be caught.
        """
        self.assertTrue(is_write_command("command ln -sf target link"))

    def test_f2_env_wrapper_ln(self):
        """env ln -sf target link — 'env' prefix."""
        self.assertTrue(is_write_command("env ln -sf target link"))

    def test_f2_absolute_path_ln(self):
        """/usr/bin/ln -sf target link — absolute path to ln.

        The \\b boundary is between / and l (/ is non-word, l is word),
        so \\bln should match.
        """
        self.assertTrue(is_write_command("/usr/bin/ln -sf target link"))

    def test_f2_sudo_ln(self):
        """sudo ln -sf target link — sudo prefix."""
        self.assertTrue(is_write_command("sudo ln -sf target link"))

    def test_f2_ln_at_end_no_space(self):
        """echo ln — 'ln' at end with no trailing space. Should NOT match."""
        self.assertFalse(is_write_command("echo ln"))

    def test_f2_xargs_ln(self):
        """xargs ln -sf — xargs feeds targets to ln."""
        # 'ln' appears with word boundary and trailing space
        self.assertTrue(is_write_command("xargs ln -sf"))

    def test_f2_ln_inside_single_quotes(self):
        """echo 'ln -sf target link' — ln inside quotes.

        Pre-existing issue: is_write_command doesn't parse quotes.
        This is a known false positive across ALL write patterns.
        """
        # This WILL match (known pre-existing false positive)
        result = is_write_command("echo 'ln -sf target link'")
        # Document the behavior
        self.assertTrue(result, "Known pre-existing: ln inside quotes matches")

    def test_f2_ln_tab_separator(self):
        """ln\\t-sf target link — tab instead of space after ln."""
        self.assertTrue(is_write_command("ln\t-sf target link"))

    def test_f2_ln_multiple_spaces(self):
        """ln   -sf target link — multiple spaces after ln."""
        self.assertTrue(is_write_command("ln   -sf target link"))

    def test_f2_newline_ln(self):
        """Newline before ln — should this match in subcommand context?"""
        self.assertTrue(is_write_command("\nln -sf target link"))


# ============================================================
# F3: >| Clobber — Adversarial Tests
# ============================================================


class TestF3_Adversarial(unittest.TestCase):
    """F3: Try to bypass >| clobber detection and exploit split_commands interaction."""

    def test_f3_clobber_split_by_pipe(self):
        """echo x >| file.txt — split_commands treats | as pipe separator.

        This is the known SEC-F3-1 finding. split_commands produces:
        ['echo x >', 'file.txt']. Neither sub-command triggers write/delete.
        Layer 1 scan should still catch protected paths.
        """
        subs = split_commands("echo x >| file.txt")
        # Verify the split happens at |
        self.assertEqual(len(subs), 2,
            "split_commands should split >| at pipe character")
        self.assertEqual(subs[0], "echo x >")
        self.assertEqual(subs[1], "file.txt")

    def test_f3_clobber_simple_extraction(self):
        """echo x >| file.txt — direct extraction (no split_commands)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("echo x >| file.txt", Path(tmpdir))
            target_names = [t.name for t in targets]
            self.assertIn("file.txt", target_names,
                ">| should extract file.txt as redirection target")

    def test_f3_fd_clobber(self):
        """cmd 2>| errors.log — fd number with clobber."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("cmd 2>| errors.log", Path(tmpdir))
            target_names = [t.name for t in targets]
            self.assertIn("errors.log", target_names,
                "2>| should extract errors.log")

    def test_f3_clobber_protected_file_layer1(self):
        """echo x >| .env — Layer 1 should catch .env even with >| split."""
        verdict, reason = scan_protected_paths("echo x >| .env", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow",
            "Layer 1 should catch .env in >| context")

    def test_f3_ampersand_clobber(self):
        """cmd &>| file.txt — &> with | — unusual combination."""
        # This is an unusual combo. Let's see how it splits
        subs = split_commands("cmd &>| file.txt")
        # &> is handled as redirect in split_commands, then | splits
        # The behavior depends on how & is handled

    def test_f3_double_clobber(self):
        """cmd >|>| file.txt — double clobber nonsense.

        The regex should handle this gracefully without ReDoS.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("cmd >|>| file.txt", Path(tmpdir))
            # Should extract something without hanging

    def test_f3_clobber_with_space(self):
        """cmd > | file.txt — space between > and |.

        This is > (redirect to nothing?) then | (pipe). Not a clobber.
        """
        subs = split_commands("cmd > | file.txt")
        # > should be redirection, | should be pipe
        # This should not be treated as >|


# ============================================================
# F4: ReDoS Fix — Adversarial Tests
# ============================================================


class TestF4_Adversarial(unittest.TestCase):
    """F4: Try to trigger ReDoS or bypass the split patterns."""

    def test_f4_performance_130k(self):
        """130K character input must complete in <1s."""
        cmd = "python3 " + "x " * 65000 + "pathlib.Path('f').unlink()"
        start = time.time()
        result = is_delete_command(cmd)
        elapsed = time.time() - start
        self.assertTrue(result, "pathlib.Path().unlink() should be detected")
        self.assertLess(elapsed, 1.0, f"ReDoS: took {elapsed:.2f}s (>1s)")

    def test_f4_performance_260k(self):
        """260K character input — should still be linear."""
        cmd = "python3 " + "x " * 130000 + "os.remove('f')"
        start = time.time()
        result = is_delete_command(cmd)
        elapsed = time.time() - start
        self.assertTrue(result)
        self.assertLess(elapsed, 2.0, f"ReDoS: took {elapsed:.2f}s (>2s)")

    def test_f4_nested_parens_pathlib(self):
        """pathlib.Path(foo(bar)).unlink() — nested parens bypass [^)]* .

        The pattern uses [^)]*  which stops at the first ). So
        pathlib.Path(foo(bar) would match [^)]* as 'foo(bar', then
        the closing ) matches, then .unlink should follow.
        But actually: pathlib.Path(foo(bar)).unlink() — the [^)]*
        matches 'foo(bar', then ) matches, then ).unlink() — but
        the regex expects .unlink immediately after ).

        Let's test: pathlib\.Path\([^)]*\)\.unlink
        Input: pathlib.Path(foo(bar)).unlink()
        [^)]* matches: foo(bar  (stops at first ))
        Then expects: )  — matches first )
        Then expects: \.unlink — but next char is ) not .
        So this does NOT match.
        """
        cmd = "python3 -c \"pathlib.Path(foo(bar)).unlink()\""
        result = is_delete_command(cmd)
        self.assertFalse(result,
            "Nested parens should prevent match — [^)]* stops at first )")

    def test_f4_pathlib_no_parens(self):
        """pathlib.Path.unlink — no constructor call, should not match.

        The regex requires \\( after Path.
        """
        cmd = "python3 -c \"pathlib.Path.unlink(p)\""
        result = is_delete_command(cmd)
        self.assertFalse(result,
            "pathlib.Path.unlink without constructor should not match")

    def test_f4_shutil_move_preserved(self):
        """V1 hotfix: shutil.move must still be detected.

        The V1-CODE review found shutil.move was dropped during the split.
        This was fixed in the V1 hotfix. Verify it's present.
        """
        cmd = "python3 -c \"shutil.move('a', 'b')\""
        result = is_delete_command(cmd)
        self.assertTrue(result,
            "shutil.move must be detected (V1 hotfix)")

    def test_f4_shutil_move_in_config(self):
        """Verify shutil.move is in guardian.default.json block patterns."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        patterns = [p["pattern"] for p in config["bashToolPatterns"]["block"]]
        has_shutil_move = any("shutil\\.move" in p or "shutil\\\\.move" in p for p in patterns)
        self.assertTrue(has_shutil_move,
            "shutil.move must be in config block patterns")

    def test_f4_os_rmdir_detected(self):
        """os.rmdir should be detected in the first split pattern."""
        cmd = "python3 -c \"os.rmdir('/tmp/dir')\""
        result = is_delete_command(cmd)
        self.assertTrue(result, "os.rmdir should be detected")

    def test_f4_pathlib_purepath_unlink(self):
        """pathlib.PurePosixPath — PurePath doesn't have unlink().

        Not a real bypass since PurePath can't do filesystem ops,
        but verify the regex doesn't match PurePosixPath.
        """
        cmd = "python3 -c \"pathlib.PurePosixPath('f').unlink()\""
        result = is_delete_command(cmd)
        # pathlib.PurePosixPath does not match pathlib.Path
        self.assertFalse(result,
            "PurePosixPath should not match pathlib.Path pattern")

    def test_f4_adversarial_backtracking_attempt(self):
        """Try to create backtracking with the new split patterns.

        Pattern 1: [^|&\\n]*(?:os\\.remove|...) — try input with many
        near-matches to force backtracking.
        """
        # Create input with many "os.remov" near-misses followed by "os.remove"
        cmd = "python3 " + "os.remov " * 10000 + "os.remove('f')"
        start = time.time()
        result = is_delete_command(cmd)
        elapsed = time.time() - start
        self.assertTrue(result)
        self.assertLess(elapsed, 2.0, f"Near-miss backtracking: {elapsed:.2f}s")

    def test_f4_pipe_in_python_code(self):
        """python3 -c 'a | b; os.remove(f)' — pipe in python code.

        [^|&\\n]* stops at |, so os.remove after a pipe should not match.
        But split_commands would split at | first, so the subcommand
        'b; os.remove(f)' would not start with python3.
        """
        cmd = "python3 -c 'a | b; os.remove(f)'"
        # split_commands splits at |
        subs = split_commands(cmd)
        # After split, only first sub starts with python3
        # The second sub 'b; os.remove(f)' doesn't start with python
        # So is_delete_command on the second sub should not match the interpreter pattern


# ============================================================
# F5: Archive Symlink Safety — Adversarial Tests
# ============================================================


class TestF5_Adversarial(unittest.TestCase):
    """F5: Try to bypass archive symlink protection."""

    def test_f5_symlink_preserved_not_dereferenced(self):
        """Archive should preserve symlinks, not follow them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            # Create a symlink pointing to /etc/passwd
            link_path = project / "evil_link"
            link_path.symlink_to("/etc/passwd")

            archive_dir, archived = archive_files([link_path], project)

            if archived:
                orig, arch = archived[0]
                # The archived copy should be a symlink, not a regular file
                self.assertTrue(os.path.islink(arch),
                    "Archived symlink should remain a symlink")
                # It should point to /etc/passwd (preserved target)
                self.assertEqual(os.readlink(arch), "/etc/passwd",
                    "Symlink target should be preserved")
                # It should NOT have copied /etc/passwd contents
                if os.path.isfile(arch) and not os.path.islink(arch):
                    self.fail("Symlink was dereferenced — /etc/passwd contents copied!")

            # Cleanup
            if archive_dir and archive_dir.exists():
                shutil.rmtree(archive_dir)

    def test_f5_symlink_chain(self):
        """A -> B -> /etc/shadow — symlink chain. Only first link preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            link_b = project / "link_b"
            link_b.symlink_to("/etc/shadow")

            link_a = project / "link_a"
            link_a.symlink_to(str(link_b))

            archive_dir, archived = archive_files([link_a], project)

            if archived:
                orig, arch = archived[0]
                self.assertTrue(os.path.islink(arch),
                    "Chained symlink should be preserved as symlink")
                # Should point to link_b, not /etc/shadow
                self.assertEqual(os.readlink(arch), str(link_b),
                    "Should preserve immediate symlink target, not follow chain")

            if archive_dir and archive_dir.exists():
                shutil.rmtree(archive_dir)

    def test_f5_hardlink_not_caught_by_islink(self):
        """Hardlinks are NOT detected by os.path.islink().

        This is expected behavior — hardlinks share the same inode
        and can't point outside the filesystem. shutil.copy2 copies
        the data, which is a faithful archive.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            original = project / "original.txt"
            original.write_text("test data")

            hardlink = project / "hardlink.txt"
            os.link(str(original), str(hardlink))

            self.assertFalse(os.path.islink(hardlink),
                "Hardlink should not be detected as symlink")

            archive_dir, archived = archive_files([hardlink], project)

            if archived:
                orig, arch = archived[0]
                # Data should be copied (shutil.copy2)
                self.assertTrue(arch.exists())
                self.assertEqual(arch.read_text(), "test data")

            if archive_dir and archive_dir.exists():
                shutil.rmtree(archive_dir)

    def test_f5_copytree_symlinks_param(self):
        """Verify shutil.copytree uses symlinks=True in source code."""
        with open(BASH_GUARDIAN_PATH) as f:
            source = f.read()
        self.assertIn("symlinks=True", source,
            "copytree must use symlinks=True")

    def test_f5_broken_symlink_handling(self):
        """Broken symlink — target doesn't exist. Archive should handle gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            broken_link = project / "broken"
            broken_link.symlink_to("/nonexistent/path/that/does/not/exist")

            self.assertTrue(os.path.islink(broken_link))
            self.assertFalse(broken_link.exists())  # Broken — target missing

            # archive_files checks is_file() which returns False for broken symlinks
            # So the file branch won't execute... but archived.append still runs
            # (pre-existing bug noted in V1-CODE review)
            archive_dir, archived = archive_files([broken_link], project)

            if archive_dir and archive_dir.exists():
                shutil.rmtree(archive_dir)

    def test_f5_dir_with_symlinks_inside(self):
        """Directory containing symlinks to sensitive files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            target_dir = project / "mydir"
            target_dir.mkdir()

            # Create a symlink inside the dir pointing outside
            (target_dir / "evil").symlink_to("/etc/passwd")
            (target_dir / "normal.txt").write_text("safe content")

            archive_dir, archived = archive_files([target_dir], project)

            if archived:
                orig, arch = archived[0]
                evil_arch = arch / "evil"
                if evil_arch.exists() or os.path.islink(evil_arch):
                    self.assertTrue(os.path.islink(evil_arch),
                        "Symlink inside dir should be preserved by copytree(symlinks=True)")

            if archive_dir and archive_dir.exists():
                shutil.rmtree(archive_dir)


# ============================================================
# F6: Process Substitution Exclusion — Adversarial Tests
# ============================================================


class TestF6_Adversarial(unittest.TestCase):
    """F6: Try to bypass process substitution filtering."""

    def test_f6_process_sub_filtered(self):
        """>(grep error) — should be filtered (starts with '(')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("tee >(grep error)", Path(tmpdir))
            for t in targets:
                self.assertFalse(str(t.name).startswith("("),
                    "Process substitution should be filtered")

    def test_f6_input_process_sub(self):
        """<(sort file) — input process substitution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("diff <(sort a) <(sort b)", Path(tmpdir))
            for t in targets:
                self.assertFalse(str(t.name).startswith("("),
                    "Input process substitution should be filtered")

    def test_f6_real_paren_filename(self):
        """cmd > '(file.txt)' — literal file starting with (.

        Known edge case: file named (file.txt) used as redirect target
        is incorrectly filtered because strip("'\"") removes quotes,
        leaving (file.txt) which starts with (.
        Severity: INFO — such filenames are extremely rare.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("cmd > '(file.txt)'", Path(tmpdir))
            # Known false negative: literal (file.txt) is filtered
            paren_targets = [t for t in targets if t.name.startswith("(")]
            # This is expected to be empty (false negative)

    def test_f6_nested_process_sub(self):
        """>(>(inner)) — nested process substitution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("cmd >(>(inner))", Path(tmpdir))
            for t in targets:
                self.assertFalse(str(t.name).startswith("("),
                    "Nested process substitution should be filtered")

    def test_f6_redirect_after_process_sub(self):
        """diff <(sort a) > output.txt — mix of process sub and real redirect.

        The process sub should be filtered but output.txt should be kept.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets(
                "diff <(sort a) > output.txt", Path(tmpdir)
            )
            target_names = [t.name for t in targets]
            self.assertIn("output.txt", target_names,
                "Real redirect target should be kept")
            self.assertNotIn("(sort", [t.name for t in targets],
                "Process sub should be filtered")

    def test_f6_space_before_paren(self):
        """cmd > (file) — space before paren. Is this process sub or file?

        In bash, > (file) with a space is actually a subshell redirect,
        not a file named (file). The filter should catch it.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets("cmd > (file)", Path(tmpdir))
            # The regex captures (file) which starts with (, so it's filtered
            for t in targets:
                self.assertFalse(str(t.name).startswith("("))


# ============================================================
# F7: Path Traversal Fix — Adversarial Tests
# ============================================================


class TestF7_Adversarial(unittest.TestCase):
    """F7: Try to bypass path traversal prevention."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_f7_simple_traversal(self):
        """/project/../etc/passwd — basic traversal."""
        evil = self.project / ".." / "etc" / "passwd"
        self.assertFalse(_is_within_project_or_would_be(evil, self.project))

    def test_f7_deep_traversal(self):
        """/project/a/b/c/../../../../etc/passwd — deep traversal."""
        evil = self.project / "a" / "b" / "c" / ".." / ".." / ".." / ".." / "etc" / "passwd"
        self.assertFalse(_is_within_project_or_would_be(evil, self.project))

    def test_f7_dot_traversal(self):
        """/project/./../../etc/passwd — dot then traversal."""
        evil = self.project / "." / ".." / ".." / "etc" / "passwd"
        self.assertFalse(_is_within_project_or_would_be(evil, self.project))

    def test_f7_legitimate_dotdot(self):
        """/project/sub/../file.txt — legitimate traversal within project."""
        legitimate = self.project / "sub" / ".." / "file.txt"
        self.assertTrue(_is_within_project_or_would_be(legitimate, self.project))

    def test_f7_prefix_sibling(self):
        """/project-evil/file — prefix sibling should be rejected."""
        sibling = Path(str(self.project) + "-evil") / "file"
        self.assertFalse(_is_within_project_or_would_be(sibling, self.project))

    def test_f7_symlink_inside_project_to_outside(self):
        """Symlink inside project pointing outside. resolve() follows it."""
        link_path = self.project / "link_to_etc"
        link_path.symlink_to("/etc")

        evil = link_path / "passwd"
        # resolve() follows the symlink: /project/link_to_etc/passwd -> /etc/passwd
        self.assertFalse(_is_within_project_or_would_be(evil, self.project),
            "Symlink escaping project should be rejected")

    def test_f7_symlink_chain_escape(self):
        """Symlink chain: A -> B -> /etc. Deep traversal through chain."""
        link_b = self.project / "link_b"
        link_b.symlink_to("/etc")

        link_a = self.project / "link_a"
        link_a.symlink_to(str(link_b))

        evil = link_a / "passwd"
        self.assertFalse(_is_within_project_or_would_be(evil, self.project),
            "Symlink chain escaping project should be rejected")

    def test_f7_nonexistent_path_traversal(self):
        """Non-existent path with traversal: /project/nonexist/../../etc/passwd.

        resolve(strict=False) handles non-existent components by
        canonicalizing what it can.
        """
        evil = self.project / "nonexist" / ".." / ".." / "etc" / "passwd"
        self.assertFalse(_is_within_project_or_would_be(evil, self.project))

    def test_f7_trailing_slash(self):
        """Path with trailing slash should still work."""
        path = Path(str(self.project) + "/")
        self.assertTrue(_is_within_project_or_would_be(path, self.project))

    def test_f7_root_path(self):
        """/ should be rejected (unless project is /)."""
        root = Path("/")
        if str(self.project.resolve()) != "/":
            self.assertFalse(_is_within_project_or_would_be(root, self.project))

    def test_f7_absolute_outside(self):
        """/etc/passwd — absolute path outside project."""
        self.assertFalse(_is_within_project_or_would_be(Path("/etc/passwd"), self.project))

    def test_f7_many_dotdots(self):
        """100 ../  components — should resolve and be rejected."""
        evil = self.project
        for _ in range(100):
            evil = evil / ".."
        evil = evil / "etc" / "passwd"
        self.assertFalse(_is_within_project_or_would_be(evil, self.project))

    def test_f7_project_root_itself(self):
        """The project directory itself should be within project."""
        self.assertTrue(_is_within_project_or_would_be(self.project, self.project))

    def test_f7_null_byte_in_path(self):
        """Path with null byte should be rejected (ValueError)."""
        try:
            evil = Path("/tmp/test\x00evil")
            result = _is_within_project_or_would_be(evil, self.project)
            # If we get here, the function handled it gracefully
            self.assertFalse(result)
        except (ValueError, OSError):
            # Expected — null bytes are invalid in paths
            pass

    def test_f7_very_long_path(self):
        """Very long path should be handled gracefully."""
        # Path with 1000 components
        long_path = self.project
        for i in range(1000):
            long_path = long_path / f"dir{i}"
        result = _is_within_project_or_would_be(long_path, self.project)
        self.assertTrue(result, "Long path within project should be accepted")


# ============================================================
# F8: Git Flags Before rm — Adversarial Tests
# ============================================================


class TestF8_Adversarial(unittest.TestCase):
    """F8: Try to bypass git rm detection with creative flag usage."""

    def test_f8_basic_git_rm(self):
        """git rm file — basic case."""
        self.assertTrue(is_delete_command("git rm file"))

    def test_f8_git_C_rm(self):
        """git -C . rm file — short flag with value."""
        self.assertTrue(is_delete_command("git -C . rm file"))

    def test_f8_git_c_config_rm(self):
        """git -c key=val rm file — config flag."""
        self.assertTrue(is_delete_command("git -c key=val rm file"))

    def test_f8_git_multiple_flags_rm(self):
        """git -C . -c key=val rm file — multiple flags."""
        self.assertTrue(is_delete_command("git -C . -c key=val rm file"))

    def test_f8_git_work_tree_long_flag(self):
        """git --work-tree=/tmp rm file — long flag with = value.

        The V1 hotfix added --[a-z][-a-z]*(?:=\\S+|\\s+\\S+) to handle
        long flags. This should now be caught.
        """
        self.assertTrue(is_delete_command("git --work-tree=/tmp rm file"),
            "V1 hotfix: --work-tree with = should be caught")

    def test_f8_git_work_tree_space_value(self):
        """git --work-tree /tmp rm file — long flag with space value."""
        self.assertTrue(is_delete_command("git --work-tree /tmp rm file"),
            "V1 hotfix: --work-tree with space value should be caught")

    def test_f8_git_git_dir_equals(self):
        """git --git-dir=.git rm file — --git-dir with = value."""
        self.assertTrue(is_delete_command("git --git-dir=.git rm file"),
            "V1 hotfix: --git-dir with = should be caught")

    def test_f8_git_git_dir_space(self):
        """git --git-dir .git rm file — --git-dir with space value."""
        self.assertTrue(is_delete_command("git --git-dir .git rm file"),
            "V1 hotfix: --git-dir with space value should be caught")

    def test_f8_git_boolean_flag_no_value(self):
        """git --no-pager rm file — boolean flag (no value).

        The regex expects --flag value (consuming 'rm' as value) or
        --flag=value. For --no-pager (no value), the regex consumes
        --no-pager as the flag and 'rm' as its value, then fails.

        This is a KNOWN BYPASS documented in V1-CODE review.
        """
        result = is_delete_command("git --no-pager rm file")
        # Document whether this is caught or bypassed
        # The regex --[a-z][-a-z]*(?:=\S+|\s+\S+) treats 'rm' as the value
        # Then looks for another 'rm\s+' — finds 'file' but that's not 'rm'
        # So this is a FALSE NEGATIVE (known bypass)
        if not result:
            # Known bypass — document it
            pass  # Expected: not caught

    def test_f8_git_paginate_rm(self):
        """git --paginate rm file — another boolean flag."""
        result = is_delete_command("git --paginate rm file")
        # Same issue as --no-pager: boolean flag without value

    def test_f8_git_bare_rm(self):
        """git --bare rm file — boolean flag."""
        result = is_delete_command("git --bare rm file")
        # Same issue

    def test_f8_git_status_not_delete(self):
        """git status — should NOT be detected as delete."""
        self.assertFalse(is_delete_command("git status"))

    def test_f8_git_log_not_delete(self):
        """git log — should NOT be detected as delete."""
        self.assertFalse(is_delete_command("git log"))

    def test_f8_git_C_status_not_delete(self):
        """git -C . status — should NOT be detected as delete."""
        self.assertFalse(is_delete_command("git -C . status"))

    def test_f8_git_uppercase_long_flag(self):
        """git --Work-Tree=/tmp rm file — uppercase in long flag.

        The regex uses [a-z][-a-z]* which only matches lowercase.
        Git itself accepts case-sensitive options.
        """
        result = is_delete_command("git --Work-Tree=/tmp rm file")
        # Uppercase W won't match [a-z], so the long flag pattern doesn't match
        # But --Work-Tree is not a valid git option anyway

    def test_f8_git_double_dash_rm(self):
        """git -- rm file — double dash then rm.

        '--' ends option parsing. After --, 'rm' is a pathspec, not subcommand.
        The regex doesn't know about -- semantics, so it might match.
        """
        result = is_delete_command("git -- rm file")
        # The regex sees 'git ... rm\s+' and matches
        # This is a false positive — 'rm' after -- is a filename, not subcommand
        # But false positives are acceptable for security

    def test_f8_git_C_attached_value(self):
        """git -C/tmp rm file — flag with attached value (no space).

        The regex expects -[A-Za-z]\\s+\\S+ (space between flag and value).
        -C/tmp has no space, so the flag+value pair is not consumed.
        """
        result = is_delete_command("git -C/tmp rm file")
        # -C/tmp is treated as a single token. The regex doesn't match -C/tmp
        # because it expects '-' + letter + whitespace + value.
        # So this falls through and 'rm\s+' is still found after 'git\s+'
        # Wait: the regex is git\s+(?:...)*rm\s+
        # 'git -C/tmp rm file' -> 'git' + ' ' + '-C/tmp rm file'
        # The flag pattern tries '-C' + ' ' + '/tmp' + ' ' but that consumes '-C'
        # then expects whitespace, gets '/', fails. So it doesn't consume -C/tmp.
        # Then it tries to match 'rm\s+' at position after 'git '. But the next
        # text is '-C/tmp rm file', and 'rm\s+' would need to match at a position.
        # Actually, (?:...)*  can match zero times, so it tries to match 'rm\s+'
        # right after 'git\s+'. But next char is '-', not 'r'. So no match.
        # Unless the regex engine backtracks...

        # Actually the * quantifier tries to match as many flag groups as possible.
        # If it fails to match -C/tmp as a flag group, it falls back to zero
        # matches, then tries rm\s+ immediately after git\s+, which is at '-C/tmp rm'.
        # '-' != 'r', so no match.
        #
        # This IS a bypass.

    def test_f8_git_many_flags_overflow(self):
        """git -C a -c b=c -C d -c e=f -C g rm file — many flag pairs."""
        cmd = "git " + "-C dir " * 50 + "rm file"
        start = time.time()
        result = is_delete_command(cmd)
        elapsed = time.time() - start
        self.assertTrue(result, "Many flags should still detect rm")
        self.assertLess(elapsed, 1.0, f"Flag overflow: {elapsed:.2f}s")

    def test_f8_chained_git_rm(self):
        """git status && git -C . rm file — chained commands."""
        subs = split_commands("git status && git -C . rm file")
        self.assertFalse(is_delete_command(subs[0]))  # git status
        self.assertTrue(is_delete_command(subs[1]))  # git -C . rm file

    def test_f8_git_rm_with_force_flag(self):
        """git rm -f file — rm with its own flags."""
        self.assertTrue(is_delete_command("git rm -f file"))

    def test_f8_git_rm_cached(self):
        """git rm --cached file — removes from index only."""
        self.assertTrue(is_delete_command("git rm --cached file"))

    def test_f8_mixed_short_long_flags(self):
        """git -C . --work-tree=/tmp rm file — mixed flag types."""
        self.assertTrue(is_delete_command("git -C . --work-tree=/tmp rm file"),
            "Mixed short and long flags should be caught")


# ============================================================
# F9: Schema Fix — Adversarial Tests
# ============================================================


class TestF9_Adversarial(unittest.TestCase):
    """F9: Verify schema cosmetic fix."""

    def test_f9_schema_default_is_ask(self):
        """exactMatchAction default should be 'ask', not 'deny'."""
        with open(str(_bootstrap._REPO_ROOT / "assets" / "guardian.schema.json")) as f:
            schema = json.load(f)

        exact_match = schema["properties"]["bashPathScan"]["properties"]["exactMatchAction"]
        self.assertEqual(exact_match["default"], "ask",
            "Schema default should be 'ask' (F9 fix)")

    def test_f9_config_matches_schema(self):
        """Config and schema defaults should be consistent."""
        with open(GUARDIAN_CONFIG_PATH) as f:
            config = json.load(f)
        with open(str(_bootstrap._REPO_ROOT / "assets" / "guardian.schema.json")) as f:
            schema = json.load(f)

        config_value = config["bashPathScan"]["exactMatchAction"]
        schema_default = schema["properties"]["bashPathScan"]["properties"]["exactMatchAction"]["default"]
        self.assertEqual(config_value, schema_default,
            "Config value and schema default should match")


# ============================================================
# F10: Boundary Regex — Adversarial Tests
# ============================================================


class TestF10_Adversarial(unittest.TestCase):
    """F10: Try to bypass boundary regex with missing delimiters."""

    def test_f10_colon_boundary_docker(self):
        """docker -v .env:/app — colon as boundary."""
        verdict, reason = scan_protected_paths("docker -v .env:/app", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow",
            "Colon boundary should detect .env in docker volume mount")

    def test_f10_colon_boundary_scp(self):
        """scp host:.env . — colon as boundary."""
        verdict, reason = scan_protected_paths("scp host:.env .", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow",
            "Colon boundary should detect .env in scp")

    def test_f10_bracket_boundary(self):
        """arr[.env] — bracket as boundary."""
        verdict, reason = scan_protected_paths("echo arr[.env]", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow",
            "Bracket boundary should detect .env")

    def test_f10_missing_at_sign_boundary(self):
        """user@.env — @ as boundary. Is @ in the character class?

        @ is NOT in the boundary regex. This could be a gap.
        """
        verdict, reason = scan_protected_paths("cat user@.env", SCAN_CONFIG)
        # @ is not a boundary character
        # The question is: does \b or another char in the boundary class help?
        # 'user@.env' — @ is a non-word char, so if boundary_before uses \\b
        # or raw string matching, it might still work.
        # Let's check: boundary_before = (?:^|[\s;|&<>("\`'=/,{\[:\]])
        # @ is NOT in this list. So '.env' in 'user@.env' won't match
        # because @ doesn't satisfy boundary_before.

    def test_f10_missing_hash_boundary(self):
        """comment#.env — # as boundary. Not in character class."""
        verdict, reason = scan_protected_paths("echo comment#.env", SCAN_CONFIG)
        # # is not in boundary chars

    def test_f10_missing_percent_boundary(self):
        """${var%.env} — % as boundary in parameter expansion."""
        verdict, reason = scan_protected_paths("echo ${var%.env}", SCAN_CONFIG)
        # % is not in boundary chars, but { is, so .env might still be caught
        # Wait: in ${var%.env}, the boundary before .env is %, not in the class

    def test_f10_missing_tilde_boundary(self):
        """~/.env — tilde as boundary."""
        verdict, reason = scan_protected_paths("cat ~/.env", SCAN_CONFIG)
        # / is in the boundary_before class (=/ are there), so this works
        # Actually: boundary_before has '=/,' — / is included via the = char?
        # Let me check: [\s;|&<>(\"`'=/,{\[:\]]
        # The = and / are separate chars in the class. / IS there.
        # So ~/.env has / before .env, which IS a boundary.
        self.assertNotEqual(verdict, "allow",
            "~/.env should be caught (/ is a boundary)")

    def test_f10_backtick_boundary(self):
        """`.env` — backtick as boundary."""
        verdict, reason = scan_protected_paths("echo `.env`", SCAN_CONFIG)
        # ` IS in the boundary class (it's in \"`')
        # Wait: the class has " and ` and ' — backtick IS included
        self.assertNotEqual(verdict, "allow",
            "Backtick boundary should detect .env")

    def test_f10_dollar_paren_boundary(self):
        """$(.env) — dollar-paren as boundary."""
        verdict, reason = scan_protected_paths("echo $(.env)", SCAN_CONFIG)
        # ( is in boundary_before, so this should match
        self.assertNotEqual(verdict, "allow",
            "Dollar-paren should detect .env")

    def test_f10_no_false_positive_envvar(self):
        """echo .envvar — .env as substring should NOT match."""
        verdict, reason = scan_protected_paths("echo .envvar", SCAN_CONFIG)
        # .envvar has no boundary after .env (v is a word char, not in boundary_after)
        self.assertEqual(verdict, "allow",
            ".envvar should not trigger — no boundary after .env")

    def test_f10_exclamation_boundary(self):
        """echo !.env — ! as boundary. Not in character class."""
        verdict, reason = scan_protected_paths("echo !.env", SCAN_CONFIG)
        # ! is NOT in boundary_before

    def test_f10_plus_boundary(self):
        """cat +.env — + as boundary. Not in character class."""
        verdict, reason = scan_protected_paths("cat +.env", SCAN_CONFIG)
        # + is NOT in boundary_before

    def test_f10_pem_with_colon(self):
        """docker -v server.pem:/cert — .pem with colon boundary."""
        verdict, reason = scan_protected_paths(
            "docker -v server.pem:/cert", SCAN_CONFIG
        )
        # .pem is a suffix pattern, uses boundary_after
        # : is now in boundary_after, so this should match
        self.assertNotEqual(verdict, "allow",
            "server.pem: should be caught with colon boundary")

    def test_f10_id_rsa_with_bracket(self):
        """echo keys[id_rsa] — id_rsa with bracket boundary."""
        verdict, reason = scan_protected_paths("echo keys[id_rsa]", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow",
            "Bracket boundary should detect id_rsa")

    def test_f10_multiple_protected_paths(self):
        """docker -v .env:/app -v id_rsa:/key — multiple paths."""
        verdict, reason = scan_protected_paths(
            "docker -v .env:/app -v id_rsa:/key", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow",
            "Multiple protected paths should be caught")


# ============================================================
# V1 Hotfix Tests — shutil.move and git long flags
# ============================================================


class TestV1Hotfix_ShutilMove(unittest.TestCase):
    """V1 Hotfix: shutil.move must be detected in is_delete_command."""

    def test_shutil_move_in_python(self):
        """python3 -c 'shutil.move(src, dst)' — should be delete."""
        self.assertTrue(is_delete_command("python3 -c 'shutil.move(src, dst)'"),
            "shutil.move must be detected")

    def test_shutil_move_in_python3(self):
        """python3 -c 'import shutil; shutil.move(a, b)'."""
        self.assertTrue(is_delete_command(
            "python3 -c 'import shutil; shutil.move(a, b)'"
        ))

    def test_shutil_move_in_code_source(self):
        """Verify shutil.move appears in is_delete_command source code."""
        with open(BASH_GUARDIAN_PATH) as f:
            source = f.read()
        # Find the is_delete_command function
        func_start = source.find("def is_delete_command")
        func_end = source.find("\ndef ", func_start + 1)
        func_body = source[func_start:func_end]
        self.assertIn("shutil\\.move", func_body,
            "shutil.move must be in is_delete_command patterns")

    def test_shutil_move_regex_pattern(self):
        """Verify the regex pattern matches shutil.move correctly."""
        pattern = r"(?:py|python[23]?|python\d[\d.]*)\s[^|&\n]*(?:os\.remove|os\.unlink|shutil\.rmtree|shutil\.move|os\.rmdir)"
        self.assertTrue(re.search(pattern, "python3 -c 'shutil.move(a, b)'"))


class TestV1Hotfix_GitLongFlags(unittest.TestCase):
    """V1 Hotfix: git rm with long flags (--work-tree, --git-dir)."""

    def test_git_work_tree_equals(self):
        """git --work-tree=dir rm file."""
        self.assertTrue(is_delete_command("git --work-tree=dir rm file"))

    def test_git_work_tree_space(self):
        """git --work-tree dir rm file."""
        self.assertTrue(is_delete_command("git --work-tree dir rm file"))

    def test_git_git_dir_equals(self):
        """git --git-dir=.git rm file."""
        self.assertTrue(is_delete_command("git --git-dir=.git rm file"))

    def test_git_git_dir_space(self):
        """git --git-dir .git rm file."""
        self.assertTrue(is_delete_command("git --git-dir .git rm file"))

    def test_git_combined_long_flags(self):
        """git --git-dir=X --work-tree=Y rm file — combined."""
        self.assertTrue(is_delete_command(
            "git --git-dir=X --work-tree=Y rm file"
        ))

    def test_git_mixed_short_long(self):
        """git -C . --work-tree=Y rm file — mixed."""
        self.assertTrue(is_delete_command(
            "git -C . --work-tree=Y rm file"
        ))

    def test_git_long_flag_no_value_bypass(self):
        """git --no-pager rm file — boolean long flag (no value).

        Known bypass: the regex treats 'rm' as the flag's value.
        Document this as a known limitation.
        """
        result = is_delete_command("git --no-pager rm file")
        # This is the known boolean flag bypass
        # --no-pager consumes 'rm' as its value


# ============================================================
# Cross-Fix Interaction Tests
# ============================================================


class TestCrossFix_Interactions(unittest.TestCase):
    """Test interactions between multiple fixes."""

    def test_f1_f3_interaction_clobber_bypass(self):
        """echo x >| protected — F3 + F1 + split_commands interaction.

        split_commands splits at |. Neither sub-command triggers write/delete.
        F1 can't trigger because is_write/is_delete are False.
        Layer 1 scan is the only defense.
        """
        subs = split_commands("echo x >| .env")
        # After split: ['echo x >', '.env']
        for sub in subs:
            # Neither should trigger write/delete detection strongly
            # 'echo x >' has the redirect pattern but target is missing
            pass

        # Layer 1 should still catch .env
        verdict, reason = scan_protected_paths("echo x >| .env", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow",
            "Layer 1 must catch .env even when >| is split by pipe")

    def test_f1_f8_interaction_git_long_flag_bypass(self):
        """git --no-pager rm CLAUDE.md — F8 boolean flag + F1.

        If is_delete_command misses this, F1 can't trigger either.
        The command passes through as a benign git operation.
        """
        cmd = "git --no-pager rm CLAUDE.md"
        is_del = is_delete_command(cmd)
        # If not detected as delete, F1 safety net doesn't apply
        # And no archive is created

    def test_f2_f1_ln_with_variable(self):
        """ln -sf $TARGET link — F2 detects write, F1 checks paths.

        F2 detects ln as write. extract_paths gets $TARGET which
        after expandvars stays as $TARGET (unset). F1 should trigger
        because write detected but paths unresolvable.
        """
        self.assertTrue(is_write_command("ln -sf $TARGET link"))

    def test_f7_f1_traversal_in_delete(self):
        """rm ../../../etc/passwd — F7 prevents traversal, F1 handles it.

        extract_paths resolves the path. F7's fix makes
        _is_within_project_or_would_be reject it. Then sub_paths is
        empty (path outside project), and F1 triggers "ask".
        """
        self.assertTrue(is_delete_command("rm ../../../etc/passwd"))
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = extract_paths("rm ../../../etc/passwd", Path(tmpdir),
                                  allow_nonexistent=True)
            # Path should be rejected as outside project
            self.assertEqual(len(paths), 0,
                "Traversal path outside project should not be returned")

    def test_f3_f6_clobber_process_sub(self):
        """>|(cmd) — clobber + process substitution combined."""
        with tempfile.TemporaryDirectory() as tmpdir:
            targets = extract_redirection_targets(">|(cmd)", Path(tmpdir))
            # (cmd) starts with (, should be filtered by F6
            for t in targets:
                self.assertFalse(str(t.name).startswith("("))

    def test_all_fixes_compound_command(self):
        """Complex compound command testing multiple fixes.

        git -C . rm file.txt && ln -sf /tmp/evil .env && python3 -c 'os.remove(f)' > output.txt
        """
        cmd = "git -C . rm file.txt && ln -sf /tmp/evil .env && python3 -c 'os.remove(f)' > output.txt"
        subs = split_commands(cmd)
        self.assertEqual(len(subs), 3)

        # Sub 1: git -C . rm file.txt — F8 should detect delete
        self.assertTrue(is_delete_command(subs[0]))

        # Sub 2: ln -sf /tmp/evil .env — F2 should detect write
        self.assertTrue(is_write_command(subs[1]))

        # Sub 3: python3 -c 'os.remove(f)' > output.txt — F4 should detect delete
        self.assertTrue(is_delete_command(subs[2]))

        # Layer 1 should catch .env
        verdict, _ = scan_protected_paths(cmd, SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow")


# ============================================================
# Encoding and Special Character Tests
# ============================================================


class TestEncodingTricks(unittest.TestCase):
    """Test encoding tricks and special characters."""

    def test_escaped_chars_in_command(self):
        """rm \\ .env — backslash-escaped space, different path."""
        # shlex.split handles this: rm and '.env' are separate tokens
        self.assertTrue(is_delete_command("rm \\ .env"))

    def test_quoted_command_names(self):
        """'rm' file.txt — command name in quotes.

        is_delete_command uses regex, so 'rm' with quotes would match
        if the pattern is at string start: (?:^|[;&|]\\s*)'rm'\\s+
        But the anchor is ^|[;&|], and the first char is ', not r.
        """
        result = is_delete_command("'rm' file.txt")
        # The regex (?:^|[;&|]\s*)rm\s+ won't match because first char is '
        # This is a potential bypass via quoting

    def test_double_quoted_command(self):
        """"rm" file.txt — double-quoted command name."""
        result = is_delete_command('"rm" file.txt')
        # Same issue as single-quoted

    def test_backslash_in_command_name(self):
        """r\\m file.txt — backslash in command name.

        Shell removes backslash: r\\m -> rm. But the guardian sees
        the raw string with backslash, so rm\\s+ doesn't match.
        """
        result = is_delete_command("r\\m file.txt")
        # rm pattern won't match r\m

    def test_unicode_rm_lookalike(self):
        """Using unicode characters that look like 'rm' but aren't.

        This is a theoretical attack — in practice, the shell would
        not recognize unicode-lookalike commands.
        """
        # U+0072 is 'r', U+006D is 'm' — these are the real chars
        # A unicode attack would use different codepoints that render similarly
        # Not practical for shell commands, but worth documenting

    def test_tab_as_whitespace_in_patterns(self):
        """rm\\tfile.txt — tab instead of space.

        \\s+ matches tabs, so this should be caught.
        """
        self.assertTrue(is_delete_command("rm\tfile.txt"))

    def test_vertical_tab_in_command(self):
        """rm\\vfile.txt — vertical tab. \\s includes \\v in Python regex."""
        result = is_delete_command("rm\vfile.txt")
        # \v is matched by \s in Python regex
        self.assertTrue(result, "Vertical tab should be matched by \\s")


# ============================================================
# Performance and Stress Tests
# ============================================================


class TestPerformanceStress(unittest.TestCase):
    """Stress tests for performance and DoS resistance."""

    def test_many_subcommands(self):
        """1000 subcommands joined by && — stress test split_commands."""
        cmd = " && ".join(["echo hello"] * 1000)
        start = time.time()
        subs = split_commands(cmd)
        elapsed = time.time() - start
        self.assertEqual(len(subs), 1000)
        self.assertLess(elapsed, 2.0, f"1000 subcommands: {elapsed:.2f}s")

    def test_deeply_nested_parens(self):
        """$(((((...))))) — deeply nested command substitutions."""
        cmd = "$(" * 100 + "echo hello" + ")" * 100
        start = time.time()
        subs = split_commands(cmd)
        elapsed = time.time() - start
        self.assertLess(elapsed, 2.0, f"Deep nesting: {elapsed:.2f}s")

    def test_very_long_single_command(self):
        """500K character single command — performance test."""
        cmd = "echo " + "x" * 500000
        start = time.time()
        result = is_write_command(cmd)
        elapsed = time.time() - start
        self.assertLess(elapsed, 5.0, f"500K command: {elapsed:.2f}s")

    def test_scan_protected_paths_long_command(self):
        """Layer 1 scan on 100K command — performance."""
        cmd = "cat " + "normal_file.txt " * 10000
        start = time.time()
        verdict, _ = scan_protected_paths(cmd, SCAN_CONFIG)
        elapsed = time.time() - start
        self.assertEqual(verdict, "allow")
        self.assertLess(elapsed, 5.0, f"Layer 1 scan 100K: {elapsed:.2f}s")

    def test_redos_f4_pattern1(self):
        """Pattern 1 with near-miss repetition — ReDoS resistance."""
        # [^|&\n]* followed by alternation
        cmd = "python3 " + "os.remov " * 50000
        start = time.time()
        result = is_delete_command(cmd)
        elapsed = time.time() - start
        self.assertFalse(result)  # No actual match
        self.assertLess(elapsed, 3.0, f"Pattern 1 near-miss: {elapsed:.2f}s")

    def test_redos_f8_many_flags(self):
        """F8 regex with many flag pairs — ReDoS resistance."""
        cmd = "git " + "-C dir " * 5000 + "rm file"
        start = time.time()
        result = is_delete_command(cmd)
        elapsed = time.time() - start
        self.assertTrue(result)
        self.assertLess(elapsed, 2.0, f"F8 many flags: {elapsed:.2f}s")

    def test_extract_paths_many_args(self):
        """extract_paths with 10K arguments — performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = "rm " + " ".join([f"file{i}.txt" for i in range(10000)])
            start = time.time()
            paths = extract_paths(cmd, Path(tmpdir), allow_nonexistent=True)
            elapsed = time.time() - start
            self.assertLess(elapsed, 5.0, f"10K paths: {elapsed:.2f}s")


# ============================================================
# split_commands Edge Cases
# ============================================================


class TestSplitCommands_Adversarial(unittest.TestCase):
    """Adversarial tests for split_commands."""

    def test_clobber_split(self):
        """>| splits as pipe — known limitation."""
        subs = split_commands("echo x >| file")
        self.assertGreater(len(subs), 1,
            "split_commands splits >| at pipe (known)")

    def test_process_sub_not_split(self):
        """>(cmd) should NOT be split — process substitution."""
        subs = split_commands("tee >(grep error) file.txt")
        # >( increases depth, so | inside shouldn't split
        # But > before ( is not $, <, or > at i-1...
        # Actually, the depth tracking checks command[i-1] in ('$', '<', '>')
        # For >(, command[i-1] is '>', so depth increases. Good.
        self.assertEqual(len(subs), 1,
            "Process substitution should not be split")

    def test_backtick_not_split(self):
        """Pipe inside backticks should not split."""
        subs = split_commands("echo `cmd | grep x`")
        self.assertEqual(len(subs), 1,
            "Pipe inside backticks should not cause split")

    def test_single_quote_pipe(self):
        """Pipe inside single quotes should not split."""
        subs = split_commands("echo 'a | b'")
        self.assertEqual(len(subs), 1)

    def test_double_quote_pipe(self):
        """Pipe inside double quotes should not split."""
        subs = split_commands('echo "a | b"')
        self.assertEqual(len(subs), 1)

    def test_escaped_pipe(self):
        """Escaped pipe \\| should not split."""
        subs = split_commands("echo a \\| b")
        self.assertEqual(len(subs), 1,
            "Escaped pipe should not cause split")

    def test_dollar_paren_pipe(self):
        """Pipe inside $() should not split."""
        subs = split_commands("echo $(cmd | grep x)")
        self.assertEqual(len(subs), 1)

    def test_ampersand_redirect(self):
        """&> should not split as background operator."""
        subs = split_commands("cmd &> output.txt")
        self.assertEqual(len(subs), 1,
            "&> redirect should not split")

    def test_fd_redirect(self):
        """2>&1 should not split."""
        subs = split_commands("cmd 2>&1")
        self.assertEqual(len(subs), 1,
            "2>&1 should not split")


if __name__ == "__main__":
    unittest.main()
