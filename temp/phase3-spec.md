# Phase 3 Spec: Interpreter+Heredoc ASK Backstop

## Problem

After Phase 1's heredoc body retention for interpreter commands, the heredoc body IS preserved
in the redacted string. However, Layer 0 block patterns use `[^|&\n]*` which stops at newlines.
This means multiline interpreter heredoc bodies evade block pattern detection:

```bash
bash << EOF
rm -rf /
EOF
```

Phase 1 retains `rm -rf /` in the redacted string, but block patterns like
`rm\s+(-[a-zA-Z]*)*\s*--(preserve-root=never|no-preserve-root)[^|&\n]*` can't match across
the heredoc boundary.

## Solution: Defense-in-depth ASK backstop

Any sub-command that is an interpreter with a heredoc operator (`<<`) triggers an ASK verdict.
This is defense-in-depth — legitimate uses exist (e.g., installing tools, running test scripts)
but they warrant user confirmation in `--dangerously-skip-permissions` mode.

## Implementation

### 3a. `_is_interpreter_heredoc(sub_cmd)` function

**File**: `hooks/scripts/bash_guardian.py`
**Location**: After `_classify_heredoc_safety()` (around line 233), before `split_commands()`

**Approach (action plan V1 fix F3-1 HIGH)**: Use `_extract_base_command()` instead of ad-hoc
regex patterns. This reuses the existing robust prefix/flag/path handling.

```python
def _is_interpreter_heredoc(sub_cmd: str) -> bool:
    """Check if a sub-command is an interpreter with a heredoc operator.

    Defense-in-depth backstop: even with Phase 1 heredoc body retention,
    block patterns using [^|&\\n]* cannot match across newline boundaries
    in retained bodies. This detects the pattern and escalates to ASK.

    Uses _extract_base_command() for robust interpreter detection, handling:
    - env/sudo/nohup/nice prefixes
    - Absolute paths (/usr/bin/bash)
    - Variable assignments (FOO=bar bash << EOF)
    - I/O redirect tokens before the command

    Args:
        sub_cmd: A single sub-command string from split_commands().

    Returns:
        True if the sub-command is an interpreter with heredoc.
    """
    if '<<' not in sub_cmd:
        return False

    # Extract command portion before the heredoc operator
    cmd_before = sub_cmd.split('<<', 1)[0]
    base_cmd = _extract_base_command(cmd_before)
    return base_cmd in _INTERPRETER_COMMANDS
```

**Key design decisions**:
- `'<<' in sub_cmd` catches both `<<` (heredoc) and `<<<` (here-string). Both feed input
  to interpreters and warrant ASK — this is intentional.
- Split at first `<<` to isolate command portion, avoiding `shlex.split()` failure on heredoc body
- `_extract_base_command()` handles env/sudo/nice/nohup/absolute paths/variable assignments
- Returns False on any parsing failure (fail-open to avoid false ASK) — but the broader
  system is fail-closed: unrecognized patterns still hit F1 if write/delete is detected.

### 3b. Integration in per-sub-command loop

**File**: `hooks/scripts/bash_guardian.py`, line 1943
**Add at TOP of `for sub_cmd in sub_commands:` loop**, BEFORE `is_write`/`is_delete` checks:

```python
    for sub_cmd in sub_commands:
        # Phase 3: Interpreter+heredoc backstop (defense-in-depth)
        # Block patterns can't match multiline retained heredoc bodies
        # due to [^|&\n]* stopping at newlines. ASK for interpreter+heredoc.
        if _is_interpreter_heredoc(sub_cmd):
            final_verdict = _stronger_verdict(
                final_verdict,
                ("ask", f"Interpreter command with heredoc: "
                 f"{truncate_command(sub_cmd)}")
            )

        is_write = is_write_command(sub_cmd)
        is_delete = is_delete_command(sub_cmd)
        # ... rest unchanged
```

**Verdict**: `ask` (NOT `deny`). Legitimate uses exist (e.g., `python3 << EOF` for inline scripts).

### 3c. Tests

**File**: `tests/security/test_interpreter_heredoc.py`

Test classes:
1. **TestIsInterpreterHeredoc** (~8 tests): Unit tests for the detection function
   - `bash << EOF` → True
   - `python3 << EOF` → True (Python interpreter)
   - `node << EOF` → True (Node)
   - `cat << EOF` → False (not an interpreter)
   - `env bash << EOF` → True (env prefix)
   - `sudo -u root bash << EOF` → True (sudo prefix)
   - `/usr/bin/bash << EOF` → True (absolute path)
   - `bash <<< "hello"` → True (here-string also caught)
   - `FOO=bar bash << EOF` → True (variable assignment prefix)
   - `echo "<<" something` → depends on split behavior (edge case)

2. **TestInterpreterHeredocIntegration** (~6 tests): Full main() flow
   - `bash << EOF\necho hello\nEOF` → ASK (interpreter heredoc)
   - `cat << EOF\nsome text\nEOF` → ALLOW (not interpreter)
   - `sudo bash << EOF\nls\nEOF` → ASK (sudo prefix)
   - `python3 << EOF\nprint("hello")\nEOF` → ASK (Python)
   - `bash -c "echo test"` → no heredoc trigger (no `<<`)
   - `bash script.sh` → no heredoc trigger (no `<<`)

## Important notes

- `_INTERPRETER_COMMANDS` already includes: bash, sh, zsh, dash, ksh, csh, tcsh, fish,
  python, python2, python3, py, node, deno, bun, perl, ruby, source, eval, exec
- `source` with heredoc: `source /dev/stdin << EOF` — `_extract_base_command` returns "source",
  which IS in `_INTERPRETER_COMMANDS`. This is correct behavior.
- `exec` with heredoc: `exec << EOF` — exec IS in the interpreter commands set, correct.
- `eval` with heredoc: unusual but `eval << EOF` would match. Correct (eval is dangerous).
- No interaction with Phase 2 (interpreter payload path resolution): Phase 2 handles `-c`/`-e`
  payloads, Phase 3 handles `<<` heredocs. They're independent code paths.
- The backstop fires BEFORE write/delete detection, so even a benign `bash << EOF\necho hi\nEOF`
  triggers ASK. This is intentional — any code execution via heredoc warrants confirmation.

## Test baseline
- Current: 1017 passed, 11 pre-existing failures (TestNewBlockPatterns), 1 pre-existing error
- Expected after Phase 3: ~1030+ passed (13+ new tests), same pre-existing failures
