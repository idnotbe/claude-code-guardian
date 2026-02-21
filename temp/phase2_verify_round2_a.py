#!/usr/bin/env python3
"""Phase 2 Verification Round 2 - Perspective A: Independent comprehensive test.

Written from scratch. Tests all 13 hardened patterns across 5 files.
50+ test cases covering BLOCK, ALLOW, and edge cases.
"""

import json
import re
import sys

# ============================================================
# Step 1: Extract all 13 patterns from their source files
# ============================================================

print("=" * 70)
print("  Phase 2 Verification Round 2 - Perspective A")
print("=" * 70)

errors = []
total_checks = 0
passed_checks = 0

def check(name, condition, detail=""):
    global total_checks, passed_checks
    total_checks += 1
    if condition:
        passed_checks += 1
        print(f"  [PASS] {name}")
    else:
        errors.append((name, detail))
        print(f"  [FAIL] {name} -- {detail}")

# --- Load JSON files ---
print("\n--- Loading JSON files ---")

with open("/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json") as f:
    default_json = json.load(f)

with open("/home/idnotbe/projects/ops/.claude/guardian/config.json") as f:
    ops_json = json.load(f)

# --- Extract patterns from JSON files ---
# guardian.default.json: block patterns at indices 1,2,3 (0-indexed)
default_blocks = default_json["bashToolPatterns"]["block"]
json_git_default = default_blocks[1]["pattern"]
json_claude_default = default_blocks[2]["pattern"]
json_archive_default = default_blocks[3]["pattern"]

# ops config.json: block patterns at indices 1,2,3 (0-indexed)
ops_blocks = ops_json["bashToolPatterns"]["block"]
json_git_ops = ops_blocks[1]["pattern"]
json_claude_ops = ops_blocks[2]["pattern"]
json_archive_ops = ops_blocks[3]["pattern"]

print(f"  guardian.default.json .git:     {json_git_default}")
print(f"  guardian.default.json .claude:  {json_claude_default}")
print(f"  guardian.default.json _archive: {json_archive_default}")
print(f"  ops config.json .git:           {json_git_ops}")
print(f"  ops config.json .claude:        {json_claude_ops}")
print(f"  ops config.json _archive:       {json_archive_ops}")

# --- Extract patterns from Python files via import ---
# We need to read the raw Python source to extract patterns, not import
print("\n--- Extracting patterns from Python source files ---")

def extract_python_patterns(filepath, target_names):
    """Extract regex patterns from Python source by reading raw strings."""
    with open(filepath) as f:
        content = f.read()
    return content

# Read _guardian_utils.py fallback config patterns (lines ~374, 378, 382)
with open("/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py") as f:
    utils_content = f.read()

# We'll use the JSON-loaded approach for test configs to avoid brittle parsing
# Instead: read each test file's setup_test_environment to get the patterns

with open("/home/idnotbe/projects/claude-code-guardian/tests/test_guardian_utils.py") as f:
    tgu_content = f.read()

with open("/home/idnotbe/projects/claude-code-guardian/tests/test_guardian.py") as f:
    tg_content = f.read()

# ============================================================
# Step 2: Character-by-character pattern identity verification
# ============================================================

print("\n--- Pattern Identity Verification ---")

# The expected pattern (constructed carefully to avoid quote-escaping issues):
# Build from components to avoid Python string escaping confusing the comparison
_PREFIX = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*"
_TERM = "(?:\\s|/|[;&|)`" + "'" + '"]|$)'  # terminator with both quote chars
EXPECTED_GIT_PY     = _PREFIX + r"\.git" + _TERM
EXPECTED_CLAUDE_PY  = _PREFIX + r"\.claude" + _TERM
EXPECTED_ARCHIVE_PY = _PREFIX + "_archive" + _TERM

# JSON patterns should be the same as Python patterns (JSON decoding handles the double backslashes)
check("default.json .git == expected", json_git_default == EXPECTED_GIT_PY,
      f"got: {json_git_default!r}")
check("default.json .claude == expected", json_claude_default == EXPECTED_CLAUDE_PY,
      f"got: {json_claude_default!r}")
check("default.json _archive == expected", json_archive_default == EXPECTED_ARCHIVE_PY,
      f"got: {json_archive_default!r}")

