# Task C: Fix Tokenizer (split_commands) Failures

## Overview
Fix 7 failing tests in `tests/security/test_bypass_v2.py` related to `split_commands()`.

## Failing Tests

### 1. `${VAR:-;}` should NOT split at `;`
**Root cause**: `split_commands()` does not track `${}` parameter expansion. The `;` inside `${VAR:-;}` is treated as a command separator.
**Fix**: Track `${}` nesting. When encountering `${` (at depth 0), push a brace counter. Consume until matching `}`. Must handle nested `${}`.

### 2. `${VAR//a|b/c}` should NOT split at `|`
**Same root cause**: Parameter expansion not tracked. `|` inside `${VAR//a|b/c}` splits.
**Fix**: Same fix as #1 — `${}` tracking will handle this.

### 3. `(cd /tmp; ls)` bare subshell — should NOT split
**Root cause**: `split_commands()` only tracks `$()`, `<()`, `>()` — not bare `(...)`. A bare `(` without preceding `$`, `<`, `>` does not increment depth.
**Fix**: Track bare `(...)` subshells. When `(` is encountered without `$`, `<`, `>` prefix, still increment depth. Be careful: `((` for arithmetic is already tracked.

### 4. `{echo a; echo b;}` brace group — should NOT split
**Root cause**: `split_commands()` has no brace group tracking. `{` and `}` are not recognized.
**Fix**: Track `{...}` when `{` appears as a word (preceded by whitespace or start-of-string, NOT `${`). This is complex because `{` in bash is only a reserved word at the start of a command, not a metacharacter.
**CAUTION**: This is the trickiest fix. Brace groups in bash are NOT subshells — they run in the current shell. The `{` must be a command word, not part of parameter expansion.

### 5. `!(*.txt|*.md)` extglob — should NOT split at `|`
**Root cause**: Extglob patterns `?(...)`, `*(...)`, `+(...)`, `@(...)`, `!(...)` contain `|` as alternation. `split_commands()` splits on `|`.
**Fix**: Detect extglob prefix chars `?*+@!` immediately followed by `(` and track depth. Only at depth 0.

### 6. `[[ regex | ]]` conditional — should NOT split at `|`
**Root cause**: `[[ ... ]]` compound command not tracked. `|` inside is treated as pipe.
**Fix**: Track `[[` and `]]` as paired delimiters. When inside `[[ ]]`, don't split on `|`, `&&`, etc.

### 7. `(( x & y ))` arithmetic — should NOT split at `&`
**Root cause**: `arithmetic_depth` tracking doesn't prevent `&` from being a separator. Only `<<` is gated on `arithmetic_depth`.
**Fix**: Inside `arithmetic_depth > 0`, also skip `&` as separator (and `|`, `;`).

## Implementation Strategy
Prioritize by impact:
1. **${}** tracking (#1, #2) — most common in real commands
2. **Bare ()** subshell (#3) — common
3. **(( )) operators** (#7) — simple extension of existing code
4. **[[ ]]** tracking (#6) — moderately common
5. **Extglob** (#5) — less common
6. **Brace groups** (#4) — least common, hardest to implement

## Key Constraints
- Changes are ONLY in `split_commands()` function
- Must not break any existing tests
- Must remain fail-closed (unknown constructs should NOT hide commands)
- Must handle nesting correctly

## Validation
After changes:
```bash
python3 tests/security/test_bypass_v2.py 2>&1 | grep -E "tokenizer.*FAIL|tokenizer.*PASS"
python3 -m pytest tests/core/ tests/security/ -v 2>&1 | tail -5
```
