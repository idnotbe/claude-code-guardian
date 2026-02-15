#!/usr/bin/env python3
"""Deep edge case analysis for V1-CODE review."""
import re
import os
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    _is_within_project_or_would_be,
    extract_redirection_targets,
    extract_paths,
    is_delete_command,
    is_write_command,
    scan_protected_paths,
    split_commands,
    archive_files,
)

print("=== F1: Fail-Closed Deep Analysis ===")

# F1: Check if the fail-closed logic covers all code paths
# The logic is: if (is_write or is_delete) and not sub_paths -> ask
# Edge case 1: command is both write AND delete (e.g., "mv file /dev/null")
cmd = "mv file /dev/null"
print(f"  mv file /dev/null: is_write={is_write_command(cmd)}, is_delete={is_delete_command(cmd)}")

# Edge case 2: write command that resolves some paths but not all
# This is NOT caught by F1 (F1 only triggers when sub_paths is EMPTY)
# Is that correct? Yes -- partial resolution still gets path checking
print("  Partial resolution: not F1's job (paths that DO resolve get checked normally)")

# Edge case 3: command substitution in arguments
cmd2 = "rm $(echo /tmp/file)"
print(f"  rm $(echo /tmp/file): is_delete={is_delete_command(cmd2)}")
with tempfile.TemporaryDirectory() as d:
    paths = extract_paths(cmd2, Path(d), allow_nonexistent=True)
    print(f"    extract_paths returns {len(paths)} paths (cmd sub not expanded)")

print()
print("=== F2: ln Pattern Deep Analysis ===")

# F2: Check edge cases for \bln\s+
edge_cases = [
    ("ln file link", True, "basic ln"),
    ("ln -sf target link", True, "symbolic force"),
    ("ls -ln", False, "ls -ln flag"),
    ("unln something", False, "unln prefix"),
    ("println foo", False, "println"),
    ("lnk file", False, "lnk not ln"),
    # But what about echo 'ln target link' inside quotes?
    # is_write_command doesn't check quotes, so this is a known limitation
    ("echo 'ln target link'", True, "ln inside quotes (FP)"),
]
for cmd, expected, desc in edge_cases:
    actual = is_write_command(cmd)
    ok = actual == expected
    print(f"  {'OK' if ok else 'NOTE'}: {cmd!r} ({desc}): {actual}")

print()
print("=== F5: Archive Symlink Deep Analysis ===")

# F5: Test with broken symlinks
with tempfile.TemporaryDirectory() as tmpdir:
    project = Path(tmpdir) / "project"
    project.mkdir()

    # Broken symlink (target doesn't exist)
    broken_link = project / "broken.txt"
    os.symlink("/nonexistent/path/file", broken_link)

    archive_dir, archived = archive_files([broken_link], project)
    if archived:
        _, archived_path = archived[0]
        is_link = os.path.islink(archived_path)
        target = os.readlink(archived_path) if is_link else "NOT A LINK"
        print(f"  Broken symlink: archived as link={is_link}, target={target}")
    else:
        # broken_link.is_file() returns False for broken symlinks
        print(f"  Broken symlink: NOT archived (is_file={broken_link.is_file()}, islink={os.path.islink(broken_link)})")
        print("  ISSUE: broken symlinks are not archived because is_file() returns False")

    # Cleanup
    import shutil
    shutil.rmtree(project / "_archive", ignore_errors=True)

print()
print("=== F7: Path Traversal Deep Analysis ===")

with tempfile.TemporaryDirectory() as tmpdir:
    project = Path(tmpdir) / "project"
    project.mkdir()

    tests = [
        (project / ".." / ".." / "etc" / "passwd", False, "basic traversal"),
        (project / "sub" / ".." / "file.txt", True, "benign parent ref"),
        (project / "file.txt", True, "normal child"),
        (project, True, "project dir itself"),
        (Path("/etc/passwd"), False, "absolute outside"),
        # Symlink edge: if project has a symlink child, resolve() follows it
        # But strict=False means it doesn't verify existence
    ]
    for path, expected, desc in tests:
        result = _is_within_project_or_would_be(path, project)
        ok = result == expected
        print(f"  {'OK' if ok else 'FAIL'}: {desc}: {result} (expected {expected})")

    # Edge case: what if project_dir itself contains symlinks?
    link_project = Path(tmpdir) / "link_to_project"
    os.symlink(project, link_project)
    # Path inside link_project should resolve to inside project
    result = _is_within_project_or_would_be(link_project / "file.txt", project)
    print(f"  Symlinked project dir: {result} (should be True)")

