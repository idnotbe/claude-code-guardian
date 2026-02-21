import re

# The pattern provided by the user
# Using triple quotes to avoid escaping issues
PATTERN = r"""(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`'"]|$)"""

# Flags provided: IGNORECASE | DOTALL
FLAGS = re.IGNORECASE | re.DOTALL

def test_pattern(text):
    match = re.search(PATTERN, text, FLAGS)
    return bool(match)

test_cases = [
    # Baseline - should match
    ("rm .claude", True),
    ("rm -rf .claude", True),
    ("echo hi; rm .claude", True),
    
    # 1. Shell quoting tricks
    ("rm '.claude'", True),
    ('rm ".claude"', True),
    ("rm .cl''aude", False), # Shell concatenation - regex sees literal .cl''aude, shell sees .claude
    ('rm .cl""aude', False),
    (r"rm \.claude", False), # Regex expects literal . but here it is \.
    
    # 2. Command prefixes
    ("sudo rm .claude", False), # "sudo" is not "rm"
    ("env rm .claude", False),
    ("nohup rm .claude", False),
    ("busybox rm .claude", False),
    
    # 3. Variable expansion
    ("D=.claude; rm $D", False),
    ("rm ${TARGET}", False),
    
    # 4. Glob patterns
    ("rm .claud?", False),
    ("rm .cl*", False),
    ("rm .[c]laude", False),
    
    # 6. Newline injection (Multiline flag is OFF)
    ("echo hello\nrm .claude", False), # Newline is a separator in shell, but not in regex anchor
    ("echo hello\r\nrm .claude", False),
    
    # 9. Indirect execution
    ("find . -name .claude -exec rm {} \;", False),
    ("echo .claude | xargs rm", False),
    
    # 10. Aliasing/Functions
    ('myrm() { rm "$@"; }; myrm .claude', False),
    
    # Path variations
    ("rm ./ .claude", True), # " .claude"
    ("rm /abs/path/.claude", True),
    ("rm ./.claude", True),
    
    # Obfuscation
    ("rm  .claude", True),
    ("rm\t.claude", True),
    
    # 5. Encoding tricks
    (r"rm $'\056claude'", False), # Bash ANSI-C quoting
    (r"rm $'\x2eclaude'", False),
]

print(f"Testing pattern: {PATTERN}")
print("-" * 60)
print(f"{'TEST CASE':<50} | {'MATCH':<5} | {'EXPECTED':<8} | {'RESULT':<4}")
print("-" * 60)

for text, expected in test_cases:
    matched = test_pattern(text)
    # status = "CAUGHT" if matched else "BYPASSED"
    # But expected is True if we expect it to be caught.
    # So if expected is False, and matched is False, it's a "PASS" on our expectation (which is a successful bypass).
    
    status = "CAUGHT" if matched else "BYPASSED"
    print(f"{repr(text):<50} | {str(matched):<5} | {str(expected):<8} | {status}")
