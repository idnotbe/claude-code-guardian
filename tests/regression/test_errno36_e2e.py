#!/usr/bin/env python3
"""End-to-end test for bash_guardian.py hook.

Simulates the JSON input that Claude Code sends to the PreToolUse hook
and verifies:
1. The original crash command doesn't crash the hook
2. Various multiline commands are handled gracefully
3. The hook produces valid JSON output (or exits cleanly)
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

GUARDIAN_SCRIPT = str(_bootstrap._REPO_ROOT / "hooks" / "scripts" / "bash_guardian.py")

# Create temp project dir
TEST_DIR = tempfile.mkdtemp(prefix="errno36_e2e_")
guardian_dir = Path(TEST_DIR) / ".claude" / "guardian"
guardian_dir.mkdir(parents=True, exist_ok=True)
git_dir = Path(TEST_DIR) / ".git"
git_dir.mkdir(parents=True, exist_ok=True)

# Write minimal config
config = {
    "bashToolPatterns": {"block": [], "ask": []},
    "zeroAccessPaths": [],
    "readOnlyPaths": [],
    "noDeletePaths": [],
}
with open(guardian_dir / "config.json", "w") as f:
    json.dump(config, f)

passed = 0
failed = 0
errors = []

def run_hook(command: str, test_name: str) -> dict:
    """Pipe a command to bash_guardian.py as JSON and return result."""
    global passed, failed

    hook_input = json.dumps({
        "tool_name": "Bash",
        "tool_input": {
            "command": command
        }
    })

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = TEST_DIR

    try:
        result = subprocess.run(
            [sys.executable, GUARDIAN_SCRIPT],
            input=hook_input,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        # The hook should NOT crash (exit code 0 means normal, even if deny)
        if result.returncode == 0:
            passed += 1
            print(f"  [PASS] {test_name} (exit={result.returncode})")
        else:
            failed += 1
            errors.append(test_name)
            print(f"  [FAIL] {test_name} (exit={result.returncode})")
            print(f"         stderr: {result.stderr[:200]}")

        # Check stdout is valid JSON if non-empty
        if result.stdout.strip():
            try:
                output = json.loads(result.stdout)
                decision = output.get('hookSpecificOutput', {}).get('permissionDecision', 'N/A')
                print(f"         response: {decision}")
                return output
            except json.JSONDecodeError:
                print(f"         stdout (not JSON): {result.stdout[:100]}")

        return {}

    except subprocess.TimeoutExpired:
        failed += 1
        errors.append(test_name)
        print(f"  [FAIL] {test_name} (TIMEOUT)")
        return {}
    except Exception as e:
        failed += 1
        errors.append(test_name)
        print(f"  [FAIL] {test_name} ({type(e).__name__}: {e})")
        return {}


# ============================================================
# TEST 1: Original crash command
# ============================================================
print("\n" + "=" * 60)
print("E2E TEST 1: Original crash command piped to hook")
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

run_hook(CRASH_COMMAND, "Original crash command (Errno 36)")

# ============================================================
# TEST 2: Multiline commands from Gemini's suggestions
# ============================================================
print("\n" + "=" * 60)
print("E2E TEST 2: Gemini-suggested multiline commands")
print("=" * 60)

gemini_commands = [
    (
        "Heredoc file creation",
        """cat <<EOF > .github/workflows/ci.yml
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Test
        run: echo "Testing..."
EOF"""
    ),
    (
        "bash -c with logical operators",
        """/bin/bash -c 'if ! command -v uv &> /dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi && uv venv && source .venv/bin/activate'"""
    ),
    (
        "Embedded python script",
        """python3 -c "
import sys, json, os
try:
    with open('package.json') as f:
        data = json.load(f)
    print('Found scripts')
except Exception as e:
    print(e)
    sys.exit(1)
" """
    ),
    (
        "Find with while loop",
        """find src -name "*.ts" -type f -not -path "*/node_modules/*" -print0 | while IFS= read -r -d '' file; do
    if grep -q "deprecated_function" "$file"; then
        echo "Refactoring $file..."
        sed -i 's/deprecated_function/new_feature/g' "$file"
    fi
done"""
    ),
    (
        "Function + trap + execution",
        """cleanup() {
    echo "Cleaning up temp files..."
    rm -rf /tmp/test_env_*
}
trap cleanup EXIT

mkdir -p /tmp/test_env_$$
echo "Running tests in isolated env..."
./run_integration_tests.sh --tmp-dir /tmp/test_env_$$"""
    ),
    (
        "shopt + globstar + loop",
        """shopt -s globstar
for img in assets/**/*.png; do
    echo "Optimizing $img"
    convert "$img" -resize 50% "${img%.*}.jpg"
done"""
    ),
    (
        "Long token (JWT-like in curl)",
        # NOTE: Intentionally fake JWT structure for regression testing.
        # Do not replace with a real token. See: GitGuardian incident 2026-02.
        """curl -X POST https://api.example.test/v1/deploy \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer eyJhbGciOiAibm9uZSIsICJ0eXAiOiAiSldUIn0.eyJzdWIiOiAiMDAwMDAwMDAwMCIsICJuYW1lIjogIkZBS0UtVE9LRU4tRk9SLVRFU1RJTkctT05MWSIsICJpYXQiOiAwfQ.FAKE_SIGNATURE_FOR_TESTING_DO_NOT_USE_000000000" \\
  -d '{"deploy_id": "982374-af823-1234", "force": true}'"""
    ),
    (
        "Chained git commands",
        """git fetch --prune && \\
git branch -r | awk '{print $1}' | egrep -v -f /dev/fd/0 <(git branch -vv | grep origin) | awk '{print $1}' | xargs git branch -d || echo "No local branches to prune" """
    ),
    (
        "Nested heredoc inside bash -c",
        """bash -c 'cat <<INNER_EOF > setup_env.sh
#!/bin/bash
export ENV_TYPE=staging
echo "Environment configured"
INNER_EOF
chmod +x setup_env.sh'"""
    ),
]

for name, cmd in gemini_commands:
    run_hook(cmd, name)

# ============================================================
# TEST 3: Simple commands (regression check)
# ============================================================
print("\n" + "=" * 60)
print("E2E TEST 3: Simple commands (regression)")
print("=" * 60)

simple_commands = [
    ("ls -la", "ls -la"),
    ("git status", "git status"),
    ("echo hello", "echo hello"),
    ("pwd", "pwd"),
    ("cat README.md", "cat README.md"),
]

for name, cmd in simple_commands:
    run_hook(cmd, name)

# ============================================================
# TEST 4: Non-Bash tool (should exit cleanly)
# ============================================================
print("\n" + "=" * 60)
print("E2E TEST 4: Non-Bash tool (should passthrough)")
print("=" * 60)

non_bash_input = json.dumps({
    "tool_name": "Read",
    "tool_input": {"file_path": "/some/file.txt"}
})

env = os.environ.copy()
env["CLAUDE_PROJECT_DIR"] = TEST_DIR

result = subprocess.run(
    [sys.executable, GUARDIAN_SCRIPT],
    input=non_bash_input,
    capture_output=True,
    text=True,
    timeout=10,
    env=env,
)
if result.returncode == 0 and not result.stdout.strip():
    passed += 1
    print(f"  [PASS] Non-Bash tool exits silently (exit={result.returncode})")
else:
    failed += 1
    errors.append("Non-Bash tool passthrough")
    print(f"  [FAIL] Non-Bash tool (exit={result.returncode}, stdout={result.stdout[:100]})")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("E2E SUMMARY")
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
