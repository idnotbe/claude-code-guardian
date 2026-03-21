"""Phase 2 tests: Interpreter payload path resolution (F1 enrichment).

Tests verify that:
1. extract_paths_from_interpreter_payload() correctly extracts paths from
   interpreter -c/-e payload string literals
2. F2-1: Project boundary check uses Path.relative_to() (not str.startswith)
3. F2-2: Interpolation markers ({}, $) cause literal rejection
4. URLs and MIME types are filtered out
5. Glob patterns are expanded within project boundary
6. F1 block routes interpreter paths through normal validation or fires
   enriched ASK with API name
7. Non-interpreter commands retain standard F1 ASK behavior
"""
import os
import tempfile
import unittest
import sys
from pathlib import Path

# Bootstrap imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401

from bash_guardian import (
    extract_paths_from_interpreter_payload,
    is_within_project,
)


class TestExtractPathsBasic(unittest.TestCase):
    """Basic path extraction from interpreter payloads."""

    def setUp(self):
        """Create a temp directory to act as project_dir."""
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_python_remove_single_file(self):
        """python3 -c with os.remove and a relative path extracts the path."""
        # Create the target directory so the path resolves within project
        staging = self.project_dir / ".staging"
        staging.mkdir()
        (staging / "file.json").touch()

        cmd = 'python3 -c "os.remove(\'.staging/file.json\')"'
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.project_dir / ".staging" / "file.json")

    def test_node_unlink_single_file(self):
        """node -e with fs.unlinkSync and a relative path extracts the path."""
        temp_dir = self.project_dir / "temp"
        temp_dir.mkdir()
        (temp_dir / "cache.txt").touch()

        cmd = 'node -e "fs.unlinkSync(\'./temp/cache.txt\')"'
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.project_dir / "temp" / "cache.txt")

    def test_double_quoted_path(self):
        """Double-quoted path within single-quoted payload is extracted."""
        staging = self.project_dir / "data"
        staging.mkdir()
        (staging / "out.txt").touch()

        cmd = """python3 -c 'os.remove("data/out.txt")'"""
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.project_dir / "data" / "out.txt")

    def test_variable_only_path(self):
        """Path stored in variable only (no string literal) returns empty."""
        cmd = 'python3 -c "os.remove(path_var)"'
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_chr_obfuscated(self):
        """chr() obfuscated path returns empty (fail-closed)."""
        cmd = """python3 -c "os.remove(chr(46)+'env')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_non_interpreter_command(self):
        """Non-interpreter command (rm) returns empty."""
        cmd = "rm -f file.txt"
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_no_payload(self):
        """Interpreter without -c/-e flag returns empty."""
        cmd = "python3 script.py"
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])


class TestFilteringRules(unittest.TestCase):
    """URL, MIME type, and interpolation filtering."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_url_filtered(self):
        """URLs (containing ://) are filtered out."""
        cmd = """python3 -c "requests.get('https://example.com/api/data')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_mime_type_filtered(self):
        """MIME types (single slash, not path-like) are filtered out."""
        cmd = """python3 -c "headers={'Content-Type': 'application/json'}" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_fstring_interpolation_rejected(self):
        """F2-2: Literals containing {} are rejected (unresolvable f-strings)."""
        cmd = """python3 -c "os.remove(f'.claude/{var}')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_dollar_interpolation_rejected(self):
        """F2-2: Literals containing $ are rejected (shell variable interpolation)."""
        cmd = """python3 -c "os.remove('$HOME/.env')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_curly_brace_in_path_rejected(self):
        """F2-2: Even standalone curly braces in path literal are rejected."""
        (self.project_dir / "data").mkdir()
        cmd = """python3 -c "os.remove('./data/{}.json')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])


class TestProjectBoundary(unittest.TestCase):
    """F2-1: Project boundary enforcement via Path.relative_to()."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_path_outside_project(self):
        """Absolute path outside project returns empty."""
        cmd = """python3 -c "os.remove('/etc/passwd')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_traversal_attack(self):
        """Relative path that resolves outside project returns empty."""
        cmd = """python3 -c "os.remove('../../etc/passwd')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_project_prefix_confusion(self):
        """F2-1: /tmp/proj vs /tmp/proj_evil — relative_to prevents confusion.

        If project_dir is /tmp/proj, a path in /tmp/proj_evil must NOT
        be considered within project. str.startswith would fail this.
        """
        # Create a sibling directory with a longer name
        evil_dir = Path(str(self.project_dir) + "_evil")
        evil_dir.mkdir(exist_ok=True)
        try:
            evil_file = evil_dir / "secret.txt"
            evil_file.touch()

            # The path is NOT within project_dir despite sharing a prefix
            self.assertFalse(is_within_project(evil_file, self.project_dir))

            # Construct command referencing the evil path
            cmd = f"""python3 -c "os.remove('{evil_file}')" """
            result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
            self.assertEqual(result, [])
        finally:
            import shutil
            shutil.rmtree(evil_dir, ignore_errors=True)

    def test_path_within_project_accepted(self):
        """Path clearly inside project is accepted."""
        subdir = self.project_dir / "src"
        subdir.mkdir()
        target = subdir / "temp.py"
        target.touch()

        cmd = f"""python3 -c "os.remove('{target}')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].resolve(), target.resolve())


class TestGlobExpansion(unittest.TestCase):
    """Glob pattern expansion within project boundary."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_glob_expansion_with_files(self):
        """Glob pattern expands to actual files within project."""
        staging = self.project_dir / ".staging"
        staging.mkdir()
        (staging / "a.json").touch()
        (staging / "b.json").touch()
        (staging / "c.txt").touch()

        cmd = """python3 -c "for f in glob.glob('.staging/*.json'): os.remove(f)" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        # Should find the 2 json files
        self.assertEqual(len(result), 2)
        names = sorted(p.name for p in result)
        self.assertEqual(names, ["a.json", "b.json"])

    def test_glob_no_matches(self):
        """Glob pattern with no matches returns empty."""
        cmd = """python3 -c "for f in glob.glob('.nonexistent/*.json'): os.remove(f)" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])


