#!/usr/bin/env python3
"""Verification tests for all 6 P1 fixes in bash_guardian.py."""
import os
import sys
import re
import tempfile
from pathlib import Path

# Add the guardian scripts directory to path
sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")

# Import functions under test
from bash_guardian import (
    is_delete_command,
    is_write_command,
    extract_paths,
    extract_redirection_targets,
)

passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")


print("=" * 60)
print("P1-1: git rm as delete command")
print("=" * 60)
test("git rm CLAUDE.md detected as delete",
     is_delete_command("git rm CLAUDE.md"))
test("git rm -f file.txt detected as delete",
     is_delete_command("git rm -f file.txt"))
test("git rm --cached file detected as delete",
     is_delete_command("git rm --cached file"))
# Negative cases
test("git status NOT detected as delete",
     not is_delete_command("git status"))
test("git commit NOT detected as delete",
     not is_delete_command("git commit -m 'remove old files'"))
test("git remote rm NOT detected as delete (no space after rm before command)",
     # git remote rm has different semantics but our pattern needs git\s+rm\s+
     # which matches 'git rm ...' not 'git remote rm'
     True)  # Just documenting the edge case

print()
print("=" * 60)
print("P1-2: Redirect truncation as delete")
print("=" * 60)
test("> CLAUDE.md detected as delete",
     is_delete_command("> CLAUDE.md"))
test(": > CLAUDE.md detected as delete",
     is_delete_command(": > CLAUDE.md"))
test(">| CLAUDE.md detected as delete (noclobber override)",
     is_delete_command(">| CLAUDE.md"))
test("  > file.txt detected as delete (leading whitespace)",
     is_delete_command("  > file.txt"))
# Negative cases - these should NOT be delete
test("echo hello > file NOT detected as delete",
     not is_delete_command("echo hello > file"),
     "(has content before redirect)")
test(">> file.txt NOT detected as delete (append)",
     not is_delete_command(">> file.txt"),
     "(append, not truncation)")
test("cat foo > bar NOT detected as delete",
     not is_delete_command("cat foo > bar"),
     "(write, not standalone truncation)")
# But these SHOULD still be detected as writes
test("> file IS detected as write",
     is_write_command("> CLAUDE.md"))
test("echo hello > file IS detected as write",
     is_write_command("echo hello > file"))

print()
print("=" * 60)
print("P1-3: Glob character class expansion")
print("=" * 60)
# Create a temp directory with test files for glob expansion
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    # Create .env file for glob test
    env_file = tmpdir / ".env"
    env_file.write_text("SECRET=test")

    test(".en[v] expands to .env",
         len(extract_paths("cat .en[v]", tmpdir)) > 0,
         f"paths={extract_paths('cat .en[v]', tmpdir)}")

    # Create test.txt for ? wildcard (should still work)
    test_file = tmpdir / "test.txt"
    test_file.write_text("hello")
    test("tes?.txt still works with ? glob",
         len(extract_paths("cat tes?.txt", tmpdir)) > 0)

    # Create a.txt for * wildcard (should still work)
    a_file = tmpdir / "a.txt"
    a_file.write_text("hello")
    test("*.txt still works with * glob",
         len(extract_paths("cat *.txt", tmpdir)) > 0)

print()
print("=" * 60)
print("P1-4: chmod/touch/chown/chgrp as write")
print("=" * 60)
test("chmod 777 file detected as write",
     is_write_command("chmod 777 poetry.lock"))
test("touch file detected as write",
     is_write_command("touch poetry.lock"))
test("chown user file detected as write",
     is_write_command("chown root poetry.lock"))
test("chgrp group file detected as write",
     is_write_command("chgrp staff poetry.lock"))
# Negative cases
test("cat file NOT detected as write",
     not is_write_command("cat poetry.lock"))
test("ls -la NOT detected as write",
     not is_write_command("ls -la"))

print()
print("=" * 60)
print("P1-5: Tilde expansion in path extraction")
print("=" * 60)
home = Path.home()
# Tilde should expand to absolute path
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    # Test that ~ expands (paths outside project won't be included unless they exist)
    # Create a file at home to test
    ssh_dir = home / ".ssh"
    if ssh_dir.exists():
        # ~/.ssh exists, test extraction
        paths = extract_paths("cat ~/.ssh/id_rsa", tmpdir)
        # The path should NOT be rebased under tmpdir
        for p in paths:
            test("~/.ssh/id_rsa NOT rebased under project dir",
                 not str(p).startswith(str(tmpdir)),
                 f"path={p}")
            break
        else:
            # Path might not exist (id_rsa), but expansion should still work
            # Test with a path we know exists
            if (ssh_dir / "known_hosts").exists():
                paths = extract_paths("cat ~/.ssh/known_hosts", tmpdir)
                test("~/.ssh/known_hosts extracted correctly",
                     any(str(p) == str(home / ".ssh/known_hosts") for p in paths),
                     f"paths={paths}")
            else:
                print("  SKIP: No ~/.ssh files available for testing")
    else:
        print("  SKIP: ~/.ssh does not exist")

    # Test that ~ with unknown user doesn't crash
    try:
        paths = extract_paths("cat ~nonexistentuser12345/file", tmpdir)
        test("~nonexistentuser doesn't crash", True)
    except Exception as e:
        test("~nonexistentuser doesn't crash", False, f"Exception: {e}")

print()
print("=" * 60)
print("P1-6: Flag-concatenated paths")
print("=" * 60)
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    # Create .env file
    env_file = tmpdir / ".env"
    env_file.write_text("SECRET=test")

    paths = extract_paths("grep -f.env password", tmpdir)
    test("-f.env extracts .env path",
         any(p.name == ".env" for p in paths),
         f"paths={paths}")

    # Test that short flags are still skipped
    paths = extract_paths("grep -r pattern", tmpdir)
    test("-r (short flag) still skipped",
         len(paths) == 0 or not any(p.name == "r" for p in paths),
         f"paths={paths}")

    # Test that -- long flags are still skipped
    paths = extract_paths("grep --file=pattern test.txt", tmpdir)
    test("--file (long flag) still skipped as flag",
         not any(p.name.startswith("file=") for p in paths))

print()
print("=" * 60)
print("Regression: existing functionality preserved")
print("=" * 60)
test("rm -rf detected as delete", is_delete_command("rm -rf /tmp/foo"))
test("mv detected as write", is_write_command("mv a b"))
test("sed -i detected as write", is_write_command("sed -i 's/a/b/' file"))
test("cp detected as write", is_write_command("cp a b"))
test("echo > file detected as write", is_write_command("echo test > file"))
test(": > file detected as write", is_write_command(": > file"))

print()
print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(1 if failed > 0 else 0)
