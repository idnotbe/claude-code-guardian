import re

new_pattern = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`'\"]|$)"

bypasses = [
    (r"\rm .git", False, "Backslash bypass"),
    ("sudo rm .git", False, "sudo prefix"),
    ("command rm .git", False, "command prefix"),
]

print(f"{'TEST CASE':<30} | {'MATCH':<10} | {'EXPECTED':<10} | {'COMMENT'}")
print("-" * 80)

for text, expected, comment in bypasses:
    match = bool(re.search(new_pattern, text))
    status = "PASS" if match == expected else "FAIL"
    print(f"{text:<30} | {str(match):<10} | {str(expected):<10} | {comment}")
