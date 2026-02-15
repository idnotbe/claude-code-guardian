import re

redirect_pattern = r"^\s*(?::)?\s*>(?!>)\|?\s*\S+"
write_patterns = [
    r"\bchmod\s+",
    r"\btouch\s+",
    r"\bchown\s+",
    r"\bchgrp\s+",
]

redirects = [
    "> file",
    ": > file",
    "echo > file",
    "echo -n > file",
    "cp /dev/null file",
    ">| file",
    ">> file",
]

writes = [
    "chmod 777 file",
    "chmod-x file",
    "chmod=777 file",
    "install -m 777 file",
    "setfacl -m u:user:rwx file",
    "touch file",
    "touch-file",
]

print(f"Redirect Pattern: {redirect_pattern}")
for cmd in redirects:
    match = re.search(redirect_pattern, cmd)
    print(f"'{cmd}': {bool(match)}")

print("\nWrite Patterns:")
for pattern in write_patterns:
    print(f"Pattern: {pattern}")
    for cmd in writes:
        match = re.search(pattern, cmd)
        if match:
            print(f"  Matches: '{cmd}'")