class TestF1Integration(unittest.TestCase):
    """F1 block integration: enriched messages and path routing.

    These tests verify the F1 block behavior by testing the components
    that the F1 block uses, since main() requires full environment setup.
    """

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_f1_enriched_message_contains_api_name(self):
        """When interpreter path resolution fails, detail string has API name."""
        from _guardian_utils import check_interpreter_payload

        cmd = 'python3 -c "os.remove(some_var)"'
        is_interp, interp_detail = check_interpreter_payload(cmd)
        self.assertTrue(is_interp)

        # Extract API name the way F1 block does
        api_name = (
            interp_detail.rsplit(": ", 1)[-1]
            if ": " in interp_detail
            else ""
        )
        self.assertEqual(api_name, "os.remove")

        # Verify path extraction returns empty (variable, no string literal)
        paths = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(paths, [])

        # The F1 message would be: "Detected delete via os.remove but could not resolve target paths"
        op_type = "delete"
        api_info = f" via {api_name}" if api_name else ""
        msg = f"Detected {op_type}{api_info} but could not resolve target paths"
        self.assertIn("os.remove", msg)
        self.assertIn("delete", msg)

    def test_f1_paths_resolved_skips_ask(self):
        """When interpreter paths are resolved, they are returned (no F1 ASK).

        The F1 block will use these paths for normal validation instead of
        generating an ASK verdict.
        """
        subdir = self.project_dir / ".staging"
        subdir.mkdir()
        target = subdir / "file.json"
        target.touch()

        cmd = 'python3 -c "os.remove(\'.staging/file.json\')"'

        from _guardian_utils import check_interpreter_payload
        is_interp, _ = check_interpreter_payload(cmd)
        self.assertTrue(is_interp)

        paths = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        # Paths resolved -> F1 block would NOT fire ASK
        self.assertTrue(len(paths) > 0)
        self.assertEqual(paths[0], self.project_dir / ".staging" / "file.json")

    def test_f1_non_interpreter_unchanged(self):
        """Non-interpreter commands: check_interpreter_payload returns False.

        F1 block falls through to standard ASK (unchanged behavior).
        """
        from _guardian_utils import check_interpreter_payload

        cmd = "some_custom_tool --delete-all"
        is_interp, interp_detail = check_interpreter_payload(cmd)
        self.assertFalse(is_interp)
        self.assertEqual(interp_detail, "")

    def test_f1_node_unlink_enriched(self):
        """Node fs.unlink: enriched F1 message includes API name."""
        from _guardian_utils import check_interpreter_payload

        cmd = 'node -e "fs.unlinkSync(dynamic_path)"'
        is_interp, interp_detail = check_interpreter_payload(cmd)
        self.assertTrue(is_interp)

        api_name = (
            interp_detail.rsplit(": ", 1)[-1]
            if ": " in interp_detail
            else ""
        )
        # The pattern matches "fs.unlink" (the shorter pattern fires first)
        self.assertIn("fs.unlink", api_name)

        # No string literal path -> empty
        paths = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(paths, [])


