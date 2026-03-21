# Phase 2: F1 Interpreter Path Resolution — Final Summary

**Date**: 2026-03-21
**Status**: COMPLETE, verified (2 rounds)
**Test count**: 37 Phase 2 tests, 1017 total (11 pre-existing failures, 1 pre-existing error)

## Implementation

### Core: `extract_paths_from_interpreter_payload(command, project_dir)`
- Extracts file paths from interpreter `-c`/`-e` payload string literals
- Uses `_QUOTED_LITERAL_RE` regex for single/double-quoted strings
- Filters: URLs, MIME types (prefix allowlist), interpolation markers, backslash escapes
- Project boundary via `is_within_project()` (Path.relative_to-based)
- Fail-closed: returns `[]` on any error → F1 ASK fires

### F1 block modification (3-branch decision)
1. **Interpreter + paths resolved**: Routes through normal path validation (zeroAccess, readOnly, noDelete, symlink)
2. **Interpreter + paths NOT resolved**: Enriched F1 ASK with API name (e.g., "via os.remove")
3. **Non-interpreter**: Standard F1 ASK (unchanged behavior)

### Security filters (F2-1, F2-2, V1, V2)
- **F2-1**: Project boundary via `Path.relative_to()` (NOT `str.startswith()`)
- **F2-2**: Reject `{}`, `$`, `%` in literals (interpolation markers)
- **V1**: Reject `\` in all literals (JS/language escape sequences)
- **V1**: Project root literals (`.`, `./`) rejected via resolve comparison
- **V1**: MIME filter rewritten with known prefix allowlist
- **V2**: `./.` and `././` variants caught by resolved path comparison
- **V2**: Mixed paths fail-closed (any out-of-project literal → return `[]`)

## Bugs Found and Fixed (2 rounds of verification)

| # | Severity | Finding | Fix | Source |
|---|----------|---------|-----|--------|
| 1 | CRITICAL | Decoy `.` literal suppresses F1 | Reject literals resolving to project root | V1 security + V1 clink |
| 2 | CRITICAL | Mixed paths: out-of-project silently dropped | If any out-of-project → return [] | V2 clink (both models) |
| 3 | MEDIUM | `%` format string bypasses F2-2 | Added `%` to rejection set | V1 clink (Gemini) |
| 4 | MEDIUM | JS `\/` escape divergence | Reject `\` in all literals | V1 clink (Codex) |
| 5 | MEDIUM | MIME filter too aggressive on `src/utils` | Prefix allowlist instead of heuristic | V1 edges + V1 clink (Gemini) |
| 6 | LOW | `./.` bypasses string-based root check | Use resolve() comparison | V2 clink (both models) |

## Verification Results

### V1 Round (3 agents + clink)
- Security auditor: 2 CRITICAL (decoy literal, `.` literal), 2 LOW
- Edge case verifier: 16 cases traced, 2 bugs, 3 concerns
- Cross-model clink: Codex 5/10, Gemini 3/10 — both found decoy bypass independently
- All converged on same CRITICAL: decoy literal attack

### V2 Round (adversarial + clink)
- Adversarial: 32 probes, 0 bypasses, 1 usability concern (MIME dir names)
- Cross-model clink: Found `./.` bypass + mixed paths bypass, V1 fixes verified correct
- After V2 fixes: Codex/Gemini both confirmed correct

### Known Accepted Limitations
- Decoy literal + chr() obfuscation: accepted per threat model (AI agents don't generate obfuscated code)
- chr()/base64/exec() path construction: invisible to static extraction (fail-closed → F1 ASK)
- Interpreter-mediated writes: pre-existing gap, not Phase 2 scope
- TOCTOU: systemic, applies across all guardian layers

## Files Modified
- `hooks/scripts/bash_guardian.py` — new function + F1 block modification
- `tests/regression/test_interpreter_path_resolution.py` — 37 new tests (7 classes)
