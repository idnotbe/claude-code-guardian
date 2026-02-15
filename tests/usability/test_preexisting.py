#!/usr/bin/env python3
"""Distinguish pre-existing false positives from V2-introduced ones."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import is_write_command, scan_protected_paths
import json, re

with open(str(_bootstrap._REPO_ROOT / 'assets' / 'guardian.default.json')) as f:
    config = json.load(f)

print('=== Pre-existing vs V2-introduced false positives ===')
print()

# Test: would echo "cp file" have been a write false positive BEFORE V2 fixes?
# Answer: YES, because \bcp\s+ existed before. F2 only adds \bln\s+.
echo_cmds_pre_existing = [
    ('echo "cp file1 file2"', 'cp pattern (pre-existing)'),
    ('echo "mv old new"', 'mv pattern (pre-existing)'),
    ('echo "chmod 755 file"', 'chmod pattern (pre-existing)'),
    ('echo "tee output"', 'tee pattern (pre-existing)'),
    ('echo "sed -i s/a/b/ file"', 'sed -i pattern (pre-existing)'),
]
echo_cmds_new = [
    ('echo "ln -s target link"', 'ln pattern (NEW from F2)'),
]

print('Pre-existing false positives (NOT caused by V2 fixes):')
for cmd, desc in echo_cmds_pre_existing:
    w = is_write_command(cmd)
    print(f'  {"WRITE" if w else "OK   "}: "{cmd}" [{desc}]')

print()
print('NEW false positive from F2:')
for cmd, desc in echo_cmds_new:
    w = is_write_command(cmd)
    print(f'  {"WRITE" if w else "OK   "}: "{cmd}" [{desc}]')

print()
print('=== F10 boundary: pre-existing vs new ===')
# BEFORE F10, the boundary did NOT include :, [, ]
# So "echo .env: ..." and "docker -v .env:/app" would have used space-based boundaries
# Let's check what boundary_before looked like BEFORE F10

# Before F10: (?:^|[\s;|&<>("`'=/,{])
# After F10:  (?:^|[\s;|&<>("`'=/,{\[:\]])
# The : addition means ".env:" now matches where before it would not have
# because ":" was not a boundary char

# Which of the false positives are NEW from F10?
print('Commands that would have been ALLOWED before F10 (new false positives from :):')
# Simulate pre-F10 boundary by checking if the match depends on :
boundary_tests = [
    ('echo ".env: do not commit"', '.env', 'NEW: colon after .env is new boundary'),
    ('scp host:.env .', '.env', 'NEW: colon before .env is new boundary'),
    ('docker run -v .env:/app/.env ubuntu', '.env', 'NEW: colon as boundary enables match'),
    ('echo "see id_rsa for details"', 'id_rsa', 'PRE-EXISTING: space boundary before id_rsa'),
    ('echo "check .pem files"', '.pem', 'PRE-EXISTING: space boundary before .pem'),
    ('cat .env', '.env', 'PRE-EXISTING: space boundary'),
]
for cmd, lit, desc in boundary_tests:
    verdict, reason = scan_protected_paths(cmd, config)
    print(f'  {verdict.upper():5}: "{cmd}" [{desc}]')

print()
print('=== Impact Summary ===')
print('F2 (ln): Adds 1 new false-positive class (echo "ln ..."), same pattern as')
print('  pre-existing cp/mv/chmod/tee/sed patterns. Not a regression in kind.')
print()
print('F10 (:): Adds new false positives for commands that mention .env with colon:')
print('  - echo ".env: description" (informational echo)')
print('  - Docker/scp commands (intentional detection - good)')
print('  Trade-off: catches real docker/scp bypasses but also catches benign echo/comments')
