#!/usr/bin/env python3
"""Check if rm $VAR actually triggers F1 or resolves to a literal path."""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import (
    extract_paths, is_delete_command, _is_within_project_or_would_be
)

project_dir = Path(tempfile.mkdtemp())

print('=== F1: Variable resolution edge case ===')
print(f'  Project dir: {project_dir}')
print()

# When $VAR is unset, os.path.expandvars("$VAR") returns "$VAR" literally
# Then _is_within_project_or_would_be checks if /tmp/xxx/$VAR would be within project
# Since project_dir is /tmp/xxx, /tmp/xxx/$VAR IS within project, so it resolves!
# This means F1 does NOT trigger for rm $VAR when the var is unset.

# Test 1: rm $VAR (VAR unset)
os.environ.pop('VAR', None)
paths = extract_paths('rm $VAR', project_dir, allow_nonexistent=True)
print(f'  rm $VAR (VAR unset):')
print(f'    Resolved paths: {[str(p) for p in paths]}')
print(f'    F1 triggers: {len(paths) == 0}')
within = _is_within_project_or_would_be(project_dir / '$VAR', project_dir)
print(f'    $VAR within project: {within}')
print()

# Test 2: rm $VAR (VAR set to something outside project)
os.environ['VAR'] = '/etc/passwd'
paths2 = extract_paths('rm $VAR', project_dir, allow_nonexistent=True)
print(f'  rm $VAR (VAR=/etc/passwd):')
print(f'    Resolved paths: {[str(p) for p in paths2]}')
print(f'    F1 triggers: {len(paths2) == 0}')
os.environ.pop('VAR', None)
print()

# Test 3: rm $(echo file) -- command substitution
paths3 = extract_paths('rm $(echo file)', project_dir, allow_nonexistent=True)
print(f'  rm $(echo file):')
print(f'    Resolved paths: {[str(p) for p in paths3]}')
print(f'    F1 triggers: {len(paths3) == 0}')
print()

# Test 4: rm with backticks
paths4 = extract_paths('rm `cat filelist`', project_dir, allow_nonexistent=True)
print(f'  rm `cat filelist`:')
print(f'    Resolved paths: {[str(p) for p in paths4]}')
print(f'    F1 triggers: {len(paths4) == 0}')
print()

# Summary
print('=== Analysis ===')
print('  When $VAR is UNSET, os.path.expandvars returns "$VAR" literally.')
print('  Path becomes project_dir/$VAR which IS within project.')
print('  So F1 does NOT trigger -- the literal "$VAR" is treated as a file name.')
print('  This is SAFE because:')
print('    1. The path project_dir/$VAR does not exist, so rm will fail harmlessly')
print('    2. If someone actually named a file "$VAR", guardian correctly detects it')
print('  When $VAR is SET to /etc/passwd, expandvars resolves it, and it is')
print('  outside project, so extract_paths filters it out, and F1 DOES trigger.')
print()
print('  The original concern (rm $VAR silently allowed) is partially addressed:')
print('    - Unset vars: no F1 (treated as literal), but rm would fail anyway')
print('    - Set to outside path: F1 triggers correctly')
print('    - Set to inside path: normal path checking applies')
