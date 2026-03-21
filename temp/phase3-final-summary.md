# Phase 3: Interpreter+Heredoc ASK Backstop — Final Summary

**Date**: 2026-03-21
**Status**: COMPLETE, verified (2 rounds)
**Test count**: 69 Phase 3 tests, 1086 total (11 pre-existing failures, 1 pre-existing error)

## Implementation

### Core: `_is_interpreter_heredoc(sub_cmd)` (~30 LOC)
- Checks if `<<` is in sub_cmd (catches heredoc and here-string)
- Splits at first `<<` to isolate command portion
- Uses `_extract_base_command()` for robust interpreter detection (handles env/sudo/nohup/nice prefixes, absolute paths, variable assignments)
- Checks against `_INTERPRETER_COMMANDS` frozenset
- Falls back to `_VERSIONED_INTERPRETER_RE` regex for versioned interpreters

### `_INTERPRETER_COMMANDS` modification
- V1 fix: Added `.` (dot command, POSIX equivalent of `source`)

### `_VERSIONED_INTERPRETER_RE` regex
- V1: `r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)\d[\d.]*$'`
- V2 fix: `r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)(?:[-\d][\w.-]*)$'`
- Handles: `python3.10`, `python3.8m`, `bash-5.0`, `ruby-3.2`, `perl5.34.1`

### Integration in per-sub-command loop
- Added at TOP of `for sub_cmd in sub_commands:` loop
- Verdict: `ask` (not `deny`) — legitimate uses exist
- Fires BEFORE write/delete detection (intentional — any interpreter heredoc warrants confirmation)

## Bugs Found and Fixed (2 rounds of verification)

| # | Severity | Finding | Fix | Source |
|---|----------|---------|-----|--------|
| 1 | MEDIUM | `.` (dot cmd) not in `_INTERPRETER_COMMANDS` | Added `.` to frozenset | V1 (Opus + Codex) |
| 2 | MEDIUM | Versioned interpreters (python3.10) miss frozenset | Added `_VERSIONED_INTERPRETER_RE` | V1 (all 3 models) |
| 3 | MEDIUM | Regex misses `python3.8m`, `bash-5.0` | Changed to `(?:[-\d][\w.-]*)` pattern | V2 (both models) |
| 4 | MEDIUM | `sudo --flag=value` skips next token | Added `'=' not in flag` check | V2 (clink Gemini) |

## Verification Results

### V1 Round (Opus analysis + Codex + Gemini clink)
- Opus: dot command gap, versioned interpreter gap, prefix flag gap (accepted)
- Codex 5.3: HIGH missing interpreters (dot, versioned, php), HIGH prefix flags
- Gemini 3.1 Pro: CRITICAL subshell grouping, HIGH preceding heredoc, MEDIUM versioned
- Convergence: all agree on versioned interpreter gap; prefix flags accepted with Phase 1 mitigation

### V2 Round (adversarial agent + Codex + Gemini clink)
- Adversarial: 45/46 pass, 1 false positive (`python3.` trailing dot — accepted LOW)
- Codex: wrapper flags still a concern (accepted), regex still too restrictive (fixed)
- Gemini: `.split('<<')` string masking (accepted), regex too restrictive (fixed)
- All V1+V2 fixes validated, zero bypasses after fixes

### Known Accepted Limitations
- Prefix flag parsing: `nice -n 5 bash <<EOF` — Phase 1 Rule 5 retains body
- Subshell grouping: `(python <<EOF)` — Phase 1 Rule 5 retains body
- String masking: `python -c "print('<<')" <<EOF` — Phase 1 handles correctly
- Preceding heredoc: `<<EOF python` — Phase 1 Rule 5 retains body
- Missing uncommon interpreters (php, lua, awk) — Phase 1 Rule 5 retains body
- Trailing dot false positive: `python3.` — not a real command, over-ask only
- False positives on eval/exec/source heredocs — intentional conservative behavior

## Files Modified
- `hooks/scripts/bash_guardian.py` — new function + frozenset change + regex + integration
- `tests/security/test_interpreter_heredoc.py` — 69 tests (4 classes)
