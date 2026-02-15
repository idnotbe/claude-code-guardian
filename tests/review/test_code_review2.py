#!/usr/bin/env python3
"""More edge case tests"""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import glob_to_literals, scan_protected_paths

print("=== Bug: glob_to_literals('') returns [''] ===")
result = glob_to_literals('')
print(f"  Result: {result}")
print(f"  Is buggy: {result == ['']}")
print(f"  Impact: empty string literal will match any command via regex")

# Check what regex is built from empty literal
literal = ''
boundary_before = r"(?:^|[\s;|&<>(\"`'=/,{])"
boundary_after = r"(?:$|[\s;|&<>)\"`'/,}])"
regex = boundary_before + re.escape(literal) + boundary_after
print(f"  Built regex: {regex}")
print(f"  Matches 'ls -la': {bool(re.search(regex, 'ls -la'))}")
print(f"  Matches 'echo hi': {bool(re.search(regex, 'echo hi'))}")
print(f"  Matches '': {bool(re.search(regex, ''))}")

print("\n  CONCLUSION: Empty string pattern matches everything!")
print("  But is there ever an empty string in zeroAccessPaths? Checking config...")

# Check if config has empty strings
import json
config_path = str(_bootstrap._REPO_ROOT / 'assets' / 'guardian.default.json')
with open(config_path) as f:
    config = json.load(f)

zero_access = config.get('zeroAccessPaths', [])
empty_patterns = [p for p in zero_access if not p]
print(f"  Empty patterns in zeroAccessPaths: {empty_patterns}")
print(f"  Impact: {'HIGH - false positives on all commands' if empty_patterns else 'LOW - no empty patterns in default config'}")

print("\n=== Check: is_write_command false positive on URLs ===")
from bash_guardian import is_write_command
url_cmds = [
    'curl https://example.com/api > /dev/null',
    'wget https://example.com',
    'git clone https://github.com/foo/bar',
]
for cmd in url_cmds:
    result = is_write_command(cmd)
    print(f"  is_write('{cmd}'): {result}")

print("\n=== Check: is_delete_command edge cases ===")
from bash_guardian import is_delete_command
edge_cases = [
    ('rm -rf /tmp/test', True, 'basic rm'),
    ('echo remove this', False, 'echo with remove'),
    ('grep -r "rm" .', False, 'grep for rm'),
    ('firmware_update.sh', False, 'command with rm substring'),
    ('rm file.txt', True, 'simple rm'),
]
for cmd, expected, desc in edge_cases:
    result = is_delete_command(cmd)
    status = 'PASS' if result == expected else 'FAIL'
    print(f"  [{status}] {desc}: expected={expected}, got={result}")

print("\n=== Check: _is_path_candidate edge cases ===")
from bash_guardian import _is_path_candidate
candidate_tests = [
    ('', False, 'empty string'),
    ('a' * 4097, False, 'too long'),
    ('a\x00b', False, 'null byte'),
    ('normal/path', True, 'normal path'),
    ('a\nb', False, 'newline in path'),
    ('-flag', True, 'flag-like (filtered elsewhere)'),
    ('/' + 'a' * 256, False, 'component too long'),
]
for s, expected, desc in candidate_tests:
    result = _is_path_candidate(s)
    status = 'PASS' if result == expected else 'FAIL'
    print(f"  [{status}] {desc}: expected={expected}, got={result}")
