# Phase 3 Implementation Summary: Interpreter+Heredoc ASK Backstop

## What was implemented

### 1. `_is_interpreter_heredoc()` function
**File**: `hooks/scripts/bash_guardian.py` (after `_classify_heredoc_safety()`, before `split_commands()`)

A defense-in-depth function that detects when a sub-command is an interpreter
(bash, python3, node, etc.) with a heredoc operator (`<<`). This addresses
the gap where Layer 0 block patterns use `[^|&\n]*` which cannot match across
newline boundaries in retained heredoc bodies.

**Design**:
- Uses `_extract_base_command()` for robust interpreter detection (handles
  env/sudo/nohup/nice prefixes, absolute paths, variable assignments)
- Splits at first `<<` to isolate command portion before heredoc operator
- Checks result against `_INTERPRETER_COMMANDS` frozenset
- Returns False for non-interpreter commands (cat, grep, echo, etc.)
- `<<` in string check catches both heredoc (`<<`) and here-string (`<<<`)

### 2. Integration in per-sub-command loop
**File**: `hooks/scripts/bash_guardian.py`, top of `for sub_cmd in sub_commands:` loop

Added before `is_write`/`is_delete` checks. When triggered, escalates to
`ask` verdict via `_stronger_verdict()` with reason message including
truncated command preview.

**Verdict**: `ask` (not `deny`) -- legitimate uses exist (e.g., inline scripts
for tool installation, test runners).

## Test count

**47 new tests** in `tests/security/test_interpreter_heredoc.py`:
- **34 unit tests** (`TestIsInterpreterHeredoc`): Direct function testing
- **13 integration tests** (`TestInterpreterHeredocIntegration`): Full main() flow via subprocess

### Unit test coverage
- All interpreter commands: bash, sh, zsh, dash, ksh, python, python2, python3,
  node, deno, bun, perl, ruby, eval, source, exec
- Prefixes: env, sudo, nohup, nice
- Absolute paths: /usr/bin/bash, /usr/local/bin/python3
- Variable assignments: FOO=bar, A=1 B=2
- Non-interpreters: cat, grep, echo, wc (all return False)
- Edge cases: empty string, bare `<<`, tab-stripped `<<-`, quoted delimiters,
  here-string `<<<`, no-heredoc commands

### Integration test coverage
- Interpreter heredoc triggers ASK: bash, python3, node, perl, ruby
- Prefix handling: sudo, env, absolute path
- Non-interpreter heredoc NOT triggered: cat
- No false trigger on non-heredoc: bash -c, bash script.sh
- Benign content still triggers ASK (intentional)
- Dangerous content triggers at least ASK (may be deny from other checks)

## Test results

### Phase 3 tests only
```
47 passed in 0.83s
```

### Full test suite (core + security + regression)
```
1064 passed, 11 failed, 1 warning, 1 error in 4.94s
```

- **1064 passed**: Up from 1017 baseline (+47 new Phase 3 tests)
- **11 failed**: All pre-existing `TestNewBlockPatterns` failures (unchanged)
- **1 error**: Pre-existing `test_bypass_v2.py::test` error (unchanged)
- **0 regressions introduced by Phase 3**

## Issues found

None. Implementation matched the spec exactly. All new tests passed on first run,
and zero regressions were introduced in the existing test suite.

## Files modified/created

- **Modified**: `hooks/scripts/bash_guardian.py` (function + integration)
- **Created**: `tests/security/test_interpreter_heredoc.py` (47 tests)
