#!/usr/bin/env python3
"""Verify regex correctness for interpreter patterns."""
import re
import json

print("=" * 70)
print("TASK A: Regex Correctness Verification")
print("=" * 70)

# Check 1: Python interpreter name matching
print("\n--- Check 1: Python interpreter name matching ---")
python_name_pattern = r'(?:python[23]?|python\d[\d.]*)'

should_match = ['python', 'python2', 'python3', 'python3.12', 'python3.13.1']
should_not_match = ['pythonic', 'pythonista', 'python_script']

for s in should_match:
    m = re.fullmatch(python_name_pattern, s)
    status = 'PASS' if m else 'FAIL'
    print(f'  [{status}] Should match "{s}": {bool(m)}')

for s in should_not_match:
    m = re.fullmatch(python_name_pattern, s)
    status = 'PASS' if not m else 'FAIL'
    print(f'  [{status}] Should NOT match "{s}": {bool(m)}')

# Check 2: Context-aware matching (with \s boundary)
print("\n--- Check 2: Context-aware matching ---")
full_python_pattern = r'(?:python[23]?|python\d[\d.]*)\s[^;|&\n]*(?:os\.remove|os\.unlink|shutil\.rmtree|os\.rmdir)'

context_tests = [
    ('python -c "os.remove(f)"', True, 'python basic'),
    ('python3.12 -c "os.remove(f)"', True, 'python3.12'),
    ('pythonic -c "os.remove(f)"', False, 'pythonic rejected'),
    ('python_script -c "os.remove(f)"', False, 'underscore rejected'),
    ('python3 -c "print(1)"', False, 'no deletion'),
]

for cmd, expected, desc in context_tests:
    m = re.search(full_python_pattern, cmd, re.IGNORECASE)
    actual = bool(m)
    status = 'PASS' if actual == expected else 'FAIL'
    print(f'  [{status}] {desc}: expected={expected}, got={actual}')

# Check 3: Node.js pattern
print("\n--- Check 3: Node.js/Deno/Bun pattern ---")
node_pattern = r'(?:node|deno|bun)\s[^;|&\n]*(?:unlinkSync|rmSync|rmdirSync|fs\.unlink|fs\.rm\b)'

node_tests = [
    ('node -e "fs.unlinkSync(f)"', True, 'unlinkSync'),
    ('node -e "fs.rmSync(f)"', True, 'rmSync'),
    ('node -e "fs.rmdirSync(f)"', True, 'rmdirSync'),
    ('node -e "fs.rm(f, cb)"', True, 'fs.rm'),
    ('bun -e "fs.unlinkSync(f)"', True, 'bun unlinkSync'),
    ('node -e "console.log(1)"', False, 'safe node'),
    ('node script.js', False, 'no deletion'),
]

for cmd, expected, desc in node_tests:
    m = re.search(node_pattern, cmd, re.IGNORECASE)
    actual = bool(m)
    status = 'PASS' if actual == expected else 'FAIL'
    print(f'  [{status}] {desc}: expected={expected}, got={actual}')

# Check 4: fs.rm word boundary
print("\n--- Check 4: fs.rm word boundary ---")
boundary_tests = [
    ('fs.rm(', True, 'fs.rm( matches'),
    ('fs.rmdir', False, 'fs.rmdir does NOT match fs.rm\\b'),
    ('fs.rmdirSync', False, 'fs.rmdirSync does NOT match fs.rm\\b'),
    ('fs.rmSync', False, 'fs.rmSync does NOT match fs.rm\\b'),
]

for text, expected, desc in boundary_tests:
    m = re.search(r'fs\.rm\b', text)
    actual = bool(m)
    status = 'PASS' if actual == expected else 'FAIL'
    print(f'  [{status}] {desc}: expected={expected}, got={actual}')

# Check 5: JSON escaping
print("\n--- Check 5: JSON escaping in guardian.default.json ---")
with open('assets/guardian.default.json', 'r') as f:
    config = json.load(f)

block_patterns = config['bashToolPatterns']['block']
for p in block_patterns:
    reason = p.get('reason', '')
    if 'nterpreter' in reason:
        pattern = p['pattern']
        try:
            re.compile(pattern)
            print(f'  [PASS] Compiles: {pattern[:60]}')
        except re.error as e:
            print(f'  [FAIL] Compile error: {e} - {pattern[:60]}')

# Check 6: Consistency
print("\n--- Check 6: Cross-location consistency ---")
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'hooks' / 'scripts'))
import _guardian_utils

default_interp = []
for p in config['bashToolPatterns']['block']:
    reason = p.get('reason', '')
    if 'nterpreter' in reason.lower():
        default_interp.append(p['pattern'])

fallback_interp = []
for p in _guardian_utils._FALLBACK_CONFIG['bashToolPatterns']['block']:
    reason = p.get('reason', '')
    if 'nterpreter' in reason.lower():
        fallback_interp.append(p['pattern'])

print(f"  Default config: {len(default_interp)} interpreter block patterns")
print(f"  Fallback config: {len(fallback_interp)} interpreter block patterns")

# Check fallback patterns are subset of default
for fp in fallback_interp:
    found = fp in default_interp
    status = 'PASS' if found else 'FAIL'
    print(f"  [{status}] Fallback pattern in default: {fp[:50]}")

# Check perl/ruby missing from fallback
perl_ruby_in_fallback = any('perl|ruby' in p for p in fallback_interp)
print(f"  [INFO] Perl/Ruby in fallback: {perl_ruby_in_fallback} (missing is acceptable for minimal fallback)")
