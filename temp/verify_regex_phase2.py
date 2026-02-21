#!/usr/bin/env python3
"""Phase 2 Regex Verification Script - Independent Review

Tests all 13 hardened patterns across 5 files against 80+ test cases.
Verifies:
1. Pattern identity against spec (character-by-character)
2. Escaping correctness (JSON double-backslash vs Python raw single-backslash)
3. Cross-file consistency (byte-identical after JSON decode)
4. Functional correctness against must-BLOCK, must-ALLOW, and edge cases
"""

import json
import re
import sys

# ============================================================
# 1. Extract all patterns from source files
# ============================================================

# Spec patterns (from phase2-working-memory.md) - the ground truth
SPEC_JSON_GIT = r'(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`' + "'" + r'"]|$)'
SPEC_JSON_CLAUDE = r'(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`' + "'" + r'"]|$)'
SPEC_JSON_ARCHIVE = r'(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`' + "'" + r'"]|$)'

# These are identical in regex form - JSON just has doubled backslashes
SPEC_PY_GIT = SPEC_JSON_GIT
SPEC_PY_CLAUDE = SPEC_JSON_CLAUDE
SPEC_PY_ARCHIVE = SPEC_JSON_ARCHIVE

# Load JSON files
with open("/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json") as f:
    guardian_default = json.load(f)

with open("/home/idnotbe/projects/ops/.claude/guardian/config.json") as f:
    ops_config = json.load(f)

# Extract patterns from guardian.default.json (indices 1, 2, 3 in block array)
gd_git = guardian_default["bashToolPatterns"]["block"][1]["pattern"]
gd_claude = guardian_default["bashToolPatterns"]["block"][2]["pattern"]
gd_archive = guardian_default["bashToolPatterns"]["block"][3]["pattern"]

# Extract patterns from ops config.json (indices 1, 2, 3 in block array)
ops_git = ops_config["bashToolPatterns"]["block"][1]["pattern"]
ops_claude = ops_config["bashToolPatterns"]["block"][2]["pattern"]
ops_archive = ops_config["bashToolPatterns"]["block"][3]["pattern"]

# Extract patterns from _guardian_utils.py (Python raw strings - read from source)
# We'll parse the file to get the actual string values
sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")

# Read the fallback config directly from the module
import _guardian_utils
fb = _guardian_utils._FALLBACK_CONFIG
fb_git = fb["bashToolPatterns"]["block"][1]["pattern"]
fb_claude = fb["bashToolPatterns"]["block"][2]["pattern"]
fb_archive = fb["bashToolPatterns"]["block"][3]["pattern"]

# Extract patterns from test files by importing their configs
# test_guardian_utils.py sets up a test config with patterns at lines 56, 58
# We need to read the raw strings from the test setup
# Rather than import, parse the file to verify the actual string content

# For test_guardian_utils.py, we read the setup_test_environment function
# The patterns are in the test_config dict
import ast
import textwrap

def extract_patterns_from_test_config(filepath, pattern_indices):
    """Extract pattern strings from test config in test files."""
    with open(filepath) as f:
        content = f.read()

    # Find the block patterns by looking for the pattern strings
    patterns = []
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '"pattern"' in line or "'pattern'" in line:
            # Extract the raw string
            # Look for r"..." pattern
            if 'r"' in line or "r'" in line:
                # Find the raw string
                start = line.find('r"')
                if start == -1:
                    start = line.find("r'")
                if start >= 0:
                    # This is a raw string
                    quote_char = line[start+1]
                    end = line.rfind(quote_char)
                    if end > start + 2:
                        raw_str = line[start+2:end]
                        patterns.append(raw_str)
    return patterns


# ============================================================
# 2. Pattern Identity Verification
# ============================================================

print("=" * 70)
print("PHASE 2 REGEX VERIFICATION")
print("=" * 70)

results = {"pass": 0, "fail": 0, "errors": []}

