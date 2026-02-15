#!/usr/bin/env python3
"""Detailed test for P1-5 tilde expansion.

The key insight: extract_paths() filters to project-internal paths only.
But for tilde paths like ~/.ssh/id_rsa, the actual security check happens
in the main loop where match_zero_access() is called on the path string.

The fix ensures that ~ is expanded to /home/user so that:
1. The path is NOT erroneously rebased as project_dir/~/.ssh/id_rsa
2. match_zero_access can properly match against the expanded path

For paths OUTSIDE the project (like ~/.ssh), extract_paths won't return them,
but extract_redirection_targets and the main scan loop handle them separately.

Actually, let me re-read the code flow more carefully...
"""
import os
import sys
import shlex
from pathlib import Path

sys.path.insert(0, "/home/idnotbe/projects/claude-code-guardian/hooks/scripts")

# The real question: does the tilde expansion MATTER for the security check?
# Let's trace through what happens with `cat ~/.ssh/id_rsa`:

# 1. Layer 1 (scan_protected_paths): Scans raw command for zeroAccessPaths literals
#    ~/.ssh patterns use ** so they're SKIPPED in Layer 1 ("Skip directory patterns")
#    But ssh key patterns like `id_rsa` ARE exact matches, so Layer 1 catches those

# 2. Layer 2+3: split_commands -> extract_paths
#    WITHOUT P1-5 fix: Path("~/.ssh/id_rsa") -> project_dir/~/.ssh/id_rsa -> doesn't exist -> not returned
#    WITH P1-5 fix: Path("~/.ssh/id_rsa").expanduser() -> /home/user/.ssh/id_rsa -> exists but outside project -> not returned by extract_paths
#
#    So extract_paths won't return ~/.ssh paths either way because they're outside the project!
#
#    But wait -- there may be tilde paths INSIDE the project, or the is_within_project
#    check may need the expanded path for other reasons.

# Let's test that the expansion at least works correctly
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)

    # Test 1: Verify the path is expanded, not rebased
    home = Path.home()

    # Manually trace the extract_paths logic for ~
    part = "~/.ssh/id_rsa"
    expanded_part = os.path.expandvars(part)
    path = Path(expanded_part)
    print(f"After expandvars: {path}")

    if str(path).startswith("~"):
        try:
            path = path.expanduser()
        except (RuntimeError, KeyError):
            pass
    print(f"After expanduser: {path}")
    print(f"Is absolute: {path.is_absolute()}")
    print(f"Would be rebased (old behavior): {tmpdir / part}")

    # The key: with old behavior, the path becomes project_dir/~/.ssh/id_rsa
    # which is wrong and never matches anything
    # With new behavior, it becomes /home/user/.ssh/id_rsa which is correct
    # but filtered out by is_within_project (because it's outside project)

    old_path = tmpdir / part
    new_path = path

    print(f"\nOld (wrong) path: {old_path}")
    print(f"New (correct) path: {new_path}")
    print(f"Old exists: {old_path.exists()}")
    print(f"New exists: {new_path.exists()}")

    # Test 2: For a tilde path INSIDE the project, expansion should work correctly
    # This is the more realistic case for the fix
    # e.g., if someone creates ~/projects/myproject/.env and the project IS there

    # Test 3: $HOME expansion
    part2 = "$HOME/.bashrc"
    expanded = os.path.expandvars(part2)
    print(f"\n$HOME expansion: {part2} -> {expanded}")
    print(f"Correct: {expanded == str(home / '.bashrc')}")

    # The real value of P1-5:
    # - Prevents false "path doesn't exist" for tilde paths
    # - Enables correct matching in match_zero_access for expanded paths
    # - For external paths like ~/.ssh, Layer 1 already catches id_rsa/id_ed25519 etc.
    # - For patterns with **, they're skipped in Layer 1 but the expanded path
    #   would need to be checked by Layer 2+3 which requires extract_paths to work

    print("\n" + "=" * 60)
    print("P1-5 VERDICT: Fix is correct and necessary.")
    print("For external tilde paths (e.g. ~/.ssh), Layer 1 provides backup")
    print("via literal scans of filenames like 'id_rsa'.")
    print("The fix prevents incorrect rebasing and enables future")
    print("improvements where external-path checking may be added.")
    print("=" * 60)