class TestV1Fixes(unittest.TestCase):
    """V1 verification fixes: decoy literal, % interpolation, JS escape, MIME."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_dot_literal_rejected(self):
        """V1 fix: '.' literal resolving to project root is rejected as decoy."""
        cmd = """python3 -c "os.remove('.' + 'env')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        # '.' should be filtered out (trivial decoy), 'env' has no / or .
        self.assertEqual(result, [])

    def test_dot_slash_literal_rejected(self):
        """V1 fix: './' literal resolving to project root is rejected."""
        cmd = """python3 -c "os.remove('./' + secret)" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_percent_format_string_rejected(self):
        """V1 fix: F2-2 rejects % interpolation (C-style format strings)."""
        cmd = """python3 -c "os.remove('%s/passwd' % base_dir)" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_js_escape_backslash_rejected(self):
        """V1 fix: Backslash in double-quoted literal rejected (JS escape)."""
        cmd = r"""node -e "fs.unlinkSync('.claude\/settings.json')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_backslash_in_any_quote_rejected(self):
        """V1 fix: Backslash in ANY quoted literal is rejected.

        Because extract_interpreter_payload() strips outer shell quotes,
        the inner literal's quote type doesn't determine escape semantics
        (JS/Perl/Ruby single-quotes DO support escapes unlike Python).
        """
        cmd = """python3 -c "os.remove('dir\\\\name/file.txt')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_mime_type_still_filtered(self):
        """MIME types with known prefixes are still filtered."""
        cmd = """python3 -c "headers={'Accept': 'text/html'}" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_extensionless_path_no_longer_filtered(self):
        """V1 fix: Extensionless paths like 'src/utils' NOT filtered as MIME."""
        subdir = self.project_dir / "src"
        subdir.mkdir()
        target = subdir / "utils"
        target.touch()

        cmd = """python3 -c "os.remove('src/utils')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        # 'src/utils' is NOT a known MIME prefix → should be extracted
        self.assertEqual(len(result), 1)

    def test_decoy_with_chr_obfuscation(self):
        """Decoy literal + chr() obfuscation: decoy path extracts but chr() doesn't.

        Known accepted limitation per threat model: the decoy path will be
        validated through normal pipeline, but the chr()-constructed target
        is invisible to static extraction. This is accepted because AI agents
        generate straightforward code, not chr()-obfuscated payloads.
        """
        staging = self.project_dir / "src"
        staging.mkdir()
        (staging / "main.py").touch()

        cmd = 'python3 -c "os.remove(\'./src/main.py\'); os.remove(chr(46)+\'env\')"'
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        # Only the literal path is extracted; chr() is invisible
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "main.py")

    def test_multiple_paths_both_extracted(self):
        """Multiple valid path literals are all extracted."""
        dir_a = self.project_dir / "a"
        dir_a.mkdir()
        (dir_a / "1.txt").touch()
        dir_b = self.project_dir / "b"
        dir_b.mkdir()
        (dir_b / "2.txt").touch()

        cmd = """python3 -c "os.remove('./a/1.txt'); os.remove('./b/2.txt')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(len(result), 2)
        names = sorted(p.name for p in result)
        self.assertEqual(names, ["1.txt", "2.txt"])


class TestV2Fixes(unittest.TestCase):
    """V2 verification fixes: mixed paths fail-closed, ./ variants."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_dot_slash_dot_rejected(self):
        """V2 fix: './' resolves to project root, rejected."""
        cmd = """python3 -c "os.remove('./.') " """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_dot_slash_dot_slash_rejected(self):
        """V2 fix: '././' resolves to project root, rejected."""
        cmd = """python3 -c "os.remove('././') " """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_mixed_paths_fail_closed(self):
        """V2 fix: Out-of-project path alongside in-project → return empty.

        If payload contains both /etc/passwd (outside project) and a valid
        in-project path, the function should return empty to trigger F1 ASK.
        """
        subdir = self.project_dir / "src"
        subdir.mkdir()
        (subdir / "valid.txt").touch()

        cmd = """python3 -c "os.remove('/etc/passwd'); os.remove('./src/valid.txt')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        # V2: returns [] because /etc/passwd is out-of-project → fail-closed
        self.assertEqual(result, [])

    def test_traversal_mixed_fail_closed(self):
        """V2 fix: Traversal path alongside valid path → return empty."""
        subdir = self.project_dir / "data"
        subdir.mkdir()
        (subdir / "file.txt").touch()

        cmd = """python3 -c "os.remove('../../etc/passwd'); os.remove('./data/file.txt')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])

    def test_all_in_project_still_works(self):
        """V2 fix does NOT break all-in-project case."""
        dir_a = self.project_dir / "a"
        dir_a.mkdir()
        (dir_a / "1.txt").touch()
        dir_b = self.project_dir / "b"
        dir_b.mkdir()
        (dir_b / "2.txt").touch()

        cmd = """python3 -c "os.remove('./a/1.txt'); os.remove('./b/2.txt')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(len(result), 2)

    def test_single_out_of_project_returns_empty(self):
        """Single out-of-project path (no in-project paths) returns empty."""
        cmd = """python3 -c "os.remove('/etc/shadow')" """
        result = extract_paths_from_interpreter_payload(cmd, self.project_dir)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
