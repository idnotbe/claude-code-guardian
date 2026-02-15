#!/usr/bin/env python3
"""Real-world test for the OSError Errno 36 (ENAMETOOLONG) bug fix in bash_guardian.py.

This test verifies that:
1. The EXACT command that caused the crash no longer crashes
2. _is_path_candidate correctly rejects non-path strings
3. extract_paths handles multiline commands gracefully
4. Normal commands still work (no regression)

Bug: Multiline bash command caused OSError Errno 36 when shlex.split() produced
tokens containing newlines/long strings that were then passed to os.path operations.

Fix: Added _is_path_candidate() guard in extract_paths() that rejects strings with
newlines, null bytes, or exceeding OS path length limits.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Setup: point to the guardian scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402
GUARDIAN_DIR = str(_bootstrap._REPO_ROOT / 'hooks' / 'scripts')

# We need a project dir for extract_paths
TEST_DIR = tempfile.mkdtemp(prefix="errno36_test_")
os.environ["CLAUDE_PROJECT_DIR"] = TEST_DIR

# Create .claude/guardian directory for logging
guardian_dir = Path(TEST_DIR) / ".claude" / "guardian"
guardian_dir.mkdir(parents=True, exist_ok=True)

# Create a minimal config so guardian doesn't use fallback
import json
config = {
    "bashToolPatterns": {"block": [], "ask": []},
    "zeroAccessPaths": [],
    "readOnlyPaths": [],
    "noDeletePaths": [],
}
with open(guardian_dir / "config.json", "w") as f:
    json.dump(config, f)

# Now import the functions under test
# Clear any cached config first
import _guardian_utils
_guardian_utils._config_cache = None
_guardian_utils._using_fallback_config = False

from bash_guardian import _is_path_candidate, extract_paths

# ============================================================
# Test tracking
# ============================================================
passed = 0
failed = 0
errors = []

def test(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        errors.append(name)
        print(f"  [FAIL] {name}")
        if detail:
            print(f"         {detail}")

# ============================================================
# TEST 1: The EXACT crash command from the log
# ============================================================
print("\n" + "=" * 60)
print("TEST 1: Original crash command (OSError Errno 36)")
print("=" * 60)

CRASH_COMMAND = """bash -c '
# Test alias with multiple flags (for comparison)
shopt -s expand_aliases
alias test_alias="echo --flag1 val1 --flag1 val2"
# Aliases cannot take arguments appended after substitution reliably
# in non-interactive shells. Functions are the correct approach.
echo "Alias test in non-interactive: skipped (aliases need interactive shell)"

# Function works:
test_func() { echo --flag1 val1 --flag1 val2 "$@"; }
echo "Function test: $(test_func --extra-arg)"
'"""

try:
    paths = extract_paths(CRASH_COMMAND, Path(TEST_DIR))
    test("Original crash command does not raise OSError", True)
    test("Returns empty or valid paths (no crash)", isinstance(paths, list))
except OSError as e:
    test("Original crash command does not raise OSError", False, f"OSError: {e}")
    test("Returns empty or valid paths (no crash)", False, f"OSError: {e}")
except Exception as e:
    test("Original crash command does not raise OSError", False, f"{type(e).__name__}: {e}")
    test("Returns empty or valid paths (no crash)", False, f"{type(e).__name__}: {e}")

# ============================================================
# TEST 2: _is_path_candidate unit tests
# ============================================================
print("\n" + "=" * 60)
print("TEST 2: _is_path_candidate unit tests")
print("=" * 60)

# Should REJECT (return False)
test("Rejects empty string", not _is_path_candidate(""))
test("Rejects string with newlines", not _is_path_candidate("line1\nline2"))
test("Rejects string with carriage return", not _is_path_candidate("line1\rline2"))
test("Rejects string with null byte", not _is_path_candidate("path\x00injection"))
test("Rejects string > 4096 chars", not _is_path_candidate("a" * 5000))
test("Rejects path with component > 255 chars", not _is_path_candidate("dir/" + "x" * 256 + "/file"))

# Should ACCEPT (return True)
test("Accepts normal relative path", _is_path_candidate("src/main.py"))
test("Accepts absolute path", _is_path_candidate("/home/user/file.txt"))
test("Accepts path with spaces", _is_path_candidate("/home/user/my file.txt"))
test("Accepts single filename", _is_path_candidate("README.md"))
test("Accepts dotfile", _is_path_candidate(".gitignore"))
# Note: "a" * 4096 is a single component of 4096 chars (> 255 NAME_MAX), so it's correctly rejected.
# A valid 4096-char path must use "/" separators to keep each component <= 255.
test("Rejects 4096-char single component (exceeds NAME_MAX)", not _is_path_candidate("a" * 4096))
test("Accepts 4096-char path with separators", _is_path_candidate("/".join(["a" * 100] * 40)))
test("Accepts component at exactly 255 chars", _is_path_candidate("dir/" + "x" * 255 + "/file"))

# Edge cases from the crash: multiline content that shlex.split might produce
multiline_token = """
# Test alias with multiple flags (for comparison)
shopt -s expand_aliases
alias test_alias="echo --flag1 val1 --flag1 val2"
"""
test("Rejects multiline shell script content", not _is_path_candidate(multiline_token))

# ============================================================
# TEST 3: Other multiline commands (Claude Code common patterns)
# ============================================================
print("\n" + "=" * 60)
print("TEST 3: Other multiline commands (common Claude Code patterns)")
print("=" * 60)

