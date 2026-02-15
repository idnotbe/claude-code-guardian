#!/usr/bin/env python3
"""Test whether Layer 1 raw scan catches -f.env pattern."""
import re
import sys

# Simulate Layer 1 scan for '-f.env'
# The boundary_before regex from scan_protected_paths
boundary_before = r'(?:^|[\s;|&<>("`\'=/,{])'
boundary_after = r"(?:$|[\s;|&<>)\"`'/,}])"

# For .env exact match pattern
literal = '.env'
regex = boundary_before + re.escape(literal) + boundary_after

command = 'grep -f.env password'
match = re.search(regex, command)
print(f'Layer 1 scan for literal in command: {"MATCH" if match else "NO MATCH"}')
if match:
    print(f'  matched: "{match.group()}"')

# Character before the literal
idx = command.index('.env')
char_before = command[idx-1] if idx > 0 else '(start)'
print(f'Character before .env: "{char_before}"')
print(f'Is "f" in boundary chars: {"f" in set(" ;|&<>()\"\x60\x27=/,{}")}')

# Also test what exactMatchAction would do
# With P0-2 fix, exactMatchAction is now "ask" not "deny"
print(f'\nConclusion: Layer 1 {"CATCHES" if match else "MISSES"} -f.env')
if not match:
    print('  Need to add special handling in extract_paths for flag-concatenated paths')
