# Verification Round 2: Regression Testing Results

**Date:** 2026-02-22
**Modified file:** `hooks/scripts/bash_guardian.py`
**Test file:** `tests/test_heredoc_fixes.py`

---

## Step 1: Compile Check

```
python3 -m py_compile hooks/scripts/bash_guardian.py
```

**Result:** PASS (exit code 0, no syntax errors)

---

## Step 2: Dedicated Heredoc Tests

```
python3 -m pytest tests/test_heredoc_fixes.py -v
```

**Result:** 31 passed, 0 failed, 0 errors

| Test Class | Tests | Status |
|---|---|---|
| TestHeredocSplitting | 13 | ALL PASS |
| TestArithmeticBypassPrevention | 4 | ALL PASS |
| TestParseHeredocDelimiter | 4 | ALL PASS |
| TestWriteCommandQuoteAwareness | 8 | ALL PASS |
| TestScanProtectedPathsHeredocAware | 2 | ALL PASS |

---

## Step 3: Core + Security Suites

```
python3 -m pytest tests/core/ tests/security/ -q
```

**Result:** 627 passed, 3 failed, 1 error (in 2.97s)

### Failures (ALL PRE-EXISTING -- NOT REGRESSIONS)

| Test | File | Reason |
|---|---|---|
| `test_ln_pattern_in_source` | `tests/core/test_v2fixes.py:209` | Looks for `\bln\s+` in source but pattern changed to `(?<![A-Za-z-])ln\s+` in prior commit |
| `test_ln_symlink_not_detected` | `tests/security/test_v2_adversarial.py:211` | Asserts `ln -s` is NOT write; it now IS (intentional improvement from prior commit) |
| `test_ln_symlink_gap` | `tests/security/test_v2_adversarial.py:497` | Same as above -- known gap test now stale |

### Errors (ALL PRE-EXISTING -- NOT REGRESSIONS)

| Test | File | Reason |
|---|---|---|
| `test` (fixture error) | `tests/security/test_bypass_v2.py:77` | Standalone script with `def test(name, ...)` -- pytest interprets `name` as a fixture |

---

## Step 4: Standalone bypass_v2.py

```
python3 tests/security/test_bypass_v2.py
```

**Result:** 85 passed, 16 failed (standalone runner)

### Security Bypasses Found (ALL PRE-EXISTING)

| Category | Test | Expected | Actual |
|---|---|---|---|
| zeroAccess | `cat .en[v]` (char class) | deny | allow |
| zeroAccess | `cat .en?` (question mark glob) | deny | allow |
| zeroAccess | `cat $'\x2e\x65\x6e\x76'` (hex encoded .env) | deny | allow |

These 3 bypasses are documented known gaps (glob character classes and encoding escapes bypass literal string scanning).

### Other Failures (ALL PRE-EXISTING)

- 8 tokenizer edge cases (parameter expansion, subshell, brace groups, extglob, `[[ ]]`, arithmetic `&`, comments)
- 3 write detection gaps (chmod, chown, touch on read-only paths)
- 2 delete detection gaps (truncation via `>`, `git rm`)

**No new failures introduced by the heredoc fix.**

---

## Step 5: Regression Suite

```
python3 tests/regression/test_errno36_e2e.py
```

**Result:** 16 passed, 0 failed

| Section | Tests | Status |
|---|---|---|
| E2E TEST 1: Original Errno 36 crash | 1 | PASS |
| E2E TEST 2: Gemini-suggested multiline | 9 | ALL PASS |
| E2E TEST 3: Simple commands | 5 | ALL PASS |
| E2E TEST 4: Non-Bash tool passthrough | 1 | PASS |

Note: pytest collection of this file produces an INTERNALERROR (SystemExit caught) which is pre-existing and expected -- this file is designed for standalone execution only.

---

## Aggregate Results

| Suite | Passed | Failed | Errors | New Regressions |
|---|---|---|---|---|
| Heredoc tests | 31 | 0 | 0 | **NONE** |
| Core + Security | 627 | 3 | 1 | **NONE** |
| Standalone bypass_v2 | 85 | 16 | 0 | **NONE** |
| Regression e2e | 16 | 0 | 0 | **NONE** |
| **TOTAL** | **759** | **19** | **1** | **NONE** |

All 19 failures and 1 error are pre-existing and documented. Zero new regressions.

---

## Vibe Check Assessment

**Verdict:** Approach is sound. The 5-step verification pyramid (compile, unit, integration, standalone, e2e) is thorough and appropriate for a parser-level fix in a security-critical codebase.

**Minor note:** Confirmation bias risk when all tests pass as expected -- but the test assertions themselves are strong (testing both positive and negative cases).

---

## Gemini (gemini-3.1-pro-preview) Code Review

Consulted via pal `clink` tool with the prompt: "Review these test results for a bash guardian heredoc fix. Are there any concerning patterns?"

### Findings

#### CRITICAL: Security Bypass via Heredoc Body Stripping (Layer 1)

Gemini identified that the Layer 1 scan change (`scan_protected_paths` now operates on joined sub-commands instead of raw command string) creates a security blind spot: heredoc bodies are completely invisible to the Layer 1 scanner.

**Attack vector example:**
```bash
python3 << 'EOF'
print(open('.env').read())  # Layer 1 no longer sees '.env'
EOF
```

Previously, Layer 1 acted as defense-in-depth and would catch `.env` anywhere in the raw string. The heredoc-aware scan now excludes heredoc bodies entirely.

**Irony noted:** The test `test_env_in_heredoc_body_not_flagged` formally verifies and codifies this blind spot as desired behavior.

**Recommendation from Gemini:**
1. Revert Layer 1 to scan raw command string, OR implement context-aware matching that scans heredoc bodies unless the sub-command is a known-safe document-writing pattern
2. Add interpreter-heredoc security tests (`bash << EOF`, `python << EOF`, `node << EOF`)
3. Address false-positive inconsistency between `cat << EOF` and `echo` patterns

#### MEDIUM: Missing Interpreter Security Tests

The heredoc test suite verifies what is NOT a heredoc but lacks tests for restricted paths inside interpreter heredocs being correctly flagged.

#### POSITIVE: Arithmetic Context, Quote Awareness, Bash Parsing

Gemini validated the arithmetic_depth tracking, quote-aware write checks, and `let val<<1` heredoc detection as excellent, precise solutions.

---

## Action Items from This Verification

1. **[CRITICAL] Address Layer 1 heredoc body blind spot** -- The Gemini finding is valid. The scan should either:
   - Scan raw command AND joined sub-commands (union approach)
   - Scan heredoc bodies specifically when the command prefix is an interpreter (`python`, `bash`, `node`, `perl`, `ruby`)
   - Keep current behavior but document as accepted risk with compensating controls
2. **[LOW] Update stale ln tests** -- 3 pre-existing test failures from the ln pattern change should be updated to match current behavior
3. **[LOW] Fix bypass_v2.py pytest compat** -- Add `__test__ = False` or rename the standalone `test()` function

---

## Conclusion

**No regressions detected.** All 759 passing tests continue to pass. All 19 failures and 1 error are pre-existing and documented.

However, Gemini's code review surfaced a **critical architectural concern**: the Layer 1 scan change that excludes heredoc bodies creates a defense-in-depth gap for interpreter-mediated attacks via heredocs. This should be addressed as a follow-up before merging.
