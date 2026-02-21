import re
import time
import sys

# Define the patterns as they appear in the JSON (but unescaped for Python string literals)
# JSON: "(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)`]|$)"
patterns = {
    "git": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`]|$)",
    "claude": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)",
    "archive": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`]|$)",
}

flags = re.IGNORECASE | re.DOTALL

test_cases = [
    # 1. Anchoring
    ("echo rm .git", "git", False, "Should NOT match 'rm' as argument to echo"),
    ("rm .git", "git", True, "Should match at start"),
    ("; rm .git", "git", True, "Should match after semicolon"),
    ("| rm .git", "git", True, "Should match after pipe"),
    ("& rm .git", "git", True, "Should match after ampersand"),
    ("`rm .git`", "git", True, "Should match inside backticks"),
    ("(rm .git)", "git", True, "Should match inside parens"),
    ("echo foo; rm .git", "git", True, "Should match after command separator"),

    # 2. Word boundary
    ("deleting .git", "git", False, "Should NOT match 'deleting' due to \\b"),
    ("deleted .git", "git", False, "Should NOT match 'deleted' due to \\b"),
    ("delete .git", "git", True, "Should match 'delete'"),

    # 3. False positive check
    ("python3 memory_write.py --action delete .claude/memory/MEMORY.md", "claude", False, "Should be ALLOWED (argument to python script)"),
    ("python3 memory_write.py --action delete .claude", "claude", False, "Should be ALLOWED (argument to python script)"),
    
    # 4. True positive check
    ("rm -rf .git", "git", True, "Should be BLOCKED"),
    ("delete .claude/config", "claude", True, "Should be BLOCKED"),
    
    # 5. Edge cases
    ("rm -rf src/.git", "git", True, "Should block .git inside path"),
    ("rm .gitignore", "git", False, "Should NOT block .gitignore"),
    ("rm src/.git/config", "git", True, "Should block inside .git"),
    
    # Newline check
    ("echo foo\nrm .git", "git", True, "Should match after newline"),
]

print(f"{'TEST CASE':<60} | {'PATT':<8} | {'EXPECT':<6} | {'ACTUAL':<6} | {'RESULT'}")
print("-" * 100)

for text, pat_key, expected, desc in test_cases:
    pattern = patterns[pat_key]
    match = re.search(pattern, text, flags)
    actual = bool(match)
    result = "PASS" if actual == expected else "FAIL"
    print(f"{text[:60]:<60} | {pat_key:<8} | {str(expected):<6} | {str(actual):<6} | {result}")
    if result == "FAIL":
        print(f"  -> {desc}")

# 5. ReDoS check (simple timing)
print("\n--- ReDoS Check ---")
long_string = "rm " + (" " * 50000) + ".git"
start = time.time()
re.search(patterns["git"], long_string, flags)
duration = time.time() - start
print(f"Long whitespace ({len(long_string)} chars): {duration:.6f}s")

attack_string = "rm " + ("a" * 50000)
start = time.time()
re.search(patterns["git"], attack_string, flags)
duration = time.time() - start
print(f"Long non-match ({len(attack_string)} chars): {duration:.6f}s")
