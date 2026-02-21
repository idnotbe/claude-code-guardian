import re

# Added ['"] to terminator: (?:\s|/|[;&|)`]|$|['"])
pattern = r'''(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$|['"])'''
regex = re.compile(pattern)

test_cases = [
    ('rm ".claude"', True, "Double quoted target"),
    ("rm '.claude'", True, "Single quoted target"),
    ('rm ".claude_backup"', False, "Quoted backup file (suffix check)"),
    ('rm "foo/.claude"', True, "Quoted path ending in .claude"),
    ('rm "foo/.claude/"', True, "Quoted path ending in .claude/")
]

print(f"Testing FIXED pattern: {pattern}\n")

for text, expected, description in test_cases:
    match = regex.search(text)
    is_match = match is not None
    status = "PASS" if is_match == expected else "FAIL"
    print(f"[{status}] {description}")
    print(f"  Input:    '{text}'")
    print(f"  Match:   {is_match}")
    print()
