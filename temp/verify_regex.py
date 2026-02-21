#!/usr/bin/env python3
"""
Verification Round 1 - Regex Correctness Test Script
Independently verifies all 10 pattern changes from the regex update fix.
"""

import re
import json
import sys

PASS_COUNT = 0
FAIL_COUNT = 0

def check(label, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [PASS] {label}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {label}")
        if detail:
            print(f"         {detail}")

def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)

# ============================================================
# STEP 1: Load and verify patterns from all 4 files
# ============================================================
section("STEP 1: LOAD AND COMPILE ALL 10 PATTERNS")

# --- File 1: guardian.default.json (JSON escaping) ---
with open("assets/guardian.default.json", "r") as f:
    cfg = json.load(f)

block_patterns = cfg["bashToolPatterns"]["block"]
json_git = block_patterns[1]["pattern"]
json_claude = block_patterns[2]["pattern"]
json_archive = block_patterns[3]["pattern"]

print(f"\nJSON .git:     {json_git!r}")
print(f"JSON .claude:  {json_claude!r}")
print(f"JSON _archive: {json_archive!r}")

# Verify compilation
for name, pat in [("json_git", json_git), ("json_claude", json_claude), ("json_archive", json_archive)]:
    try:
        re.compile(pat)
        check(f"{name} compiles", True)
    except re.error as e:
        check(f"{name} compiles", False, str(e))

# --- File 2: _guardian_utils.py (Python raw strings) ---
# We extract patterns by importing the module's fallback config
# But to avoid import complexities, we'll read the file and extract via regex
with open("hooks/scripts/_guardian_utils.py", "r") as f:
    utils_content = f.read()

# Find the fallback block patterns for .git, .claude, _archive
# These are Python raw strings: r"..."
py_utils_patterns = re.findall(r'r"(\(\?i\)\(\?:\^\|\[;\|&`\(]\\.+(?:git|claude|_archive)\(.+?\))"', utils_content)
print(f"\n_guardian_utils.py extracted {len(py_utils_patterns)} patterns")

# Manual extraction - read the exact lines
utils_lines = utils_content.split("\n")
py_git = py_claude = py_archive = None
for i, line in enumerate(utils_lines):
    stripped = line.strip()
    if '"pattern": r"' in stripped:
        # Extract the raw string content
        m = re.search(r'"pattern": r"(.+?)",?\s*$', stripped)
        if m:
            pat = m.group(1)
            if ".git(" in pat and "FALLBACK" not in stripped:
                py_git = pat
            elif ".claude(" in pat and "FALLBACK" not in stripped:
                py_claude = pat
            elif "_archive(" in pat and "FALLBACK" not in stripped:
                py_archive = pat

# Try searching in the fallback block region (lines 370-385)
for i in range(368, min(390, len(utils_lines))):
    line = utils_lines[i].strip()
    if '"pattern": r"' in line:
        m = re.search(r'"pattern": r"(.+?)"', line)
        if m:
            pat = m.group(1)
            if ".git(" in pat:
                py_git = pat
            elif ".claude(" in pat:
                py_claude = pat
            elif "_archive(" in pat:
                py_archive = pat

print(f"\nPython _guardian_utils.py:")
print(f"  .git:     {py_git!r}")
print(f"  .claude:  {py_claude!r}")
print(f"  _archive: {py_archive!r}")

for name, pat in [("py_utils_git", py_git), ("py_utils_claude", py_claude), ("py_utils_archive", py_archive)]:
    if pat is None:
        check(f"{name} found", False, "Pattern not extracted")
    else:
        try:
            re.compile(pat)
            check(f"{name} compiles", True)
        except re.error as e:
            check(f"{name} compiles", False, str(e))

# --- File 3: test_guardian_utils.py (Python raw strings) ---
with open("tests/test_guardian_utils.py", "r") as f:
    test_utils_content = f.read()

test_utils_lines = test_utils_content.split("\n")
test_git = test_claude = None
for i, line in enumerate(test_utils_lines):
    stripped = line.strip()
    if '"pattern": r"' in stripped:
        m = re.search(r'"pattern": r"(.+?)"', stripped)
        if m:
            pat = m.group(1)
            if ".git(" in pat:
                test_git = pat
            elif ".claude(" in pat:
                test_claude = pat

print(f"\ntest_guardian_utils.py:")
print(f"  .git:    {test_git!r}")
print(f"  .claude: {test_claude!r}")