multiline_commands = [
    # Heredoc pattern
    (
        "heredoc command",
        """cat <<'EOF'
This is a heredoc
with multiple lines
and special chars: $HOME ~/ ../
EOF"""
    ),
    # For loop
    (
        "for loop over files",
        """for f in *.py; do
    echo "Processing $f"
    python3 -c "import ast; ast.parse(open('$f').read())"
done"""
    ),
    # If-else
    (
        "if-else statement",
        """if [ -f "package.json" ]; then
    npm install
    npm run build
else
    echo "No package.json found"
fi"""
    ),
    # Python one-liner
    (
        "python multiline one-liner",
        """python3 -c "
import json
import sys
data = json.load(open('config.json'))
print(json.dumps(data, indent=2))
" """
    ),
    # Piped chain across lines
    (
        "piped chain with backslash continuation",
        """find . -name "*.py" -type f | \
    xargs grep -l "import os" | \
    sort | \
    head -20"""
    ),
    # Complex bash -c
    (
        "complex bash -c with function definitions",
        """bash -c '
check_deps() {
    for cmd in python3 node npm git; do
        if command -v "$cmd" > /dev/null 2>&1; then
            echo "[OK] $cmd found: $(command -v "$cmd")"
        else
            echo "[MISSING] $cmd not found"
        fi
    done
}
check_deps
'"""
    ),
    # Node.js one-liner
    (
        "node multiline one-liner",
        """node -e "
const fs = require('fs');
const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
console.log(pkg.name + '@' + pkg.version);
" """
    ),
    # While read loop
    (
        "while read loop",
        """git log --oneline --no-merges -20 | while read hash msg; do
    echo "Commit: $hash - $msg"
    git show --stat --format="" "$hash"
    echo "---"
done"""
    ),
    # docker-compose style
    (
        "docker compose multiline",
        """docker compose -f docker-compose.yml \
    -f docker-compose.override.yml \
    up --build -d \
    --force-recreate \
    --remove-orphans"""
    ),
    # Nested command substitution
    (
        "nested command substitution",
        """echo "Python version: $(python3 --version 2>&1)"
echo "Node version: $(node --version 2>&1)"
echo "Git version: $(git --version 2>&1)"
echo "Disk usage: $(du -sh . 2>/dev/null | cut -f1)"
"""
    ),
]

for name, cmd in multiline_commands:
    try:
        paths = extract_paths(cmd, Path(TEST_DIR))
        test(f"No crash: {name}", True)
    except OSError as e:
        test(f"No crash: {name}", False, f"OSError: {e}")
    except Exception as e:
        test(f"No crash: {name}", False, f"{type(e).__name__}: {e}")

# ============================================================
# TEST 4: Normal commands (regression check)
# ============================================================
print("\n" + "=" * 60)
print("TEST 4: Normal commands (no regression)")
print("=" * 60)

# Create some test files
(Path(TEST_DIR) / "test.py").touch()
(Path(TEST_DIR) / "README.md").touch()
(Path(TEST_DIR) / "src").mkdir(exist_ok=True)
(Path(TEST_DIR) / "src" / "main.py").touch()

normal_commands = [
    ("simple ls", "ls -la"),
    ("simple cat", f"cat {TEST_DIR}/test.py"),
    ("simple rm", f"rm {TEST_DIR}/test.py"),
    ("git status", "git status"),
    ("python run", f"python3 {TEST_DIR}/src/main.py"),
    ("echo", 'echo "hello world"'),
]

for name, cmd in normal_commands:
    try:
        paths = extract_paths(cmd, Path(TEST_DIR))
        test(f"No crash: {name}", isinstance(paths, list))
    except Exception as e:
        test(f"No crash: {name}", False, f"{type(e).__name__}: {e}")

# Test that existing paths are actually extracted
try:
    readme_path = Path(TEST_DIR) / "README.md"
    paths = extract_paths(f"cat {readme_path}", Path(TEST_DIR))
    test("Extracts existing file path", len(paths) >= 1 and readme_path.resolve() in [p.resolve() for p in paths],
         f"Expected {readme_path} in {paths}")
except Exception as e:
    test("Extracts existing file path", False, f"{type(e).__name__}: {e}")

# ============================================================
# TEST 5: Edge cases - strings that could trigger Errno 36
# ============================================================
print("\n" + "=" * 60)
print("TEST 5: Edge cases that could trigger Errno 36")
print("=" * 60)

edge_cases = [
    ("very long argument", f"echo {'A' * 300}"),
    ("arg with special chars", "echo 'hello\nworld'"),
    ("binary-like content", f"echo $'\\x00\\x01\\x02\\x03'"),
    ("deeply nested path", "cat " + "/".join(["a"] * 100) + "/file.txt"),
    ("unicode path", "cat /tmp/\u00e9\u00e0\u00fc/file.txt"),
    ("empty command", ""),
    ("just flags", "cmd --flag1 --flag2 --flag3"),
]

for name, cmd in edge_cases:
    try:
        paths = extract_paths(cmd, Path(TEST_DIR))
        test(f"No crash: {name}", isinstance(paths, list))
    except OSError as e:
        test(f"No crash: {name}", False, f"OSError: {e}")
    except Exception as e:
        test(f"No crash: {name}", False, f"{type(e).__name__}: {e}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
total = passed + failed
print(f"  Total:  {total}")
print(f"  PASSED: {passed}")
print(f"  FAILED: {failed}")

if errors:
    print("\n  Failed tests:")
    for e in errors:
        print(f"    - {e}")

print("=" * 60)

# Cleanup
try:
    shutil.rmtree(TEST_DIR)
except Exception:
    pass

sys.exit(0 if failed == 0 else 1)
