#!/usr/bin/env python3
"""Tests for Enhancement 1 (split allowedExternalPaths) and Enhancement 2
(bash external path extraction).

Enhancement 1 replaced the single ``allowedExternalPaths`` config key with:
  - ``allowedExternalReadPaths``  (Read only)
  - ``allowedExternalWritePaths`` (Read + Write + Edit)

``match_allowed_external_path()`` returns ``str | None``: one of
``"readwrite"``, ``"read"``, or ``None`` (no match).

Enhancement 2 updated ``extract_paths()`` in bash_guardian.py to include
allowed external paths in the extraction pipeline so they flow through
zeroAccess / readOnly / noDelete enforcement.

Run:
    python -m pytest tests/core/test_external_path_mode.py -v
    python3 tests/core/test_external_path_mode.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

import _guardian_utils as gu
from _guardian_utils import (
    _FALLBACK_CONFIG,
    load_guardian_config,
    match_allowed_external_path,
    match_path_pattern,
    match_zero_access,
    validate_guardian_config,
)
from bash_guardian import extract_paths, is_write_command, is_delete_command


def _make_project_dir(prefix="ext_test_"):
    """Create a temp project dir with .git/ and return (dir_path, config_path).

    Config is placed at .claude/guardian/config.json (the path that
    load_guardian_config() searches).
    """
    test_dir = tempfile.mkdtemp(prefix=prefix)
    (Path(test_dir) / ".git").mkdir(parents=True, exist_ok=True)
    config_dir = Path(test_dir) / ".claude" / "guardian"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    return test_dir, config_path


def _set_config(config_path, config):
    """Write config and clear the guardian module's config cache."""
    with open(config_path, "w") as f:
        json.dump(config, f)
    gu._config_cache = None
    gu._using_fallback_config = False
    gu._active_config_path = None


# ============================================================
# Group 1: match_allowed_external_path() -- Config Parsing
# ============================================================