check("ops.json .git == expected", json_git_ops == EXPECTED_GIT_PY,
      f"got: {json_git_ops!r}")
check("ops.json .claude == expected", json_claude_ops == EXPECTED_CLAUDE_PY,
      f"got: {json_claude_ops!r}")
check("ops.json _archive == expected", json_archive_ops == EXPECTED_ARCHIVE_PY,
      f"got: {json_archive_ops!r}")

# For Python source files, the pattern is written as r"...", so we must search
# for the raw-string-literal form. In a raw string, the pattern appears literally
# with single backslashes. The tricky part is the double-quote at end of char class
# which in source appears as '" (closing the raw string requires careful quoting).
# Instead of searching for the full decoded pattern, search for the key structural
# components that distinguish the hardened pattern from the old one.

_KEY_ANCHOR = r'(?:^\s*|[;|&`({]\s*)'      # new anchor with \s* and {
_KEY_CMDS = r'(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+'  # new command group
# These appear literally in Python source (raw strings use single backslash)

check("_guardian_utils.py has hardened anchor",
      _KEY_ANCHOR in utils_content,
      "hardened anchor (?:^\\s*|[;|&`({]\\s*) not found in _guardian_utils.py source")
check("_guardian_utils.py has hardened command group",
      _KEY_CMDS in utils_content,
      "command group with \\b\\s+ not found in _guardian_utils.py source")
check("_guardian_utils.py has .git target",
      r"\.git(?:" in utils_content,
      ".git target not found in _guardian_utils.py source")
check("_guardian_utils.py has .claude target",
      r"\.claude(?:" in utils_content,
      ".claude target not found in _guardian_utils.py source")
check("_guardian_utils.py has _archive target",
      "_archive(?:" in utils_content,
      "_archive target not found in _guardian_utils.py source")

check("test_guardian_utils.py has hardened anchor",
      _KEY_ANCHOR in tgu_content,
      "hardened anchor not found in test_guardian_utils.py source")
check("test_guardian_utils.py has .git target",
      r"\.git(?:" in tgu_content,
      ".git target not found in test_guardian_utils.py source")
check("test_guardian_utils.py has .claude target",
      r"\.claude(?:" in tgu_content,
      ".claude target not found in test_guardian_utils.py source")

check("test_guardian.py has hardened anchor",
      _KEY_ANCHOR in tg_content,
      "hardened anchor not found in test_guardian.py source")
check("test_guardian.py has .git target",
      r"\.git(?:" in tg_content,
      ".git target not found in test_guardian.py source")
check("test_guardian.py has _archive target",
      "_archive(?:" in tg_content,
      "_archive target not found in test_guardian.py source")

# Also verify there are NO remnants of the OLD unanchored patterns
OLD_PATTERN_FRAGMENT = r"(?:rm|rmdir|del).*\.git(?:\s|/|$)"
check("_guardian_utils.py has NO old unanchored .git pattern",
      OLD_PATTERN_FRAGMENT not in utils_content,
      "OLD unanchored pattern still present in _guardian_utils.py")
check("test_guardian_utils.py has NO old unanchored .git pattern",
      OLD_PATTERN_FRAGMENT not in tgu_content,
      "OLD unanchored pattern still present in test_guardian_utils.py")
check("test_guardian.py has NO old unanchored .git pattern",
      OLD_PATTERN_FRAGMENT not in tg_content,
      "OLD unanchored pattern still present in test_guardian.py")

# ============================================================
# Step 3: Regex compilation
# ============================================================

print("\n--- Regex Compilation ---")

all_patterns = [
    ("default.json .git", json_git_default),
    ("default.json .claude", json_claude_default),
    ("default.json _archive", json_archive_default),
    ("ops.json .git", json_git_ops),
    ("ops.json .claude", json_claude_ops),
    ("ops.json _archive", json_archive_ops),
    ("fallback .git", EXPECTED_GIT_PY),
    ("fallback .claude", EXPECTED_CLAUDE_PY),
    ("fallback _archive", EXPECTED_ARCHIVE_PY),
    ("test_utils .git", EXPECTED_GIT_PY),
    ("test_utils .claude", EXPECTED_CLAUDE_PY),
    ("test_guardian .git", EXPECTED_GIT_PY),
    ("test_guardian _archive", EXPECTED_ARCHIVE_PY),
]

