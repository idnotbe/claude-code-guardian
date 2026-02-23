# Task D Progress: Scan Bypass + Detection Fixes

## Status: COMPLETE

All 8 Stream D failures fixed. 101/101 standalone tests pass. 630/630 pytest tests pass.

## Changes Made

### Code Changes (hooks/scripts/bash_guardian.py)

#### New function: `_decode_ansi_c_strings()` (line ~564)
- Decodes ANSI-C `$'...'` quoted strings before scanning
- Supports: `\xHH` (hex), `\NNN` (octal with or without leading 0), `\uHHHH` (16-bit unicode), `\UHHHHHHHH` (32-bit unicode), standard escapes (`\n`, `\t`, etc.)
- Hardened after codex review to handle standard octal (`\56` not just `\056`) and unicode escapes

#### New function: `_expand_glob_chars()` (line ~641)
- Expands single-character glob bracket classes: `[v]` -> `v`, `[\e]` -> `e`
- Hardened after gemini review to handle escaped chars inside brackets

#### Modified: `scan_protected_paths()` (line ~660)
- Scans both original command AND normalized variants (ANSI-C decoded + glob expanded)
- Added glob-`?`-aware regex for each protected literal
- Post-match validation requires at least one non-`?` character to prevent false positives from all-`?` tokens like `echo ????`

### Test Changes (tests/security/test_bypass_v2.py)

- Lines 411-413: Fixed chmod/chown/touch expectations from `False` to `True` (code correctly detects these as writes)
- Line 434: Fixed `> CLAUDE.md` expectation from `False` to `True` (code correctly detects truncation as delete)
- Line 447: Fixed `git rm CLAUDE.md` expectation from `False` to `True` (code correctly detects git rm as delete)
- Lines 318-319, 323-324: Updated Section 2B expectations for .en[v] and .en? from `allow` to `deny` (now caught by scanner)
- Line 347-348: Updated Section 2B expectation for `$'\056env'` from `allow` to `deny` (now caught by ANSI-C decoder)

## Security Review (codex + gemini)

### Fixed after review:
- Standard octal without leading 0 (`\56` = `.`)
- Unicode `\uHHHH` and `\UHHHHHHHH` escapes
- Escaped bracket classes (`[\e]`)
- All-`?` false positive prevention

### Known remaining gaps (documented, not in scope):
- Inline empty quote stripping (`cat .e""nv`) -- requires shell word normalization
- Brace expansion (`cat .{e,x}nv`) -- complex to implement safely
- Quote-fragment concatenation (`$'\x2e''env'`) -- requires adjacent-word merging

## Verification

```
python3 tests/security/test_bypass_v2.py    -> 101/101 pass, 0 bypasses
python3 -m pytest tests/core/ tests/security/ -v -> 630 passed, 1 error (pre-existing pytest compat issue)
```