class TestExternalPathConfigParsing(unittest.TestCase):
    """Test that match_allowed_external_path() correctly reads the split
    config keys and returns the right mode string or None."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir, cls.config_path = _make_project_dir("ext_mode_test_")
        cls.orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = cls.test_dir

    @classmethod
    def tearDownClass(cls):
        if cls.orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = cls.orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        # Clean cache for next test class
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    def setUp(self):
        # Clear cache before every test to avoid cross-test pollution
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    # ----------------------------------------------------------
    # Test 1: Read path matches with mode "read"
    # ----------------------------------------------------------
    def test_read_path_matches_read_mode(self):
        """Path in allowedExternalReadPaths returns 'read'."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/ext/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertEqual(result, "read")

    # ----------------------------------------------------------
    # Test 2: Write path matches with mode "readwrite"
    # ----------------------------------------------------------
    def test_write_path_matches_readwrite_mode(self):
        """Path in allowedExternalWritePaths returns 'readwrite'."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": ["/tmp/ext/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertEqual(result, "readwrite")

    # ----------------------------------------------------------
    # Test 3: Unmatched path returns None
    # ----------------------------------------------------------
    def test_unmatched_returns_none(self):
        """Path not in any list returns None."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/ext/**"],
            "allowedExternalWritePaths": ["/tmp/write/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/opt/other/file.txt")
        self.assertIsNone(result)

    # ----------------------------------------------------------
    # Test 4: Write path checked before read (write wins)
    # ----------------------------------------------------------
    def test_write_path_checked_before_read(self):
        """Path in BOTH lists returns 'readwrite' -- write wins."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/ext/**"],
            "allowedExternalWritePaths": ["/tmp/ext/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertEqual(result, "readwrite")

    # ----------------------------------------------------------
    # Test 5: Both lists empty
    # ----------------------------------------------------------
    def test_empty_lists(self):
        """Both lists empty => None for any path."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertIsNone(result)

    # ----------------------------------------------------------
    # Test 6: Only write list set, path matches => readwrite
    # ----------------------------------------------------------
    def test_only_write_list_matches_readwrite(self):
        """Only allowedExternalWritePaths set => 'readwrite'."""
        _set_config(self.config_path, {
            "allowedExternalWritePaths": ["/tmp/ext/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertEqual(result, "readwrite")

    # ----------------------------------------------------------
    # Test (extra): Non-string entries in lists are safely ignored
    # ----------------------------------------------------------
    def test_non_string_entries_ignored(self):
        """Non-string entries in path lists do not crash or match."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [42, None, {"path": "/tmp/ext/**"}, "/tmp/ext/**"],
            "allowedExternalWritePaths": [True, [], "/tmp/write/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        # The string entry should still match
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertEqual(result, "read")
        # Write list string should still match
        result = match_allowed_external_path("/tmp/write/data.json")
        self.assertEqual(result, "readwrite")


# ============================================================
# Group 2: Mode Enforcement in run_path_guardian_hook()
# ============================================================


class TestModeEnforcement(unittest.TestCase):
    """Test the mode-check logic used in run_path_guardian_hook().

    Since run_path_guardian_hook() calls sys.exit(), we test the mode
    enforcement logic directly -- the exact conditional from the source:
        if ext_mode == "read" and tool_name.lower() in ("write", "edit"):
            -> deny
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir, cls.config_path = _make_project_dir("ext_enforce_test_")
        cls.orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = cls.test_dir

    @classmethod
    def tearDownClass(cls):
        if cls.orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = cls.orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    def setUp(self):
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    @staticmethod
    def _would_deny(mode, tool_name):
        """Reproduce the exact mode-check conditional from run_path_guardian_hook()."""
        return mode == "read" and tool_name.lower() in ("write", "edit")

    # ----------------------------------------------------------
    # Test 7: Read tool on read-only external path => allowed
    # ----------------------------------------------------------
    def test_read_tool_on_read_path_allowed(self):
        """mode='read', tool='Read' => NOT denied (read is permitted)."""
        self.assertFalse(self._would_deny("read", "Read"))

    # ----------------------------------------------------------
    # Test 8: Write tool on read-only external path => denied
    # ----------------------------------------------------------
    def test_write_tool_on_read_path_denied(self):
        """mode='read', tool='Write' => DENIED."""
        self.assertTrue(self._would_deny("read", "Write"))

    # ----------------------------------------------------------
    # Test 9: Edit tool on read-only external path => denied
    # ----------------------------------------------------------
    def test_edit_tool_on_read_path_denied(self):
        """mode='read', tool='Edit' => DENIED."""
        self.assertTrue(self._would_deny("read", "Edit"))

    # ----------------------------------------------------------
    # Test 10: Write tool on readwrite external path => allowed
    # ----------------------------------------------------------
    def test_write_tool_on_write_path_allowed(self):
        """mode='readwrite', tool='Write' => NOT denied."""
        self.assertFalse(self._would_deny("readwrite", "Write"))

    # ----------------------------------------------------------
    # Test 11: Edit tool on readwrite external path => allowed
    # ----------------------------------------------------------
    def test_edit_tool_on_write_path_allowed(self):
        """mode='readwrite', tool='Edit' => NOT denied."""
        self.assertFalse(self._would_deny("readwrite", "Edit"))

    # ----------------------------------------------------------
    # Integration: match + mode check together
    # ----------------------------------------------------------
    def test_integration_read_path_blocks_write_tool(self):
        """End-to-end: path in read list + Write tool => would deny."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/readonly/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        ext_mode = match_allowed_external_path("/tmp/readonly/data.csv")
        self.assertIsNotNone(ext_mode)
        self.assertEqual(ext_mode, "read")
        self.assertTrue(self._would_deny(ext_mode, "Write"))
        self.assertTrue(self._would_deny(ext_mode, "Edit"))
        self.assertFalse(self._would_deny(ext_mode, "Read"))

    def test_integration_write_path_allows_all_tools(self):
        """End-to-end: path in write list + any tool => would NOT deny."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": ["/tmp/writable/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        ext_mode = match_allowed_external_path("/tmp/writable/data.csv")
        self.assertIsNotNone(ext_mode)
        self.assertEqual(ext_mode, "readwrite")
        self.assertFalse(self._would_deny(ext_mode, "Read"))
        self.assertFalse(self._would_deny(ext_mode, "Write"))
        self.assertFalse(self._would_deny(ext_mode, "Edit"))


# ============================================================
# Group 3: extract_paths() -- External Path Extraction
# ============================================================


class TestExtractPathsExternal(unittest.TestCase):
    """Test that extract_paths() includes allowed external paths and
    excludes non-allowed external paths."""

    @classmethod
    def setUpClass(cls):
        # Create a fake project directory
        cls.project_dir_str, cls.config_path = _make_project_dir("ext_extract_proj_")
        cls.project_dir = Path(cls.project_dir_str)

        # Create an external temp directory with real files
        cls.ext_dir = tempfile.mkdtemp(prefix="ext_extract_ext_")
        cls.ext_file = Path(cls.ext_dir) / "allowed_file.txt"
        cls.ext_file.write_text("test content")
        cls.ext_file2 = Path(cls.ext_dir) / "allowed_data.csv"
        cls.ext_file2.write_text("a,b,c")
        cls.non_allowed_dir = tempfile.mkdtemp(prefix="ext_noallow_")
        cls.non_allowed_file = Path(cls.non_allowed_dir) / "secret.txt"
        cls.non_allowed_file.write_text("secret")

        # Create a project-internal file
        cls.internal_file = cls.project_dir / "internal.txt"
        cls.internal_file.write_text("project file")

        cls.orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = cls.project_dir_str

    @classmethod
    def tearDownClass(cls):
        if cls.orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = cls.orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        shutil.rmtree(cls.project_dir_str, ignore_errors=True)
        shutil.rmtree(cls.ext_dir, ignore_errors=True)
        shutil.rmtree(cls.non_allowed_dir, ignore_errors=True)
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    def setUp(self):
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    # ----------------------------------------------------------
    # Test 12: External allowed read path is extracted
    # ----------------------------------------------------------
    def test_extract_includes_allowed_external_read_path(self):
        """Allowed external read path is included in extract_paths() output."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [self.ext_dir + "/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        paths = extract_paths(f"cat {self.ext_file}", self.project_dir)
        path_strs = [str(p) for p in paths]
        self.assertIn(
            str(self.ext_file),
            path_strs,
            f"Expected {self.ext_file} in extracted paths, got {path_strs}",
        )

    # ----------------------------------------------------------
    # Test 13: Non-allowed external path is NOT extracted
    # ----------------------------------------------------------
    def test_extract_excludes_non_allowed_external(self):
        """External path NOT in config is not extracted."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [self.ext_dir + "/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        paths = extract_paths(f"cat {self.non_allowed_file}", self.project_dir)
        path_strs = [str(p) for p in paths]
        self.assertNotIn(
            str(self.non_allowed_file),
            path_strs,
            f"Non-allowed path {self.non_allowed_file} should NOT be extracted",
        )

    # ----------------------------------------------------------
    # Test 14: Project-internal paths still extracted normally
    # ----------------------------------------------------------
    def test_extract_still_includes_project_paths(self):
        """Project-internal paths are extracted regardless of external config."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        paths = extract_paths(f"cat {self.internal_file}", self.project_dir)
        path_strs = [str(p) for p in paths]
        self.assertIn(
            str(self.internal_file),
            path_strs,
            f"Project-internal path should always be extracted, got {path_strs}",
        )

    # ----------------------------------------------------------
    # Test 15: Path in allowedExternalWritePaths also extracted
    # ----------------------------------------------------------
    def test_extract_external_with_write_paths(self):
        """Path in allowedExternalWritePaths is also extracted."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": [self.ext_dir + "/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        paths = extract_paths(f"cat {self.ext_file}", self.project_dir)
        path_strs = [str(p) for p in paths]
        self.assertIn(
            str(self.ext_file),
            path_strs,
            f"Write-allowed external path should be extracted, got {path_strs}",
        )

    # ----------------------------------------------------------
    # Extra: Both project-internal and external in same command
    # ----------------------------------------------------------
    def test_extract_mixed_internal_and_external(self):
        """Command with both internal and external paths extracts both."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [self.ext_dir + "/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        cmd = f"diff {self.internal_file} {self.ext_file}"
        paths = extract_paths(cmd, self.project_dir)
        path_strs = [str(p) for p in paths]
        self.assertIn(str(self.internal_file), path_strs)
        self.assertIn(str(self.ext_file), path_strs)


# ============================================================
# Group 4: Security -- zeroAccess on External Paths
# ============================================================


class TestZeroAccessOnExternalPaths(unittest.TestCase):
    """Verify that zeroAccessPaths still blocks access to sensitive files
    even when those files are within an allowed external path."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir, cls.config_path = _make_project_dir("ext_zero_test_")
        cls.orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = cls.test_dir

    @classmethod
    def tearDownClass(cls):
        if cls.orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = cls.orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    def setUp(self):
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    # ----------------------------------------------------------
    # Test 16: .env in external path matched by zeroAccess
    # ----------------------------------------------------------
    def test_external_env_file_matched_by_zero_access(self):
        """Path like /tmp/ext/.env matches allowedExternalReadPaths AND
        zeroAccessPaths. zeroAccess wins in check order."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/ext/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [".env", ".env.*"],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path = "/tmp/ext/.env"
        # Path matches allowed external
        ext_mode = match_allowed_external_path(path)
        self.assertEqual(ext_mode, "read", "Path should match allowedExternalReadPaths")
        # But also matches zeroAccess
        self.assertTrue(
            match_zero_access(path),
            ".env should be caught by zeroAccessPaths even in allowed external dir",
        )

    # ----------------------------------------------------------
    # Test 17: *.key in external path matched by zeroAccess
    # ----------------------------------------------------------
    def test_external_key_file_matched_by_zero_access(self):
        """Path like /tmp/ext/secret.key matches allowedExternalWritePaths
        AND zeroAccessPaths. zeroAccess wins."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": ["/tmp/ext/**"],
            "zeroAccessPaths": ["*.key"],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path = "/tmp/ext/secret.key"
        ext_mode = match_allowed_external_path(path)
        self.assertEqual(ext_mode, "readwrite", "Path should match allowedExternalWritePaths")
        self.assertTrue(
            match_zero_access(path),
            "*.key should be caught by zeroAccessPaths even in allowed external dir",
        )

    # ----------------------------------------------------------
    # Extra: *.pem in external path
    # ----------------------------------------------------------
    def test_external_pem_file_matched_by_zero_access(self):
        """PEM file in allowed external dir still blocked by zeroAccess."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/ext/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": ["*.pem"],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path = "/tmp/ext/server.pem"
        ext_mode = match_allowed_external_path(path)
        self.assertEqual(ext_mode, "read")
        self.assertTrue(match_zero_access(path))


# ============================================================
# Group 5: Backward Compatibility
# ============================================================


class TestBackwardCompatibility(unittest.TestCase):
    """Verify that the old allowedExternalPaths key is truly removed
    and the fallback config uses the new split keys."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir, cls.config_path = _make_project_dir("ext_compat_test_")
        cls.orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = cls.test_dir

    @classmethod
    def tearDownClass(cls):
        if cls.orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = cls.orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    def setUp(self):
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    # ----------------------------------------------------------
    # Test 18: Old allowedExternalPaths key is ignored
    # ----------------------------------------------------------
    def test_old_allowedExternalPaths_key_ignored(self):
        """Config with old 'allowedExternalPaths' key (no new keys) --
        path is NOT matched, because the new code only reads the new keys."""
        _set_config(self.config_path, {
            "allowedExternalPaths": ["/tmp/ext/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        result = match_allowed_external_path("/tmp/ext/file.txt")
        self.assertIsNone(
            result,
            "Old 'allowedExternalPaths' key should be ignored by new code",
        )

    # ----------------------------------------------------------
    # Test 19: Fallback config has new keys
    # ----------------------------------------------------------
    def test_fallback_config_has_new_keys(self):
        """_FALLBACK_CONFIG has allowedExternalReadPaths and
        allowedExternalWritePaths (both empty lists)."""
        self.assertIn(
            "allowedExternalReadPaths",
            _FALLBACK_CONFIG,
            "Fallback config must have allowedExternalReadPaths",
        )
        self.assertIn(
            "allowedExternalWritePaths",
            _FALLBACK_CONFIG,
            "Fallback config must have allowedExternalWritePaths",
        )
        self.assertEqual(
            _FALLBACK_CONFIG["allowedExternalReadPaths"],
            [],
            "Fallback allowedExternalReadPaths must be empty (fail-closed)",
        )
        self.assertEqual(
            _FALLBACK_CONFIG["allowedExternalWritePaths"],
            [],
            "Fallback allowedExternalWritePaths must be empty (fail-closed)",
        )

    # ----------------------------------------------------------
    # Test 19b: Fallback config does NOT have old key
    # ----------------------------------------------------------
    def test_fallback_config_no_old_key(self):
        """_FALLBACK_CONFIG should NOT contain the old 'allowedExternalPaths' key."""
        self.assertNotIn(
            "allowedExternalPaths",
            _FALLBACK_CONFIG,
            "Old 'allowedExternalPaths' key must be removed from fallback config",
        )

    # ----------------------------------------------------------
    # Extra: Old key + new keys -- new keys take effect
    # ----------------------------------------------------------
    def test_old_and_new_keys_coexist_new_wins(self):
        """If both old and new keys exist, only new keys are read."""
        _set_config(self.config_path, {
            "allowedExternalPaths": ["/tmp/old/**"],
            "allowedExternalReadPaths": ["/tmp/new-read/**"],
            "allowedExternalWritePaths": ["/tmp/new-write/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        # Old key path: not matched
        result_old = match_allowed_external_path("/tmp/old/file.txt")
        self.assertIsNone(result_old)
        # New read key path: matched
        result_read = match_allowed_external_path("/tmp/new-read/file.txt")
        self.assertEqual(result_read, "read")
        # New write key path: matched
        result_write = match_allowed_external_path("/tmp/new-write/file.txt")
        self.assertEqual(result_write, "readwrite")


# ============================================================
# Group 5b: Deprecation Warning for old allowedExternalPaths
# ============================================================


class TestDeprecationWarning(unittest.TestCase):
    """Test that validate_guardian_config() emits a deprecation warning
    when the old 'allowedExternalPaths' key is present in config."""

    def test_deprecated_key_triggers_warning(self):
        """Config with old 'allowedExternalPaths' key produces deprecation message."""
        config = {
            "allowedExternalPaths": ["/tmp/old/**"],
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        }
        errors = validate_guardian_config(config)
        deprecated_msgs = [e for e in errors if "DEPRECATED" in e and "allowedExternalPaths" in e]
        self.assertTrue(
            len(deprecated_msgs) > 0,
            f"Expected deprecation warning for 'allowedExternalPaths', got: {errors}",
        )

    def test_no_deprecated_key_no_warning(self):
        """Config without old key produces no deprecation message."""
        config = {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        }
        errors = validate_guardian_config(config)
        deprecated_msgs = [e for e in errors if "DEPRECATED" in e]
        self.assertEqual(
            len(deprecated_msgs),
            0,
            f"No deprecation warning expected, got: {deprecated_msgs}",
        )

    def test_deprecation_message_suggests_migration(self):
        """Deprecation message suggests the correct new key names."""
        config = {
            "allowedExternalPaths": ["/tmp/**"],
            "zeroAccessPaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        }
        errors = validate_guardian_config(config)
        deprecated_msgs = [e for e in errors if "DEPRECATED" in e]
        self.assertTrue(len(deprecated_msgs) > 0)
        msg = deprecated_msgs[0]
        self.assertIn("allowedExternalReadPaths", msg)
        self.assertIn("allowedExternalWritePaths", msg)


# ============================================================
# Group 6: Bash Guardian -- External Read-Only Enforcement
# ============================================================


class TestBashExternalReadOnlyEnforcement(unittest.TestCase):
    """Test that the bash guardian enforcement loop blocks write/delete
    commands on paths that are in allowedExternalReadPaths (mode='read').

    This addresses the CRITICAL security issue where extract_paths()
    included external paths but the enforcement loop did not re-check
    the external path mode, allowing writes to read-only external paths.
    """

    @classmethod
    def setUpClass(cls):
        cls.test_dir, cls.config_path = _make_project_dir("ext_bash_enforce_")
        cls.orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = cls.test_dir

    @classmethod
    def tearDownClass(cls):
        if cls.orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = cls.orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    def setUp(self):
        gu._config_cache = None
        gu._using_fallback_config = False
        gu._active_config_path = None

    # ----------------------------------------------------------
    # Test 27: is_write_command detects sed -i as a write
    # ----------------------------------------------------------
    def test_sed_inplace_is_write(self):
        """is_write_command('sed -i ...') should return True."""
        self.assertTrue(
            is_write_command("sed -i 's/old/new/g' /tmp/readonly/file.py"),
            "sed -i should be detected as a write command",
        )

    # ----------------------------------------------------------
    # Test 28: is_write_command detects cp as a write
    # ----------------------------------------------------------
    def test_cp_is_write(self):
        """is_write_command('cp ...') should return True."""
        self.assertTrue(
            is_write_command("cp /src/file.txt /tmp/readonly/file.txt"),
            "cp should be detected as a write command",
        )

    # ----------------------------------------------------------
    # Test 29: is_write_command detects tee as a write
    # ----------------------------------------------------------
    def test_tee_is_write(self):
        """is_write_command('tee ...') should return True."""
        self.assertTrue(
            is_write_command("echo hello | tee /tmp/readonly/output.txt"),
            "tee should be detected as a write command",
        )

    # ----------------------------------------------------------
    # Test 30: is_write_command detects redirection as a write
    # ----------------------------------------------------------
    def test_redirect_is_write(self):
        """is_write_command('echo ... > file') should return True."""
        self.assertTrue(
            is_write_command("echo malicious > /tmp/readonly/target.txt"),
            "Redirection (>) should be detected as a write command",
        )

    # ----------------------------------------------------------
    # Test 31: cat is NOT a write command
    # ----------------------------------------------------------
    def test_cat_is_not_write(self):
        """is_write_command('cat ...') should return False."""
        self.assertFalse(
            is_write_command("cat /tmp/readonly/file.txt"),
            "cat (without redirection) should not be a write command",
        )

    # ----------------------------------------------------------
    # Test 32: is_delete_command detects rm
    # ----------------------------------------------------------
    def test_rm_is_delete(self):
        """is_delete_command('rm ...') should return True."""
        self.assertTrue(
            is_delete_command("rm /tmp/readonly/file.txt"),
            "rm should be detected as a delete command",
        )

    # ----------------------------------------------------------
    # Test 33: External read-only path blocks write in bash enforcement
    # ----------------------------------------------------------
    def test_bash_enforcement_denies_write_to_read_only_external(self):
        """For a path in allowedExternalReadPaths, when is_write is True
        and match_allowed_external_path returns mode='read', the verdict
        should be deny.

        This simulates the logic in bash_guardian.py enforcement loop:
            if is_write or is_delete:
                ext_mode = match_allowed_external_path(path_str)
                if ext_mode == "read":
                    -> deny
        """
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/readonly/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path_str = "/tmp/readonly/important.py"
        is_write = is_write_command("sed -i 's/old/new/g' /tmp/readonly/important.py")

        # Verify preconditions
        self.assertTrue(is_write, "sed -i should be a write command")

        ext_mode = match_allowed_external_path(path_str)
        self.assertIsNotNone(ext_mode, "Path should match allowedExternalReadPaths")
        self.assertEqual(ext_mode, "read", "Mode should be 'read'")

        # The enforcement logic: write + read-only external => deny
        should_deny = (is_write) and ext_mode == "read"
        self.assertTrue(
            should_deny,
            "Write command targeting read-only external path should be denied",
        )

    # ----------------------------------------------------------
    # Test 34: External read-only path blocks delete in bash enforcement
    # ----------------------------------------------------------
    def test_bash_enforcement_denies_delete_to_read_only_external(self):
        """Delete command on read-only external path should also be denied."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/readonly/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path_str = "/tmp/readonly/important.py"
        is_delete = is_delete_command("rm /tmp/readonly/important.py")

        self.assertTrue(is_delete, "rm should be a delete command")

        ext_mode = match_allowed_external_path(path_str)
        self.assertIsNotNone(ext_mode)
        self.assertEqual(ext_mode, "read")

        should_deny = is_delete and ext_mode == "read"
        self.assertTrue(
            should_deny,
            "Delete command targeting read-only external path should be denied",
        )

    # ----------------------------------------------------------
    # Test 35: External readwrite path allows write in bash enforcement
    # ----------------------------------------------------------
    def test_bash_enforcement_allows_write_to_readwrite_external(self):
        """Path in allowedExternalWritePaths with mode='readwrite' should
        NOT be denied for writes."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": [],
            "allowedExternalWritePaths": ["/tmp/writable/**"],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path_str = "/tmp/writable/data.csv"
        is_write = is_write_command("sed -i 's/old/new/g' /tmp/writable/data.csv")

        ext_mode = match_allowed_external_path(path_str)
        self.assertIsNotNone(ext_mode)
        self.assertEqual(ext_mode, "readwrite")

        # The enforcement logic: write + readwrite external => NOT denied
        should_deny = (is_write) and ext_mode == "read"
        self.assertFalse(
            should_deny,
            "Write command to readwrite external path should NOT be denied",
        )

    # ----------------------------------------------------------
    # Test 36: Non-external path does not trigger external check
    # ----------------------------------------------------------
    def test_bash_enforcement_non_external_not_affected(self):
        """Path not in any external list should not match, so the
        external read-only check does not apply."""
        _set_config(self.config_path, {
            "allowedExternalReadPaths": ["/tmp/readonly/**"],
            "allowedExternalWritePaths": [],
            "zeroAccessPaths": [],
            "readOnlyPaths": [],
            "noDeletePaths": [],
            "bashToolPatterns": {"block": [], "ask": []},
        })
        path_str = "/opt/unrelated/file.txt"

        ext_mode = match_allowed_external_path(path_str)
        self.assertIsNone(ext_mode)

        # Since ext_mode is None, the check would not fire
        should_deny = ext_mode == "read"
        self.assertFalse(should_deny)


# ============================================================
# Entry point for direct execution
# ============================================================

if __name__ == "__main__":
    unittest.main()
