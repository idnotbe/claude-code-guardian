#!/usr/bin/env python3
"""Test suite for bash guardian bypass protection (Phases 2-6).

Run: python3 /home/idnotbe/projects/ops/temp/test_guardian_bypass.py
"""

import sys
import os

sys.path.insert(0, '/home/idnotbe/projects/claude-code-guardian/hooks/scripts')

# Need to set env vars before importing
os.environ.setdefault('CLAUDE_PROJECT_DIR', '/tmp/test-project')

from bash_guardian import (
    split_commands,
    glob_to_literals,
    scan_protected_paths,
    is_write_command,
    is_delete_command,
    _is_inside_quotes,
    _stronger_verdict,
)

passed = 0
failed = 0

def test(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name}")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {actual}")


# ============================================================
# Phase 2: split_commands tests
# ============================================================

# Basic splitting
test("single command", split_commands("echo hello"), ["echo hello"])
test("semicolon", split_commands("echo a; echo b"), ["echo a", "echo b"])
test("and-then", split_commands("echo a && echo b"), ["echo a", "echo b"])
test("or-else", split_commands("echo a || echo b"), ["echo a", "echo b"])
test("pipe", split_commands("cat file | grep x"), ["cat file", "grep x"])
test("background (M-4)", split_commands("echo a & echo b"), ["echo a", "echo b"])
test("newline", split_commands("echo a\necho b"), ["echo a", "echo b"])

# Quote handling - should NOT split
test("double-quoted semicolon", split_commands('echo "a;b"'), ['echo "a;b"'])
test("single-quoted semicolon", split_commands("echo 'a;b'"), ["echo 'a;b'"])
test("double-quoted pipe", split_commands('echo "a|b"'), ['echo "a|b"'])

# C-2: Backslash escape - \; should be literal, not delimiter
test("escaped semicolon", split_commands("echo a\\; echo b"), ["echo a\\; echo b"])

# C-2: Backtick handling
test("backtick simple", split_commands("echo `date`"), ["echo `date`"])

# Subshell handling
test("command substitution", split_commands("echo $(echo hello)"), ["echo $(echo hello)"])
test("process sub", split_commands("cat <(echo hello)"), ["cat <(echo hello)"])

# Complex compound
test("three commands", split_commands("a; b && c"), ["a", "b", "c"])
test("empty between", split_commands("a;; b"), ["a", "b"])

# Codex review fix: & in redirection context should NOT split
test("redirect &>", split_commands("cmd &> /dev/null"), ["cmd &> /dev/null"])
test("redirect 2>&1", split_commands("cmd 2>&1"), ["cmd 2>&1"])
test("redirect >&2", split_commands("echo err >&2"), ["echo err >&2"])
# But standalone & still splits
test("background &", split_commands("sleep 5 & echo done"), ["sleep 5", "echo done"])

# Gemini review fix: brace expansion in scan
# (tested in scan_protected_paths section below)

# ============================================================
# Phase 5: glob_to_literals tests (C-3 fix)
# ============================================================

# Exact matches
test("exact .env", glob_to_literals(".env"), [".env"])
test("exact id_rsa", glob_to_literals("id_rsa"), ["id_rsa"])
test("exact id_ed25519", glob_to_literals("id_ed25519"), ["id_ed25519"])

# Prefix matches
test("prefix .env.*", glob_to_literals(".env.*"), [".env."])
test("prefix id_rsa.*", glob_to_literals("id_rsa.*"), ["id_rsa."])
test("prefix id_ed25519.*", glob_to_literals("id_ed25519.*"), ["id_ed25519."])

# Suffix matches (distinctive)
test("suffix *.pem", glob_to_literals("*.pem"), [".pem"])
test("suffix *.pfx", glob_to_literals("*.pfx"), [".pfx"])
test("suffix *.p12", glob_to_literals("*.p12"), [".p12"])
test("suffix *.tfstate", glob_to_literals("*.tfstate"), [".tfstate"])
test("suffix *.tfstate.backup", glob_to_literals("*.tfstate.backup"), [".tfstate.backup"])  # distinctive suffix

# C-3 fix: Too generic patterns -> empty
test("generic *.env", glob_to_literals("*.env"), [])
test("generic *.key", glob_to_literals("*.key"), [])
test("generic *.log", glob_to_literals("*.log"), [])
test("wildcard middle *cred*.json", glob_to_literals("*credentials*.json"), [])
test("wildcard middle *svc*.json", glob_to_literals("*serviceAccount*.json"), [])

# ============================================================
# Phase 5: scan_protected_paths tests
# ============================================================

