#!/usr/bin/env python3
"""Verify Gemini's quoted-path bypass finding."""
import re

pat = r"""(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)"""

# Gemini's finding: quoted paths
test_cases = [
    ('rm ".claude"', "quoted with double quotes"),
    ("rm '.claude'", "quoted with single quotes"),
    ('rm ".claude/"', "quoted with trailing slash"),
    ('rm -rf ".claude"', "rm -rf with quotes"),
]

print("Testing Gemini finding: quoted path bypass")
print()
for cmd, desc in test_cases:
    m = re.search(pat, cmd)
    status = "BLOCKED" if m else "ALLOWED"
    print(f"  {status}: {repr(cmd)} ({desc})")

print()
print("Note: Is this a PRE-EXISTING gap?")
old_pat = r"""(?i)(?:rm|rmdir|del|remove-item).*\.claude(?:\s|/|$)"""
for cmd, desc in test_cases:
    m = re.search(old_pat, cmd)
    status = "BLOCKED" if m else "ALLOWED"
    print(f"  OLD {status}: {repr(cmd)} ({desc})")

print()
# Actually, wait. Let me look at this more carefully.
# `rm ".claude"` - the regex .* will consume the opening quote,
# then \.claude matches .claude, then the terminator needs to match "
# Since " is NOT in the terminator, the full match at that position fails.
# BUT the regex engine backtracks .* to try other positions...
# Actually no. .* is greedy and will consume as much as possible,
# but the engine will backtrack to find \.claude.
# The key question: can the engine find \.claude followed by a valid terminator?

# In `rm ".claude"`:
# After matching `rm `, .* tries to consume `".claude"`
# Then \.claude needs to match but nothing is left
# Backtrack: .* = `".claude` -> \.claude needs `"` -> no
# Backtrack: .* = `".claud` -> \.claude needs `e"` -> no
# Backtrack: .* = `".clau` -> no...
# ...
# Backtrack: .* = `"` -> \.claude matches `.claude`, next char is `"` -> not in terminator -> fail
# Backtrack: .* = `` (empty) -> \.claude needs to match `".claude"` -> `.` matches `"`, then `claude` matches `claude` -> next char is `"` -> not in terminator -> fail

# Wait! `.` in \.claude is escaped (literal dot). So `\.claude` requires literal `.claude`.
# Let me re-check: .* = empty -> next is `"` which is not `.` -> fail.
# .* = `"` -> next is `.claude"` -> `\.claude` matches `.claude` -> next is `"` -> not in terminator -> fail.
#
# So the match DOES fail. The terminator is indeed missing `"` and `'`.

# But let's check: is this the SAME behavior as the OLD pattern?
print("Both old and new patterns have the same gap with quoted paths.")
print("This is NOT a regression - it's a pre-existing limitation.")
print("The spec did not include quotes in the terminator, and this fix")
print("is scoped to command-position anchoring, not terminator expansion.")