def check(name, condition, detail=""):
    if condition:
        results["pass"] += 1
        print(f"  [PASS] {name}")
    else:
        results["fail"] += 1
        results["errors"].append(name)
        print(f"  [FAIL] {name}")
        if detail:
            print(f"         {detail}")

print("\n--- 2a. Pattern Identity: guardian.default.json ---")

check("guardian.default.json .git pattern matches spec",
      gd_git == SPEC_JSON_GIT,
      f"Expected: {SPEC_JSON_GIT!r}\n         Got:      {gd_git!r}")

check("guardian.default.json .claude pattern matches spec",
      gd_claude == SPEC_JSON_CLAUDE,
      f"Expected: {SPEC_JSON_CLAUDE!r}\n         Got:      {gd_claude!r}")

check("guardian.default.json _archive pattern matches spec",
      gd_archive == SPEC_JSON_ARCHIVE,
      f"Expected: {SPEC_JSON_ARCHIVE!r}\n         Got:      {gd_archive!r}")

print("\n--- 2b. Pattern Identity: ops config.json ---")

check("ops config.json .git pattern matches spec",
      ops_git == SPEC_JSON_GIT,
      f"Expected: {SPEC_JSON_GIT!r}\n         Got:      {ops_git!r}")

check("ops config.json .claude pattern matches spec",
      ops_claude == SPEC_JSON_CLAUDE,
      f"Expected: {SPEC_JSON_CLAUDE!r}\n         Got:      {ops_claude!r}")

check("ops config.json _archive pattern matches spec",
      ops_archive == SPEC_JSON_ARCHIVE,
      f"Expected: {SPEC_JSON_ARCHIVE!r}\n         Got:      {ops_archive!r}")

print("\n--- 2c. Pattern Identity: _guardian_utils.py fallback ---")

check("_guardian_utils.py fallback .git matches spec",
      fb_git == SPEC_PY_GIT,
      f"Expected: {SPEC_PY_GIT!r}\n         Got:      {fb_git!r}")

check("_guardian_utils.py fallback .claude matches spec",
      fb_claude == SPEC_PY_CLAUDE,
      f"Expected: {SPEC_PY_CLAUDE!r}\n         Got:      {fb_claude!r}")

check("_guardian_utils.py fallback _archive matches spec",
      fb_archive == SPEC_PY_ARCHIVE,
      f"Expected: {SPEC_PY_ARCHIVE!r}\n         Got:      {fb_archive!r}")

# ============================================================
# 3. Cross-file Consistency
# ============================================================

print("\n--- 3. Cross-file Consistency (byte-identical after decode) ---")

all_git = [gd_git, ops_git, fb_git]
all_claude = [gd_claude, ops_claude, fb_claude]
all_archive = [gd_archive, ops_archive, fb_archive]

check("All .git patterns are identical across 3 sources",
      len(set(all_git)) == 1,
      f"Unique patterns: {set(all_git)}")

check("All .claude patterns are identical across 3 sources",
      len(set(all_claude)) == 1,
      f"Unique patterns: {set(all_claude)}")

check("All _archive patterns are identical across 3 sources",
      len(set(all_archive)) == 1,
      f"Unique patterns: {set(all_archive)}")

# ============================================================
# 3b. Verify test file patterns
# ============================================================

print("\n--- 3b. Test File Pattern Verification ---")

