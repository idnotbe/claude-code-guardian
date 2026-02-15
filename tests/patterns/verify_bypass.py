#!/usr/bin/env python3
"""Verify bypass vectors for interpreter-mediated deletion fix."""
import re
import time

python_pattern = r'(?:python[23]?|python\d[\d.]*)\s[^;|&\n]*(?:os\.remove|os\.unlink|shutil\.rmtree|os\.rmdir)'
node_pattern = r'(?:node|deno|bun)\s[^;|&\n]*(?:unlinkSync|rmSync|rmdirSync|fs\.unlink|fs\.rm\b)'
perl_ruby_pattern = r'(?:perl|ruby)\s[^;|&\n]*(?:\bunlink\b|File\.delete|FileUtils\.rm)'

all_patterns = [python_pattern, node_pattern, perl_ruby_pattern]

def check_any(cmd):
    for p in all_patterns:
        if re.search(p, cmd, re.IGNORECASE | re.DOTALL):
            return True
    return False

print("=" * 70)
print("TASK B: Bypass Analysis")
print("=" * 70)

# Bypass 1: Variable assignment
print("\n--- Bypass 1: Variable assignment ---")
cmd = 'python3 -c "import os; o=os; o.remove(\'file\')"'
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - o.remove not detected'}")

# Bypass 2: exec wrapping
print("\n--- Bypass 2: exec wrapping ---")
cmd = "python3 -c \"exec('os.remove(\\\"file\\\")')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  Analysis: 'os.remove' appears literally in the string, so regex CAN match it")

# Bypass 3: pathlib
print("\n--- Bypass 3: pathlib ---")
cmd = "python3 -c \"import pathlib; pathlib.Path('file').unlink()\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - pathlib.Path.unlink not in pattern'}")

# Bypass 4: heredoc
print("\n--- Bypass 4: heredoc ---")
cmd = "python3 << 'EOF'\nos.remove('file')\nEOF"
detected = check_any(cmd)
print(f"  Command: python3 << 'EOF'\\nos.remove('file')\\nEOF")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - heredoc body after newline'}")

# Bypass 5: env prefix
print("\n--- Bypass 5: env prefix ---")
cmd = "env python3 -c \"os.remove('file')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - env prefix blocks match'}")

# Bypass 6: Node.js fs.promises
print("\n--- Bypass 6: Node.js fs.promises.unlink ---")
cmd = "node -e \"require('fs').promises.unlink('file')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - promises.unlink != fs.unlink'}")

# Additional vectors
print("\n--- Additional: piped input ---")
cmd = "echo \"os.remove('f')\" | python3"
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - piped stdin invisible'}")

print("\n--- Additional: Windows py launcher ---")
cmd = "py -c \"os.remove('f')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - py launcher not in pattern'}")

print("\n--- Additional: Deno.removeSync ---")
cmd = "deno eval \"Deno.removeSync('f')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS - Deno.removeSync not in pattern'}")

print("\n--- Additional: Absolute path ---")
cmd = "/usr/bin/python3 -c \"os.remove('f')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS'}")

print("\n--- Additional: semicolon chain ---")
cmd = "echo hi; python3 -c \"os.remove('f')\""
detected = check_any(cmd)
print(f"  Command: {cmd}")
print(f"  Detected: {detected}")
print(f"  VERDICT: {'Caught' if detected else 'BYPASS'}")

# ReDoS checks
print("\n" + "=" * 70)
print("TASK B.7: ReDoS Risk Analysis")
print("=" * 70)

patterns_named = {
    'python': python_pattern,
    'node': node_pattern,
    'perl_ruby': perl_ruby_pattern,
}

for name, pattern in patterns_named.items():
    adversarial = name.split('_')[0] + ' ' + 'a' * 100000
    start = time.time()
    m = re.search(pattern, adversarial, re.IGNORECASE | re.DOTALL)
    elapsed = time.time() - start
    status = 'PASS' if elapsed < 0.5 else 'FAIL'
    print(f"  [{status}] {name}: 100k no-match in {elapsed:.4f}s")

print("\nReDoS Summary: [^;|&\\n]* is negated char class = O(n), no backtracking risk")
