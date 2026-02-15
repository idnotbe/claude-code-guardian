#!/usr/bin/env python3
"""V1-Security verification tests for P0+P1 fixes."""
import re
import time

print("=" * 60)
print("V1-SECURITY VERIFICATION TESTS")
print("=" * 60)

# ============================================================
# P0-1: ReDoS fix verification
# ============================================================
print("\n--- P0-1: ReDoS eval pattern ---")
new_pat = r'(?i)eval\s+(?:[\'"]\s*)?(?:rm|del|rmdir|shred)'

# Adversarial: must complete in <100ms
test_input = 'eval ' + 'x' * 20000
start = time.time()
re.search(new_pat, test_input)
elapsed_ms = (time.time() - start) * 1000
print(f"20k adversarial: {elapsed_ms:.2f}ms {'PASS' if elapsed_ms < 100 else 'FAIL'}")

test_input = 'eval ' + 'x' * 40000
start = time.time()
re.search(new_pat, test_input)
elapsed_ms = (time.time() - start) * 1000
print(f"40k adversarial: {elapsed_ms:.2f}ms {'PASS' if elapsed_ms < 100 else 'FAIL'}")

# ============================================================
# P0-3: Verdict fail-close verification
# ============================================================
print("\n--- P0-3: Verdict fail-close ---")

_VERDICT_PRIORITY = {"deny": 2, "ask": 1, "allow": 0}
_FAIL_CLOSE_PRIORITY = max(_VERDICT_PRIORITY.values())

def _stronger_verdict(current, candidate):
    if _VERDICT_PRIORITY.get(candidate[0], _FAIL_CLOSE_PRIORITY) > _VERDICT_PRIORITY.get(current[0], _FAIL_CLOSE_PRIORITY):
        return candidate
    return current

# Unknown beats allow
result = _stronger_verdict(("allow", "ok"), ("unknown_string", "test"))
print(f"unknown vs allow: {result[0]} {'PASS' if result[0] == 'unknown_string' else 'FAIL'}")

# Unknown ties with deny (deny kept since not strictly greater)
result = _stronger_verdict(("deny", "blocked"), ("unknown_string", "test"))
print(f"unknown vs deny: {result[0]} {'PASS' if result[0] == 'deny' else 'FAIL'}")

# Allow does not beat unknown
result = _stronger_verdict(("unknown_string", "test"), ("allow", "ok"))
print(f"allow vs unknown: {result[0]} {'PASS' if result[0] == 'unknown_string' else 'FAIL'}")

# Two unknowns: current kept
result = _stronger_verdict(("weird1", "a"), ("weird2", "b"))
print(f"unknown vs unknown: {result[0]} {'PASS' if result[0] == 'weird1' else 'FAIL'}")

# ============================================================
# P1-1: git rm delete detection
# ============================================================
print("\n--- P1-1: git rm ---")
pat = r'(?:^|[;&|]\s*)git\s+rm\s+'
positives = [
    "git rm CLAUDE.md",
    "git rm -f file.txt",
    "git rm --cached file",
    "git rm -r dir/",
]
negatives = [
    "git status",
    "git commit -m 'remove files'",
    "git add .",
    "git push",
]
for cmd in positives:
    m = bool(re.search(pat, cmd, re.IGNORECASE))
    print(f"  {'PASS' if m else 'FAIL'}: detect '{cmd}'")
for cmd in negatives:
    m = bool(re.search(pat, cmd, re.IGNORECASE))
    print(f"  {'PASS' if not m else 'FAIL'}: safe '{cmd}'")

# Bypass vectors (known gaps)
bypass_vectors = [
    "git -C . rm CLAUDE.md",        # git -C before rm
    "/usr/bin/git rm CLAUDE.md",    # absolute path
    "command git rm CLAUDE.md",     # shell wrapper
]
print("  Known gaps (not caught):")
for cmd in bypass_vectors:
    m = bool(re.search(pat, cmd, re.IGNORECASE))
    print(f"    {'GAP-CONFIRMED' if not m else 'CAUGHT'}: '{cmd}'")