# Read test_guardian_utils.py and test_guardian.py test configs
# Parse the raw file to find patterns
def find_delete_patterns_in_file(filepath):
    """Find .git, .claude, _archive delete patterns in a file."""
    with open(filepath) as f:
        content = f.read()

    found = {}
    # Look for the specific patterns
    for target in ['.git', '.claude', '_archive']:
        escaped = target.replace('.', r'\.')
        # Search for the pattern containing this target
        # In Python source, the pattern appears as a raw string
        search = rf'(?:rm|rmdir|del|delete|deletion|remove-item).*\\{escaped}'

        # Find lines containing this target in a pattern context
        for line in content.split('\n'):
            if target in line and ('pattern' in line.lower() or 'r"' in line or "r'" in line):
                # Extract what comes after r" or r'
                for prefix in ['r"', "r'"]:
                    idx = line.find(prefix)
                    if idx >= 0:
                        quote = line[idx+1]
                        # Find matching close quote
                        rest = line[idx+2:]
                        end = rest.rfind(quote)
                        if end >= 0:
                            found[target] = rest[:end]
                            break
    return found

tgu_patterns = find_delete_patterns_in_file(
    "/home/idnotbe/projects/claude-code-guardian/tests/test_guardian_utils.py")
tg_patterns = find_delete_patterns_in_file(
    "/home/idnotbe/projects/claude-code-guardian/tests/test_guardian.py")

# test_guardian_utils.py has .git and .claude patterns
if '.git' in tgu_patterns:
    check("test_guardian_utils.py .git pattern matches spec",
          tgu_patterns['.git'] == SPEC_PY_GIT,
          f"Expected: {SPEC_PY_GIT!r}\n         Got:      {tgu_patterns['.git']!r}")
else:
    check("test_guardian_utils.py .git pattern found", False, "Pattern not found in file")

if '.claude' in tgu_patterns:
    check("test_guardian_utils.py .claude pattern matches spec",
          tgu_patterns['.claude'] == SPEC_PY_CLAUDE,
          f"Expected: {SPEC_PY_CLAUDE!r}\n         Got:      {tgu_patterns['.claude']!r}")
else:
    check("test_guardian_utils.py .claude pattern found", False, "Pattern not found in file")

# test_guardian.py has .git and _archive patterns
if '.git' in tg_patterns:
    check("test_guardian.py .git pattern matches spec",
          tg_patterns['.git'] == SPEC_PY_GIT,
          f"Expected: {SPEC_PY_GIT!r}\n         Got:      {tg_patterns['.git']!r}")
else:
    check("test_guardian.py .git pattern found", False, "Pattern not found in file")

if '_archive' in tg_patterns:
    check("test_guardian.py _archive pattern matches spec",
          tg_patterns['_archive'] == SPEC_PY_ARCHIVE,
          f"Expected: {SPEC_PY_ARCHIVE!r}\n         Got:      {tg_patterns['_archive']!r}")
else:
    check("test_guardian.py _archive pattern found", False, "Pattern not found in file")


# ============================================================
# 4. Escaping Correctness
# ============================================================

print("\n--- 4. Escaping Correctness ---")

# Read raw JSON to verify doubled backslashes
with open("/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json") as f:
    raw_json_gd = f.read()

with open("/home/idnotbe/projects/ops/.claude/guardian/config.json") as f:
    raw_json_ops = f.read()

# In raw JSON, backslashes should be doubled
check("guardian.default.json has \\\\s (doubled backslash) in raw text",
      "\\\\s" in raw_json_gd)

check("guardian.default.json has \\\\b (doubled backslash) in raw text",
      "\\\\b\\\\s" in raw_json_gd)

check("ops config.json has \\\\s (doubled backslash) in raw text",
      "\\\\s" in raw_json_ops)

# All JSON patterns should compile as regex
for name, pat in [("gd_git", gd_git), ("gd_claude", gd_claude), ("gd_archive", gd_archive),
                   ("ops_git", ops_git), ("ops_claude", ops_claude), ("ops_archive", ops_archive),
                   ("fb_git", fb_git), ("fb_claude", fb_claude), ("fb_archive", fb_archive)]:
    try:
        re.compile(pat)
        check(f"{name} compiles as valid regex", True)
    except re.error as e:
        check(f"{name} compiles as valid regex", False, str(e))


# ============================================================
# 5. Functional Tests - 80+ Cases
# ============================================================

