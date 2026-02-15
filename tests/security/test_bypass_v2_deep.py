#!/usr/bin/env python3
"""V2 Deep Analysis: Trace bypasses through ALL layers end-to-end.

For each bypass found in the first pass, trace through:
- Layer 0: Block/Ask patterns
- Layer 1: scan_protected_paths (raw string scan)
- Layer 2: split_commands
- Layer 3: extract_paths + extract_redirection_targets
- Layer 4: is_write_command + is_delete_command + match_zero_access/read_only/no_delete

The question: Does ANY layer catch the bypass?
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    split_commands,
    scan_protected_paths,
    is_write_command,
    is_delete_command,
    extract_redirection_targets,
    extract_paths,
)
from _guardian_utils import (
    match_block_patterns,
    match_ask_patterns,
    match_zero_access,
    match_read_only,
    match_no_delete,
)

test_config = {
    "zeroAccessPaths": [
        ".env", ".env.*", ".env*.local", "*.pem", "*.key",
        "id_rsa", "id_rsa.*", "id_ed25519", "id_ed25519.*",
        "secrets.json", "secrets.yaml", "secrets.yml", "*.tfstate",
    ],
    "readOnlyPaths": [
        "package-lock.json", "yarn.lock", "poetry.lock", "*.lock",
    ],
    "noDeletePaths": [
        ".gitignore", "CLAUDE.md", "LICENSE", "LICENSE.*",
        "README.md", "Makefile", "package.json", "pyproject.toml",
    ],
    "bashPathScan": {
        "enabled": True,
        "scanTiers": ["zeroAccess"],
        "exactMatchAction": "deny",
        "patternMatchAction": "ask",
    },
}

project_dir = Path("/tmp/test-project")

# Create test files so extract_paths can find them
project_dir.mkdir(parents=True, exist_ok=True)
test_files = [
    ".env", ".env.local", ".env.production",
    "id_rsa", "server.pem", "secrets.json",
    "poetry.lock", "package-lock.json",
    "CLAUDE.md", "LICENSE", ".gitignore", "README.md",
    "Makefile", "package.json", "pyproject.toml",
]
for f in test_files:
    (project_dir / f).touch()


def trace_command(cmd: str, description: str):
    """Trace a command through all guardian layers."""
    print(f"\n{'='*60}")
    print(f"COMMAND: {cmd}")
    print(f"DESC: {description}")
    print(f"{'='*60}")

    # Layer 0: Block patterns
    blocked, reason = match_block_patterns(cmd)
    print(f"  Layer 0 (block): {'BLOCKED - ' + reason if blocked else 'pass'}")
    if blocked:
        print(f"  RESULT: CAUGHT by Layer 0")
        return "caught", "Layer 0 block"

    # Layer 0b: Ask patterns
    ask, ask_reason = match_ask_patterns(cmd)
    layer0b = f"ASK - {ask_reason}" if ask else "pass"
    print(f"  Layer 0b (ask): {layer0b}")

    # Layer 1: Scan protected paths
    scan_v, scan_r = scan_protected_paths(cmd, test_config)
    print(f"  Layer 1 (scan): {scan_v}" + (f" - {scan_r}" if scan_r else ""))

    # Layer 2: Split commands
    subs = split_commands(cmd)
    print(f"  Layer 2 (split): {len(subs)} sub-commands: {subs}")

    # Layer 3+4: Per-sub-command analysis
    any_caught = False
    for i, sub in enumerate(subs):
        is_w = is_write_command(sub)
        is_d = is_delete_command(sub)
        paths = extract_paths(sub, project_dir, allow_nonexistent=(is_w or is_d))
        redir_paths = extract_redirection_targets(sub, project_dir)
        all_paths = paths + redir_paths

        print(f"  Sub-cmd #{i}: '{sub}'")
        print(f"    write={is_w}, delete={is_d}")
        print(f"    paths={[str(p) for p in paths]}")
        print(f"    redir_paths={[str(p) for p in redir_paths]}")

        for p in all_paths:
            ps = str(p)
            za = match_zero_access(ps)
            ro = match_read_only(ps)
            nd = match_no_delete(ps)
            if za or (is_w and ro) or (is_d and nd):
                print(f"    >>> CAUGHT: {p.name} (zero={za}, ro={ro}, nd={nd})")
                any_caught = True

    # Final verdict
    if scan_v == "deny":
        print(f"  RESULT: CAUGHT by Layer 1 (scan)")
        return "caught", "Layer 1 scan"
    elif any_caught:
        print(f"  RESULT: CAUGHT by Layer 3+4")
        return "caught", "Layer 3+4"
    elif ask:
        print(f"  RESULT: PARTIAL - ask from Layer 0b only")
        return "partial", "Layer 0b ask"
    elif scan_v == "ask":
        print(f"  RESULT: PARTIAL - ask from Layer 1 scan")
        return "partial", "Layer 1 ask"
    else:
        print(f"  RESULT: *** BYPASSED ALL LAYERS ***")
        return "bypassed", "none"


print("=" * 70)
print("V2 DEEP ANALYSIS: Full Layer Trace for Bypass Candidates")
print("=" * 70)

# ===== ZERO-ACCESS BYPASSES =====
print("\n\n### ZERO-ACCESS BYPASS CANDIDATES ###\n")

results = []

# B1: Glob character class
r = trace_command("cat .en[v]", "Glob char class to avoid literal .env")
results.append(("cat .en[v]", "zeroAccess", r))

# B2: Glob question mark
r = trace_command("cat .en?", "Glob ? to avoid literal .env")
results.append(("cat .en?", "zeroAccess", r))

# B3: Hex encoding in $'...'
r = trace_command("cat $'\\x2e\\x65\\x6e\\x76'", "Hex-encoded .env in ANSI-C quotes")
results.append(("cat $'\\x2e\\x65\\x6e\\x76'", "zeroAccess", r))

# B4: Variable concatenation
r = trace_command("a=.en; b=v; cat ${a}${b}", "Split .env across two variables")
results.append(("a=.en; b=v; cat ${a}${b}", "zeroAccess", r))

# B5: printf construction
r = trace_command("cat $(printf '.%s' env)", "printf to construct .env")
results.append(("cat $(printf '.%s' env)", "zeroAccess", r))

# B6: eval with split quotes
r = trace_command("eval 'cat .e''nv'", "eval with split single quotes")
results.append(("eval 'cat .e''nv'", "zeroAccess", r))

# B7: Octal escape
r = trace_command("cat $'\\056env'", "Octal escape for . in .env")
results.append(("cat $'\\056env'", "zeroAccess", r))

# B8: Python chr() bypass
r = trace_command("python3 -c 'open(chr(46)+\"env\").read()'", "Python chr() to construct .")
results.append(("python3 -c 'open(chr(46)+\"env\").read()'", "zeroAccess", r))

# B9: rev command
r = trace_command("cat $(echo vne. | rev)", "Reverse string to construct .env")
results.append(("cat $(echo vne. | rev)", "zeroAccess", r))

# B10: base64 decode
r = trace_command("cat $(echo LmVudg== | base64 -d)", "Base64 decode to construct .env")
results.append(("cat $(echo LmVudg== | base64 -d)", "zeroAccess", r))

# B11: find with partial name
r = trace_command("find . -name '.e*' -maxdepth 1 -exec cat {} +", "find with partial glob")
results.append(("find . -name '.e*' -maxdepth 1 -exec cat {} +", "zeroAccess", r))

# B12: Wildcard cat
r = trace_command("cat .e*", "Shell glob to read .env")
results.append(("cat .e*", "zeroAccess", r))

# B13: Using head instead of cat
r = trace_command("head -100 .env", "head instead of cat for .env")
results.append(("head -100 .env", "zeroAccess", r))

# ===== READ-ONLY BYPASSES =====
print("\n\n### READ-ONLY BYPASS CANDIDATES ###\n")

# R1: chmod on lock file
r = trace_command("chmod 777 poetry.lock", "chmod to modify permissions of lock file")
results.append(("chmod 777 poetry.lock", "readOnly", r))

# R2: touch on lock file
r = trace_command("touch poetry.lock", "touch to modify timestamps of lock file")
results.append(("touch poetry.lock", "readOnly", r))

# R3: chown on lock file
r = trace_command("chown user poetry.lock", "chown to change ownership")
results.append(("chown user poetry.lock", "readOnly", r))

# R4: truncate on lock file
r = trace_command("truncate -s 0 poetry.lock", "truncate lock file to zero")
results.append(("truncate -s 0 poetry.lock", "readOnly", r))

# R5: xattr modification
r = trace_command("xattr -w key val poetry.lock", "xattr modification")
results.append(("xattr -w key val poetry.lock", "readOnly", r))

# ===== NO-DELETE BYPASSES =====
print("\n\n### NO-DELETE BYPASS CANDIDATES ###\n")

# D1: mv to /tmp (not /dev/null)
r = trace_command("mv CLAUDE.md /tmp/", "mv to /tmp (effective deletion)")
results.append(("mv CLAUDE.md /tmp/", "noDelete", r))

# D2: Truncate via redirect
r = trace_command("> CLAUDE.md", "Truncate via redirect (empty file)")
results.append(("> CLAUDE.md", "noDelete", r))

# D3: cp /dev/null over file
r = trace_command("cp /dev/null CLAUDE.md", "cp /dev/null to empty the file")
results.append(("cp /dev/null CLAUDE.md", "noDelete", r))

# D4: git rm
r = trace_command("git rm CLAUDE.md", "git rm to delete tracked file")
results.append(("git rm CLAUDE.md", "noDelete", r))

# D5: git rm --cached
r = trace_command("git rm --cached CLAUDE.md", "git rm --cached to unstage")
results.append(("git rm --cached CLAUDE.md", "noDelete", r))

# D6: mv to .. (outside project)
r = trace_command("mv CLAUDE.md ../", "mv outside project directory")
results.append(("mv CLAUDE.md ../", "noDelete", r))

# ===== TOKENIZER-EXPLOITABLE BYPASSES =====
print("\n\n### TOKENIZER-EXPLOITABLE BYPASS CANDIDATES ###\n")

# T1: ${VAR} with dangerous default containing .env access
r = trace_command("echo ${VAR:-$(cat .env)}", "Parameter expansion default runs cat .env")
results.append(("echo ${VAR:-$(cat .env)}", "tokenizer-exploit", r))

# T2: Comment hiding
r = trace_command("echo safe #; cat .env", "Comment hides .env access from split")
results.append(("echo safe #; cat .env", "tokenizer-exploit", r))

# T3: Subshell hiding
r = trace_command("(cat .env)", "Bare subshell with .env access")
results.append(("(cat .env)", "tokenizer-exploit", r))


# ===== SUMMARY =====
print("\n\n" + "=" * 70)
print("SUMMARY OF ALL BYPASS TRACES")
print("=" * 70)

bypassed = [(cmd, tier, r) for cmd, tier, r in results if r[0] == "bypassed"]
partial = [(cmd, tier, r) for cmd, tier, r in results if r[0] == "partial"]
caught = [(cmd, tier, r) for cmd, tier, r in results if r[0] == "caught"]

print(f"\nTotal tested: {len(results)}")
print(f"Caught: {len(caught)}")
print(f"Partial (ask only): {len(partial)}")
print(f"BYPASSED: {len(bypassed)}")

if bypassed:
    print(f"\n*** FULL BYPASSES ({len(bypassed)}) ***")
    for cmd, tier, (status, layer) in bypassed:
        print(f"  [{tier}] {cmd}")

if partial:
    print(f"\n*** PARTIAL BYPASSES ({len(partial)}) ***")
    for cmd, tier, (status, layer) in partial:
        print(f"  [{tier}] {cmd} -- caught by: {layer}")

# Cleanup
shutil.rmtree(project_dir, ignore_errors=True)
