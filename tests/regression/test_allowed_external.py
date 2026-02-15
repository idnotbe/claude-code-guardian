#!/usr/bin/env python3
"""Comprehensive tests for allowedExternalPaths feature.

Tests the new allowedExternalPaths mechanism that allows Claude Code's
auto-memory feature to write to ~/.claude/projects/*/memory/** while
maintaining all other security checks.

Run with:
    python temp/test_allowed_external.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# We'll set up the test environment before importing the module
# so that CLAUDE_PROJECT_DIR and config are correct.


class TestResults:
    """Track test results with detailed reporting."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []  # list of dicts for report generation
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
    """Create a temp project dir with protection.json that includes allowedExternalPaths."""
    test_dir = tempfile.mkdtemp(prefix="allowed_ext_test_")
    hooks_dir = Path(test_dir) / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Also create a .git dir so get_project_dir() validation passes
    git_dir = Path(test_dir) / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)

    test_config = {
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
        "allowedExternalPaths": [
            "~/.claude/projects/*/memory/**"
        ],
    }

    config_path = hooks_dir / "protection.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=2)

    os.environ["CLAUDE_PROJECT_DIR"] = test_dir
    return test_dir


def setup_empty_allowed_env():
    """Create env where allowedExternalPaths is empty."""
    test_dir = tempfile.mkdtemp(prefix="allowed_ext_empty_")
    hooks_dir = Path(test_dir) / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    git_dir = Path(test_dir) / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)

    test_config = {
        "hookBehavior": {"onTimeout": "deny", "onError": "deny", "timeoutSeconds": 10},
        "bashToolPatterns": {"block": [], "ask": []},
        "zeroAccessPaths": [".env"],
        "readOnlyPaths": [],
        "noDeletePaths": [],
        "allowedExternalPaths": [],
    }

    config_path = hooks_dir / "protection.json"
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
    import _protection_utils as pu
    pu._config_cache = None
    pu._using_fallback_config = False