test_config = {
    "zeroAccessPaths": [
        ".env",
        ".env.*",
        ".env*.local",
        "*.pem",
        "id_rsa",
        "id_rsa.*",
    ],
    "bashPathScan": {
        "enabled": True,
        "exactMatchAction": "deny",
        "patternMatchAction": "ask",
    },
}

# Should deny (exact match)
v, r = scan_protected_paths("cat .env", test_config)
test("scan: cat .env -> deny", v, "deny")

# I-4 fix: ./.env should also be caught (/ in boundary)
v, r = scan_protected_paths("cat ./.env", test_config)
test("scan: cat ./.env -> deny (I-4)", v, "deny")

# Prefix pattern match -> ask
v, r = scan_protected_paths("cat .env.local", test_config)
test("scan: cat .env.local -> ask (prefix)", v, "ask")

# Suffix pattern match -> ask
v, r = scan_protected_paths("ls server.pem", test_config)
test("scan: ls server.pem -> ask (suffix)", v, "ask")

# Should allow (no match)
v, r = scan_protected_paths("ls -la", test_config)
test("scan: ls -la -> allow", v, "allow")

v, r = scan_protected_paths("git status", test_config)
test("scan: git status -> allow", v, "allow")

v, r = scan_protected_paths("npm install express", test_config)
test("scan: npm install -> allow", v, "allow")

# Gemini review fix: brace expansion should be caught
v, r = scan_protected_paths("cp {id_rsa,backup} dest", test_config)
test("scan: brace expansion {id_rsa,...} -> deny", v, "deny")

v, r = scan_protected_paths("cp {backup,id_rsa} dest", test_config)
test("scan: brace expansion {...,id_rsa} -> deny", v, "deny")

# Disabled scanning
disabled_config = dict(test_config, bashPathScan={"enabled": False})
v, r = scan_protected_paths("cat .env", disabled_config)
test("scan: disabled -> allow", v, "allow")

# ============================================================
# Phase 4: Enhanced write/delete detection
# ============================================================

# Write detection
test("write: sed -i", is_write_command("sed -i 's/x/y/' file"), True)
test("write: cp", is_write_command("cp source dest"), True)
test("write: dd", is_write_command("dd if=/dev/zero of=file"), True)
test("write: rsync", is_write_command("rsync src dest"), True)
test("write: patch", is_write_command("patch file.txt"), True)
test("write: colon truncate", is_write_command(": > file"), True)
test("write: tee", is_write_command("tee output.txt"), True)
test("write: redirect", is_write_command("echo x > file"), True)

# I-2 fix: install should NOT be write
test("write: npm install (I-2)", is_write_command("npm install express"), False)
test("write: pip install (I-2)", is_write_command("pip install requests"), False)

# Non-write commands
test("not write: ls", is_write_command("ls -la"), False)
test("not write: cat", is_write_command("cat file"), False)
test("not write: grep", is_write_command("grep pattern file"), False)
test("not write: sed (no -i)", is_write_command("sed 's/x/y/' file"), False)

# Delete detection
test("delete: rm", is_delete_command("rm file"), True)
test("delete: mv /dev/null", is_delete_command("mv file /dev/null"), True)

# ============================================================
# Quote awareness (_is_inside_quotes)
# ============================================================

test("quotes: > outside", _is_inside_quotes('echo x > file', 7), False)
test("quotes: > inside double", _is_inside_quotes('echo "x > y"', 9), True)
test("quotes: > inside single", _is_inside_quotes("echo 'x > y'", 9), True)
test("quotes: > after close", _is_inside_quotes('echo "x" > file', 9), False)

# ============================================================
# Verdict aggregation
# ============================================================

test("verdict: deny > ask", _stronger_verdict(("ask", "r1"), ("deny", "r2")), ("deny", "r2"))
test("verdict: deny > allow", _stronger_verdict(("allow", ""), ("deny", "r")), ("deny", "r"))
test("verdict: ask > allow", _stronger_verdict(("allow", ""), ("ask", "r")), ("ask", "r"))
test("verdict: deny stays", _stronger_verdict(("deny", "r1"), ("ask", "r2")), ("deny", "r1"))
test("verdict: ask stays over allow", _stronger_verdict(("ask", "r1"), ("allow", "")), ("ask", "r1"))

# ============================================================
# Summary
# ============================================================

print(f"\n{'='*50}")
print(f"Tests passed: {passed}")
print(f"Tests failed: {failed}")
print(f"Total: {passed + failed}")
if failed == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"FAILURES: {failed}")
    sys.exit(1)
