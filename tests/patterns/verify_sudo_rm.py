
import re
delete_patterns = [
    r"(?:^|[;&|]\s*)rm\s+",
]
cmd = "sudo rm file"
match = any(re.search(p, cmd, re.IGNORECASE) for p in delete_patterns)
print(f"Command: '{cmd}', Detected: {match}")

cmd2 = "xargs rm"
match2 = any(re.search(p, cmd2, re.IGNORECASE) for p in delete_patterns)
print(f"Command: '{cmd2}', Detected: {match2}")
