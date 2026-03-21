# Phase 0: Verification Round 1 Summary

**Date**: 2026-03-21
**Verifiers**: Edge case agent (Opus 4.6), Codex 5.3 (pal clink), Gemini 3.1 Pro (pal clink)

## Critical Finding: ANSI-C Escape Decoding Bypass (FIXED)

Both Codex and Gemini independently identified that the original ANSI-C handler did NOT decode escape sequences. `$'\x45OF'` produced delimiter `\x45OF` instead of `EOF`. This was a real bypass:
- Bash: delimiter = `EOF`, body terminates at `EOF`, subsequent commands execute
- Guardian (unfixed): delimiter = `\x45OF`, body never terminates, subsequent commands hidden
- **Fix applied**: Now uses `_decode_ansi_c_strings()` to decode escapes. `$'\x45OF'` → `EOF`.

## Other Findings from Cross-Model Review

| Finding | Severity | Status |
|---------|----------|--------|
| ANSI-C escape not decoded | CRITICAL | **FIXED** — reuse existing `_decode_ansi_c_strings()` |
| Escaped newline in bare word | HIGH | **FIXED** — added `\<newline>` handling in bare-word loop |
| Concatenated tokens (`'EO'F`) | HIGH | Pre-existing, not introduced by Phase 0 |
| Mixed inline quotes (`E"O"F`) | HIGH | Pre-existing, not introduced by Phase 0 |
| `\$'EOF'` divergence | LOW-MOD | Fail-closed + outside threat model (AI agents don't craft this) |
| `$'E\'OF'` raw backslash | LOW | Fail-closed (unterminated heredoc) |

## Edge Case Analysis (from edge verifier)

10 edge cases traced through code:
- 5 match bash behavior exactly
- 3 diverge in fail-closed direction (safe)
- 1 pre-existing limitation (unterminated quote)
- 1 known divergence (`\$'EOF'`) — documented with test

## Test Results

- **24 Phase 0 tests** pass (including 3 new known-divergence tests)
- **881 total tests** pass, 11 pre-existing failures, 1 pre-existing error
- No regressions from Phase 0 changes

## Changes Made After V1 Review

1. `_parse_heredoc_delimiter()`: ANSI-C branch now calls `_decode_ansi_c_strings()` for escape decoding
2. `_parse_heredoc_delimiter()`: Bare-word handler now handles `\<newline>` line continuation
3. Added tests: `test_ansi_c_hex_escape_decoded`, `test_ansi_c_hex_escape_split_commands`
4. Updated test: `test_ansi_c_with_escape_in_delim` to expect decoded newline
