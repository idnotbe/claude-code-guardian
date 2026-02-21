import re

# Fixed: escaped the double quote inside the string literal
new_pattern = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`'\"]|$)"

# Potential bypasses
bypasses = [
    ("rm\\ .git", False, "Escaped space (bypass expected?)"),
    ("rm\t.git", True, "Tab separator"),
    ("rm\n.git", True, "Newline separator"),
    ("rm .git.", False, "Trailing dot (should not match)"),
    ("rm .git..", False, "Trailing dots (should not match)"),
    ("rm .git/", True, "Trailing slash (should match)"),
    ("rm .git/config", True, "Subfile (should match)"),
    ("rm .gitignore", False, "Gitignore file (should NOT match)"),
    ("rm .git", True, "Basic match"),
    ("rm .git]", False, "Trailing bracket (should not match as ] is not in suffix)"),
]

print(f"{'TEST CASE':<30} | {'MATCH':<10} | {'EXPECTED':<10} | {'COMMENT'}")
print("-" * 80)

for text, expected, comment in bypasses:
    match = bool(re.search(new_pattern, text))
    status = "PASS" if match == expected else "FAIL"
    print(f"{text:<30} | {str(match):<10} | {str(expected):<10} | {comment}")