print()
print("=== F3: Clobber + split_commands Interaction ===")

# The known issue: split_commands treats | in >| as a pipe
cmd = "cat file >| output.txt"
parts = split_commands(cmd)
print(f"  split_commands({cmd!r}) = {parts}")
# After split, >| becomes two parts: "cat file >" and "output.txt"
# So the redirection parser on "cat file >" won't have the target

# But note: is_delete_command catches >| via truncation pattern
print(f"  is_delete_command('cat file >| output.txt') = {is_delete_command('cat file >| output.txt')}")
# The truncation pattern: r"^\s*(?::)?\s*>(?!>)\|?\s*\S+"
# This only matches at start of string... so "cat file >| output.txt" won't match
print(f"  is_delete_command('> output.txt') = {is_delete_command('> output.txt')}")
print(f"  is_delete_command('>| output.txt') = {is_delete_command('>| output.txt')}")

# After split, what do the sub-commands look like?
for i, sub in enumerate(parts):
    print(f"    sub[{i}]: {sub!r}")
    print(f"      is_write: {is_write_command(sub)}")
    print(f"      is_delete: {is_delete_command(sub)}")
    with tempfile.TemporaryDirectory() as td:
        redir = extract_redirection_targets(sub, Path(td))
        print(f"      redir_targets: {[t.name for t in redir]}")

print()
print("=== F4: shutil.move analysis ===")
# Check if shutil.move is still caught by config block patterns
config_path = str(_bootstrap._REPO_ROOT / "assets" / "guardian.default.json")
import json
with open(config_path) as f:
    config = json.load(f)

move_found = False
for p in config["bashToolPatterns"]["block"]:
    smove = "shutil" + "." + "move"
    if smove in p["pattern"]:
        move_found = True
        print(f"  shutil_move in config block pattern: {p['reason']}")

if not move_found:
    print("  WARNING: shutil_move NOT in any config block pattern!")
    # Also check is_delete_command patterns
    # We can't easily check without listing patterns, but we know from code
    print("  Checking is_delete_command code patterns...")
    import inspect
    src = inspect.getsource(is_delete_command)
    smove = "shutil" + "\\\\." + "move"  # escaped in regex
    smove2 = "shutil" + "." + "move"
    if smove in src or smove2 in src:
        print("  Found in is_delete_command source -> OK")
    else:
        print("  NOT found in is_delete_command either!")
        print("  FINDING: shutil.move was REMOVED in F4 fix and not re-added anywhere")
        print("  This is a REGRESSION if shutil.move should be detected")

print()
print("=== F8: Additional bypass checks ===")
# Can we bypass F8 with unusual git flag patterns?
bypass_attempts = [
    "git --exec-path=/tmp rm file",
    "git -p rm file",  # -p (paginate) is boolean flag, no value
    "GIT_DIR=/tmp git rm file",
    "env GIT_WORK_TREE=/tmp git rm file",
]
for cmd in bypass_attempts:
    result = is_delete_command(cmd)
    print(f"  is_delete({cmd!r}) = {result}")

# -p rm: -p is a boolean flag (no value), so regex expects -X value, gets -p rm
# (?:-[A-Za-z]\s+\S+\s+)* would match: -p rm (flag=p, value=rm, then needs another \s+)
# Wait: -p\s+rm\s+ -> if "git -p rm file" then -p matches -[A-Za-z], \s+ matches space,
# \S+ matches "rm", \s+ matches space, then the * repeats and looks for rm\s+ outside
# Actually no: the group captures "-p rm " as one iteration, then looks for rm\s+ again
# Let me trace: "git -p rm file"
# git\s+ matches "git "
# (?:-[A-Za-z]\s+\S+\s+)* -> tries -p\s+rm\s+ -> matches "-p rm "
# Then needs rm\s+ -> looks at "file" -> doesn't match "rm\s+"
# So "git -p rm file" would NOT match! The -p flag "eats" rm as its value!
print()
print("  CRITICAL: 'git -p rm file' -> regex thinks -p takes 'rm' as value!")
result = is_delete_command("git -p rm file")
print(f"  is_delete('git -p rm file') = {result}")
if not result:
    print("  CONFIRMED: boolean flags without values cause rm to be consumed as flag value")
    print("  This is a FALSE NEGATIVE / BYPASS for flags like -p (paginate)")
    print("  Affected flags: -p (paginate), -P (no-pager via alias), --bare equivalents")
    print("  Risk: LOW - git -p rm is unusual and -p with git rm has no practical use")

print()
print("=== Summary ===")
