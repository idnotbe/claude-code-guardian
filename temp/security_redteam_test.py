#!/usr/bin/env python3
"""Security Red-Team Test: Phase 2 Hardening Verification

Tests the 3 hardening fixes:
1. Leading whitespace: ^\s* anchor
2. Brace group: { in separator class
3. Quoted paths: ' and " in terminator class

Also tests bypass attempts and false positive regressions.
"""
import os
import re
import sys
import time
from pathlib import Path

# Set up path to import _guardian_utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'hooks' / 'scripts'))

# Need a test environment
import tempfile, shutil, json

test_dir = tempfile.mkdtemp(prefix="redteam_test_")
hooks_dir = Path(test_dir) / ".claude" / "guardian"
hooks_dir.mkdir(parents=True, exist_ok=True)

# Load the actual default config from the repo
default_config_path = Path(__file__).resolve().parent.parent / "assets" / "guardian.default.json"
with open(default_config_path, "r") as f:
    test_config = json.load(f)

config_path = hooks_dir / "config.json"
with open(config_path, "w") as f:
    json.dump(test_config, f, indent=2)

os.environ["CLAUDE_PROJECT_DIR"] = test_dir

import _guardian_utils
_guardian_utils._config_cache = None

from _guardian_utils import match_block_patterns, match_ask_patterns, evaluate_rules

# ============================================================
# Test Infrastructure
# ============================================================

class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record(self, name, passed, expected=None, got=None):
        if passed:
            self.passed += 1
            print(f"  [OK] {name}")
        else:
            self.failed += 1
            self.errors.append((name, expected, got))
            print(f"  [FAIL] {name} (expected={expected}, got={got})")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailed tests:")
            for name, exp, got in self.errors:
                print(f"  - {name}")
        print(f"{'='*60}")
        return self.failed == 0

results = Results()

# Extract the hardened patterns for direct regex testing
config = _guardian_utils.load_guardian_config()
block_patterns = config.get("bashToolPatterns", {}).get("block", [])

# Find the .claude and .git patterns
claude_pattern = None
git_pattern = None
archive_pattern = None
for p in block_patterns:
    pat = p["pattern"]
    if ".claude" in pat and "rm|rmdir|del" in pat:
        claude_pattern = pat
    elif ".git" in pat and "rm|rmdir|del" in pat:
        git_pattern = pat
    elif "_archive" in pat and "rm|rmdir|del" in pat:
        archive_pattern = pat

print(f"Claude pattern: {claude_pattern}")
print(f"Git pattern:    {git_pattern}")
print(f"Archive pattern: {archive_pattern}")

# ============================================================
# Section 1: Verify the 3 specific fixes
# ============================================================

print("\n" + "="*60)
print("SECTION 1: Verify the 3 hardening fixes")
print("="*60)

# Fix 1: Leading whitespace
print("\n--- Fix 1: Leading whitespace ---")
fix1_tests = [
    ("  rm .claude/config", True, "leading spaces before rm .claude"),
    ("\trm .claude/config", True, "leading tab before rm .claude"),
    ("   rm -rf .git/", True, "leading spaces before rm -rf .git/"),
    ("\t\trm _archive/x", True, "leading tabs before rm _archive"),
    ("    rmdir .claude", True, "leading spaces before rmdir .claude"),
    ("\t  rm .git/index", True, "mixed tab+space before rm .git"),
    ("  \t  rm .claude/settings.json", True, "mixed whitespace before rm .claude"),
]

for cmd, expect_block, desc in fix1_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Fix1: {desc}", matched == expect_block, expect_block, matched)

# Fix 2: Brace groups
print("\n--- Fix 2: Brace groups ---")
fix2_tests = [
    ("{ rm .claude/x; }", True, "brace group rm .claude"),
    ("{ del .git/config; }", True, "brace group del .git"),
    ("{ rmdir _archive; }", True, "brace group rmdir _archive"),
    ("{rm .claude/x;}", True, "tight brace group rm .claude"),
    ("{ rm -rf .git; echo done; }", True, "brace group rm .git with trailing"),
]

for cmd, expect_block, desc in fix2_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Fix2: {desc}", matched == expect_block, expect_block, matched)

# Fix 3: Quoted paths
print("\n--- Fix 3: Quoted paths ---")
fix3_tests = [
    ('rm ".claude/config"', True, 'double-quoted .claude path'),
    ("rm '.claude/config'", True, "single-quoted .claude path"),
    ('rm ".git/config"', True, 'double-quoted .git path'),
    ("rm '.git/config'", True, "single-quoted .git path"),
    ('del "_archive/x"', True, 'double-quoted _archive path'),
    ("del '_archive/x'", True, "single-quoted _archive path"),
    ('rm -rf ".claude"', True, 'double-quoted .claude dir'),
    ("rm -rf '.git'", True, "single-quoted .git dir"),
]

