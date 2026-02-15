import re

# Boundary characters:
# whitespace, ;, |, &, <, >, (, ), ", backtick, ', =, /, comma, {, }

# Use triple quoted raw string to avoid escaping issues
regex_str = r"""(?:^|[\s;|,<>()"`'=/,{}])\.env(?:$|[\s;|,<>()"`'=/,{}])"""

pattern = re.compile(regex_str)

test_cases = [
    # Basic matches
    "cat .env",
    "echo \"test .env\"",
    ".env",
    " .env ",

    # Non-matches (should be false for .env inside words)
    ".environment",
    "my.env",
    ".env.local", # . is NOT a boundary char listed.
    "config.env.json",

    # Potential false positives
    "git commit -m \"Updated .env handling\"",
    "grep \".env\" file.txt",
    "find . -name \".env\"",
    "cp .env.example .env.local", # Check if .env match inside
    "sed 's/.env/.config/'",
    "rm .env",
    "echo .env >> .gitignore",
    "code .env",
    "LINK=https://site.com/.env", # / is boundary.
    "cat my.env",
    "cat .env_backup", # _ is not boundary.
]

print(f"Testing pattern: {regex_str}")

for t in test_cases:
    match = pattern.search(t)
    print(f"'{t}': {'MATCH' if match else 'NO MATCH'}")
