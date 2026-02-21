#!/usr/bin/env python3
"""Check if the extra backslash in fallback terminator class creates a real difference."""
import re
import sys
import json

sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")
import _guardian_utils

fb_git = _guardian_utils._FALLBACK_CONFIG["bashToolPatterns"]["block"][1]["pattern"]

with open("/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json") as f:
    gd = json.load(f)
gd_git = gd["bashToolPatterns"]["block"][1]["pattern"]

# Test case where .git is followed by backslash then more text
# In the fallback, backslash IS in the terminator class, so it terminates the match
# In the spec/JSON, backslash is NOT in the terminator class

edge_cases = [
    "rm .git" + "\\" + "something",  # .git\something
    "rm .git" + "\\" + " ",  # .git\ (space)
    "rm .git" + "\\",  # .git\ at end
]

for cmd in edge_cases:
    fb_match = bool(re.search(fb_git, cmd, re.DOTALL))
    gd_match = bool(re.search(gd_git, cmd, re.DOTALL))
    same = "SAME" if fb_match == gd_match else "DIFF"
    print("{} | fb={} gd={} | {}".format(same, fb_match, gd_match, repr(cmd)))

# Analysis of the character class contents:
# Fallback raw string has: [;&|)`'\"]
# After Python raw string processing: ; & | ) ` ' \ "
# The \\ becomes a literal backslash, and " is literal double-quote
#
# JSON decoded string has: [;&|)`'"]
# After JSON decode: ; & | ) ` ' "
# No backslash in the set
#
# So the fallback pattern also matches backslash as a terminator.
# This makes the fallback SLIGHTLY more restrictive (blocks more).
# From a security standpoint, this is fine (fail-closed direction).
# But it's technically inconsistent with the spec.

print()
print("CONCLUSION:")
print("The fallback has an extra backslash in the terminator class.")
print("In raw string r\"[;&|)`'\\\"]\", the \\\\ is a literal backslash char.")
print("This makes fallback terminate on backslash too (stricter, not a security issue).")
print("For spec compliance, should be r\"[;&|)`'\\\"]\", i.e. just r'[;&|)`' + chr(39) + chr(34) + ']'")
print()

# The REAL question: what is the intended raw string in the _guardian_utils.py source?
# Let me check the actual source file
with open("/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py") as f:
    lines = f.readlines()

# Find the relevant lines
for i, line in enumerate(lines, 1):
    if ".git" in line and "remove-item" in line and "pattern" in line:
        print(f"Line {i}: {line.rstrip()}")
    if ".claude" in line and "remove-item" in line and "pattern" in line:
        print(f"Line {i}: {line.rstrip()}")
    if "_archive" in line and "remove-item" in line and "pattern" in line:
        print(f"Line {i}: {line.rstrip()}")