for name, pat in [("test_utils_git", test_git), ("test_utils_claude", test_claude)]:
    if pat is None:
        check(f"{name} found", False, "Pattern not extracted")
    else:
        try:
            re.compile(pat)
            check(f"{name} compiles", True)
        except re.error as e:
            check(f"{name} compiles", False, str(e))

# --- File 4: test_guardian.py (Python raw strings) ---
with open("tests/test_guardian.py", "r") as f:
    test_guard_content = f.read()

test_guard_lines = test_guard_content.split("\n")
tg_git = tg_archive = None
for i, line in enumerate(test_guard_lines):
    stripped = line.strip()
    if '"pattern": r"' in stripped:
        m = re.search(r'"pattern": r"(.+?)"', stripped)
        if m:
            pat = m.group(1)
            if ".git(" in pat:
                tg_git = pat
            elif "_archive(" in pat:
                tg_archive = pat

print(f"\ntest_guardian.py:")
print(f"  .git:     {tg_git!r}")
print(f"  _archive: {tg_archive!r}")

for name, pat in [("test_guard_git", tg_git), ("test_guard_archive", tg_archive)]:
    if pat is None:
        check(f"{name} found", False, "Pattern not extracted")
    else:
        try:
            re.compile(pat)
            check(f"{name} compiles", True)
        except re.error as e:
            check(f"{name} compiles", False, str(e))


# ============================================================
# STEP 2: Verify all 10 patterns are identical (modulo target)
# ============================================================
section("STEP 2: CROSS-FILE PATTERN CONSISTENCY")

# All .git patterns should be identical
git_patterns = {"json": json_git, "utils": py_git, "test_utils": test_git, "test_guard": tg_git}
git_unique = set(v for v in git_patterns.values() if v is not None)
check("All .git patterns are identical across files",
      len(git_unique) == 1,
      f"Found {len(git_unique)} distinct patterns: {git_unique}")

# All .claude patterns should be identical
claude_patterns = {"json": json_claude, "utils": py_claude, "test_utils": test_claude}
claude_unique = set(v for v in claude_patterns.values() if v is not None)
check("All .claude patterns are identical across files",
      len(claude_unique) == 1,
      f"Found {len(claude_unique)} distinct patterns: {claude_unique}")

# All _archive patterns should be identical
archive_patterns = {"json": json_archive, "utils": py_archive, "test_guard": tg_archive}
archive_unique = set(v for v in archive_patterns.values() if v is not None)
check("All _archive patterns are identical across files",
      len(archive_unique) == 1,
      f"Found {len(archive_unique)} distinct patterns: {archive_unique}")


# ============================================================
# STEP 3: Verify regex structure
# ============================================================
section("STEP 3: VERIFY REGEX STRUCTURE")

# Use the .claude pattern as reference (all share same structure)
reference = json_claude
print(f"\nReference pattern: {reference!r}\n")

# Check for required components
check("Has (?i) case-insensitive flag", reference.startswith("(?i)"))
check("Has command-position anchor (?:^|[;|&`(]\\s*)",
      r"(?:^|[;|&`(]\s*)" in reference)
check("Has full alternation group",
      r"(?:rm|rmdir|del|delete|deletion|remove-item)" in reference)
check("Has \\b word boundary after alternation",
      r"remove-item)\b" in reference)
check("Has \\s+ required whitespace",
      r"\b\s+" in reference)
check("Has .* any-chars bridge",
      r"\s+.*" in reference)
check("Has \\.claude literal dot target",
      r"\.claude" in reference)
check("Has enriched terminator (?:\\s|/|[;&|)`]|$)",
      r"(?:\s|/|[;&|)`]|$)" in reference)

# Verify the anchor does NOT include \s in the character class
# (this was the key fix - using [;|&`(] instead of [\s;|&`(])
anchor_match = re.search(r'\(\?:\^\|\[([^\]]+)\]', reference)
if anchor_match:
    anchor_chars = anchor_match.group(1)
    check("Anchor char class does NOT contain \\s",
          "\\s" not in anchor_chars and r"\s" not in anchor_chars,
          f"Anchor chars: {anchor_chars!r}")
else:
    check("Anchor found", False, "Could not extract anchor character class")


# ============================================================
# STEP 4: Programmatic regex testing against all test cases
# ============================================================
section("STEP 4: PROGRAMMATIC REGEX TESTING")

# Test all 3 pattern variants
patterns = {
    ".git": json_git,
    ".claude": json_claude,
    "_archive": json_archive,
}

# --- Must-PASS cases (should NOT match = ALLOWED) ---
print("\n--- Must-PASS (ALLOWED) cases ---\n")

