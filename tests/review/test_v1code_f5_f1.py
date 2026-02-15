#!/usr/bin/env python3
"""Additional edge case tests for F5 and F1."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import archive_files

print("=== F5: Broken Symlink Archiving ===")
with tempfile.TemporaryDirectory() as tmpdir:
    project = Path(tmpdir) / "project"
    project.mkdir()

    broken_link = project / "broken.txt"
    os.symlink("/nonexistent/path/file", broken_link)

    # Check what archive_files does with the broken symlink
    # The code flow:
    # 1. file_path.is_file() -> False for broken symlinks
    # 2. file_path.is_dir() -> False
    # 3. Neither branch executes -> file not archived
    print(f"  broken_link.is_file() = {broken_link.is_file()}")
    print(f"  broken_link.is_dir() = {broken_link.is_dir()}")
    print(f"  broken_link.exists() = {broken_link.exists()}")
    print(f"  os.path.islink(broken_link) = {os.path.islink(broken_link)}")
    print(f"  os.path.lexists(broken_link) = {os.path.lexists(broken_link)}")

    archive_dir, archived = archive_files([broken_link], project)
    print(f"  Archived: {len(archived)} files")
    if not archived:
        print("  ISSUE: Broken symlinks silently skipped (not archived)")
        print("  This is a MINOR issue - broken symlinks rarely contain valuable data")
        print("  But the user might expect them to be preserved")

    # Also check: what about the file_size calculation for broken symlinks?
    # file_path.stat() would fail for broken symlinks (FileNotFoundError)
    # But the code checks .is_file() first, which returns False, so stat() is never called
    print("  Stat() safety: is_file() check prevents stat() on broken symlinks -> OK")

    # Cleanup
    import shutil
    shutil.rmtree(project / "_archive", ignore_errors=True)

print()
print("=== F5: Symlink to sensitive file ===")
with tempfile.TemporaryDirectory() as tmpdir:
    project = Path(tmpdir) / "project"
    project.mkdir()

    # Symlink pointing to /etc/passwd (exists, readable)
    sensitive_link = project / "passwd_link"
    os.symlink("/etc/passwd", sensitive_link)

    archive_dir, archived = archive_files([sensitive_link], project)
    if archived:
        _, archived_path = archived[0]
        is_link = os.path.islink(archived_path)
        if is_link:
            target = os.readlink(archived_path)
            print(f"  Sensitive symlink preserved as link -> {target} (F5 WORKING)")
        else:
            print("  FAIL: Sensitive symlink was dereferenced (data leaked to archive)")

    import shutil
    shutil.rmtree(project / "_archive", ignore_errors=True)

print()
print("=== F1: Edge case - delete command with redirection target only ===")
# If a delete command only has redirection targets (no argument paths),
# the F1 check uses sub_paths which includes both extract_paths AND extract_redirection_targets
# So this should be handled correctly
from bash_guardian import extract_paths, extract_redirection_targets, is_delete_command
with tempfile.TemporaryDirectory() as tmpdir:
    cmd = "> file.txt"  # truncation delete, target is redirection
    is_del = is_delete_command(cmd)
    paths = extract_paths(cmd, Path(tmpdir), allow_nonexistent=True)
    redir = extract_redirection_targets(cmd, Path(tmpdir))
    sub_paths = paths + redir
    print(f"  '{cmd}': is_delete={is_del}, paths={len(paths)}, redir={len(redir)}, sub_paths={len(sub_paths)}")
    if is_del and sub_paths:
        print("  OK: truncation has redir target, F1 does not trigger (correct)")
    elif is_del and not sub_paths:
        print("  F1 triggers: truncation with no resolvable target")

print()
print("=== F3: split_commands + >| interaction severity ===")
from bash_guardian import split_commands
# How often does >| appear in practice?
# >| is the clobber operator, used when set -o noclobber is active
# It's relatively rare. The split at | is a pre-existing limitation.
# After split, "cat file >" and "output.txt" are separate sub-commands.
# "cat file >" has a dangling redirect that extract_redirection_targets won't extract
# because the regex needs a target after >
# "output.txt" looks like a plain command, not flagged.
# NET EFFECT: >| in a compound command loses detection capability
# But is_delete_command on the ORIGINAL (unsplit) command catches the pattern
# Wait - the original command goes through split_commands first, then each sub is analyzed
# The Layer 0 block/ask patterns run BEFORE split, so they catch >| if matched

# Check: does the original pre-split command get checked by Layer 0?
# Looking at main(): match_block_patterns(command) and match_ask_patterns(command)
# run on the full command BEFORE split_commands
# But the truncation pattern >(?!>)\|? is only in is_delete_command, not in block/ask patterns
# So: >| IS split by split_commands, and detection is lost in Layer 2+
print("  >| split interaction:")
print("  Layer 0 (block/ask patterns): runs on FULL command -> does NOT have >| pattern")
print("  Layer 1 (path scan): runs on FULL command -> might catch protected path")
print("  Layer 2+ (split): >| is split at |, detection lost")
print("  Net: >| clobber to protected paths caught by Layer 1 scan only")
print("  Severity: MEDIUM - the F3 fix is less effective than intended in compound commands")

print()
print("=== Done ===")
