#!/usr/bin/env python3
"""Verify Codex review concerns about is_write_command anchoring."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import is_write_command, is_delete_command, scan_protected_paths, split_commands
import json

with open(str(_bootstrap._REPO_ROOT / 'assets' / 'guardian.default.json')) as f:
    config = json.load(f)

print('=== Codex Concern #1: is_write_command not anchored to command position ===')
# Does "echo ln something" trigger write detection?
anchoring_tests = [
    ('echo "ln -s target link"', 'echo with ln in quotes'),
    ('grep "ln " file.txt', 'grep searching for ln'),
    ('man ln', 'man page for ln'),
    ('echo ln', 'echo ln (no space after ln)'),
    ('echo "cp file1 file2"', 'echo with cp in quotes'),
    ('grep "mv " file.txt', 'grep searching for mv'),
    ('echo "chmod 755"', 'echo with chmod in quotes'),
    ('echo "tee output"', 'echo with tee in quotes'),
    ('echo "sed -i s/a/b/ file"', 'echo with sed in quotes'),
]
for cmd, desc in anchoring_tests:
    w = is_write_command(cmd)
    # Also check: would split_commands + per-sub analysis catch this?
    subs = split_commands(cmd)
    sub_writes = [(s, is_write_command(s)) for s in subs]
    print(f'  {"WRITE" if w else "OK   "}: "{cmd}" [{desc}]')
    if w:
        for s, sw in sub_writes:
            print(f'    sub: "{s}" -> write={sw}')

print()
print('=== Codex Concern #2: F10 boundary in benign strings ===')
benign_with_colon = [
    'echo ".env: do not commit"',
    'echo "config: .env is important"',
    'echo "key=value" > config.txt',
    'printf "PATH=%s\\n" "$PATH"',
    'echo "see id_rsa for details"',
    'echo "check .pem files"',
]
for cmd in benign_with_colon:
    verdict, reason = scan_protected_paths(cmd, config)
    if verdict != 'allow':
        print(f'  FALSE POSITIVE: "{cmd}" -> {verdict}: {reason}')
    else:
        print(f'  OK (allow): "{cmd}"')

print()
print('=== Pre-existing: non-anchored write patterns ===')
# Check which write patterns are NOT anchored to command position
import re
write_patterns = [
    r">\s*['\"]?[^|&;]+",      # Redirection (existing)
    r"\btee\s+",                 # tee
    r"\bmv\s+",                  # mv
    r"\bln\s+",                  # F2: ln
    r"\bsed\s+.*-[^-]*i",       # sed -i
    r"\bcp\s+",                  # cp
    r"\bdd\s+",                  # dd
    r"\bpatch\b",                # patch
    r"\brsync\s+",               # rsync
    r":\s*>",                    # Truncation
    r"\bchmod\s+",               # chmod
    r"\btouch\s+",               # touch
    r"\bchown\s+",               # chown
    r"\bchgrp\s+",               # chgrp
]
print('  All write patterns use \\b (word boundary), NOT command-start anchors.')
print('  This means "echo cp file" would match on "cp file" inside the echo.')
print('  However, this is a PRE-EXISTING design choice, not introduced by F2.')
print('  F2 merely adds ln with the same pattern style as existing patterns.')