# ============================================================
# P1-2: Truncation detection
# ============================================================
print("\n--- P1-2: Redirect truncation ---")
pat = r'^\s*(?::)?\s*>(?!>)\|?\s*\S+'
positives = [
    "> CLAUDE.md",
    ": > CLAUDE.md",
    ">| CLAUDE.md",
    "  > file.txt",
]
negatives = [
    "echo hello > file",
    ">> file.txt",
    "cat foo > bar",
]
for cmd in positives:
    m = bool(re.search(pat, cmd))
    print(f"  {'PASS' if m else 'FAIL'}: detect '{cmd}'")
for cmd in negatives:
    m = bool(re.search(pat, cmd))
    print(f"  {'PASS' if not m else 'FAIL'}: safe '{cmd}'")

# Known gap
print("  Known gaps:")
for cmd in ["1> CLAUDE.md", "2> CLAUDE.md"]:
    m = bool(re.search(pat, cmd))
    print(f"    {'GAP-CONFIRMED' if not m else 'CAUGHT'}: '{cmd}'")

# ============================================================
# P1-3: Glob bracket expansion
# ============================================================
print("\n--- P1-3: Glob bracket check ---")
# The check: if "*" in str(path) or "?" in str(path) or "[" in str(path)
test_paths = [".en[v]", "test?.txt", "*.py", "normal.txt"]
for p in test_paths:
    has_glob = "*" in p or "?" in p or "[" in p
    print(f"  '{p}' triggers glob: {has_glob}")

# ============================================================
# P1-4: Metadata write commands
# ============================================================
print("\n--- P1-4: Metadata write commands ---")
write_pats = [r"\bchmod\s+", r"\btouch\s+", r"\bchown\s+", r"\bchgrp\s+"]
positives = ["chmod 777 file", "touch file", "chown root file", "chgrp staff file"]
negatives = ["cat file", "ls -la", "grep pattern"]
for cmd in positives:
    m = any(re.search(p, cmd, re.IGNORECASE) for p in write_pats)
    print(f"  {'PASS' if m else 'FAIL'}: detect '{cmd}'")
for cmd in negatives:
    m = any(re.search(p, cmd, re.IGNORECASE) for p in write_pats)
    print(f"  {'PASS' if not m else 'FAIL'}: safe '{cmd}'")

# ============================================================
# P1-6: Flag-concatenated path
# ============================================================
print("\n--- P1-6: Flag path extraction ---")
# Verify Layer 1 does NOT catch -f.env
boundary_before = r'(?:^|[\s;|&<>()"' + r"'" + r'`=/,{])'
boundary_after = r'(?:$|[\s;|&<>)"' + r"'" + r'/,}])'
layer1_regex = boundary_before + re.escape('.env') + boundary_after
test_cmd = 'grep -f.env password'
m = re.search(layer1_regex, test_cmd)
print(f"  Layer 1 catches 'grep -f.env password': {bool(m)} (should be False)")
# Char before .env is 'f', not in boundary set
idx = test_cmd.index('.env')
char_before = test_cmd[idx-1] if idx > 0 else '^'
print(f"  Char before .env: '{char_before}' (not in boundary set = Layer 1 misses)")
print(f"  P1-6 fix needed: {'YES' if not m else 'NO'}")

# ============================================================
# Cross-cutting: final verdict emission check
# ============================================================
print("\n--- Final verdict emission check ---")
print("  Checking if unknown verdicts can slip through to allow...")
print("  In main(): final_verdict starts as ('allow', '')")
print("  If unknown verdict enters via _stronger_verdict, it becomes ('unknown', 'reason')")
print("  Final emission checks: if final_verdict[0] == 'deny' -> deny")
print("  Then: if final_verdict[0] == 'ask' -> ask")
print("  Else: implicit allow (sys.exit(0) with no output)")
print("  ISSUE: An unknown verdict is NOT 'deny' and NOT 'ask', so it falls through to allow!")
print("  This is the Codex Critical #1 finding - fail-close is incomplete at emission")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
