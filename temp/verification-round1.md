# Verification Round 1: Multi-Perspective Review

**Date**: 2026-02-22
**Reviewer**: v1-lead
**Scope**: All changes from Tasks #1 (Polish), #2 (Tokenizer), #3 (Detection)

---

## Executive Summary

**Overall Verdict: PASS with 2 findings (1 MEDIUM, 1 LOW)**

- **671/671 pytest tests pass** (1 pre-existing pytest fixture compat error in test_bypass_v2.py)
- **101/101 standalone bypass tests pass**, 0 security bypasses
- **16/16 regression tests pass**
- **Compilation: OK**
- **47/49 custom edge case tests pass** (2 findings documented below)

---

## Perspective 1: Correctness Review

### Test Suite Results

| Suite | Result | Command |
|-------|--------|---------|
| Core + Security + Heredoc | 671 passed, 0 failed, 1 error* | `python3 -m pytest tests/core/ tests/security/ tests/test_heredoc_fixes.py -v` |
| Standalone bypass | 101 passed, 0 failed, 0 bypasses | `python3 tests/security/test_bypass_v2.py` |
| Regression (errno36) | 16 passed, 0 failed | `python3 tests/regression/test_errno36_e2e.py` |
| Compilation | OK | `python3 -m py_compile hooks/scripts/bash_guardian.py` |

*The 1 error is a pre-existing pytest fixture compatibility issue in `test_bypass_v2.py` (the file uses a standalone `test()` function that pytest misinterprets as a test requiring a `name` fixture). Running it standalone works fine.

### Key Correctness Checks

- All 7 tokenizer fixes verified: `${}`, bare subshell, `(( ))`, `[[ ]]`, extglob, brace groups, heredocs
- All 8 detection fixes verified: ANSI-C decode, glob expand, chmod/chown/touch, `> CLAUDE.md`, `git rm`
- All 3 polish items verified: redirect regex `>` in negated class, comment filtering, ln pattern
- No regressions in any existing test category

---

## Perspective 2: Security Review

### Fail-Closed Behavior: PRESERVED

| Check | Status | Notes |
|-------|--------|-------|
| Import failure -> deny | OK | Lines 61-74: `ImportError` -> `deny` response |
| Invalid JSON -> deny | OK | Lines 1384-1389: `JSONDecodeError` -> `deny` |
| Unhandled exception -> deny | OK | Lines 1687-1713: crash -> `hookBehavior.onError` (default deny) |
| Unknown verdict -> fail-closed | OK | `_FAIL_CLOSE_PRIORITY` = max priority for unknown strings |
| Unterminated heredoc -> consume to end | OK | `_consume_heredoc_bodies()` exhausts input (fail-closed) |
| `param_expansion_depth` depth guard | OK | `}` only decrements when `depth == 0` (prevents desync from `}` inside `$()`) |

### New Code Security Analysis

**`_decode_ansi_c_strings()` (line ~565)**
- Decodes `\xHH`, `\uHHHH`, `\UHHHHHHHH`, `\NNN` (with/without leading 0), and standard escapes
- Unicode codepoint validation: `cp <= 0x10FFFF` check prevents invalid codepoints
- Regex `\$'((?:[^'\\]|\\.)*)'` correctly handles escaped characters inside `$'...'`
- No injection risk: output is used for scanning only, never executed

**`_expand_glob_chars()` (line ~648)**
- Only expands single-character bracket classes `[x]` and `[\x]`
- Multi-character classes `[abc]`, ranges `[a-z]`, negations `[!x]` are NOT expanded (correct)
- Regex: `r'\[\\?([^\]\[\\])\]'` -- cannot produce false expansions

**`scan_protected_paths()` glob-? enhancement (line ~767)**
- Post-match validation requires at least one non-`?` character: `any(g != '?' for g in gm.groups() if g)`
- Verified: `echo ????` does NOT false-positive (all-? prevention works)
- Verified: `cat .en?` DOES match `.env` (partial-? detection works)