must_pass = [
    # .claude tests
    ("python3 memory_write.py --action delete .claude/memory/MEMORY.md", ".claude",
     "delete as argument, not command"),
    ("python3 memory_write.py --action delete --path .claude/memory/X", ".claude",
     "delete as argument with --path"),
    ("python3 mem.py --action retire .claude/memory/sessions/foo.json", ".claude",
     "renamed action (no delete at all)"),
    ('echo "deletion" | grep .claude', ".claude",
     "deletion in echo string, not a command position"),
    ("some-tool --model .claude/config", ".claude",
     "no delete command anywhere"),
    ("cat .claude/memory/MEMORY.md", ".claude",
     "cat is read-only"),
    ("ls .claude/memory/", ".claude",
     "ls is read-only"),

    # .git tests
    ("python3 script.py --action delete .git/config", ".git",
     "delete as argument, not command"),
    ("git status", ".git",
     "git status is safe"),
    ("echo deleting .git is bad", ".git",
     "deleting does not match due to \\b"),

    # _archive tests
    ("ls _archive/", "_archive",
     "ls is read-only"),
    ("python3 script.py --action delete _archive/x", "_archive",
     "delete as argument"),
    ("cat _archive/readme.md", "_archive",
     "cat is read-only"),
]

for cmd, target, reason in must_pass:
    pat = patterns[target]
    match = re.search(pat, cmd)
    check(f"ALLOWED: {cmd!r} ({reason})",
          match is None,
          f"Pattern {target} matched but should not have! Match: {match}")

# --- Must-BLOCK cases (should match) ---
print("\n--- Must-BLOCK (BLOCKED) cases ---\n")

must_block = [
    # .claude blocks
    ("rm -rf .claude/", ".claude", "rm at start"),
    ("rm .claude/memory/X", ".claude", "rm as command"),
    ("del .claude/config", ".claude", "del as command"),
    ("delete .claude/config", ".claude", "delete as command"),
    ("rmdir .claude/memory", ".claude", "rmdir as command"),
    ("echo hello; rm .claude/x", ".claude", "rm after semicolon"),
    ("echo hello && del .claude/x", ".claude", "del after &&"),
    ("(rm .claude/x)", ".claude", "rm after open paren"),
    ("Remove-Item .claude/config", ".claude", "PowerShell remove-item"),
    ("DELETION .claude/stuff", ".claude", "deletion case-insensitive"),

    # .git blocks
    ("rm -rf .git", ".git", "rm at start"),
    ("rm -rf .git/", ".git", "rm with trailing slash"),
    ("delete .git/", ".git", "delete as command"),
    ("rmdir .git", ".git", "rmdir as command"),
    ("echo x; del .git/config", ".git", "del after semicolon"),

    # _archive blocks
    ("rm -rf _archive", "_archive", "rm at start"),
    ("delete _archive/old", "_archive", "delete as command"),
    ("rmdir _archive", "_archive", "rmdir as command"),
    ("echo x | rm _archive/y", "_archive", "rm after pipe"),
]

for cmd, target, reason in must_block:
    pat = patterns[target]
    match = re.search(pat, cmd)
    check(f"BLOCKED: {cmd!r} ({reason})",
          match is not None,
          f"Pattern {target} did NOT match but should have!")


# ============================================================
# STEP 5: Verify DO NOT CHANGE items
# ============================================================
section("STEP 5: VERIFY DO NOT CHANGE ITEMS")

# 5a: is_delete_command() in bash_guardian.py was NOT modified
with open("hooks/scripts/bash_guardian.py", "r") as f:
    bg_content = f.read()

# Check that is_delete_command still has the original patterns
check("is_delete_command has r\"(?:^|[;&|]\\s*)rm\\s+\"",
      r'r"(?:^|[;&|]\s*)rm\s+"' in bg_content)
check("is_delete_command has r\"(?:^|[;&|]\\s*)del\\s+\"",
      r'r"(?:^|[;&|]\s*)del\s+"' in bg_content)
check("is_delete_command has r\"(?:^|[;&|]\\s*)rmdir\\s+\"",
      r'r"(?:^|[;&|]\s*)rmdir\s+"' in bg_content)
check("is_delete_command has r\"(?:^|[;&|]\\s*)Remove-Item\\s+\"",
      r'r"(?:^|[;&|]\s*)Remove-Item\s+"' in bg_content)
check("is_delete_command has r\"(?:^|[;&|]\\s*)ri\\s+\"",
      r'r"(?:^|[;&|]\s*)ri\s+"' in bg_content)

