import re

pattern = r"(?:^|[;&|]\s*)git\s+rm\s+"

commands = [
    "git rm file",
    "git  rm file",
    "git -C . rm file",
    "git --git-dir=.git rm file",
    "echo a; git rm file",
    "git-rm file",
    "git \"rm\" file",
    "git 'rm' file",
    "git\rm file",
]

print(f"Pattern: {pattern}")
for cmd in commands:
    match = re.search(pattern, cmd)
    print(f"'{cmd}': {bool(match)}")