for cmd, expect_block, desc in fix3_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Fix3: {desc}", matched == expect_block, expect_block, matched)


# ============================================================
# Section 2: False positive regressions
# ============================================================

print("\n" + "="*60)
print("SECTION 2: False positive regression tests")
print("="*60)

regression_tests = [
    ("python3 memory_write.py --action delete .claude/memory/MEMORY.md", False,
     "memory_write.py --action delete must NOT block"),
    ("cat .claude/memory/MEMORY.md", False, "cat .claude/memory must NOT block"),
    ("git status", False, "git status must NOT block"),
    ("ls -la", False, "ls must NOT block"),
    ("echo hello", False, "echo must NOT block"),
    ("rm temp.txt", False, "rm temp.txt must NOT block"),
    ("git push origin main", False, "normal git push must NOT block"),
    ("python3 -c 'print(1)'", False, "safe python must NOT block"),
    ("node -e 'console.log(1)'", False, "safe node must NOT block"),
    ("git log --oneline", False, "git log must NOT block"),
]

for cmd, expect_block, desc in regression_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Regression: {desc}", matched == expect_block, expect_block, matched)


# ============================================================
# Section 3: Red-team bypass attempts
# ============================================================

print("\n" + "="*60)
print("SECTION 3: Red-team bypass attempts")
print("="*60)

# --- Whitespace bypass attempts ---
print("\n--- Whitespace bypasses ---")
ws_bypass_tests = [
    ("  rm .claude/x", True, "multiple spaces"),
    ("\t  rm .claude/x", True, "tab + spaces"),
    ("\t\t\t rm .claude/x", True, "multiple tabs + space"),
    # Vertical tab and form feed - \s in Python regex includes \v \f
    ("\vrm .claude/x", True, "vertical tab (\\v) before rm"),
    ("\frm .claude/x", True, "form feed (\\f) before rm"),
    ("\r rm .claude/x", True, "carriage return + space before rm"),
]

for cmd, expect_block, desc in ws_bypass_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"WS-bypass: {desc}", matched == expect_block, expect_block, matched)

# --- Quoting bypass attempts ---
print("\n--- Quoting bypasses ---")
quote_bypass_tests = [
    ('rm ".claude/config"', True, "standard double-quote"),
    ("rm '.claude/config'", True, "standard single-quote"),
    # Backtick as path quoting (unusual) - already handled by backtick in separator
    # Escaped quotes - regex should still see the path after escaped quote
    ('rm \\".claude/config\\"', True, 'escaped double-quotes'),
]

for cmd, expect_block, desc in quote_bypass_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Quote-bypass: {desc}", matched == expect_block, expect_block, matched)

# --- Separator bypass attempts ---
print("\n--- Separator bypasses ---")
sep_bypass_tests = [
    (";;rm .claude/x", True, "double semicolons"),
    ("echo x; rm .claude/x", True, "semicolon separated"),
    ("echo x | rm .claude/x", True, "pipe separated"),
    ("echo x && rm .claude/x", True, "&& separated"),
    ("echo x || rm .claude/x", True, "|| separated"),
    ("(rm .claude/x)", True, "subshell parens"),
    ("{ rm .claude/x; }", True, "brace group"),
    ("`rm .claude/x`", True, "backtick execution"),
]

for cmd, expect_block, desc in sep_bypass_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Sep-bypass: {desc}", matched == expect_block, expect_block, matched)

# --- Shell trick bypass attempts ---
print("\n--- Shell trick bypasses ---")
shell_trick_tests = [
    ("eval rm .claude/x", True, "eval rm (caught by eval pattern)"),
    ("eval 'rm .claude/x'", True, "eval 'rm' (caught by eval pattern)"),
    ("sh -c 'rm .claude/x'", True, "sh -c rm (has rm + .claude in string)"),
    ("$(rm .claude/x)", True, "command substitution (caught by $() pattern)"),
]

for cmd, expect_block, desc in shell_trick_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Shell-trick: {desc}", matched == expect_block, expect_block, matched)