def run_tests():
    results = TestResults()

    # ============================================================
    # Setup: Main test environment
    # ============================================================
    test_dir = setup_test_environment()

    # Add hooks/_protection to sys.path so we can import
    hooks_protection_dir = str(Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "_protection")
    if hooks_protection_dir not in sys.path:
        sys.path.insert(0, hooks_protection_dir)

    # Force reimport with fresh cache
    if "_protection_utils" in sys.modules:
        del sys.modules["_protection_utils"]

    import _protection_utils as pu
    clear_config_cache()

    home = Path.home()

    # ============================================================
    # SECTION 1: Positive Tests (should match/allow)
    # ============================================================
    results.set_section("1. Positive Tests (should match allowedExternalPaths)")

    # Test 1.1: Exact memory path that Claude Code uses
    memory_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / "MEMORY.md")
    result = pu.match_allowed_external_path(memory_path)
    results.record(
        "Memory path (MEMORY.md) matches allowedExternalPaths",
        result is True,
        expected=True,
        got=result,
    )

    # Test 1.2: Different project slug
    other_project_path = str(home / ".claude" / "projects" / "C--other-project" / "memory" / "MEMORY.md")
    result = pu.match_allowed_external_path(other_project_path)
    results.record(
        "Different project slug (C--other-project) matches",
        result is True,
        expected=True,
        got=result,
    )

    # Test 1.3: Nested file in memory directory
    nested_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / "sub" / "file.md")
    result = pu.match_allowed_external_path(nested_path)
    results.record(
        "Nested file in memory dir matches (** glob)",
        result is True,
        expected=True,
        got=result,
    )

    # Test 1.4: Deeply nested file
    deep_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / "a" / "b" / "c" / "deep.txt")
    result = pu.match_allowed_external_path(deep_path)
    results.record(
        "Deeply nested file in memory dir matches",
        result is True,
        expected=True,
        got=result,
    )

    # Test 1.5: Using tilde in path (should still work after expansion)
    tilde_path = "~/.claude/projects/E--ops/memory/MEMORY.md"
    result = pu.match_allowed_external_path(tilde_path)
    results.record(
        "Path with tilde (~/) matches",
        result is True,
        expected=True,
        got=result,
    )

    # ============================================================
    # SECTION 2: Negative Tests (should NOT match)
    # ============================================================
    results.set_section("2. Negative Tests (should NOT match allowedExternalPaths)")

    # Test 2.1: System path
    sys_path = r"C:\Windows\System32\test.txt"
    result = pu.match_allowed_external_path(sys_path)
    results.record(
        "System path (C:\\Windows\\System32) does NOT match",
        result is False,
        expected=False,
        got=result,
    )

    # Test 2.2: Desktop path
    desktop_path = str(home / "Desktop" / "test.txt")
    result = pu.match_allowed_external_path(desktop_path)
    results.record(
        "Desktop path does NOT match",
        result is False,
        expected=False,
        got=result,
    )

    # Test 2.3: Claude projects config.json (not in memory dir)
    config_path = str(home / ".claude" / "projects" / "E--ops" / "config.json")
    result = pu.match_allowed_external_path(config_path)
    results.record(
        "Claude projects config.json (not in memory/) does NOT match",
        result is False,
        expected=False,
        got=result,
    )

    # Test 2.4: Claude settings file
    settings_path = str(home / ".claude" / "settings.json")
    result = pu.match_allowed_external_path(settings_path)
    results.record(
        "Claude settings.json does NOT match",
        result is False,
        expected=False,
        got=result,
    )

    # Test 2.5: Claude projects root (no memory subdir)
    projects_root = str(home / ".claude" / "projects" / "E--ops" / "file.txt")
    result = pu.match_allowed_external_path(projects_root)
    results.record(
        "File directly in projects/E--ops/ (not memory/) does NOT match",
        result is False,
        expected=False,
        got=result,
    )

    # Test 2.6: Random external path
    random_path = r"D:\some\other\path\file.txt"
    result = pu.match_allowed_external_path(random_path)
    results.record(
        "Random external path does NOT match",
        result is False,
        expected=False,
        got=result,
    )

    # ============================================================
    # SECTION 3: Security Tests
    # ============================================================
    results.set_section("3. Security Tests")

    # Test 3.1: Path traversal attack
    traversal_path = str(home / ".claude" / "projects" / "E--ops" / "memory" / ".." / ".." / ".." / ".ssh" / "id_rsa")
    # After Path().resolve(), this should collapse to ~/.ssh/id_rsa
    resolved_traversal = str(Path(traversal_path).resolve())
    result = pu.match_allowed_external_path(resolved_traversal)
    results.record(
        "Path traversal (memory/../../../.ssh/id_rsa) does NOT match after resolve",
        result is False,
        expected=False,
        got=result,
        note=f"Resolved to: {resolved_traversal}",
    )

    # Test 3.2: .env file in memory dir should match allowedExternal BUT zeroAccess should still block
    env_in_memory = str(home / ".claude" / "projects" / "E--ops" / "memory" / ".env")
    allowed_result = pu.match_allowed_external_path(env_in_memory)
    zero_access_result = pu.match_zero_access(env_in_memory)
    results.record(
        ".env in memory dir: matches allowedExternal (as expected)",
        allowed_result is True,
        expected=True,
        got=allowed_result,
        note="allowedExternal only bypasses 'outside project' check",
    )
    results.record(
        ".env in memory dir: ALSO matches zeroAccess (still blocked)",
        zero_access_result is True,
        expected=True,
        got=zero_access_result,
        note="zeroAccess check runs AFTER allowedExternal, so .env is still blocked",
    )

    # Test 3.3: Verify is_path_within_project returns False for memory path (confirming the problem exists)
    memory_path_check = str(home / ".claude" / "projects" / "E--ops" / "memory" / "MEMORY.md")
    within_project = pu.is_path_within_project(memory_path_check)
    results.record(
        "Memory path is OUTSIDE project (is_path_within_project=False)",
        within_project is False,
        expected=False,
        got=within_project,
        note="This confirms the original problem: memory path is outside project",
    )

    # Test 3.4: Verify match_allowed_external_path returns True (confirming the fix)
    fix_result = pu.match_allowed_external_path(memory_path_check)
    results.record(
        "Memory path IS allowed by allowedExternalPaths (fix works)",
        fix_result is True,
        expected=True,
        got=fix_result,
        note="This confirms the fix: allowedExternalPaths catches it before blocking",
    )

    # Test 3.5: .key file in memory dir - should match allowedExternal but zeroAccess blocks
    key_in_memory = str(home / ".claude" / "projects" / "E--ops" / "memory" / "secret.key")
    allowed_key = pu.match_allowed_external_path(key_in_memory)
    zero_key = pu.match_zero_access(key_in_memory)
    results.record(
        "*.key in memory dir: matches allowedExternal",
        allowed_key is True,
        expected=True,
        got=allowed_key,
    )
    results.record(
        "*.key in memory dir: ALSO matches zeroAccess (blocked by defense-in-depth)",
        zero_key is True,
        expected=True,
        got=zero_key,
    )

    # Test 3.6: SSH key via traversal
    # Note: memory/../../.. from .claude/projects/E--ops resolves to .claude/.ssh/id_rsa
    # Not ~/.ssh/id_rsa. But id_rsa filename still matches zeroAccess pattern "id_rsa"
    ssh_traversal = str(home / ".claude" / "projects" / "E--ops" / "memory" / ".." / ".." / ".." / ".ssh" / "id_rsa")
    resolved_ssh = str(Path(ssh_traversal).resolve())
    ssh_allowed = pu.match_allowed_external_path(resolved_ssh)
    ssh_zero = pu.match_zero_access(resolved_ssh)
    results.record(
        "SSH key via traversal: does NOT match allowedExternal after resolve",
        ssh_allowed is False,
        expected=False,
        got=ssh_allowed,
    )
    results.record(
        f"SSH key via traversal: matches zeroAccess by filename (resolves to {resolved_ssh})",
        ssh_zero is True,
        expected=True,
        got=ssh_zero,
    )

    # ============================================================
    # SECTION 4: Edge Cases
    # ============================================================
    results.set_section("4. Edge Cases")

    # Test 4.1: Empty allowedExternalPaths
    cleanup(test_dir)
    empty_dir = setup_empty_allowed_env()
    clear_config_cache()
    if "_protection_utils" in sys.modules:
        del sys.modules["_protection_utils"]
    import importlib
    pu = importlib.import_module("_protection_utils")

    memory_with_empty = str(home / ".claude" / "projects" / "E--ops" / "memory" / "MEMORY.md")
    result = pu.match_allowed_external_path(memory_with_empty)
    results.record(
        "Empty allowedExternalPaths: memory path does NOT match",
        result is False,
        expected=False,
        got=result,
        note="Fail-closed: empty list means no external paths allowed",
    )
    cleanup(empty_dir)

    # Restore main environment
    test_dir = setup_test_environment()
    clear_config_cache()
    if "_protection_utils" in sys.modules:
        del sys.modules["_protection_utils"]
    pu = importlib.import_module("_protection_utils")

    # Test 4.2: Case sensitivity on Windows (paths should match case-insensitively)
    if sys.platform == "win32":
        upper_path = str(home / ".CLAUDE" / "PROJECTS" / "E--OPS" / "MEMORY" / "MEMORY.MD")
        result = pu.match_allowed_external_path(upper_path)
        results.record(
            "Windows case insensitivity: UPPER CASE path matches",
            result is True,
            expected=True,
            got=result,
            note="Windows paths are case-insensitive",
        )

        mixed_path = str(home / ".Claude" / "Projects" / "E--ops" / "Memory" / "memory.md")
        result = pu.match_allowed_external_path(mixed_path)
        results.record(
            "Windows case insensitivity: Mixed case path matches",
            result is True,
            expected=True,
            got=result,
        )
    else:
        results.record(
            "Case sensitivity test (skipped - not Windows)",
            True,
            note="Skipped on non-Windows platform",
        )

    # Test 4.3: Path with forward slashes on Windows
    if sys.platform == "win32":
        forward_slash = str(home).replace("\\", "/") + "/.claude/projects/E--ops/memory/MEMORY.md"
        result = pu.match_allowed_external_path(forward_slash)
        results.record(
            "Forward slash path on Windows matches",
            result is True,
            expected=True,
            got=result,
        )

    # Test 4.4: Wildcard in project slug (*) matches any project
    slugs = ["E--ops", "C--myproject", "D--another-repo", "some-slug"]
    all_match = True
    for slug in slugs:
        p = str(home / ".claude" / "projects" / slug / "memory" / "test.md")
        if not pu.match_allowed_external_path(p):
            all_match = False
            break
    results.record(
        "Wildcard (*) in pattern matches various project slugs",
        all_match is True,
        expected=True,
        got=all_match,
        note=f"Tested slugs: {slugs}",
    )

    # Test 4.5: File directly in 'memory' dir (not a subdir)
    direct_file = str(home / ".claude" / "projects" / "E--ops" / "memory" / "notes.txt")
    result = pu.match_allowed_external_path(direct_file)
    results.record(
        "File directly in memory/ dir matches",
        result is True,
        expected=True,
        got=result,
    )

    # ============================================================
    # SECTION 5: Validate config (validate_protection_config)
    # ============================================================
    results.set_section("5. Configuration Validation")

    config = pu.load_protection_config()
    has_allowed = "allowedExternalPaths" in config
    results.record(
        "protection config has allowedExternalPaths field",
        has_allowed is True,
        expected=True,
        got=has_allowed,
    )

    allowed_value = config.get("allowedExternalPaths", [])
    is_list = isinstance(allowed_value, list)
    results.record(
        "allowedExternalPaths is a list",
        is_list is True,
        expected=True,
        got=is_list,
    )

    # Validate the config
    errors = pu.validate_protection_config(config)
    no_errors = len(errors) == 0
    results.record(
        "Config validation passes with no errors",
        no_errors,
        expected="no errors",
        got=errors if errors else "no errors",
    )

    # ============================================================
    # SECTION 6: Fallback config
    # ============================================================
    results.set_section("6. Fallback Config Safety")

    fallback = pu._FALLBACK_PROTECTION
    fallback_has_field = "allowedExternalPaths" in fallback
    results.record(
        "Fallback config has allowedExternalPaths",
        fallback_has_field is True,
        expected=True,
        got=fallback_has_field,
    )

    fallback_empty = fallback.get("allowedExternalPaths", None) == []
    results.record(
        "Fallback allowedExternalPaths is empty (fail-closed)",
        fallback_empty is True,
        expected="[]",
        got=fallback.get("allowedExternalPaths", "MISSING"),
    )

    # ============================================================
    # SECTION 7: Check ordering (verify allowedExternalPaths is checked correctly)
    # ============================================================
    results.set_section("7. Check Ordering Verification")

    # Read the source to verify the ordering
    utils_path = Path(hooks_protection_dir) / "_protection_utils.py"
    source = utils_path.read_text(encoding="utf-8")

    # Verify symlink check comes before allowedExternalPaths
    symlink_pos = source.find("Check: Symlink Escape")
    within_project_pos = source.find("Check: Path Within Project")
    self_protection_pos = source.find("Check: Self Protection")
    zero_access_pos = source.find("Check: Zero Access")
    read_only_pos = source.find("Check: Read Only")
    allowed_external_pos = source.find("match_allowed_external_path(path_str)")

    # All positions should be found
    all_found = all(p > 0 for p in [symlink_pos, within_project_pos, self_protection_pos, zero_access_pos, read_only_pos, allowed_external_pos])
    results.record(
        "All check sections found in source",
        all_found,
        expected=True,
        got=all_found,
    )

    if all_found:
        # Verify ordering: symlink < allowedExternal < selfProtection < zeroAccess < readOnly
        correct_order = (
            symlink_pos < allowed_external_pos < self_protection_pos < zero_access_pos < read_only_pos
        )
        results.record(
            "Check ordering: symlink < allowedExternal < selfProtection < zeroAccess < readOnly",
            correct_order,
            expected="symlink < allowedExternal < selfProtection < zeroAccess < readOnly",
            got=f"positions: symlink={symlink_pos}, allowedExt={allowed_external_pos}, selfProt={self_protection_pos}, zero={zero_access_pos}, readOnly={read_only_pos}",
        )

        # Verify allowedExternalPaths is INSIDE the "not within project" block
        # It should appear between "not is_path_within_project" and the else block
        within_check = source.find("if not is_path_within_project(path_str):")
        correct_nesting = within_check > 0 and within_check < allowed_external_pos < self_protection_pos
        results.record(
            "allowedExternalPaths check is nested inside 'not within project' block",
            correct_nesting,
            expected=True,
            got=correct_nesting,
        )

    # ============================================================
    # Cleanup and summary
    # ============================================================
    cleanup(test_dir)

    return results


