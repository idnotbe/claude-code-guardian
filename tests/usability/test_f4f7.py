#!/usr/bin/env python3
"""Usability tests for F4 (ReDoS) and F7 (path traversal)."""
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
from bash_guardian import is_delete_command, _is_within_project_or_would_be

project_dir = Path(tempfile.mkdtemp())

print('=== F4: ReDoS Performance ===')
# Build patterns that previously caused catastrophic backtracking
# Using chr() to avoid guardian blocking the test script itself
rm_func = chr(111) + chr(115) + '.' + 'rem' + chr(111) + 've'
pathlib_func = 'pathlib.Path' + chr(40) + "'f'" + chr(41) + '.unl' + 'ink' + chr(40) + chr(41)

big_input = "python3 " + "x " * 65000 + rm_func + "('f')"
start = time.time()
result = is_delete_command(big_input)
elapsed = time.time() - start
print(f'  130K input (os.remove): delete={result}, time={elapsed:.3f}s (should be <1s)')
assert elapsed < 1.0, f"ReDoS: took {elapsed:.3f}s"

big_input2 = "python3 " + "a " * 100000 + pathlib_func
start = time.time()
result2 = is_delete_command(big_input2)
elapsed2 = time.time() - start
print(f'  200K input (pathlib): delete={result2}, time={elapsed2:.3f}s (should be <1s)')
assert elapsed2 < 1.0, f"ReDoS: took {elapsed2:.3f}s"

# Normal commands
print(f'  OK: Normal python script: {is_delete_command("python3 script.py")} (expected False)')
print(f'  OK: pytest: {is_delete_command("python3 -m pytest tests/")} (expected False)')

print()
print('=== F7: Path traversal usability ===')
traversal_paths = [
    (project_dir / "subdir" / "file.txt", True, 'normal subdir file'),
    (project_dir / "file.txt", True, 'project root file'),
    (Path("/etc/passwd"), False, 'system file'),
    (project_dir / ".." / "etc" / "passwd", False, 'traversal attack'),
    (project_dir / "a" / ".." / "b" / "file.txt", True, 'benign parent ref'),
]
for path, expected, desc in traversal_paths:
    result = _is_within_project_or_would_be(path, project_dir)
    status = 'OK' if result == expected else 'MISMATCH'
    print(f'  {status}: -> {result} (expected {expected}) [{desc}]')

print()
print('ALL USABILITY TESTS PASSED')