# --- Variable expansion / glob bypass attempts ---
print("\n--- Variable/glob bypasses (known limitations) ---")
# These are inherently hard to catch with regex and represent known limitations
known_limitation_tests = [
    # These are NOT catchable by regex - variable expansion happens at shell level
    ("rm $HOME/.claude/x", True, "variable expansion $HOME (pattern sees .claude)"),
    # This IS catchable because .claud? doesn't match .claude literally
    ("rm .claud?/config", False, "glob .claud? (does NOT match .claude literally - this is a known gap)"),
]

for cmd, expect_block, desc in known_limitation_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Var/glob: {desc}", matched == expect_block, expect_block, matched)


# ============================================================
# Section 4: Newline injection tests
# ============================================================

print("\n" + "="*60)
print("SECTION 4: Newline injection tests")
print("="*60)

newline_tests = [
    ("rm\n.claude/x", True, "newline between rm and .claude"),
    ("echo x\nrm .claude/x", True, "newline injection with rm .claude"),
    ("rm -rf\n.git", True, "newline between rm -rf and .git"),
]

for cmd, expect_block, desc in newline_tests:
    matched, reason = match_block_patterns(cmd)
    results.record(f"Newline: {desc}", matched == expect_block, expect_block, matched)


# ============================================================
# Section 5: ReDoS risk assessment
# ============================================================

print("\n" + "="*60)
print("SECTION 5: ReDoS risk assessment")
print("="*60)

# The pattern structure is:
# (?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`'"]|$)
#
# The .* in the middle is the primary ReDoS concern.
# Let's test with adversarial inputs designed to cause backtracking.

# Test 1: Long string between rm and .claude (should match, test speed)
for size in [100, 1000, 10000]:
    start = time.time()
    cmd = f"rm {'A' * size}.claude/x"
    matched, _ = match_block_patterns(cmd)
    elapsed = time.time() - start
    results.record(
        f"ReDoS: rm + {size} chars + .claude ({elapsed:.4f}s)",
        elapsed < 1.0 and matched,
        "< 1s and matched",
        f"{elapsed:.4f}s, matched={matched}"
    )

# Test 2: Long string that DOESN'T match (worst case for backtracking)
for size in [100, 1000, 10000]:
    start = time.time()
    cmd = f"rm {'A' * size}"  # No .claude - regex engine must try all positions
    matched, _ = match_block_patterns(cmd)
    elapsed = time.time() - start
    results.record(
        f"ReDoS: rm + {size} chars NO match ({elapsed:.4f}s)",
        elapsed < 1.0 and not matched,
        "< 1s and not matched",
        f"{elapsed:.4f}s, matched={matched}"
    )

# Test 3: Pathological input with repeating separators
start = time.time()
cmd = "rm " + ";|&" * 3000 + ".claude/x"
matched, _ = match_block_patterns(cmd)
elapsed = time.time() - start
results.record(
    f"ReDoS: pathological separators ({elapsed:.4f}s)",
    elapsed < 2.0,
    "< 2s",
    f"{elapsed:.4f}s"
)

# Test 4: Many spaces (tests \s* groups)
start = time.time()
cmd = " " * 10000 + "rm .claude/x"
matched, _ = match_block_patterns(cmd)
elapsed = time.time() - start
results.record(
    f"ReDoS: 10k leading spaces ({elapsed:.4f}s)",
    elapsed < 1.0,
    "< 1s",
    f"{elapsed:.4f}s"
)


# ============================================================
# Section 6: Pattern consistency across all 5 files
# ============================================================

print("\n" + "="*60)
print("SECTION 6: Pattern consistency verification")
print("="*60)

