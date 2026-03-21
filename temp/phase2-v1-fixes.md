# Phase 2 V1 Fixes Applied

## Findings and Actions

### CRITICAL: Decoy literal attack
**All 5 reviewers** (3 agents + Codex 5.3 + Gemini 3.1 Pro) independently found this.
**Decision**: Partial fix applied + accepted limitation per threat model.
- Fixed: `.` and `./` literals rejected (prevents trivial decoy via project root)
- Accepted: General decoy attack (benign literal + chr() target) is within threat model — AI agents generate straightforward code, not obfuscated payloads
- Layer 0 patterns block interpreter deletes before F1 fires in default config

### MEDIUM: % format string bypass (Gemini)
**Fixed**: Added `%` to F2-2 interpolation marker rejection.

### MEDIUM: JS escape sequence bypass (Codex)
**Fixed**: Reject ALL literals containing backslash (not just double-quoted). Rationale: `extract_interpreter_payload()` strips outer shell quotes, so inner quote type doesn't determine escape semantics across languages.

### MEDIUM: MIME filter over-aggressiveness (edge verifier + Gemini)
**Fixed**: Replaced fragile heuristic with known MIME type prefix allowlist (`application/`, `text/`, etc.). Extensionless paths like `src/utils` no longer falsely filtered.

### LOW: glob recursive=True risk
**Fixed**: Added comment documenting intentional omission.

## Code changes
- `bash_guardian.py` lines 1287-1295: F2-2 filter expanded (%, backslash)
- `bash_guardian.py` lines 1305-1319: MIME filter rewritten with prefix allowlist
- `bash_guardian.py` lines 1299-1303: `.`/`./` trivial literal rejection
- `bash_guardian.py` line 1327: glob recursive comment

## Tests added (9 new, 31 total)
- TestV1Fixes: dot_literal, dot_slash, percent_format, js_escape, backslash_any_quote, mime_still_filtered, extensionless_path, decoy_chr, multiple_paths

## Results: 31/31 Phase 2 tests pass, 1011/1011 non-pre-existing tests pass