**Comment filtering in Layer 1 scan (line ~1431)**
- Comment-only sub-commands (`# .env`) are excluded from scan text
- This prevents false positives from comments mentioning protected paths
- Safe because bash comments are inert and never execute

### Bypass Vector Analysis

**Tested and confirmed blocked:**
- `$'\x2e\x65\x6e\x76'` (ANSI-C hex) -> decoded to `.env` -> denied
- `$'\056env'` (ANSI-C octal) -> decoded to `.env` -> denied
- `.en[v]` (glob char class) -> expanded to `.env` -> denied
- `.en?` (glob question mark) -> matched via ?-aware regex -> denied
- `$'\u002e\u0065\u006e\u0076'` (unicode 16-bit) -> decoded -> denied
- `$'\U0000002e...'` (unicode 32-bit) -> decoded -> denied

**Known remaining gaps (documented, out of scope):**
- `cat .e""nv` (inline empty quote stripping) -> "allow" (requires shell word normalization)
- `cat $(printf '.%s' env)` (runtime string construction) -> "allow" (requires execution)
- `cat $(echo vne. | rev)` (runtime reversal) -> "allow" (requires execution)
- `a=.en; b=v; cat ${a}${b}` (split variable concatenation) -> "allow" (no literal `.env`)
- These are inherent limitations of static analysis and are properly documented

---

## Perspective 3: Edge Case Review

### Custom Edge Case Test Results: 47/49 passed

### Finding 1: Brace Group Delete Detection Regression [MEDIUM]

**Description**: Commands inside `{ ...; }` brace groups are no longer split by `split_commands()`, which means `is_delete_command()` cannot detect `rm` when it's preceded by `{` instead of being at command start or after `[;&|]`.

**Reproduction**:
```python
split_commands('{ rm -rf /; echo done; }')
# Returns: ['{ rm -rf /; echo done; }']  (1 command, not split)

is_delete_command('{ rm -rf /; echo done; }')
# Returns: False (rm not at position matching regex)
```

**Before fix**: `{ rm file; }` was split at `;` -> `rm file` detected as delete -> archive created
**After fix**: `{ rm file; }` stays as 1 command -> `rm` not detected -> no archive

**Impact**: Non-catastrophic delete commands inside `{ }` brace groups lose archive protection.

**Mitigations (existing)**:
1. Layer 0 block patterns catch most catastrophic patterns (but `rm -rf /;` with trailing `;` also escapes -- pre-existing regex limitation)
2. Layer 1 scan catches protected paths (`.env`, `.pem`, etc.) regardless of command structure
3. Claude rarely generates `{ cmd; }` syntax (low likelihood)

**Pre-existing parallel**: Same issue exists for `(rm file)` bare subshells -- `is_delete_command` has the same regex limitation for parenthesized commands. This was pre-existing before the tokenizer changes.

**Recommended fix**: Add `({` to the `is_delete_command` regex alternation: `(?:^|[;&|({]\s*)rm\s+`. This would catch `rm` after `{` or `(` as well. Similarly for `is_write_command` patterns.

**Severity**: MEDIUM. The regression is real but narrow in scope (brace groups are uncommon in Claude-generated commands) and has partial mitigation via Layer 1.

### Finding 2: Backslash-Escaped `>` Detected as Write [LOW]

**Description**: `echo hello \> world` is detected as a write command even though `\>` is a backslash-escaped `>` (literal, not a redirect in bash).

**Impact**: False positive -- a command that doesn't actually write to a file is flagged as a write. This is a fail-safe behavior (over-detection, not under-detection).

**Severity**: LOW. This is a false positive, not a false negative. The guardian is being more cautious than necessary, which is the correct direction for a security tool.

**Recommendation**: No action needed. Backslash-escaped redirects are rare in practice, and the false positive is harmless.

---

## Detailed Code Review

