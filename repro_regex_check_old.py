import re

old_pattern = r"(?i)(?:rm|rmdir|del|remove-item).*\.git(?:\s|/|$)"

cases = [
    ("sudo rm .git", True, "sudo prefix"),
    (r"\rm .git", True, "backslash prefix"),
    ("command rm .git", True, "command prefix"),
]

print(f"{'TEST CASE':<30} | {'MATCH':<10} | {'EXPECTED':<10} | {'COMMENT'}")
print("-" * 80)

for text, expected, comment in cases:
    match = bool(re.search(old_pattern, text))
    status = "PASS" if match == expected else "FAIL"
    print(f"{text:<30} | {str(match):<10} | {str(expected):<10} | {comment}")
