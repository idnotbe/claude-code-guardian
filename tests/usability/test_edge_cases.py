#!/usr/bin/env python3
"""Edge case analysis for F1 and overall usability."""
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

project_dir = Path(tempfile.mkdtemp())

print('=== F1 Edge Cases: --version/--help on write-detected commands ===')
version_cmds = [
    'rsync --version',
    'dd --help',
    'patch --version',
    'sed --version',
    'tee --version',
    'cp --version',
    'mv --version',
    'chmod --version',
    'touch --version',
    'ln --version',
]
for cmd in version_cmds:
    w = is_write_command(cmd)
    d = is_delete_command(cmd)
    sub_cmds = split_commands(cmd)
    would_ask = False
    for sub in sub_cmds:
        if is_write_command(sub) or is_delete_command(sub):
            paths = extract_paths(sub, project_dir, allow_nonexistent=True)
            redir = extract_redirection_targets(sub, project_dir)
            if not paths and not redir:
                would_ask = True
    print(f'  {"ASK" if would_ask else "OK "}: "{cmd}" (write={w}, delete={d})')

print()
print('=== Compound commands with write + read ===')
compound_cmds = [
    'git status && cp file.txt backup.txt',
    'ls -la; echo "done" > log.txt',
    'grep pattern file.txt | tee results.txt',
    'find . -name "*.py" | xargs wc -l',
    'npm install && npm run build',
    'docker build . && docker run myapp',
]
for cmd in compound_cmds:
    sub_cmds = split_commands(cmd)
    verdicts = []
    for sub in sub_cmds:
        w = is_write_command(sub)
        d = is_delete_command(sub)
        if w or d:
            paths = extract_paths(sub, project_dir, allow_nonexistent=True)
            redir = extract_redirection_targets(sub, project_dir)
            if not paths and not redir:
                verdicts.append(f'ASK({sub.strip()[:30]})')
            else:
                verdicts.append(f'paths_found({sub.strip()[:30]})')
        else:
            verdicts.append(f'safe({sub.strip()[:30]})')
    print(f'  "{cmd[:60]}"')
    for v in verdicts:
        print(f'    -> {v}')

print()
print('=== F1: Commands where variables cause unresolvable paths (SHOULD ask) ===')
var_cmds = [
    'cp "$src" "$dst"',
    'mv "${OLD_NAME}" "${NEW_NAME}"',
    'echo "$DATA" > "$OUTPUT"',
    'tee "$LOG_FILE"',
    'rsync -av "$SRC/" "$DST/"',
    'sed -i "s/old/new/g" "$CONFIG"',
    'chmod +x "$SCRIPT"',
]
for cmd in var_cmds:
    sub_cmds = split_commands(cmd)
    for sub in sub_cmds:
        w = is_write_command(sub)
        d = is_delete_command(sub)
        if w or d:
            paths = extract_paths(sub, project_dir, allow_nonexistent=True)
            redir = extract_redirection_targets(sub, project_dir)
            if not paths and not redir:
                print(f'  ASK (correct): "{cmd}"')
            else:
                p_names = [str(p) for p in (paths + redir)]
                print(f'  RESOLVED: "{cmd}" -> {p_names}')

print()
print('=== F5: Archive symlink safety - code inspection ===')
import inspect
from bash_guardian import archive_files
source = inspect.getsource(archive_files)
has_symlinks_true = 'symlinks=True' in source
has_islink = 'os.path.islink' in source
has_readlink = 'os.readlink' in source
print(f'  symlinks=True in copytree: {has_symlinks_true}')
print(f'  os.path.islink check: {has_islink}')
print(f'  os.readlink for preservation: {has_readlink}')
if has_symlinks_true and has_islink and has_readlink:
    print('  F5 implementation: VERIFIED')
else:
    print('  F5 implementation: INCOMPLETE')

print()
print('=== F9: Schema verification ===')
import json
with open(str(_bootstrap._REPO_ROOT / 'assets' / 'guardian.schema.json')) as f:
    schema = json.load(f)
exact_default = schema['properties']['bashPathScan']['properties']['exactMatchAction']['default']
print(f'  exactMatchAction default in schema: "{exact_default}"')
with open(str(_bootstrap._REPO_ROOT / 'assets' / 'guardian.default.json')) as f:
    config = json.load(f)
exact_actual = config['bashPathScan']['exactMatchAction']
print(f'  exactMatchAction in config: "{exact_actual}"')
if exact_default == exact_actual:
    print(f'  F9: Schema matches config (both "{exact_default}") - VERIFIED')
else:
    print(f'  F9: MISMATCH - schema says "{exact_default}", config says "{exact_actual}"')
