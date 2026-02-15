#!/usr/bin/env python3
"""Check F5 broken symlink archiving behavior."""
import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import archive_files

print("=== F5: Broken Symlink Trace ===")
with tempfile.TemporaryDirectory() as tmpdir:
    project = Path(tmpdir) / "project"
    project.mkdir()

    broken_link = project / "broken.txt"
    os.symlink("/nonexistent/path/file", broken_link)

    # archive_files logic:
    # 1. file_path.is_file() -> False for broken symlinks on Linux
    #    BUT: Python docs say is_file() returns True for symlinks pointing to files
    #    For BROKEN symlinks, is_file() returns False
    # 2. file_path.is_dir() -> False
    # 3. Neither branch -> no copy/symlink action
    # BUT: archived.append() is only called after the copy, so should be empty

    # Let me check what file_size is calculated as
    # file_path.stat() would follow the symlink and fail
    # but the code does: if file_path.is_file(): file_size = file_path.stat().st_size
    # Since is_file() is False, stat() is never called

    # Then why did my previous test show 1 archived file?
    # Let me re-run carefully
    archive_dir, archived = archive_files([broken_link], project)
    print(f"  archive_dir: {archive_dir}")
    print(f"  archived count: {len(archived)}")
    for orig, arch in archived:
        print(f"    {orig} -> {arch}")
        print(f"    archived exists: {arch.exists()}")
        print(f"    archived islink: {os.path.islink(arch)}")
        if os.path.islink(arch):
            print(f"    archived target: {os.readlink(arch)}")

    # Hmm, the file_size for broken symlink:
    # is_file() returns False, is_dir() returns False
    # so file_size stays 0
    # Then: size check passes (0 < 100MB)
    # total size check passes
    # Then: file_path.is_file() -> False, skip copy
    #       file_path.is_dir() -> False, skip copytree
    # BUT archived.append() is AFTER the if/elif, so broken symlinks shouldn't be appended

    # Wait -- looking at the code more carefully
    # The is_file() branch has the islink check inside it
    # If is_file() is False AND is_dir() is False, we fall through
    # and archived.append((file_path, target_path)) is still reached!

    # Let me check the code structure
    print()
    print("  Code flow analysis:")
    print(f"    broken_link.is_file() = {broken_link.is_file()}")
    print(f"    broken_link.is_dir() = {broken_link.is_dir()}")
    print("    Neither branch runs -> but archived.append IS reached")
    print("    This means broken symlinks are 'archived' without being copied!")
    print("    The archive log will reference a non-existent file")

    if archived:
        _, arch_path = archived[0]
        print(f"    Archive path exists: {arch_path.exists()}")
        print(f"    Archive path lexists: {os.path.lexists(arch_path)}")

    shutil.rmtree(project / "_archive", ignore_errors=True)

print()
print("=== F5: Code structure check ===")
# Read the actual archive code to verify
with open(str(_bootstrap._REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")) as f:
    lines = f.readlines()

# Find the archive_files function and check the if/elif/append structure
in_archive = False
for i, line in enumerate(lines, 1):
    if "if file_path.is_file():" in line:
        in_archive = True
        start = i
    if in_archive and i <= start + 15:
        print(f"  Line {i}: {line.rstrip()}")
    if in_archive and "archived.append" in line:
        print(f"  >>> archived.append at line {i}")
        # Check indentation - is it inside the if/elif or outside?
        indent = len(line) - len(line.lstrip())
        print(f"      indent level: {indent}")
        in_archive = False
        break

print()
print("=== Done ===")
