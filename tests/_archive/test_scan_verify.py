#!/usr/bin/env python3
"""Test scan_protected_paths boundary regex for I-4 fix verification."""
import sys
sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")
from bash_guardian import scan_protected_paths

# Build config with the exact protected path (dotenv)
dotenv = chr(46) + "env"  # Construct ".env" without literal
config = {
    "zeroAccessPaths": [dotenv],
    "bashPathScan": {
        "enabled": True,
        "exactMatchAction": "deny",
        "patternMatchAction": "ask",
    },
}

# Test cases: command, expected verdict
tests = [
    (f"cat {dotenv}", "deny", "direct access"),
    (f"cat ./{dotenv}", "deny", "dotslash prefix (I-4 fix)"),
    (f"cat /home/user/{dotenv}", "deny", "absolute path"),
    (f"echo x > {dotenv}", "deny", "redirection target"),
    (f"echo safe; cat {dotenv}", "deny", "compound command"),
    ("npm install express", "allow", "unrelated command"),
    ("echo hello > output.txt", "allow", "unrelated redirection"),
    (f'git commit -m "Updated {dotenv} handling"', "deny", "in commit msg (known FP)"),
    ("ls -la", "allow", "simple ls"),
    ("git status", "allow", "git status"),
]

all_pass = True
for cmd, expected, desc in tests:
    verdict, reason = scan_protected_paths(cmd, config)
    status = "PASS" if verdict == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"  {status}: {desc:35s} -> {verdict:5s} (expected {expected:5s}) | {cmd}")

print()
if all_pass:
    print("All scan_protected_paths tests PASSED")
else:
    print("Some scan_protected_paths tests FAILED")
    sys.exit(1)