# The hardened pattern (Python raw string form):
expected_git = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`'\"]|$)"
expected_claude = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`'\"]|$)"
expected_archive = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`'\"]|$)"

# Check guardian.default.json
print("\n--- guardian.default.json ---")
with open(default_config_path, "r") as f:
    default_json = json.load(f)

json_blocks = default_json["bashToolPatterns"]["block"]
for p in json_blocks:
    pat = p["pattern"]
    if ".git" in pat and "rm|rmdir|del" in pat:
        results.record("JSON .git pattern matches expected", pat == expected_git, expected_git, pat)
    elif ".claude" in pat and "rm|rmdir|del" in pat:
        results.record("JSON .claude pattern matches expected", pat == expected_claude, expected_claude, pat)
    elif "_archive" in pat and "rm|rmdir|del" in pat:
        results.record("JSON _archive pattern matches expected", pat == expected_archive, expected_archive, pat)

# Check _guardian_utils.py fallback
print("\n--- _guardian_utils.py fallback ---")
fb_config = _guardian_utils._FALLBACK_CONFIG
fb_blocks = fb_config["bashToolPatterns"]["block"]
for p in fb_blocks:
    pat = p["pattern"]
    if ".git" in pat and "rm|rmdir|del" in pat:
        results.record("Fallback .git pattern matches expected", pat == expected_git, expected_git, pat)
    elif ".claude" in pat and "rm|rmdir|del" in pat:
        results.record("Fallback .claude pattern matches expected", pat == expected_claude, expected_claude, pat)
    elif "_archive" in pat and "rm|rmdir|del" in pat:
        results.record("Fallback _archive pattern matches expected", pat == expected_archive, expected_archive, pat)

# Check ops config
print("\n--- ops config.json ---")
ops_config_path = Path("/home/idnotbe/projects/ops/.claude/guardian/config.json")
if ops_config_path.exists():
    with open(ops_config_path, "r") as f:
        ops_json = json.load(f)
    ops_blocks = ops_json["bashToolPatterns"]["block"]
    for p in ops_blocks:
        pat = p["pattern"]
        if ".git" in pat and "rm|rmdir|del" in pat:
            results.record("Ops .git pattern matches expected", pat == expected_git, expected_git, pat)
        elif ".claude" in pat and "rm|rmdir|del" in pat:
            results.record("Ops .claude pattern matches expected", pat == expected_claude, expected_claude, pat)
        elif "_archive" in pat and "rm|rmdir|del" in pat:
            results.record("Ops _archive pattern matches expected", pat == expected_archive, expected_archive, pat)
else:
    print("  [SKIP] ops config not found")

# Check test files
print("\n--- test_guardian_utils.py ---")
test_utils_path = Path(__file__).resolve().parent.parent / "tests" / "test_guardian_utils.py"
with open(test_utils_path, "r") as f:
    test_utils_content = f.read()

# Extract patterns from test config
if expected_git in test_utils_content:
    results.record("test_guardian_utils.py has hardened .git pattern", True)
else:
    results.record("test_guardian_utils.py has hardened .git pattern", False, "pattern present", "not found")

if expected_claude in test_utils_content:
    results.record("test_guardian_utils.py has hardened .claude pattern", True)
else:
    results.record("test_guardian_utils.py has hardened .claude pattern", False, "pattern present", "not found")

print("\n--- test_guardian.py ---")
test_guardian_path = Path(__file__).resolve().parent.parent / "tests" / "test_guardian.py"
with open(test_guardian_path, "r") as f:
    test_guardian_content = f.read()

if expected_git in test_guardian_content:
    results.record("test_guardian.py has hardened .git pattern", True)
else:
    results.record("test_guardian.py has hardened .git pattern", False, "pattern present", "not found")

if expected_archive in test_guardian_content:
    results.record("test_guardian.py has hardened _archive pattern", True)
else:
    results.record("test_guardian.py has hardened _archive pattern", False, "pattern present", "not found")


# ============================================================
# Section 7: DO NOT CHANGE items verification
# ============================================================

print("\n" + "="*60)
print("SECTION 7: DO NOT CHANGE items verification")
print("="*60)

# Check bash_guardian.py is_delete_command hasn't changed
bg_path = Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "bash_guardian.py"
with open(bg_path, "r") as f:
    bg_content = f.read()

# Check is_delete_command patterns are intact (lines 612-616)
results.record(
    "is_delete_command: rm pattern intact",
    r'r"(?:^|[;&|]\s*)rm\s+"' in bg_content,
)
results.record(
    "is_delete_command: del pattern intact",
    r'r"(?:^|[;&|]\s*)del\s+"' in bg_content,
)
results.record(
    "is_delete_command: rmdir pattern intact",
    r'r"(?:^|[;&|]\s*)rmdir\s+"' in bg_content,
)

# Check SQL DELETE pattern unchanged in guardian.default.json
sql_delete_pat = r"(?i)delete\s+from\s+\w+(?:\s*;|\s*$|\s+--)"
results.record(
    "SQL DELETE pattern unchanged",
    any(p["pattern"] == sql_delete_pat for p in default_json["bashToolPatterns"]["ask"]),
)

# Check del\s+ ask pattern unchanged
del_ask_pat = r"(?i)del\s+(?:/[sq]\s+)*"
results.record(
    "del\\s+ ask pattern unchanged",
    any(p["pattern"] == del_ask_pat for p in default_json["bashToolPatterns"]["ask"]),
)


# ============================================================
# Final Summary
# ============================================================

# Cleanup
shutil.rmtree(test_dir)

success = results.summary()
sys.exit(0 if success else 1)
