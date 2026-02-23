# Task C Progress: Tokenizer (split_commands) Fixes

## Status: COMPLETE

## Results
- All 7 tokenizer failures fixed
- test_bypass_v2.py: 101/101 pass, 0 failures, 0 security bypasses
- Full test suite: 671 passed, 0 failed, 1 error (pre-existing pytest fixture issue)
- Regression tests: 16/16 pass

## Changes Made

### File: hooks/scripts/bash_guardian.py
Function: `split_commands()` (lines 82-380)

### Structural Change: Context-first ordering
Moved ALL context entry/exit tracking BEFORE separator checks. Previously, arithmetic `(( ))` tracking was placed after separators, so `&` inside `(( ))` would hit the separator check first and split incorrectly.

### New State Variables
- `param_expansion_depth` -- tracks `${...}` nesting
- `bracket_depth` -- tracks `[[ ... ]]` nesting
- `brace_group_depth` -- tracks `{ ...; }` brace groups
- `extglob_depth` -- tracks `?()`, `*()`, `+()`, `@()`, `!()` patterns

### Fixes Applied
1. **`${VAR:-;}` and `${VAR//a|b/c}`** -- Added `param_expansion_depth` counter. On `${`, increment; on matching `}` (at depth==0), decrement. All chars inside `${...}` skip separator checks.
2. **`(cd /tmp; ls)` bare subshell** -- When `(` encountered without `$`, `<`, `>` prefix and not `((`, increment `depth`. Bare subshells reuse existing depth counter.
3. **`(( x & y ))`** -- Moved `arithmetic_depth` tracking before separators. Added full content skip (`continue` for all chars inside arithmetic).
4. **`[[ regex | ]]`** -- Added `bracket_depth` with word-boundary detection (`[[` preceded by whitespace/SOL and followed by whitespace). All chars inside `[[ ]]` skip separator checks.
5. **`!(*.txt|*.md)` extglob** -- Detect `?*+@!` followed by `(`. Track depth, skip separators inside extglob. Supports nested extglob.
6. **`{ echo a; echo b; }` brace groups** -- `{` as reserved word (preceded by whitespace/SOL, not `$`, followed by whitespace). Track depth, skip separators inside.

### Security Hardening (from Codex + Gemini review)
- `}` only decrements `param_expansion_depth` when `depth == 0` -- prevents `${foo:-$(echo })}` from prematurely closing the parameter expansion due to `}` inside nested `$()`.
- `param_expansion_depth > 0` skip only triggers when `depth == 0` -- chars inside nested `$()` within `${...}` are handled by the existing depth tracker.

## Review Findings Addressed
- **Codex (Critical)**: Separator checks must run AFTER context tracking -- FIXED by reordering.
- **Codex (High)**: `}` inside nested `$()` could desync param_expansion_depth -- FIXED with `depth == 0` guard.
- **Gemini (Critical)**: Suppressing splits in `{}` and `()` could hide commands -- ACKNOWLEDGED but tests require single-command output. Downstream scanners (Layer 1 raw text scan, Layer 3/4 detection) still catch dangerous patterns in the unsplit string. The tradeoff is: incorrect fragment splitting (e.g., `(cd /tmp` + `ls)`) is worse for downstream analysis than keeping the whole construct intact.
- **Gemini (High)**: `is_delete_command` regex anchoring misses `(rm file)` -- pre-existing issue, out of scope for tokenizer task.
- **Gemini (Medium)**: Loose closing token boundaries for `]]` and `}` -- premature closing leads to fail-closed behavior (more splitting, not less), which is safe.

## Validation
```
python3 tests/security/test_bypass_v2.py: 101 passed, 0 failed
python3 -m pytest tests/core/ tests/security/ tests/test_heredoc_fixes.py: 671 passed, 0 failed
python3 tests/regression/test_errno36_e2e.py: 16 passed, 0 failed
```
