#!/usr/bin/env python3
"""Verify whether the extra backslash in fallback patterns causes functional difference."""
import re
import sys
import json

sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")
import _guardian_utils

fb_git = _guardian_utils._FALLBACK_CONFIG["bashToolPatterns"]["block"][1]["pattern"]

with open("/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json") as f:
    gd = json.load(f)
gd_git = gd["bashToolPatterns"]["block"][1]["pattern"]

print("Fallback pattern (repr):", repr(fb_git))
print("JSON pattern (repr):    ", repr(gd_git))
print()

# In the fallback (Python raw string), the terminator char class is: [;&|)`'\"]
# The \" inside a character class in regex is just a literal " (backslash is ignored inside [])
# In the JSON version, it's: [;&|)`'"]
# Both match the same set of characters

# Verify by comparing the compiled character classes
test_cases = [
    'rm ".git/config"',
    "rm '.git/config'",
    "rm .git",
    "{ rm .git; }",
    "  rm .git",
    "rm .git/hooks",
    "  rm .git|echo hi",
]

print("Functional comparison:")
all_same = True
for cmd in test_cases:
    fb_match = bool(re.search(fb_git, cmd, re.DOTALL))
    gd_match = bool(re.search(gd_git, cmd, re.DOTALL))
    status = "SAME" if fb_match == gd_match else "DIFF!"
    if fb_match != gd_match:
        all_same = False
    print(f"  {status} | fb={fb_match} gd={gd_match} | {cmd!r}")

print()
if all_same:
    print("RESULT: Extra backslash is cosmetic only - NO functional difference")
    print("The \\\" inside [...] in regex is treated as literal '\"'")
else:
    print("RESULT: FUNCTIONAL DIFFERENCE DETECTED - patterns behave differently!")

# Also verify: what does \\" mean inside a character class?
# In regex, inside [], most special chars lose meaning.
# \\" is just an escaped " which matches literal "
pat_a = re.compile(r'[\'"]')  # matches ' or "
pat_b = re.compile(r'[\'\\"]')  # matches ' or \ or "
# Wait, that's different! \\ inside [] matches a literal backslash!
print()
print("IMPORTANT: Testing if \\\\ inside [] matches backslash:")
print(f"  r'[\\'\"  ]' matches backslash: {bool(pat_a.search(chr(92)))}")
print(f"  r'[\\'\\\\\"  ]' matches backslash: {bool(pat_b.search(chr(92)))}")
print()

# Let's check precisely what the fallback pattern's char class contains
# The fallback has: [;&|)`'\"]
# In a Python raw string r"...", this is the literal characters: [ ; & | ) ` ' \ " ]
# So the character class matches: ; & | ) ` ' \ "
#
# The JSON/spec has: [;&|)`'"]
# This matches: ; & | ) ` ' "
#
# The DIFFERENCE: fallback also matches backslash \ in the terminator!
# This is a very minor difference but technically the fallback is slightly more restrictive
# (it will also terminate on a backslash character, which the spec pattern won't)

print("Checking if fallback matches backslash as terminator:")
test_bs = "rm .git\\"
fb_match_bs = bool(re.search(fb_git, test_bs, re.DOTALL))
gd_match_bs = bool(re.search(gd_git, test_bs, re.DOTALL))
print(f"  Command: {test_bs!r}")
print(f"  Fallback matches: {fb_match_bs}")
print(f"  JSON matches: {gd_match_bs}")
if fb_match_bs != gd_match_bs:
    print("  >>> BEHAVIORAL DIFFERENCE: fallback treats backslash as terminator, spec does not")
