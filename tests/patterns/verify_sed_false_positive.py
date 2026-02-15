
import re
pat = r"\bsed\s+.*-[^-]*i"
cmd = "sed -n 'print' file"
match = re.search(pat, cmd, re.IGNORECASE)
print(f"Command: '{cmd}'")
if match:
    print(f"Match found: '{match.group(0)}'")
else:
    print("No match")
