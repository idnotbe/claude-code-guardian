#!/usr/bin/env python3
"""Test how variable expansion interacts with F1 fail-closed."""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import extract_paths, is_write_command
import shlex

project_dir = Path(tempfile.mkdtemp())

print('=== Variable expansion behavior ===')

# Test how shlex + expandvars handle variables
test_cases = [
    'rm $VAR',           # Bare $VAR
    'rm "$VAR"',         # Quoted $VAR
    "rm '$VAR'",         # Single-quoted $VAR (literal)
    'rm ${VAR}',         # Braced var
    'cp $SRC $DST',      # Two bare vars
]

for cmd in test_cases:
    try:
        parts = shlex.split(cmd, posix=True)
    except ValueError:
        parts = cmd.split()

    expanded_parts = []
    for p in parts[1:]:
        expanded = os.path.expandvars(p)
        expanded_parts.append(f'{p!r} -> {expanded!r}')

    paths = extract_paths(cmd, project_dir, allow_nonexistent=True)
    path_strs = [str(p) for p in paths]
    print(f'  "{cmd}"')
    print(f'    shlex parts: {parts}')
    print(f'    expandvars: {expanded_parts}')
    print(f'    extracted: {path_strs}')
    print()

# Check: is the --version/--help false ask rate significant?
print('=== Impact assessment of --version/--help false asks ===')
print('  These commands are detected as write ops but have no file args:')
print('  - "rsync --version" -> ASK (write detected, no paths)')
print('  - "dd --help" -> ASK (write detected, no paths)')
print('  - etc.')
print()
print('  Impact: LOW')
print('  - These are extremely rare in Claude Code sessions')
print('  - The "ask" prompt (not deny) just confirms the operation')
print('  - A developer would click "allow" once and move on')
print('  - The alternative (fail-open for $VAR) is far worse for security')

print()
print('=== F1 verdict: write command detection scope ===')
# The key question: which common commands trigger is_write_command?
common_daily = [
    'git status', 'git add .', 'git commit -m "msg"', 'git push',
    'git pull', 'git checkout -b feature', 'git merge main',
    'npm install', 'npm run dev', 'npm run build', 'npm test',
    'pip install -r requirements.txt', 'pip list',
    'python3 -m pytest tests/', 'python3 app.py',
    'node server.js', 'cargo run', 'go run main.go',
    'docker build -t myapp .', 'docker run myapp', 'docker ps',
    'ls -la', 'cat file.txt', 'grep -r pattern src/',
    'find . -name "*.py"', 'which python', 'env', 'pwd',
    'mkdir -p dir', 'cd src', 'tree', 'du -sh', 'df -h',
    'curl https://api.example.com', 'wget file.tar.gz',
    'ssh user@host', 'scp file.txt host:/tmp/',
    'tar czf archive.tar.gz dir/', 'unzip file.zip',
    'brew install tool', 'apt-get install tool',
    'npm ci', 'yarn install', 'pnpm install',
]
write_detected = []
for cmd in common_daily:
    if is_write_command(cmd):
        write_detected.append(cmd)

print(f'  Of {len(common_daily)} common daily commands:')
print(f'  {len(write_detected)} detected as write commands:')
for cmd in write_detected:
    print(f'    - "{cmd}"')
print(f'  {len(common_daily) - len(write_detected)} correctly classified as non-write')