print("\n--- 5. Functional Tests ---")

# Use the canonical pattern (all are identical after decode)
PAT_GIT = re.compile(gd_git, re.DOTALL)
PAT_CLAUDE = re.compile(gd_claude, re.DOTALL)
PAT_ARCHIVE = re.compile(gd_archive, re.DOTALL)

def matches_any(cmd):
    """Return True if any of the 3 patterns match."""
    return bool(PAT_GIT.search(cmd) or PAT_CLAUDE.search(cmd) or PAT_ARCHIVE.search(cmd))

def matches_git(cmd):
    return bool(PAT_GIT.search(cmd))

def matches_claude(cmd):
    return bool(PAT_CLAUDE.search(cmd))

def matches_archive(cmd):
    return bool(PAT_ARCHIVE.search(cmd))

# ---- Must-BLOCK scenarios (30+) ----
print("\n  Must-BLOCK scenarios:")

block_tests = [
    # Basic commands
    ("rm -rf .claude/", matches_claude, "Basic: rm -rf .claude/"),
    ("rm -rf .git", matches_git, "Basic: rm -rf .git"),
    ("rm -rf _archive", matches_archive, "Basic: rm -rf _archive"),
    ("rmdir .git", matches_git, "Basic: rmdir .git"),
    ("del .claude", matches_claude, "Basic: del .claude"),
    ("delete .claude/config", matches_claude, "Basic: delete .claude/config"),
    ("deletion .git/hooks", matches_git, "Basic: deletion .git/hooks"),
    ("remove-item .claude", matches_claude, "Basic: remove-item .claude"),

    # Phase 1 cases: separator contexts
    ("echo hello; rm .claude/x", matches_claude, "Phase 1: semicolon + rm .claude"),
    ("(rm .claude/x)", matches_claude, "Phase 1: parens + rm .claude"),
    ("echo | rm .git/config", matches_git, "Phase 1: pipe + rm .git"),
    ("true && rm _archive/old", matches_archive, "Phase 1: && + rm _archive"),
    ("`rm .git/hooks`", matches_git, "Phase 1: backtick + rm .git"),

    # Phase 2 Fix 1: Leading whitespace
    ("  rm .claude/config", matches_claude, "Phase 2 Fix 1: leading spaces before rm"),
    ("\trm .claude/config", matches_claude, "Phase 2 Fix 1: leading tab before rm"),
    ("  rm -rf .git/", matches_git, "Phase 2 Fix 1: leading spaces before rm -rf .git"),
    ("\tdelete _archive/x", matches_archive, "Phase 2 Fix 1: leading tab before delete _archive"),
    ("   rmdir .git", matches_git, "Phase 2 Fix 1: multiple spaces before rmdir"),
    ("\t\trm .claude", matches_claude, "Phase 2 Fix 1: multiple tabs before rm"),
    ("  \t rm .git", matches_git, "Phase 2 Fix 1: mixed space+tab before rm"),

    # Phase 2 Fix 2: Brace groups
    ("{ rm .claude/x; }", matches_claude, "Phase 2 Fix 2: brace group rm .claude"),
    ("{ del .git/config; }", matches_git, "Phase 2 Fix 2: brace group del .git"),
    ("{ rmdir _archive; }", matches_archive, "Phase 2 Fix 2: brace group rmdir _archive"),
    ("{ rm -rf .claude/; }", matches_claude, "Phase 2 Fix 2: brace group rm -rf .claude"),

    # Phase 2 Fix 3: Quoted paths
    ('rm ".claude/config"', matches_claude, 'Phase 2 Fix 3: double-quoted .claude path'),
    ("rm '.claude/config'", matches_claude, "Phase 2 Fix 3: single-quoted .claude path"),
    ('rm ".git/config"', matches_git, 'Phase 2 Fix 3: double-quoted .git path'),
    ("rm '.git/hooks'", matches_git, "Phase 2 Fix 3: single-quoted .git path"),
    ('del "_archive/x"', matches_archive, 'Phase 2 Fix 3: double-quoted _archive path'),
    ("rm -rf '.claude/'", matches_claude, "Phase 2 Fix 3: single-quoted rm -rf .claude/"),

    # Combined Phase 2 fixes
    ('  rm ".claude/config"', matches_claude, "Combined: whitespace + quoted path"),
    ('{ rm ".git/x"; }', matches_git, "Combined: brace + quoted path"),
    ("\t{ del .claude/x; }", matches_claude, "Combined: tab + brace group"),
]