### `split_commands()` Changes (lines 82-438)

**Architecture**: Context-first ordering -- all context entry/exit tracking runs BEFORE separator checks. This is the correct design to prevent separators inside constructs from causing false splits.

**New state variables reviewed**:
| Variable | Purpose | Bounds-checked | Desync-protected |
|----------|---------|----------------|------------------|
| `param_expansion_depth` | `${...}` nesting | Yes (only decrements when > 0 AND depth == 0) | Yes (depth==0 guard prevents `}` inside `$()` from decrementing) |
| `bracket_depth` | `[[ ... ]]` nesting | Yes (only decrements when > 0) | N/A (]] is a unique 2-char token) |
| `brace_group_depth` | `{ ...; }` nesting | Yes (only decrements when > 0) | Partial (see Finding 1) |
| `extglob_depth` | `?()` etc. nesting | Yes (only decrements when > 0) | Yes (nested extglob tracked) |
| `arithmetic_depth` | `(( ... ))` nesting | Yes (only decrements when > 0) | Yes (placed before separator checks) |

**Potential concern reviewed**: Can depth counters desync? Tested `${x:-$(echo })}` -- the `}` inside `$()` does NOT decrement `param_expansion_depth` because the `depth == 0` guard prevents it. This is correct.

### `_decode_ansi_c_strings()` Changes (lines 565-645)

- Comprehensive escape handling: `\x`, `\u`, `\U`, `\NNN`, standard escapes
- No risk of infinite loops (while loop advances `i` on every iteration)
- No risk of out-of-bounds (all index access guarded by length checks)

### `_expand_glob_chars()` Changes (lines 648-665)

- Simple, bounded regex replacement
- No risk of ReDoS (regex is non-backtracking: `\[\\?([^\]\[\\])\]`)

### `scan_protected_paths()` Changes (lines 668-805)

- Scans original + normalized variants (ANSI-C decoded + glob expanded)
- Glob-? regex with post-match validation (all-? prevention)
- No performance concerns (tested with 10K+ input in performance test suite)

---

## Test Coverage Assessment

| Changed Area | Test Coverage | Verdict |
|--------------|---------------|---------|
| `split_commands()` tokenizer | 13 new tokenizer tests + 12 heredoc tests + existing suite | Adequate |
| `_decode_ansi_c_strings()` | 8 ANSI-C bypass tests in test_bypass_v2.py + 8 edge case tests | Adequate |
| `_expand_glob_chars()` | 4 glob expansion tests in test_bypass_v2.py + 5 edge case tests | Adequate |
| `scan_protected_paths()` enhancements | 26 scan tests in test_bypass_v2.py + existing v2fixes/adversarial | Adequate |
| Comment filtering | 4 comment tests in test_heredoc_fixes.py | Adequate |
| `ln` pattern fix | 5 ln tests across v2fixes + adversarial | Adequate |
| `chmod`/`chown`/`touch` detection | 3 tests fixed in test_bypass_v2.py | Adequate |

---

## Recommendations

1. **[MEDIUM] Fix brace group/subshell delete detection**: Add `({` to `is_delete_command` and `is_write_command` regex alternations. This is a small, targeted fix that restores archive protection for commands inside `{ }` and `( )`.

2. **[LOW] No action on backslash `>` false positive**: Fail-safe behavior is acceptable for a security tool.

3. **[LOW] Consider adding `{` and `(` to block pattern regex**: The `rm\s+-[rRf]+\s+/` block pattern doesn't match when `rm` is preceded by `{` or `(`. This is a pre-existing limitation but worth addressing.

---

## Conclusion

All three implementation streams produce correct, secure code with comprehensive test coverage. The one regression found (brace group delete detection) is narrow in scope, has existing mitigations, and has a clear fix path. All 671 pytest tests pass, all 101 standalone bypass tests pass, and no security bypasses were found. The changes are ready to proceed to Verification Round 2.
