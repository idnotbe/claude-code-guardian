# Phase 1: Heredoc Body Redaction — Final Summary

**Date**: 2026-03-21
**Status**: COMPLETE, verified (2 rounds)
**Test count**: 99 Phase 1 tests, 980 total (11 pre-existing failures, 1 pre-existing error)

## Implementation

### Core: Integrated redaction in `split_commands()`
- Single-parser design: same parser produces both sub-commands and redacted string
- `redact_safe_heredocs=True` returns `(sub_commands, redacted_command)` tuple
- Backward compatible: default `False` returns list only

### F1-1: Origin tracking at `<<` parse time
- `heredoc_origins` stores 4-tuples: `(origin_cmd, was_piped, full_segment, is_quoted)`
- Origin captured BEFORE `<<` is appended to current (survives all separator splits)
- `full_segment` finalized at every separator handler (`;`, `&&`, `||`, `|`, `&`, `\n`)
- Pipe handler sets `was_piped=True` for all pending origins

### 5-rule hybrid classifier (`_classify_heredoc_safety`)
1. Interpreter command → UNSAFE
2. Output redirection (checked against `full_segment`) → UNSAFE
3. Pipeline member → UNSAFE
4. Passive data sink → SAFE
5. Unknown → UNSAFE (fail-closed)

### Redacted string construction
- Safe body content replaced with empty lines (newline count preserved)
- Prevents token merging and line alignment changes
- Fail-closed: exception → original command returned

### `main()` integration
- `split_commands(command, redact_safe_heredocs=True)` called FIRST
- Layer 0/0b scan `redacted_command`
- Layer 1+ use original `sub_commands` (unchanged)

## Bugs Found and Fixed (4 rounds of review)

| # | Severity | Finding | Fix | Source |
|---|----------|---------|-----|--------|
| 1 | CRITICAL | Post-`<<` redirect bypass | `full_segment` captures entire sub-command | V1 clink (Codex) |
| 2 | CRITICAL | Unquoted heredoc expansion | `is_quoted` flag + body `$`/backtick check | V1 clink (Gemini) |
| 3 | CRITICAL | `>&3+` fd duplication bypass | Narrow exemption to `>&0/1/2/-` only | V2 clink (both) |
| 4 | CRITICAL | sudo `-p` flag sync-slip | Invert to no-arg allowlist | V2 clink (Gemini) |
| 5 | LOW | `origins` truthiness | `origins is not None` | V1 clink (Gemini) |

## Verification Results

### V1 Round (3 agents)
- Edge case verifier: 18/18 cases PASS + 6 additional concerns PASS
- Security verifier: confirmed redirect-after-`<<` (independently)
- Cross-model clink: 2 CRITICAL + 1 MEDIUM + 2 LOW findings

### V2 Round (2 agents)
- Adversarial verifier: 43 probes, 0 bypasses. All 4 fixes confirmed correct.
- Cross-model clink: 2 new CRITICAL (fd dup, sudo -p) found and fixed

### Known Accepted Limitations
- Function override (`cat() { bash; }`) — not detectable statically
- Partially-quoted delimiters (`E'O'F`) — fail-closed (unterminated)
- Quoted redirection in string (`cat ">" << EOF`) — false positive (fail-closed)
- Heredoc bodies not in `sub_commands` — pre-existing architectural gap

## Files Modified
- `hooks/scripts/bash_guardian.py` — all changes in this file
- `tests/regression/test_heredoc_redaction.py` — 99 new tests