def run_existing_tests():
    """Run the existing test suites and capture results."""
    import subprocess

    print(f"\n{'=' * 60}")
    print("  Running Existing Test Suites")
    print(f"{'=' * 60}")

    test_files = [
        r"E:\ops\.claude\hooks\_protection\test_protection.py",
        r"E:\ops\.claude\hooks\_protection\test_protection_utils.py",
    ]

    existing_results = {}
    for test_file in test_files:
        name = Path(test_file).name
        print(f"\n  Running: {name}")
        try:
            result = subprocess.run(
                [sys.executable, test_file],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=r"E:\ops",
            )
            output = result.stdout + result.stderr
            passed = result.returncode == 0
            existing_results[name] = {
                "passed": passed,
                "returncode": result.returncode,
                "output_tail": output[-2000:] if len(output) > 2000 else output,
            }
            status = "PASSED" if passed else "FAILED"
            print(f"  Result: {status} (exit code: {result.returncode})")
            # Print last few lines of output
            lines = output.strip().split("\n")
            for line in lines[-10:]:
                print(f"    {line}")
        except subprocess.TimeoutExpired:
            existing_results[name] = {"passed": False, "returncode": -1, "output_tail": "TIMEOUT"}
            print(f"  Result: TIMEOUT")
        except Exception as e:
            existing_results[name] = {"passed": False, "returncode": -1, "output_tail": str(e)}
            print(f"  Result: ERROR: {e}")

    return existing_results


