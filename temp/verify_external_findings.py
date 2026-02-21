#!/usr/bin/env python3
"""Verify external AI findings against the actual pattern behavior."""
import re
import sys
import json

sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")

with open("/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json") as f:
    gd = json.load(f)
pat = gd["bashToolPatterns"]["block"][1]["pattern"]
regex = re.compile(pat, re.DOTALL)

findings = [
    # Finding 1: Redirection bypass
    ("rm .git>log", "Redirection bypass: rm .git>log"),
    ("rm .git<input", "Redirection bypass: rm .git<input"),

    # Finding 2: Newlines (DOTALL mode)
    # Note: the guardian uses re.DOTALL flag via re.search with re.DOTALL
    # Actually, let me check if DOTALL is used...
    ("echo hello\nrm .git", "Newline: echo hello\\nrm .git"),

    # Finding 3: Brace expansion
    ("rm .git{,}", "Brace expansion: rm .git{,}"),

    # Finding 4: $IFS
    ("rm$IFS.git", "$IFS bypass: rm$IFS.git"),

    # Finding 5: sudo prefix
    ("sudo rm .git", "sudo prefix: sudo rm .git"),
    ("command rm .git", "command prefix: command rm .git"),

    # Finding 6: Quoting the verb
    ("\\rm .git", "Escaped rm: \\rm .git"),
    ("'rm' .git", "Quoted rm: 'rm' .git"),
]

print("External AI Findings Verification")
print("=" * 60)
print(f"Pattern: {pat}")
print(f"Flags: re.DOTALL (. matches newline)")
print()

for cmd, desc in findings:
    matched = bool(regex.search(cmd))
    status = "BLOCKED" if matched else "BYPASSED"
    print(f"  [{status}] {desc}")
    print(f"           Command: {cmd!r}")

# Also check: does the guardian actually use DOTALL?
# The pattern is used via re.search() in match_block_patterns()
# Let me check both with and without DOTALL
print()
print("--- Newline handling with/without DOTALL ---")
test_newline = "echo hello\nrm .git"
print(f"  With DOTALL: {bool(re.search(pat, test_newline, re.DOTALL))}")
print(f"  Without DOTALL: {bool(re.search(pat, test_newline))}")
print(f"  With MULTILINE: {bool(re.search(pat, test_newline, re.MULTILINE))}")
print(f"  With DOTALL|MULTILINE: {bool(re.search(pat, test_newline, re.DOTALL | re.MULTILINE))}")

# Check what flags match_block_patterns actually uses
import _guardian_utils
import inspect
src = inspect.getsource(_guardian_utils.match_block_patterns)
print()
print("--- match_block_patterns source excerpt ---")
for line in src.split('\n'):
    if 're.search' in line or 're.compile' in line or 'DOTALL' in line or 'MULTILINE' in line:
        print(f"  {line.strip()}")
