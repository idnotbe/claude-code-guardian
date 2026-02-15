#!/usr/bin/env python3
"""Regression tests for allowedExternalReadPaths / allowedExternalWritePaths.

Originally tested the old allowedExternalPaths mechanism. Updated to use the
split keys (allowedExternalReadPaths, allowedExternalWritePaths) introduced
in Enhancement 1.

Tests the external path allowlist feature that lets users grant read-only
or read-write access to paths outside the project directory (e.g.
~/.claude/projects/*/memory/**) while maintaining all other security checks.

Run with:
    python3 tests/regression/test_allowed_external.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Bootstrap: add hooks/scripts to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

GUARDIAN_DIR = str(_bootstrap._REPO_ROOT / "hooks" / "scripts")
if GUARDIAN_DIR not in sys.path:
    sys.path.insert(0, GUARDIAN_DIR)


class TestResults:
    """Track test results with detailed reporting."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
        self.section = ""

    def set_section(self, name: str):
        self.section = name
        print(f"\n{'=' * 60}")
        print(f"  {name}")
        print(f"{'=' * 60}")

    def record(self, name: str, passed: bool, expected=None, got=None, note=""):
        status = "PASS" if passed else "FAIL"
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        icon = "[OK]" if passed else "[FAIL]"
        print(f"  {icon} {name}")
        if not passed:
            print(f"       Expected: {expected}")
            print(f"       Got:      {got}")
        self.results.append({
            "section": self.section,
            "name": name,
            "status": status,
            "expected": expected,
            "actual": got,
            "note": note,
        })

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"  RESULTS: {self.passed}/{total} passed, {self.failed} failed")
        print(f"{'=' * 60}")
        return self.failed == 0


def setup_test_environment():
    """Create a temp project dir with guardian config using new split keys."""
    test_dir = tempfile.mkdtemp(prefix="allowed_ext_test_")
    guardian_dir = Path(test_dir) / ".claude" / "guardian"
    guardian_dir.mkdir(parents=True, exist_ok=True)

    git_dir = Path(test_dir) / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)

    test_config = {
        "version": "1.0.0",
        "hookBehavior": {"onTimeout": "deny", "onError": "deny", "timeoutSeconds": 10},
        "bashToolPatterns": {"block": [], "ask": []},
        "zeroAccessPaths": [
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "id_rsa",
            "id_rsa.*",
            "id_ed25519",
            "id_ed25519.*",
            "~/.ssh/**",
        ],
        "readOnlyPaths": [],
        "noDeletePaths": [],
        "allowedExternalReadPaths": [
            "~/.claude/projects/*/memory/**"
        ],
        "allowedExternalWritePaths": [],
    }

    config_path = guardian_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=2)

    os.environ["CLAUDE_PROJECT_DIR"] = test_dir
    return test_dir


def setup_empty_allowed_env():
    """Create env where both external path lists are empty."""
    test_dir = tempfile.mkdtemp(prefix="allowed_ext_empty_")
    guardian_dir = Path(test_dir) / ".claude" / "guardian"
    guardian_dir.mkdir(parents=True, exist_ok=True)
    git_dir = Path(test_dir) / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)

    test_config = {
        "version": "1.0.0",
        "hookBehavior": {"onTimeout": "deny", "onError": "deny", "timeoutSeconds": 10},
        "bashToolPatterns": {"block": [], "ask": []},
        "zeroAccessPaths": [".env"],
        "readOnlyPaths": [],
        "noDeletePaths": [],
        "allowedExternalReadPaths": [],
        "allowedExternalWritePaths": [],
    }

    config_path = guardian_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=2)

    os.environ["CLAUDE_PROJECT_DIR"] = test_dir
    return test_dir


def cleanup(test_dir):
    try:
        shutil.rmtree(test_dir)
    except Exception:
        pass


def clear_config_cache():
    """Clear the module's config cache so it reloads."""
    import _guardian_utils as gu
    gu._config_cache = None
    gu._using_fallback_config = False