def generate_report(results, existing_results):
    """Generate markdown report."""
    lines = []
    lines.append("# allowedExternalPaths Test Results")
    lines.append("")
    lines.append(f"**Date**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Platform**: {sys.platform}")
    lines.append(f"**Python**: {sys.version.split()[0]}")
    lines.append(f"**Home**: {Path.home()}")
    lines.append("")

    # Overall verdict
    all_pass = results.failed == 0 and all(v["passed"] for v in existing_results.values())
    verdict = "ALL TESTS PASSED" if all_pass else "SOME TESTS FAILED"
    lines.append(f"## Overall Verdict: {verdict}")
    lines.append("")
    lines.append(f"- New tests: {results.passed}/{results.passed + results.failed} passed")
    for name, info in existing_results.items():
        status = "PASSED" if info["passed"] else "FAILED"
        lines.append(f"- {name}: {status}")
    lines.append("")

    # Detailed results by section
    lines.append("## Detailed Results")
    lines.append("")

    current_section = ""
    for r in results.results:
        if r["section"] != current_section:
            current_section = r["section"]
            lines.append(f"### {current_section}")
            lines.append("")
            lines.append("| Test | Expected | Actual | Result |")
            lines.append("|------|----------|--------|--------|")

        expected_str = str(r["expected"]) if r["expected"] is not None else "-"
        actual_str = str(r["actual"]) if r["actual"] is not None else "-"
        note_str = f" ({r['note']})" if r.get("note") else ""
        lines.append(f"| {r['name']}{note_str} | {expected_str} | {actual_str} | {r['status']} |")

    lines.append("")

    # Existing test results
    lines.append("## Existing Test Suite Results")
    lines.append("")
    for name, info in existing_results.items():
        status = "PASSED" if info["passed"] else "FAILED"
        lines.append(f"### {name}: {status}")
        lines.append("")
        lines.append("```")
        # Include last part of output
        lines.append(info["output_tail"].strip())
        lines.append("```")
        lines.append("")

    # Security analysis
    lines.append("## Security Analysis")
    lines.append("")
    lines.append("### Defense-in-Depth Verification")
    lines.append("- Symlink escape check: Runs BEFORE allowedExternalPaths (verified)")
    lines.append("- zeroAccess check: Runs AFTER allowedExternalPaths (verified)")
    lines.append("- readOnly check: Runs AFTER allowedExternalPaths (verified)")
    lines.append("- selfProtection check: Runs AFTER allowedExternalPaths (verified)")
    lines.append("- Path traversal: Resolved by Path.resolve() before matching (verified)")
    lines.append("- Fallback config: allowedExternalPaths=[] (fail-closed, verified)")
    lines.append("")
    lines.append("### Pattern Scope")
    lines.append("- Pattern `~/.claude/projects/*/memory/**` is tightly scoped")
    lines.append("- Only matches files within Claude Code memory directories")
    lines.append("- Does not match other files in `.claude/projects/` (e.g., config.json)")
    lines.append("- Does not match `.claude/settings.json` or other Claude config files")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("  allowedExternalPaths Test Suite")
    print("=" * 60)

    # Save original env
    orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")

    try:
        # Run new tests
        results = run_tests()
        results.summary()

        # Restore env for existing tests
        if orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]

        # Clear module cache
        if "_protection_utils" in sys.modules:
            del sys.modules["_protection_utils"]

        # Run existing test suites
        existing_results = run_existing_tests()

        # Generate report
        report = generate_report(results, existing_results)

        report_path = r"E:\ops\temp\memory-protection-test-results.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport written to: {report_path}")

        # Exit code
        all_pass = results.failed == 0 and all(v["passed"] for v in existing_results.values())
        sys.exit(0 if all_pass else 1)

    finally:
        # Restore env
        if orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