for cmd, match_fn, desc in block_tests:
    check(f"BLOCK: {desc}", match_fn(cmd), f"Command: {cmd!r}")

# ---- Must-ALLOW scenarios (20+) ----
print("\n  Must-ALLOW scenarios:")

allow_tests = [
    # Safe commands
    ("python3 memory_write.py --action delete .claude/memory/MEMORY.md", "memory_write.py --action delete"),
    ("cat .claude/memory/MEMORY.md", "cat .claude/"),
    ("ls .claude/memory/", "ls .claude/"),
    ("git status", "git status"),
    ("npm run delete .claude/test", "npm run delete"),
    ('echo "deletion" | grep .claude', 'echo with grep'),
    ("ls -la", "ls -la"),
    ("rm temp.txt", "rm temp.txt (no protected path)"),
    ("git push origin main", "normal push"),
    ("echo hello", "echo hello"),
    ("cat .git/config", "cat .git/config"),
    ("ls .git/", "ls .git/"),
    ("git log", "git log"),
    ("cp .claude/config .claude/config.bak", "cp .claude (not delete)"),
    ("mv .git/hooks/pre-commit /tmp/", "mv .git (not delete verb)"),
    ("read .claude/settings", "read .claude (not delete verb)"),
    ("vim .git/config", "vim .git (not delete verb)"),
    ("grep -r pattern _archive/", "grep in _archive (not delete)"),
    ("find _archive -name '*.log'", "find in _archive (not delete)"),
    ("tar czf backup.tar.gz _archive/", "tar on _archive (not delete)"),
]

for cmd, desc in allow_tests:
    check(f"ALLOW: {desc}", not matches_any(cmd), f"Command: {cmd!r}")

# ---- Edge cases (25+) ----
print("\n  Edge cases:")

edge_tests = [
    # Word boundary tests
    ("deleting .claude/x", False, "word boundary: 'deleting' should not match (not in verb list)"),
    # Actually 'deletion' IS in the verb list, but 'deleting' is NOT
    ("removing .claude/x", False, "word boundary: 'removing' should not match"),
    ("rm.claude", False, "no space: rm.claude (no \\s+ separator)"),
    ("formerly .git/config", False, "random word before .git"),

    # Case insensitivity
    ("RM -rf .claude/", True, "case: RM uppercase"),
    ("Del .git/hooks", True, "case: Del mixed case"),
    ("DELETE .claude/config", True, "case: DELETE all caps"),
    ("REMOVE-ITEM .git", True, "case: REMOVE-ITEM all caps"),
    ("Rmdir _archive", True, "case: Rmdir capitalized"),

    # Path variations
    ("rm -rf .git/", True, ".git/ with trailing slash"),
    ("rm .git ", True, ".git followed by space"),
    ("rm .gitignore", False, ".gitignore should not match (has text after .git)"),
    ("rm .gitconfig", False, ".gitconfig should not match"),
    ("rm .claude_backup", False, ".claude_backup should not match (has text after .claude)"),
    ("rm _archivex", False, "_archivex should not match (has text after _archive)"),
    ("rm .git;echo done", True, ".git followed by semicolon"),
    ("rm .claude|cat", True, ".claude followed by pipe"),
    ("rm .git&", True, ".git followed by &"),
    ("rm .git)", True, ".git followed by )"),
    ("rm .git`", True, ".git followed by backtick"),

    # Empty/minimal commands
    ("rm", False, "bare rm (no target)"),
    ("del", False, "bare del (no target)"),
    ("rm  .git", True, "rm with double space before .git"),

    # Nested contexts
    ("echo $(rm .claude/x)", False, "command substitution (separate pattern handles this)"),
    # The $() creates a subshell - the anchored pattern won't match inside $()
    # because the content inside $() doesn't start at ^ or after separator

    # Git-related but not delete
    ("git add .git", False, "git add .git (not delete verb)"),

    # _archive edge cases
    ("rm _archive", True, "_archive at end of string"),
    ("rm _archive/deep/nested/file.txt", True, "_archive with deep path"),
]

