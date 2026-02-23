# Task D: Fix Scan Bypass + Write/Delete Detection Failures

## Overview
Fix 8 failing tests in `tests/security/test_bypass_v2.py` related to scan bypasses and write/delete detection.

## Part 1: Scan Bypasses (3 failures)

### 1. `cat .en[v]` — character class glob bypass
**Root cause**: `scan_protected_paths()` uses literal substring matching. `cat .en[v]` doesn't contain the literal `.env`, only `.en[v]`.
**Fix options**:
- **Option A**: Expand glob patterns in the command before scanning (risky — changes semantics)
- **Option B**: Generate regex variants that match common glob evasions: `[v]` → `v`, `?` → `.`
- **Option C**: Add a character class detection layer that tries basic glob expansion on command text
- **Recommended**: Option B — for each protected literal, also generate a regex that allows character class substitution `[x]` → `x` and `?` → `.`

### 2. `cat .en?` — question mark glob bypass
**Same root cause**: `?` in place of a character defeats literal matching.
**Fix**: Same as #1.

### 3. `cat $'\x2e\x65\x6e\x76'` — hex-encoded .env bypass
**Root cause**: ANSI-C quoting (`$'...'`) decodes hex/octal escapes at shell level. The literal command text contains `$'\x2e\x65\x6e\x76'`, not `.env`.
**Fix**: Pre-process command text to decode ANSI-C quoted strings before scanning.
**Implementation**: Add a function that finds `$'...'` sequences and decodes `\xHH`, `\NNN`, `\n`, `\t` etc.

## Part 2: Write/Delete Detection (5 failures)

### 4-6. `chmod/chown/touch` on `poetry.lock` (read-only)
**What the test checks**: These tests are in SECTION 3 "Read-Only Bypass Tests". They test whether `chmod 777 poetry.lock`, `chown user poetry.lock`, `touch poetry.lock` are properly CAUGHT when `poetry.lock` is a read-only path.
**Read the test code** in `tests/security/test_bypass_v2.py` to understand the exact assertion.
**Root cause hypothesis**: The tests may be checking the end-to-end flow where `is_write_command` returns True but the path doesn't get extracted or matched against read-only patterns. OR the test assertion is checking something else.
**Action**: Read the test code first, then determine the fix.

### 7. `> CLAUDE.md` — truncation as delete
**What the test checks**: Tests whether standalone redirect `> CLAUDE.md` (which truncates the file to zero bytes) is detected as a delete operation.
**Root cause**: `is_delete_command()` has a pattern `r"^\s*(?::)?\s*>(?!>)\|?\s*\S+"` but maybe the test expects something different.
**Action**: Read the test code to understand what it checks.

### 8. `git rm CLAUDE.md` — git rm not caught
**What the test checks**: Whether `git rm CLAUDE.md` is detected as delete AND whether `CLAUDE.md` path is extracted.
**Root cause**: `is_delete_command()` has a git rm pattern. Maybe path extraction fails for `git rm` syntax.
**Action**: Read test code first.

## Key Constraint
Read `tests/security/test_bypass_v2.py` carefully before implementing. Understand what each failing test actually asserts.

## Files to Modify
- `hooks/scripts/bash_guardian.py` — scan/detection functions
- `hooks/scripts/_guardian_utils.py` — possibly for pattern matching
- `tests/security/test_bypass_v2.py` — may need assertion fixes if tests have wrong expectations

## Validation
```bash
python3 tests/security/test_bypass_v2.py 2>&1 | grep -E "FAIL|PASS" | tail -20
python3 -m pytest tests/core/ tests/security/ -v 2>&1 | tail -5
```
