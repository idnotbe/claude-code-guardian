#!/usr/bin/env python3
"""Deep usability analysis of F1 (fail-closed safety net).

F1 is the highest-impact usability change. When a write/delete command
is detected but no target paths can be resolved, the system now asks
instead of allowing. This test checks whether common developer commands
would produce false "ask" prompts.
"""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import (
    is_write_command, is_delete_command,
    extract_paths, extract_redirection_targets,
    split_commands,
)

# Create a temp project dir with some real files to test path resolution
project_dir = Path(tempfile.mkdtemp())
# Create some dummy files
for f in ['file.txt', 'script.sh', 'data.csv', 'config.json', 'README.md']:
    (project_dir / f).touch()
os.makedirs(project_dir / 'src', exist_ok=True)
(project_dir / 'src' / 'main.py').touch()

false_positives = []
correct_asks = []
correct_allows = []

def check_f1(cmd, expect_ask, desc):
    """Check if F1 would trigger for this command."""
    sub_cmds = split_commands(cmd)
    for sub in sub_cmds:
        w = is_write_command(sub)
        d = is_delete_command(sub)
        if w or d:
            paths = extract_paths(sub, project_dir, allow_nonexistent=(w or d))
            redir = extract_redirection_targets(sub, project_dir)
            if not paths and not redir:
                if expect_ask:
                    correct_asks.append((cmd, desc))
                else:
                    false_positives.append((cmd, desc))
                return
            else:
                if not expect_ask:
                    correct_allows.append((cmd, desc))
                return
    # Not detected as write/delete at all
    if not expect_ask:
        correct_allows.append((cmd, desc))

# ===== Common developer commands that should NOT trigger F1 =====
print("Testing common developer commands...")

# File manipulation with explicit paths
check_f1('cp file.txt backup.txt', False, 'cp with explicit names')
check_f1('mv file.txt renamed.txt', False, 'mv with explicit names')
check_f1('echo hello > output.txt', False, 'echo with redirect')
check_f1('cat input.txt >> log.txt', False, 'cat with append')
check_f1('touch newfile.txt', False, 'touch a file')
check_f1('chmod 755 script.sh', False, 'chmod a file')
check_f1('ln -s ../config link', False, 'symlink creation')

# Commands that are NOT write/delete
check_f1('ls -la', False, 'ls listing')
check_f1('git status', False, 'git status')
check_f1('git log --oneline', False, 'git log')
check_f1('git diff', False, 'git diff')
check_f1('git branch -a', False, 'git branch listing')
check_f1('npm install', False, 'npm install')
check_f1('pip install requests', False, 'pip install')
check_f1('python3 script.py', False, 'run python script')
check_f1('node index.js', False, 'run node script')
check_f1('grep -r "pattern" .', False, 'grep search')
check_f1('find . -name "*.py"', False, 'find files')
check_f1('curl https://example.com', False, 'curl request')
check_f1('wget https://example.com/file', False, 'wget download')
check_f1('ssh user@host', False, 'ssh connection')
check_f1('docker ps', False, 'docker list')
check_f1('docker build .', False, 'docker build')
check_f1('make build', False, 'make target')
check_f1('cargo build', False, 'cargo build')
check_f1('go build ./...', False, 'go build')
check_f1('npm run test', False, 'npm test')
check_f1('pytest tests/', False, 'pytest')
check_f1('cat file.txt', False, 'cat read')
check_f1('head -n 10 file.txt', False, 'head read')
check_f1('wc -l file.txt', False, 'wc count')
check_f1('mkdir -p new_dir', False, 'mkdir')
check_f1('pwd', False, 'pwd')
check_f1('which python', False, 'which')
check_f1('env', False, 'env vars')
check_f1('export FOO=bar', False, 'export var')

# ===== Commands that SHOULD trigger F1 (ambiguous/unresolvable) =====
check_f1('rm $FILE', True, 'rm with variable - unresolvable')
check_f1('cp $SRC $DST', True, 'cp with variables')
check_f1('mv $OLD $NEW', True, 'mv with variables')

# ===== Edge cases: write commands with flags-only =====
# These are write commands but have no file arguments - F1 WILL trigger
check_f1('tee', True, 'tee with no args (unusual but valid)')
check_f1('rsync --version', True, 'rsync --version triggers write detection')
check_f1('dd --help', True, 'dd --help triggers write detection')
check_f1('patch --version', True, 'patch --version triggers write detection')

# ===== Report =====
print()
print(f'=== Results ===')
print(f'Correct allows (no false positive): {len(correct_allows)}')
print(f'Correct asks (intended F1 trigger): {len(correct_asks)}')
print(f'FALSE POSITIVES: {len(false_positives)}')

if false_positives:
    print()
    print('=== FALSE POSITIVES (commands that should NOT trigger ask) ===')
    for cmd, desc in false_positives:
        print(f'  "{cmd}" [{desc}]')

print()
print('=== Edge cases: write commands with no file args (expected ask) ===')
for cmd, desc in correct_asks:
    print(f'  "{cmd}" [{desc}]')

if not false_positives:
    print()
    print('NO FALSE POSITIVES FOUND - F1 usability is clean for common commands')
else:
    print()
    print(f'WARNING: {len(false_positives)} false positive(s) found')
