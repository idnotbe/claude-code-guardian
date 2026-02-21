#!/usr/bin/env python3
"""Verification Round 2 - Perspective B: Integration + Ops Focus.

Independent functional tests covering all 3 fix categories across all 3 targets.
Also validates config loading pipeline and cross-config consistency.
"""

import json
import os
import re
import sys
import tempfile
import shutil
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'hooks' / 'scripts'))


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def check(self, name, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.errors.append((name, detail))
            print(f"  [FAIL] {name} -- {detail}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"TOTAL: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailed tests:")
            for name, detail in self.errors:
                print(f"  - {name}: {detail}")
        print(f"{'='*60}")
        return self.failed == 0


def extract_patterns_from_json(filepath):
    """Load block patterns from a JSON config file."""
    with open(filepath, encoding="utf-8") as f:
        config = json.load(f)
    return [p["pattern"] for p in config.get("bashToolPatterns", {}).get("block", [])]


def matches_any(command, patterns):
    """Test if a command matches any of the given patterns."""
    for pat in patterns:
        try:
            if re.search(pat, command, re.DOTALL):
                return True
        except re.error:
            pass
    return False


def get_deletion_patterns(patterns):
    """Extract only the .git/.claude/_archive deletion patterns."""
    targets = [r"\.git", r"\.claude", r"_archive"]
    result = []
    for pat in patterns:
        for t in targets:
            if t in pat and "rm|rmdir|del" in pat:
                result.append(pat)
                break
    return result


def main():
    r = Results()

    # ========================================================
    # SECTION 1: Ops config deep dive
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 1: Ops Config Deep Dive")
    print("="*60)

    ops_path = "/home/idnotbe/projects/ops/.claude/guardian/config.json"
    default_path = str(Path(__file__).resolve().parent.parent / "assets" / "guardian.default.json")

    # 1a. Verify ops config is valid JSON
    try:
        with open(ops_path, encoding="utf-8") as f:
            ops_config = json.load(f)
        r.check("Ops config is valid JSON", True)
    except (json.JSONDecodeError, OSError) as e:
        r.check("Ops config is valid JSON", False, str(e))
        return 1

    # 1b. Extract the 3 deletion patterns
    ops_block = ops_config.get("bashToolPatterns", {}).get("block", [])
    ops_del_patterns = []
    for entry in ops_block:
        pat = entry["pattern"]
        if any(t in pat for t in [r"\.git", r"\.claude", "_archive"]):
            if "rm|rmdir|del" in pat:
                ops_del_patterns.append(pat)

    r.check("Ops has exactly 3 deletion patterns", len(ops_del_patterns) == 3,
            f"found {len(ops_del_patterns)}")

    # 1c. Verify each pattern is fully hardened
    expected_spec = {
        ".git": r'(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`' + "'" + r'"]|$)',
        ".claude": r'(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`' + "'" + r'"]|$)',
        "_archive": r'(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`' + "'" + r'"]|$)',
    }

    # 1d. Check anchoring components in ops patterns
    for pat in ops_del_patterns:
        # Fix 1: ^\s* (leading whitespace)
        r.check(f"Ops pattern has ^\\s* anchor: ...{pat[-20:]}", r"^\s*" in pat,
                f"pattern: {pat[:60]}...")
        # Fix 2: { in separator class
        r.check(f"Ops pattern has {{ in sep class: ...{pat[-20:]}", "({]" in pat,
                f"pattern: {pat[:60]}...")
        # Fix 3: quotes in terminator class
        r.check(f"Ops pattern has quotes in terminator: ...{pat[-20:]}",
                "'" in pat and '"' in pat,
                f"pattern: {pat[:60]}...")

    # 1e. Verify no other content was accidentally changed (check structural integrity)
    r.check("Ops config has version", "version" in ops_config,
            f"keys: {list(ops_config.keys())}")
    r.check("Ops config has hookBehavior", "hookBehavior" in ops_config)
    r.check("Ops config has zeroAccessPaths", "zeroAccessPaths" in ops_config)
    r.check("Ops config has gitIntegration", "gitIntegration" in ops_config)
    r.check("Ops config autoCommit.includeUntracked is false",
            ops_config.get("gitIntegration", {}).get("autoCommit", {}).get("includeUntracked") == False,
            str(ops_config.get("gitIntegration", {}).get("autoCommit", {}).get("includeUntracked")))

    # ========================================================
    # SECTION 2: Config loading pipeline + cross-config comparison
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 2: Config Loading Pipeline + Cross-Config Comparison")
    print("="*60)

    # Load default config patterns
    try:
        with open(default_path, encoding="utf-8") as f:
            default_config = json.load(f)
        r.check("Default config is valid JSON", True)
    except (json.JSONDecodeError, OSError) as e:
        r.check("Default config is valid JSON", False, str(e))
        return 1

    default_del = get_deletion_patterns(
        [p["pattern"] for p in default_config.get("bashToolPatterns", {}).get("block", [])]
    )

    r.check("Default has exactly 3 deletion patterns", len(default_del) == 3,
            f"found {len(default_del)}")

    # Compare deletion patterns between default and ops
    for i, (dp, op) in enumerate(zip(sorted(default_del), sorted(ops_del_patterns))):
        r.check(f"Pattern #{i+1} identical across default/ops",
                dp == op,
                f"\n    default: {dp}\n    ops:     {op}")

    # Verify both pattern sets compile to valid regex
    for label, pats in [("default", default_del), ("ops", ops_del_patterns)]:
        for pat in pats:
            try:
                re.compile(pat, re.DOTALL)
                r.check(f"{label} pattern compiles: ...{pat[-25:]}", True)
            except re.error as e:
                r.check(f"{label} pattern compiles: ...{pat[-25:]}", False, str(e))

    # ========================================================
    # SECTION 3: Comprehensive functional tests (40+)
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 3: Functional Tests Against Hardened Patterns")
    print("="*60)

    # Use the actual patterns from default config
    all_block_patterns = [p["pattern"] for p in default_config["bashToolPatterns"]["block"]]

    # --- Fix 1: Leading whitespace (MUST BLOCK) ---
    print("\n  -- Fix 1: Leading whitespace --")
    leading_ws_tests = [
        ("  rm .claude/config", True, "2 leading spaces + .claude"),
        ("\trm .claude/config", True, "leading tab + .claude"),
        ("   rm .claude/stuff", True, "3 leading spaces + .claude"),
        ("  rm .git/HEAD", True, "2 leading spaces + .git"),
        ("\trm .git/HEAD", True, "leading tab + .git"),
        ("   rm .git/config", True, "3 spaces + .git"),
        ("  rm _archive/old", True, "2 spaces + _archive"),
        ("\trm _archive/old", True, "tab + _archive"),
        ("   delete _archive/old", True, "3 spaces + delete + _archive"),
        ("\t\trm -rf .claude", True, "double tab + .claude"),
        ("  rmdir .git", True, "spaces + rmdir + .git"),
        ("\tdel .claude/settings", True, "tab + del + .claude"),
    ]

    for cmd, should_block, desc in leading_ws_tests:
        matched = matches_any(cmd, all_block_patterns)
        r.check(f"LWS: {desc}", matched == should_block,
                f"cmd={repr(cmd)}, expected_block={should_block}, got={matched}")

    # --- Fix 2: Brace groups (MUST BLOCK) ---
    print("\n  -- Fix 2: Brace groups --")
    brace_tests = [
        ("{ rm .claude/x; }", True, "brace group + .claude"),
        ("{ del .git/config; }", True, "brace group + del + .git"),
        ("{ rmdir _archive; }", True, "brace group + rmdir + _archive"),
        ("{rm .claude/x}", True, "tight braces + .claude"),
        ("{ rm -rf .git; }", True, "brace group + rm -rf + .git"),
        ("{delete .claude/foo;}", True, "tight brace + delete + .claude"),
        ("{ removal-item .git/x; }", False, "typo removal-item should NOT match"),
    ]

    for cmd, should_block, desc in brace_tests:
        matched = matches_any(cmd, all_block_patterns)
        r.check(f"BRACE: {desc}", matched == should_block,
                f"cmd={repr(cmd)}, expected_block={should_block}, got={matched}")

    # --- Fix 3: Quoted paths (MUST BLOCK) ---
    print("\n  -- Fix 3: Quoted paths --")
    quote_tests = [
        ('rm ".claude/config"', True, 'double-quoted .claude'),
        ("rm '.claude/config'", True, "single-quoted .claude"),
        ('rm ".git/hooks"', True, 'double-quoted .git'),
        ("rm '.git/hooks'", True, "single-quoted .git"),
        ('del "_archive/x"', True, 'double-quoted _archive'),
        ("del '_archive/x'", True, "single-quoted _archive"),
        ('rm -rf ".claude"', True, 'rm -rf double-quoted .claude'),
        ("rmdir '.git'", True, "rmdir single-quoted .git"),
        ('delete ".claude/settings"', True, 'delete double-quoted .claude'),
    ]

    for cmd, should_block, desc in quote_tests:
        matched = matches_any(cmd, all_block_patterns)
        r.check(f"QUOTE: {desc}", matched == should_block,
                f"cmd={repr(cmd)}, expected_block={should_block}, got={matched}")

    # --- Combined: multi-fix tests ---
    print("\n  -- Combined multi-fix tests --")
    combined_tests = [
        ('  rm ".claude/config"', True, "leading whitespace + quoted path"),
        ('\t{ rm .git/HEAD; }', True, "tab + brace group"),
        ('  { del ".claude/x"; }', True, "space + brace + quoted"),
        ("{ rm '.git/hooks'; }", True, "brace + single-quoted"),
    ]

    for cmd, should_block, desc in combined_tests:
        matched = matches_any(cmd, all_block_patterns)
        r.check(f"COMBO: {desc}", matched == should_block,
                f"cmd={repr(cmd)}, expected_block={should_block}, got={matched}")

    # --- Regression: MUST ALLOW ---
    print("\n  -- Regression: must ALLOW --")
    allow_tests = [
        ("python3 memory_write.py --action delete .claude/memory/MEMORY.md", False,
         "delete as python arg flag"),
        ("python3 script.py --action delete .git/config", False,
         "delete as python arg + .git"),
        ("python3 script.py --action delete _archive/x", False,
         "delete as python arg + _archive"),
        ("ls -la .claude", False, "ls .claude is safe"),
        ("cat .git/config", False, "cat .git is safe"),
        ("echo hello > test.txt", False, "echo redirect is safe"),
        ("git status", False, "git status is safe"),
        ("git push origin main", False, "normal push is safe"),
        ("rm temp.txt", False, "rm unrelated file is safe"),
        ("rm -rf /tmp/test", False, "rm /tmp is not protected path"),
        ("grep -r pattern .claude/", False, "grep .claude is safe (read)"),
        ("find . -name '*.py' -print", False, "find without delete is safe"),
    ]

    for cmd, should_block, desc in allow_tests:
        matched = matches_any(cmd, all_block_patterns)
        r.check(f"ALLOW: {desc}", matched == should_block,
                f"cmd={repr(cmd)}, expected_block={should_block}, got={matched}")

    # --- Standard block patterns still work ---
    print("\n  -- Standard blocking still works --")
    standard_tests = [
        ("rm -rf .git", True, "standard rm -rf .git"),
        ("rm -rf .claude", True, "standard rm -rf .claude"),
        ("rm _archive/backup", True, "standard rm _archive"),
        ("del .git/HEAD", True, "standard del .git"),
        ("rmdir .claude", True, "standard rmdir .claude"),
        ("delete .claude/config", True, "standalone delete .claude"),
        ("; rm .git/x", True, "semicolon + rm .git"),
        ("&& rm .claude/y", True, "and + rm .claude"),
        ("|| rm _archive/z", True, "or + rm _archive"),
        ("| rm .git", True, "pipe + rm .git"),
    ]

    for cmd, should_block, desc in standard_tests:
        matched = matches_any(cmd, all_block_patterns)
        r.check(f"STD: {desc}", matched == should_block,
                f"cmd={repr(cmd)}, expected_block={should_block}, got={matched}")

    # ========================================================
    # SECTION 4: Verify ops patterns produce IDENTICAL results
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 4: Cross-Config Behavioral Equivalence")
    print("="*60)

    # Gather ALL test commands from above
    all_test_cmds = []
    for tests in [leading_ws_tests, brace_tests, quote_tests, combined_tests,
                  allow_tests, standard_tests]:
        for cmd, expected, desc in tests:
            all_test_cmds.append((cmd, expected, desc))

    ops_all_block = [p["pattern"] for p in ops_config["bashToolPatterns"]["block"]]

    mismatches = []
    for cmd, _, desc in all_test_cmds:
        default_result = matches_any(cmd, all_block_patterns)
        ops_result = matches_any(cmd, ops_all_block)
        # We only care about the 3 deletion patterns, so filter by checking if
        # the match is from a deletion pattern specifically
        default_del_match = matches_any(cmd, default_del)
        ops_del_match = matches_any(cmd, ops_del_patterns)
        if default_del_match != ops_del_match:
            mismatches.append((cmd, desc, default_del_match, ops_del_match))

    r.check(f"Cross-config: 0 deletion-pattern behavioral mismatches (tested {len(all_test_cmds)} commands)",
            len(mismatches) == 0,
            f"mismatches: {mismatches}")

    # ========================================================
    # SECTION 5: Verify new test cases in test_guardian_utils.py
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 5: Verify New Test Cases Added")
    print("="*60)

    test_file = str(Path(__file__).resolve().parent.parent / "tests" / "test_guardian_utils.py")
    with open(test_file, encoding="utf-8") as f:
        test_content = f.read()

    r.check("Test has leading spaces case", '  rm .claude/config' in test_content)
    r.check("Test has leading tab case", r'\trm .claude/config' in test_content)
    r.check("Test has brace group case", '{ rm .claude/x; }' in test_content)
    r.check("Test has double-quoted path case", 'rm ".claude/config"' in test_content)
    r.check("Test has single-quoted path case", "rm '.claude/config'" in test_content)

    # ========================================================
    # SECTION 6: DO NOT CHANGE items
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 6: DO NOT CHANGE Items Verification")
    print("="*60)

    bash_guardian_path = str(Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "bash_guardian.py")
    with open(bash_guardian_path, encoding="utf-8") as f:
        bg_content = f.read()

    # is_delete_command() uses its own anchoring: (?:^|[;&|]\s*)
    r.check("bash_guardian.py has is_delete_command()",
            "def is_delete_command(" in bg_content)
    r.check("is_delete_command uses (?:^|[;&|]\\s*)rm pattern (NOT hardened anchor)",
            r'(?:^|[;&|]\s*)rm\s+' in bg_content)
    r.check("is_delete_command uses (?:^|[;&|]\\s*)del pattern (NOT hardened anchor)",
            r'(?:^|[;&|]\s*)del\s+' in bg_content)

    # SQL DELETE pattern in default config
    r.check("Default config has SQL DELETE ask pattern",
            r'delete\s+from\s+\w+' in json.dumps(default_config).lower())

    # del\s+ ask pattern in default config
    ask_patterns = default_config.get("bashToolPatterns", {}).get("ask", [])
    del_ask = [p for p in ask_patterns if "del\\s+" in p["pattern"]]
    r.check("Default config has del\\s+ ask pattern", len(del_ask) > 0,
            f"found {len(del_ask)}")

    # ========================================================
    # SECTION 7: Config loading pipeline integration test
    # ========================================================
    print("\n" + "="*60)
    print("SECTION 7: Config Loading Pipeline Integration")
    print("="*60)

    # Create a temp project dir with the ops config copied in
    test_dir = tempfile.mkdtemp(prefix="verify_b_")
    try:
        guardian_dir = Path(test_dir) / ".claude" / "guardian"
        guardian_dir.mkdir(parents=True)
        shutil.copy2(ops_path, guardian_dir / "config.json")

        os.environ["CLAUDE_PROJECT_DIR"] = test_dir

        import _guardian_utils
        _guardian_utils._config_cache = None
        _guardian_utils._using_fallback_config = False

        config = _guardian_utils.load_guardian_config()
        r.check("Config loaded from temp dir", config is not None)
        r.check("Config has bashToolPatterns", "bashToolPatterns" in config)

        # Test via the actual match_block_patterns function
        matched, reason = _guardian_utils.match_block_patterns("  rm .claude/config")
        r.check("match_block_patterns catches leading whitespace via loaded config",
                matched, f"matched={matched}, reason={reason}")

        matched, reason = _guardian_utils.match_block_patterns("{ rm .git/HEAD; }")
        r.check("match_block_patterns catches brace group via loaded config",
                matched, f"matched={matched}, reason={reason}")

        matched, reason = _guardian_utils.match_block_patterns('rm ".claude/config"')
        r.check("match_block_patterns catches quoted path via loaded config",
                matched, f"matched={matched}, reason={reason}")

        matched, reason = _guardian_utils.match_block_patterns("python3 memory_write.py --action delete .claude/memory/MEMORY.md")
        r.check("match_block_patterns allows python --action delete via loaded config",
                not matched, f"matched={matched}, reason={reason}")

        matched, reason = _guardian_utils.match_block_patterns("ls -la .claude")
        r.check("match_block_patterns allows ls .claude via loaded config",
                not matched, f"matched={matched}, reason={reason}")

    finally:
        _guardian_utils._config_cache = None
        shutil.rmtree(test_dir, ignore_errors=True)

    # ========================================================
    # Summary
    # ========================================================
    return 0 if r.summary() else 1


if __name__ == "__main__":
    sys.exit(main())