for cmd, should_match, desc in edge_tests:
    actual = matches_any(cmd)
    check(f"EDGE: {desc}", actual == should_match, f"Command: {cmd!r}, expected={should_match}, got={actual}")


# ============================================================
# 6. DO NOT CHANGE Verification
# ============================================================

print("\n--- 6. DO NOT CHANGE Verification ---")

# 6a. bash_guardian.py is_delete_command() lines ~612-616
with open("/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py") as f:
    bg_content = f.read()

# Check is_delete_command patterns are the OLD format (not modified)
check("bash_guardian.py has r\"(?:^|[;&|]\\s*)rm\\s+\" (original format)",
      r'r"(?:^|[;&|]\s*)rm\s+"' in bg_content)
check("bash_guardian.py has r\"(?:^|[;&|]\\s*)del\\s+\" (original format)",
      r'r"(?:^|[;&|]\s*)del\s+"' in bg_content)
check("bash_guardian.py has r\"(?:^|[;&|]\\s*)rmdir\\s+\" (original format)",
      r'r"(?:^|[;&|]\s*)rmdir\s+"' in bg_content)

# 6b. SQL DELETE pattern unchanged
sql_del_pat = guardian_default["bashToolPatterns"]["ask"][-3]["pattern"]  # Should be SQL DELETE
check("SQL DELETE pattern unchanged",
      sql_del_pat == r"(?i)delete\s+from\s+\w+(?:\s*;|\s*$|\s+--)",
      f"Got: {sql_del_pat!r}")

# 6c. del\s+ ask pattern unchanged
del_ask_pat = guardian_default["bashToolPatterns"]["ask"][1]["pattern"]
check("del\\s+ ask pattern unchanged",
      del_ask_pat == r"(?i)del\s+(?:/[sq]\s+)*",
      f"Got: {del_ask_pat!r}")


# ============================================================
# 7. ReDoS Risk Assessment
# ============================================================

print("\n--- 7. ReDoS Risk Assessment ---")

import time

# Test with adversarial inputs designed to trigger catastrophic backtracking
adversarial_inputs = [
    # Long strings with many separators
    ";" * 1000 + "rm .git",
    # Long strings with partial matches
    "rm " + "a" * 10000 + ".git",
    # Alternating patterns
    ("rm " + "." * 5000 + ".git"),
    # Many whitespace chars
    (" " * 10000 + "rm .git"),
]

for i, cmd in enumerate(adversarial_inputs):
    start = time.time()
    try:
        PAT_GIT.search(cmd)
        elapsed = time.time() - start
        check(f"ReDoS test {i+1}: completes in < 2s", elapsed < 2.0, f"Took {elapsed:.3f}s")
    except Exception as e:
        check(f"ReDoS test {i+1}: no exception", False, str(e))

# ============================================================
# Summary
# ============================================================

print("\n" + "=" * 70)
print(f"TOTAL: {results['pass']} passed, {results['fail']} failed")
if results["errors"]:
    print("\nFailed tests:")
    for e in results["errors"]:
        print(f"  - {e}")
print("=" * 70)

sys.exit(0 if results["fail"] == 0 else 1)