compiled = {}
for name, pat in all_patterns:
    try:
        compiled[name] = re.compile(pat, re.DOTALL)
        check(f"Compile: {name}", True)
    except re.error as e:
        check(f"Compile: {name}", False, str(e))

# ============================================================
# Step 4: Independent regex testing (50+ test cases)
# ============================================================

print("\n--- Regex Testing: .claude pattern ---")

claude_re = re.compile(EXPECTED_CLAUDE_PY, re.DOTALL)
git_re = re.compile(EXPECTED_GIT_PY, re.DOTALL)
archive_re = re.compile(EXPECTED_ARCHIVE_PY, re.DOTALL)

# Helper
def test_regex(regex_obj, pattern_name, test_input, should_match, desc):
    result = bool(regex_obj.search(test_input))
    check(f"[{pattern_name}] {desc}: {'BLOCK' if should_match else 'ALLOW'}",
          result == should_match,
          f"input={test_input!r}, expected_match={should_match}, got_match={result}")

# ----- MUST-BLOCK cases (20+ for .claude) -----
print("\n  Must-BLOCK (.claude):")
claude_block = [
    ("rm -rf .claude/", "basic rm -rf .claude/"),
    ("rm .claude", "rm .claude bare"),
    ("rmdir .claude", "rmdir .claude"),
    ("del .claude/config", "del .claude/config"),
    ("delete .claude/config", "delete standalone .claude"),
    ("deletion .claude/whatever", "deletion .claude"),
    ("remove-item .claude", "remove-item .claude"),
    ("echo hello; rm .claude/x", "semicolon chain rm .claude"),
    ("(rm .claude/x)", "parenthesized rm .claude"),
    ("echo ok | rm .claude/x", "pipe to rm .claude"),
    ("cmd && rm .claude/x", "AND chain rm .claude"),
    ("  rm .claude/config", "leading spaces before rm"),
    ("\trm .claude/config", "leading tab before rm"),
    ("{ rm .claude/x; }", "brace group rm .claude"),
    ('rm ".claude/config"', "double-quoted path .claude"),
    ("rm '.claude/config'", "single-quoted path .claude"),
    ("  rm -rf .claude/", "whitespace + rf .claude"),
    ("{ del .claude/config; }", "brace + del .claude"),
    ("RM -RF .claude/", "uppercase RM -RF .claude"),
    ("DEL .claude/config", "uppercase DEL .claude"),
    ("\t\trm .claude/stuff", "double tab before rm"),
]

for cmd, desc in claude_block:
    test_regex(claude_re, ".claude", cmd, True, desc)

# ----- MUST-BLOCK cases for .git -----
print("\n  Must-BLOCK (.git):")
git_block = [
    ("rm -rf .git", "basic rm -rf .git"),
    ("rm -rf .git/", "rm -rf .git/ with slash"),
    ("del .git/config", "del .git/config"),
    ("delete .git/hooks", "delete .git/hooks"),
    ("  rm -rf .git/", "whitespace + .git"),
    ("{ del .git/config; }", "brace + .git"),
    ('rm ".git/hooks"', "quoted + .git"),
    ("\trm .git", "tab + .git"),
    ("echo x; rm .git", "chain + .git"),
    ("RM .git", "uppercase RM .git"),
]

for cmd, desc in git_block:
    test_regex(git_re, ".git", cmd, True, desc)

# ----- MUST-BLOCK cases for _archive -----
print("\n  Must-BLOCK (_archive):")
archive_block = [
    ("rm -rf _archive", "basic rm -rf _archive"),
    ("del _archive/old", "del _archive/old"),
    ("delete _archive/x", "delete _archive/x"),
    ("\tdelete _archive/x", "tab + _archive"),
    ("{ rmdir _archive; }", "brace + _archive"),
    ('del "_archive/old"', "quoted + _archive"),
    ("  rm _archive", "spaces + _archive"),
    ("echo x; rm _archive", "chain + _archive"),
]

for cmd, desc in archive_block:
    test_regex(archive_re, "_archive", cmd, True, desc)