def run_tests():
    results = TestResults()

    # Setup
    test_dir = setup_test_environment()

    # Force reimport with fresh cache
    if "_guardian_utils" in sys.modules:
        del sys.modules["_guardian_utils"]

    import _guardian_utils as gu
    clear_config_cache()

    home = Path.home()

    # ============================================================
    # SECTION 1: Positive Tests (should match allowedExternalReadPaths)
    # ============================================================
    results.set_section("1. Positive Tests (should match allowedExternalReadPaths)")

    # Test 1.1: Exact memory path
    memory_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / "MEMORY.md")
    mode = gu.match_allowed_external_path(memory_path)
    results.record(
        "Memory path (MEMORY.md) matches allowedExternalReadPaths",
        mode == "read",
        expected="'read'",
        got=repr(mode),
    )

    # Test 1.2: Different project slug
    other_path = str(home / ".claude" / "projects" / "C--other-project" / "memory" / "MEMORY.md")
    mode = gu.match_allowed_external_path(other_path)
    results.record(
        "Different project slug matches",
        mode == "read",
        expected="'read'",
        got=repr(mode),
    )

    # Test 1.3: Nested file in memory directory
    nested_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / "sub" / "file.md")
    mode = gu.match_allowed_external_path(nested_path)
    results.record(
        "Nested file in memory dir matches (** glob)",
        mode == "read",
        expected="'read'",
        got=repr(mode),
    )

    # ============================================================
    # SECTION 2: Negative Tests (should NOT match)
    # ============================================================
    results.set_section("2. Negative Tests (should NOT match)")

    # Test 2.1: Desktop path
    desktop_path = str(home / "Desktop" / "test.txt")
    mode = gu.match_allowed_external_path(desktop_path)
    results.record(
        "Desktop path does NOT match",
        mode is None,
        expected="None",
        got=repr(mode),
    )

    # Test 2.2: Claude config (not in memory dir)
    config_path = str(home / ".claude" / "projects" / "E--ops" / "config.json")
    mode = gu.match_allowed_external_path(config_path)
    results.record(
        "Claude projects config.json (not in memory/) does NOT match",
        mode is None,
        expected="None",
        got=repr(mode),
    )

    # ============================================================
    # SECTION 3: Security Tests
    # ============================================================
    results.set_section("3. Security Tests")

    # Test 3.1: Path traversal
    traversal_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / ".." / ".." / ".." / ".ssh" / "id_rsa")
    resolved = str(Path(traversal_path).resolve())
    mode = gu.match_allowed_external_path(resolved)
    results.record(
        "Path traversal to .ssh/id_rsa does NOT match after resolve",
        mode is None,
        expected="None",
        got=repr(mode),
        note=f"Resolved to: {resolved}",
    )

    # Test 3.2: .env in memory dir - matches external but zeroAccess should still block
    env_in_memory = str(home / ".claude" / "projects" / "E--ops" / "memory" / ".env")
    mode = gu.match_allowed_external_path(env_in_memory)
    zero_result = gu.match_zero_access(env_in_memory)
    results.record(
        ".env in memory dir: matches external (as expected)",
        mode is not None,
        expected="not None",
        got=repr(mode),
    )
    results.record(
        ".env in memory dir: ALSO matches zeroAccess (still blocked)",
        zero_result is True,
        expected=True,
        got=zero_result,
    )

    # Test 3.3: Memory path is outside project
    memory_check = str(home / ".claude" / "projects" / "E--ops" / "memory" / "MEMORY.md")
    within_project = gu.is_path_within_project(memory_check)
    results.record(
        "Memory path is OUTSIDE project (is_path_within_project=False)",
        within_project is False,
        expected=False,
        got=within_project,
    )

    # ============================================================
    # SECTION 4: Edge Cases
    # ============================================================
    results.set_section("4. Edge Cases")

    # Test 4.1: Empty allowedExternalReadPaths/WritePaths
    cleanup(test_dir)
    empty_dir = setup_empty_allowed_env()
    clear_config_cache()
    if "_guardian_utils" in sys.modules:
        del sys.modules["_guardian_utils"]
    import importlib
    gu = importlib.import_module("_guardian_utils")

    memory_with_empty = str(home / ".claude" / "projects" / "E--ops" / "memory" / "MEMORY.md")
    mode = gu.match_allowed_external_path(memory_with_empty)
    results.record(
        "Empty external path lists: memory path does NOT match",
        mode is None,
        expected="None",
        got=repr(mode),
        note="Fail-closed: empty lists mean no external paths allowed",
    )
    cleanup(empty_dir)

    # Restore main environment
    test_dir = setup_test_environment()
    clear_config_cache()
    if "_guardian_utils" in sys.modules:
        del sys.modules["_guardian_utils"]
    gu = importlib.import_module("_guardian_utils")

    # Test 4.2: Wildcard matches various project slugs
    slugs = ["E--ops", "C--myproject", "D--another-repo", "some-slug"]
    all_match = True
    for slug in slugs:
        p = str(home / ".claude" / "projects" / slug / "memory" / "test.md")
        m = gu.match_allowed_external_path(p)
        if not m:
            all_match = False
            break
    results.record(
        "Wildcard (*) in pattern matches various project slugs",
        all_match is True,
        expected=True,
        got=all_match,
        note=f"Tested slugs: {slugs}",
    )

    # ============================================================
    # SECTION 5: Fallback Config Safety
    # ============================================================
    results.set_section("5. Fallback Config Safety")

    fallback = gu._FALLBACK_CONFIG
    has_read = "allowedExternalReadPaths" in fallback
    has_write = "allowedExternalWritePaths" in fallback
    results.record(
        "Fallback config has allowedExternalReadPaths",
        has_read is True,
        expected=True,
        got=has_read,
    )
    results.record(
        "Fallback config has allowedExternalWritePaths",
        has_write is True,
        expected=True,
        got=has_write,
    )

    read_empty = fallback.get("allowedExternalReadPaths", None) == []
    write_empty = fallback.get("allowedExternalWritePaths", None) == []
    results.record(
        "Fallback allowedExternalReadPaths is empty (fail-closed)",
        read_empty is True,
        expected="[]",
        got=fallback.get("allowedExternalReadPaths", "MISSING"),
    )
    results.record(
        "Fallback allowedExternalWritePaths is empty (fail-closed)",
        write_empty is True,
        expected="[]",
        got=fallback.get("allowedExternalWritePaths", "MISSING"),
    )

    no_old_key = "allowedExternalPaths" not in fallback
    results.record(
        "Fallback does NOT have old allowedExternalPaths key",
        no_old_key is True,
        expected=True,
        got=no_old_key,
    )

    # Cleanup
    cleanup(test_dir)

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("  allowedExternalReadPaths / allowedExternalWritePaths Test Suite")
    print("=" * 60)

    orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")

    try:
        results = run_tests()
        all_pass = results.summary()
        sys.exit(0 if all_pass else 1)
    finally:
        if orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