# 5b: SQL DELETE pattern not modified
ask_patterns = cfg["bashToolPatterns"]["ask"]
sql_delete_found = False
for p in ask_patterns:
    if "delete" in p["pattern"].lower() and "from" in p["pattern"].lower():
        sql_delete_found = True
        check("SQL DELETE pattern preserved",
              p["pattern"] == r"(?i)delete\s+from\s+\w+(?:\s*;|\s*$|\s+--)",
              f"Got: {p['pattern']!r}")
        break
check("SQL DELETE pattern found in ask list", sql_delete_found)

# 5c: del\s+ ask pattern not modified
del_ask_found = False
for p in ask_patterns:
    if p["pattern"] == r"(?i)del\s+(?:/[sq]\s+)*":
        del_ask_found = True
        check("del\\s+ ask pattern preserved", True)
        break
check("del\\s+ ask pattern found in ask list", del_ask_found)


# ============================================================
# STEP 6: Edge cases and tricky scenarios
# ============================================================
section("STEP 6: EDGE CASES AND TRICKY SCENARIOS")

pat_claude = json_claude

# Word boundary test: "deleting" should NOT match
check("'deleting .claude/x' is ALLOWED (word boundary blocks 'deleting')",
      re.search(pat_claude, "deleting .claude/x") is None)

# Word boundary test: "deleted" should NOT match
check("'deleted .claude/x' is ALLOWED (word boundary blocks 'deleted')",
      re.search(pat_claude, "deleted .claude/x") is None)

# "deletion" SHOULD match (it's in the alternation)
check("'deletion .claude/x' is BLOCKED (deletion in alternation)",
      re.search(pat_claude, "deletion .claude/x") is not None)

# Case insensitivity
check("'RM -rf .claude/' is BLOCKED (case insensitive)",
      re.search(pat_claude, "RM -rf .claude/") is not None)
check("'DEL .claude/config' is BLOCKED (case insensitive)",
      re.search(pat_claude, "DEL .claude/config") is not None)
check("'Delete .claude/config' is BLOCKED (case insensitive)",
      re.search(pat_claude, "Delete .claude/config") is not None)

# Backtick separator
check("'`rm .claude/x`' is BLOCKED (backtick separator)",
      re.search(pat_claude, "`rm .claude/x`") is not None)

# Semicolon with space
check("'echo x;  rm .claude/x' is BLOCKED (semicolon + spaces)",
      re.search(pat_claude, "echo x;  rm .claude/x") is not None)

# Pipe
check("'echo x | rm .claude/x' is BLOCKED (pipe separator)",
      re.search(pat_claude, "echo x | rm .claude/x") is not None)

# Double ampersand - the second & satisfies [;|&`(]
check("'echo x && rm .claude/x' is BLOCKED (&& separator)",
      re.search(pat_claude, "echo x && rm .claude/x") is not None)

# Target followed by semicolon (terminator)
check("'rm .claude; echo done' is BLOCKED (.claude followed by ;)",
      re.search(pat_claude, "rm .claude; echo done") is not None)

# Target followed by pipe (terminator)
check("'rm .claude | true' is BLOCKED (.claude followed by |)",
      re.search(pat_claude, "rm .claude | true") is not None)

# Target at end of string
check("'rm .claude' is BLOCKED (.claude at end of string)",
      re.search(pat_claude, "rm .claude") is not None)

# Target followed by closing paren
check("'(rm .claude)' is BLOCKED (.claude followed by ))",
      re.search(pat_claude, "(rm .claude)") is not None)

# No whitespace after command = no match (requires \s+)
check("'rm.claude' is ALLOWED (no space after rm)",
      re.search(pat_claude, "rm.claude") is None)

# Subcommand false positive: git delete (not a real git subcommand)
# This should be ALLOWED because 'git' is the command, not 'delete'
check("'git delete .claude/x' is ALLOWED (git is the command, not delete)",
      re.search(pat_claude, "git delete .claude/x") is None,
      "Hmm, 'delete' appears after space which is not a separator")

# Tricky: "npm run delete .claude/test"
check("'npm run delete .claude/test' is ALLOWED (npm is the command)",
      re.search(pat_claude, "npm run delete .claude/test") is None)


# ============================================================
# SUMMARY
# ============================================================
section("SUMMARY")
total = PASS_COUNT + FAIL_COUNT
print(f"\nTotal: {total} checks, {PASS_COUNT} passed, {FAIL_COUNT} failed")
if FAIL_COUNT == 0:
    print("\nALL CHECKS PASSED")
else:
    print(f"\n{FAIL_COUNT} CHECKS FAILED")
    sys.exit(1)