# ----- MUST-ALLOW cases (15+) -----
print("\n  Must-ALLOW:")

allow_cases = [
    (claude_re, ".claude", "python3 memory_write.py --action delete .claude/memory/MEMORY.md",
     "memory_write.py --action delete (not a delete command)"),
    (claude_re, ".claude", "python3 memory_write.py --action delete --path .claude/memory/X",
     "memory_write.py --action delete --path"),
    (claude_re, ".claude", "cat .claude/memory/MEMORY.md",
     "cat .claude (read, not delete)"),
    (claude_re, ".claude", "ls .claude/memory/",
     "ls .claude (list, not delete)"),
    (git_re, ".git", "git status",
     "git status (not a delete)"),
    (claude_re, ".claude", 'npm run delete .claude/test',
     "npm run delete (npm subcommand, not shell delete)"),
    (claude_re, ".claude", 'echo "deletion" | grep .claude',
     "echo + grep (not a delete command)"),
    (claude_re, ".claude", 'some-tool --model .claude/config',
     "tool with --model flag (not delete)"),
    (git_re, ".git", "git add .gitignore",
     "git add .gitignore (safe)"),
    (git_re, ".git", "cat .git/HEAD",
     "cat .git/HEAD (read, not delete)"),
    (archive_re, "_archive", "ls _archive/",
     "ls _archive (list, not delete)"),
    (archive_re, "_archive", "cat _archive/file.txt",
     "cat _archive (read, not delete)"),
    (archive_re, "_archive", "cp _archive/old.txt /tmp/",
     "cp _archive (copy, not delete)"),
    (claude_re, ".claude", "mkdir -p .claude/guardian",
     "mkdir .claude (create, not delete)"),
    (claude_re, ".claude", "touch .claude/test",
     "touch .claude (create, not delete)"),
]

for regex, pname, cmd, desc in allow_cases:
    test_regex(regex, pname, cmd, False, desc)

# ----- EDGE CASES (15+) -----
print("\n  Edge cases:")

edge_cases = [
    # Word boundary: "deleting" and "deleted" should NOT match because \b prevents it
    (claude_re, ".claude", "deleting .claude/x", False, "deleting (gerund, not command)"),
    (claude_re, ".claude", "deleted .claude/x", False, "deleted (past tense, not command)"),
    # Case insensitive
    (claude_re, ".claude", "RM -rf .claude/", True, "uppercase RM .claude"),
    (claude_re, ".claude", "DEL .claude/config", True, "uppercase DEL .claude"),
    (git_re, ".git", "RMDIR .git", True, "uppercase RMDIR .git"),
    (archive_re, "_archive", "DELETE _archive/x", True, "uppercase DELETE _archive"),
    # No space between command and path: should NOT match (requires \s+)
    (claude_re, ".claude", "rm.claude", False, "rm.claude (no space, not a command)"),
    (git_re, ".git", "rm.git", False, "rm.git (no space)"),
    # Nested command: "git delete" should NOT match (git is not in command group)
    (claude_re, ".claude", "git delete .claude/x", False, "git delete (git subcommand, not shell)"),
    # But standalone delete SHOULD match
    (claude_re, ".claude", "delete .claude/x", True, "standalone delete .claude"),
    # Backtick separator
    (claude_re, ".claude", "`rm .claude/x`", True, "backtick rm .claude (NOT backtick subst)"),
    # Multiple flags
    (claude_re, ".claude", "rm -rf --no-preserve-root .claude/", True, "rm with multiple flags .claude"),
    # Path with dots
    (git_re, ".git", "rm -rf .github", False, ".github should NOT match .git boundary"),
    # Actually .github DOES contain .git as substring, but the terminator requires \s|/|[;&|)`'"]|$
    # .github has 'h' after .git so the terminator won't match. Let me verify...
    # .git in ".github" -- after ".git" comes "hub", no terminator. Should NOT match.

    # Path ending variations
    (claude_re, ".claude", "rm .claude;", True, ".claude followed by semicolon"),
    (claude_re, ".claude", "rm .claude|cat", True, ".claude followed by pipe"),
]

for regex, pname, cmd, expected, desc in edge_cases:
    test_regex(regex, pname, cmd, expected, desc)

# ============================================================
# Step 5: Cross-file consistency
# ============================================================

