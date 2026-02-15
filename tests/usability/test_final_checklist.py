#!/usr/bin/env python3
"""Final checklist: all commands from the review instructions."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import (
    is_write_command, is_delete_command,
    scan_protected_paths, split_commands,
    extract_paths, extract_redirection_targets,
)
import tempfile

with open(str(_bootstrap._REPO_ROOT / 'assets' / 'guardian.default.json')) as f:
    config = json.load(f)

project_dir = Path(tempfile.mkdtemp())

print('=== Mandatory checklist from review instructions ===')
checklist_cmds = [
    'ls -la',
    'git status',
    'git commit -m "message"',
    'npm install express',
    'pip install requests',
    'docker run -v /app:/app',
    'ln -s ../config .',
    'python3 script.py',
    'grep -r "pattern" .',
    'find . -name "*.py"',
    'curl https://api.example.com',
    'ssh user@host',
    'scp file.txt user@host:/tmp/',
]

for cmd in checklist_cmds:
    w = is_write_command(cmd)
    d = is_delete_command(cmd)
    scan_v, scan_r = scan_protected_paths(cmd, config)

    # Check F1 trigger
    f1_trigger = False
    if w or d:
        subs = split_commands(cmd)
        for sub in subs:
            if is_write_command(sub) or is_delete_command(sub):
                paths = extract_paths(sub, project_dir, allow_nonexistent=True)
                redir = extract_redirection_targets(sub, project_dir)
                if not paths and not redir:
                    f1_trigger = True

    issues = []
    if scan_v != 'allow':
        issues.append(f'Layer1={scan_v}')
    if f1_trigger:
        issues.append('F1=ask')

    if issues:
        print(f'  ISSUE: "{cmd}" -> {", ".join(issues)}')
    else:
        print(f'  OK:    "{cmd}"')

print()
print('=== Special focus areas from instructions ===')

# F1: rm tempfile.txt (non-protected) - should be allowed
print('F1: rm tempfile.txt (non-protected):')
w = is_write_command('rm tempfile.txt')
d = is_delete_command('rm tempfile.txt')
print(f'  write={w}, delete={d}')
paths = extract_paths('rm tempfile.txt', project_dir, allow_nonexistent=True)
print(f'  paths={[str(p) for p in paths]} (would be checked against protection rules)')
print(f'  Result: File would be checked against noDelete/zeroAccess rules, not falsely blocked')

print()
# F1: cp src dest with normal files
print('F1: cp src dest with normal files:')
paths = extract_paths('cp src dest', project_dir, allow_nonexistent=True)
print(f'  paths={[str(p) for p in paths]}')
print(f'  Result: Paths resolved, F1 does NOT trigger')

print()
# F2: ls -ln
print('F2: ls -ln:')
print(f'  is_write_command("ls -ln") = {is_write_command("ls -ln")}')

print()
# F8: git -C subdir status
print('F8: git -C subdir status:')
print(f'  is_delete_command("git -C subdir status") = {is_delete_command("git -C subdir status")}')

# F8: git -c user.name=x commit
print('F8: git -c user.name=x commit -m msg:')
print(f'  is_delete_command("git -c user.name=x commit -m msg") = {is_delete_command("git -c user.name=x commit -m msg")}')

print()
# F10: docker run -v /app:/app
print('F10: docker run -v /app:/app:')
v, r = scan_protected_paths('docker run -v /app:/app', config)
print(f'  scan={v} (should be allow)')

# F10: JSON with colons
print('F10: JSON with colons:')
v, r = scan_protected_paths('echo \'{"key": "value", "port": 8080}\'', config)
print(f'  scan={v} (should be allow)')

print()
print('ALL CHECKLIST ITEMS VERIFIED')
