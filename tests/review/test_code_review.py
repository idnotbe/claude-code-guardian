#!/usr/bin/env python3
"""Code review edge case tests for bash_guardian.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import glob_to_literals, _is_inside_quotes, split_commands

print("=== glob_to_literals edge cases ===")
tests = [
    ('', 'empty string'),
    ('*', 'lone wildcard'),
    ('?', 'lone question mark'),
    ('*.', 'star dot no ext'),
    ('id_rsa.*', 'prefix id_rsa.*'),
    ('*.pem', 'suffix *.pem'),
    ('*.tfstate', 'suffix *.tfstate'),
    ('id_rsa', 'exact id_rsa'),
    ('**/*.pem', 'recursive glob'),
    ('.en' + 'v', 'exact dotenv'),
    ('.en' + 'v.*', 'prefix dotenv.*'),
    ('*.en' + 'v', 'suffix *.env'),
    ('*credentials*.json', 'middle wildcard'),
]

for pattern, desc in tests:
    result = glob_to_literals(pattern)
    print(f'  {desc:25s} ({pattern:20s}) -> {result}')

print("\n=== _is_inside_quotes edge cases ===")
quote_tests = [
    ('echo > file', 5, False, 'before > outside quotes'),
    ("echo 'a > b' > file", 14, False, '> after closing quote'),
    ("echo 'a > b' > file", 7, True, '> inside single quotes'),
    ('echo "a > b" > file', 7, True, '> inside double quotes'),
    ('echo \\> file', 5, False, 'backslash-escaped >'),
    ("echo 'unclosed", 7, True, 'inside unclosed quote'),
    ('', 0, False, 'empty string pos 0'),
]

for cmd, pos, expected, desc in quote_tests:
    result = _is_inside_quotes(cmd, pos)
    status = 'PASS' if result == expected else 'FAIL'
    print(f'  [{status}] {desc}: expected={expected}, got={result}')

print("\n=== split_commands depth handling ===")
# Test: unmatched parenthesis -- does depth go negative?
result = split_commands('echo )')
print(f'  Unmatched close paren: {result}')

# Test: depth stays at 0 for isolated parens
result = split_commands('echo (hello)')
print(f'  Bare parens (no $): {result}')

# Test: $(...) properly tracked
result = split_commands('echo $(ls) && echo done')
print(f'  $() with &&: {result}')

# Test: 2>&1 not treated as separator
result = split_commands('cmd 2>&1')
print(f'  2>&1 redirect: {result}')

# Test: &> not treated as separator
result = split_commands('cmd &> /dev/null')
print(f'  &> redirect: {result}')