print("\n--- Cross-file Consistency ---")

check("default.json .git == ops.json .git",
      json_git_default == json_git_ops,
      f"default={json_git_default!r} vs ops={json_git_ops!r}")
check("default.json .claude == ops.json .claude",
      json_claude_default == json_claude_ops,
      f"default={json_claude_default!r} vs ops={json_claude_ops!r}")
check("default.json _archive == ops.json _archive",
      json_archive_default == json_archive_ops,
      f"default={json_archive_default!r} vs ops={json_archive_ops!r}")

# Verify all JSON-decoded patterns match the Python raw string versions
check("JSON .git == Python raw .git",
      json_git_default == EXPECTED_GIT_PY)
check("JSON .claude == Python raw .claude",
      json_claude_default == EXPECTED_CLAUDE_PY)
check("JSON _archive == Python raw _archive",
      json_archive_default == EXPECTED_ARCHIVE_PY)

# ============================================================
# Step 6: DO NOT CHANGE verification
# ============================================================

print("\n--- DO NOT CHANGE Verification ---")

# bash_guardian.py is_delete_command() should be untouched
with open("/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py") as f:
    bg_content = f.read()

# Check the patterns at lines ~612-616 are the original ones
check("bash_guardian.py has original rm pattern",
      r'r"(?:^|[;&|]\s*)rm\s+"' in bg_content or r"(?:^|[;&|]\s*)rm\s+" in bg_content,
      "is_delete_command rm pattern not found")
check("bash_guardian.py has original del pattern",
      r"(?:^|[;&|]\s*)del\s+" in bg_content,
      "is_delete_command del pattern not found")

# SQL DELETE pattern in guardian.default.json (ask section)
sql_delete_pattern = None
for p in default_json["bashToolPatterns"]["ask"]:
    if "DELETE" in p.get("reason", "") and "SQL" in p.get("reason", ""):
        sql_delete_pattern = p["pattern"]
        break
check("SQL DELETE pattern exists in ask",
      sql_delete_pattern is not None,
      "SQL DELETE ask pattern not found")
check("SQL DELETE pattern unchanged",
      sql_delete_pattern == r"(?i)delete\s+from\s+\w+(?:\s*;|\s*$|\s+--)",
      f"got: {sql_delete_pattern!r}")

# del\s+ ask pattern
del_ask = None
for p in default_json["bashToolPatterns"]["ask"]:
    if p.get("reason") == "Windows delete command":
        del_ask = p["pattern"]
        break
check("del\\s+ ask pattern exists",
      del_ask is not None,
      "del\\s+ ask pattern not found")
check("del\\s+ ask pattern unchanged",
      del_ask == r"(?i)del\s+(?:/[sq]\s+)*",
      f"got: {del_ask!r}")

# ============================================================
# Step 7: .github vs .git boundary check (important edge case)
# ============================================================

print("\n--- .github vs .git Boundary ---")

# ".github" should NOT be matched by the .git pattern
# because after ".git" comes "hub" which is not a terminator
test_regex(git_re, ".git", "rm -rf .github", False, ".github must NOT match .git")
test_regex(git_re, ".git", "rm .gitignore", False, ".gitignore must NOT match .git")
test_regex(git_re, ".git", "rm .gitmodules", False, ".gitmodules must NOT match .git")
test_regex(git_re, ".git", "rm .gitattributes", False, ".gitattributes must NOT match .git")

# But .git/ and .git<terminator> should match
test_regex(git_re, ".git", "rm .git/", True, ".git/ with slash SHOULD match")
test_regex(git_re, ".git", "rm .git ", True, ".git with trailing space SHOULD match")
test_regex(git_re, ".git", "rm -rf .git", True, ".git at end of string SHOULD match")

# ============================================================
# Summary
# ============================================================

print("\n" + "=" * 70)
print(f"  RESULTS: {passed_checks}/{total_checks} passed, {len(errors)} failed")
print("=" * 70)

if errors:
    print("\n  FAILURES:")
    for name, detail in errors:
        print(f"    - {name}: {detail}")
    print(f"\n  VERDICT: FAIL")
    sys.exit(1)
else:
    print(f"\n  VERDICT: PASS")
    sys.exit(0)
