# Phase 3 V2 Cross-Model Analysis

**Sources**: Codex 5.3 + Gemini 3.1 Pro (V2 clink)

## V2 Clink Convergence

| Finding | Codex | Gemini | Action |
|---------|-------|--------|--------|
| V1 regex too restrictive (python3.8m, bash-5.0) | MEDIUM 6/10 | MEDIUM 5/10 | **FIXED** in V2 |
| `.` addition safe | confirmed | confirmed | KEEP |
| Wrapper flags bypass | HIGH 8/10 (claims Phase 1 not sufficient) | — | **ACCEPT** (Phase 1 Rule 5 retains body) |
| String masking bypass | — | HIGH 8/10 | **ACCEPT** (already accepted V1) |
| Regex false positives (sh1, bash2) | LOW 3/10 | LOW 1/10 | **ACCEPT** (ASK not DENY) |

## V2 Fix Applied

Changed `_VERSIONED_INTERPRETER_RE` from:
```python
r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)\d[\d.]*$'
```
to:
```python
r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)(?:[-\d][\w.-]*)$'
```

This handles:
- `python3.8m` (pymalloc suffix) ✓
- `bash-5.0` (hyphenated) ✓
- `ruby-3.2` (hyphenated) ✓
- `perl5.34.1` (micro version) ✓

Without matching:
- `shred` (no digit/hyphen after `sh`) ✓
- `perldoc` (no digit/hyphen after `perl`) ✓
- `bashrc` (no digit/hyphen after `bash`) ✓

## Accepted Limitations (V2 confirmed)

1. **Wrapper flag parsing**: `nice -n 5 bash <<EOF` — Codex says HIGH but Phase 1 Rule 5
   retains body (unknown command → UNSAFE). Block patterns scan retained body. Phase 3 is
   third-layer defense-in-depth. Missing it reduces but doesn't eliminate coverage.

2. **String masking**: `python -c "print('<<')" <<EOF` — Gemini says HIGH but requires
   `<<` in argument before heredoc operator. Phase 1 handles correctly via quote-aware parsing.

3. **Regex false positives**: `python3.` (trailing dot) — adversarial finding. Not a real
   command name, only produces over-ask. ACCEPTED.

## Codex's claim that Phase 1 is "not actually sufficient"

Codex claimed `nice -n 5 bash << EOF\nrm -rf .git\nEOF` "clean-allowed". Analyzed:
- Phase 1 retains body (Rule 5: unknown → UNSAFE) ✓
- Layer 0 scans retained body for block patterns ✓
- Whether it blocks depends on specific block pattern matches for the body content
- Phase 3 missing means no blanket ASK, but other layers still scan

The real gap is: dangerous heredoc content that doesn't match any block pattern AND uses
a prefix with flags. This is narrow — most dangerous commands (rm -rf, git push --force, etc.)
DO have block patterns. Accept for now; `_extract_base_command` flag handling is a separate
enhancement candidate.
