import re

old_pattern = r"(?i)(?:rm|rmdir|del|remove-item).*\.git(?:\s|/|$)"
new_pattern = r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`'\"]|$)"

test_cases = [
    # Expected Matches (Should be blocked by NEW)
    ("rm .git", True, "Basic rm"),
    ("rm -rf .git", True, "rm with flags"),
    ("del .git/HEAD", True, "del subdirectory"),
    ("; rm .git", True, "Semicolon separator"),
    ("&& rm .git", True, "And separator"),
    ("  rm .git", True, "Leading whitespace"),
    ("{ rm .git; }", True, "Brace group"),
    ("rm \".git\"", True, "Double quoted path"),
    ("rm '.git'", True, "Single quoted path"),
    ("delete .git", True, "New verb 'delete'"),
    ("deletion .git", True, "New verb 'deletion'"),
    ("(rm .git)", True, "Parenthesis group"),
    ("`rm .git`", True, "Backtick substitution"),

    # Expected Non-Matches (Should NOT be blocked)
    ("ls .git", False, "ls command"),
    ("cat .git/config", False, "cat command"),
    ("python3 script.py --action delete .git/config", False, "delete as argument"),
    ("echo rm .git", False, "rm as echo argument"),
    ("farm .git", False, "Suffix match (farm contains rm)"),
    ("confirm .git", False, "Suffix match (confirm contains rm)"),
]

print(f"{'TEST CASE':<50} | {'OLD':<10} | {'NEW':<10} | {'EXPECTED (NEW)':<15} | {'STATUS'}")
print("-" * 105)

all_passed = True

for text, expected_new, desc in test_cases:
    match_old = bool(re.search(old_pattern, text))
    match_new = bool(re.search(new_pattern, text))
    
    status = "PASS" if match_new == expected_new else "FAIL"
    if status == "FAIL":
        all_passed = False
        
    print(f"{text:<50} | {str(match_old):<10} | {str(match_new):<10} | {str(expected_new):<15} | {status}")

if all_passed:
    print("\nSUCCESS: All test cases passed for the NEW pattern.")
else:
    print("\nFAILURE: Some test cases failed.")
