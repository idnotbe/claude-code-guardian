# Code Quality Review: Root Test File Cleanup Decisions

**Reviewer:** code-reviewer
**Date:** 2026-02-22
**Verdict:** CONDITIONAL APPROVAL -- delete most files, but migrate unique test vectors FIRST

---

## 1. Executive Summary

The decision document recommends "DELETE ALL" 60+ root test files, claiming complete coverage
in the organized `tests/` directory. After spot-checking 7 files against the organized test
suite, I found **6 concrete coverage gaps** where the decision document's claims are inaccurate.
The majority of files (roughly 50 of 60) truly are redundant and safe to delete. However,
approximately 8-10 files contain unique adversarial payloads and parser edge cases that have
**no equivalent in the organized test suite**.

**Recommendation:** Do NOT delete all files immediately. First migrate unique test vectors
to proper unittest classes, then delete. This is a "migrate-then-delete" approach, not
"archive indefinitely."

---

## 2. Coverage Gap Verification (Spot-Check Results)

### 2a. Files Verified as SAFE TO DELETE (coverage confirmed)

| Root File | Claimed Coverage | Verified In |
|-----------|-----------------|-------------|
| `test_clobber.py` (7 lines) | "Covered by core suite" | YES -- `tests/core/test_v2fixes.py:218-241` has `TestF3_ClobberRedirection` with 3+ tests, `tests/security/test_v2fixes_adversarial.py:248-310` has 8+ adversarial clobber tests |
| `test_heredoc_bypass.py` (18 lines) | "Covered by security suite" | YES -- `tests/security/test_v2_adversarial.py`, `tests/test_heredoc_fixes.py:29+` cover heredoc split_commands bypass thoroughly |

### 2b. Files Where Coverage Claims Are INACCURATE

#### GAP 1: `test_ansi.py` (55 lines) -- UNIQUE CONTENT

**Claim:** "Covered by usability/test_edge_cases.py"
**Reality:** The organized `tests/usability/test_edge_cases.py` has **zero ANSI-C decoder tests**.
The function `_decode_ansi_c_strings()` is never directly unit-tested anywhere in the organized
suite. It is only tested indirectly via `scan_protected_paths()` integration in
`tests/security/test_bypass_v2.py:258-259` (hex `\x2e`) and `:348-349` (octal `\056`).

Missing coverage:
- Unicode 16-bit escapes (`\u002e`) -- zero tests in organized suite
- Unicode 32-bit escapes (`\U0000002e`) -- zero tests in organized suite
- Control characters (`\cE`) -- zero tests in organized suite
- Octal without leading zero (`\56` vs `\056`) -- zero direct tests
- Standard escape sequences (`\n`, `\t`, `\r`, etc.) -- zero direct tests

**Risk:** An ANSI-C decoder regression would be invisible to the organized test suite.

#### GAP 2: `test_empty_quotes.py` (22 lines) -- PARTIALLY COVERED

**Claim:** "Covered by security/adversarial suites"
**Reality:** The organized suite covers `cat .e""nv` (empty quotes) at
`tests/security/test_bypass_v2.py:253` and `tests/security/test_v2_crossmodel.py:70-81`.
However, `test_empty_quotes.py` tests 8 obfuscation techniques:
- Techniques 1-4 (literal, empty quotes, backslash, glob ?) -- COVERED
- Technique 5 (ANSI-C octal without leading 0) -- NOT COVERED directly
- Technique 6 (ANSI-C unicode \u) -- NOT COVERED
- Technique 7 (ANSI-C 1-char hex) -- NOT COVERED
- Technique 8 (glob with escaped char `[\e]`) -- NOT COVERED

#### GAP 3: `test_del.py` (6 lines) -- CLAIM INACCURATE

**Claim:** "is_delete_command() covered by core/test_p0p1_comprehensive.py"
**Reality:** The specific test case `is_delete_command('bash -c "rm -rf .git"')` is NOT
covered. I searched for `bash -c` combined with `is_delete_command` or `rm` across all of
`tests/core/` and `tests/security/` -- zero matches. The organized suite tests `rm -rf`,
`rm -f`, `rm --force` directly, but never tests the `bash -c "rm ..."` wrapper pattern,
which is a real-world bypass vector.

#### GAP 4: `test_bypass3.py` (13 lines) -- PARTIALLY COVERED

**Claim:** "Heredoc + unclosed quotes covered by security suite"
**Reality:** The specific pattern of `cat > /etc/passwd << 'EOF'` with unclosed quotes
inside the heredoc body has no direct equivalent in the organized tests. The test verifies
`is_write_command()` and `extract_redirection_targets()` behavior with heredoc + unclosed
quote interaction. Only `tests/review/test_code_review.py:38` mentions "unclosed quote" but
in a different context.

#### GAP 5: `temp/test_edge_cases_v1.py` (301 lines, 9 categories) -- SIGNIFICANT UNIQUE CONTENT

**Claim:** "Edge cases fully covered by core/security/usability suites"
**Reality:** After systematic search, I found these categories have NO equivalent in organized tests:

| Category | test_edge_cases_v1.py | Organized Tests |
|----------|----------------------|-----------------|
| Edge Case 1: Nested constructs (`${VAR:-$(echo;echo)}`) | 5 tests | ZERO matches |
| Edge Case 2: Depth tracking attacks (desync `}` inside `$()`) | 4 tests | ZERO matches |
| Edge Case 3: ANSI-C decoder (unicode 16/32-bit, empty string) | 9 tests | Partial (hex/octal only) |
| Edge Case 4: `_expand_glob_chars()` | 6 tests | ZERO (function not tested anywhere) |
| Edge Case 5: Tokenizer boundaries (lone `;`, `&`, `|`) | 6 tests | Partial (empty/"   " covered, lone operators NOT) |
| Edge Case 6: Feature interactions (extglob+conditional, arithmetic+param) | 5 tests | 1 partial match |
| Edge Case 7: Scan false positive prevention (all-? token) | 4 tests | ZERO matches |
| Edge Case 8: Quote-aware write detection | 5 tests | In tests/test_heredoc_fixes.py only |
| Edge Case 9: Security bypass via new features | 5 tests | ZERO matches |

**This file alone has ~30 unique test vectors with no organized equivalent.**

---

## 3. False Negatives (Files Missing from Decision Doc)

The decision document appears comprehensive for root-level files. I did not find any root
test files omitted from the analysis.

However, I note that `tests/test_heredoc_fixes.py` (listed as "unique" and kept) is the
ONLY location for quote-aware `is_write_command()` tests. If this file were ever reorganized
or deleted, that coverage would be lost. It should be migrated to `tests/core/` as part of
the test consolidation effort.

---

## 4. Archival vs. Deletion: Best Practices Assessment

### Against `tests/_archive/` (long-term archival):
- Print-based scripts do not run in CI -- they will silently bit-rot
- Developers will ignore archived scripts, creating a false sense of coverage
- The test vectors are the valuable part, not the script infrastructure

### Against immediate "DELETE ALL":
- Unique adversarial payloads will be lost from working tree (yes, in git history, but
  nobody searches git history for test vectors)
- Coverage gaps will persist unnoticed until a real bypass occurs

### Recommended approach: "Migrate-then-Delete"
1. **Phase 1 (before cleanup):** Extract unique test vectors from flagged files and create
   proper unittest test classes:
   - `tests/core/test_parsers.py` -- direct unit tests for `_decode_ansi_c_strings()` and
     `_expand_glob_chars()` (from `test_ansi.py`, `test_bracket.py`, `test_brace.py`,
     `temp/test_edge_cases_v1.py` categories 3-4)
   - `tests/core/test_tokenizer_boundaries.py` or add to existing -- lone operator handling,
     nested constructs, depth tracking (from `temp/test_edge_cases_v1.py` categories 1-2, 5-6)
   - `tests/security/test_bypass_vectors.py` or add to existing -- bash -c wrapper,
     scan false positive prevention, bypass via new features (from `test_del.py`,
     `temp/test_edge_cases_v1.py` categories 7, 9)
2. **Phase 2 (after migration verified):** Delete ALL root scratch files
3. **No permanent archive** -- once migrated, the scratch files serve no purpose

---

## 5. Special Case: `temp/test_edge_cases_v1.py`

**Should it be preserved?** YES, temporarily, until its test vectors are migrated.

This file is the single most valuable scratch test file in the repository:
- 301 lines with 49 test assertions across 9 categories
- Tests internal functions directly (`_decode_ansi_c_strings`, `_expand_glob_chars`)
- Contains the ONLY tests for `_expand_glob_chars()` anywhere in the codebase
- Contains the ONLY tests for nested construct depth tracking
- Contains the ONLY tests for tokenizer boundary conditions with lone operators
- Has proper pass/fail counting (not just print statements)

Deleting this file without migration would create the largest single coverage gap in the
cleanup operation.

---

## 6. Files Safe to Delete Immediately (No Unique Coverage)

These files contain no test vectors that aren't already covered:

**Python (safe to delete ~29 of 37):**
- `test_parser.py`, `test_parser2.py`, `test_parser3.py` -- scratch prototypes
- `test_heredoc_bypass.py`, `test_heredoc_bypass_review.py`, `test_heredoc_bypass_top.py` -- covered
- `test_scan.py`, `test_scan2.py` -- covered
- `test_eval_regex.py` -- covered
- `test_sub.py`, `test_bg.py` -- scratch
- `test_bypass.py`, `test_bypass_old.py`, `test_bypass2.py`, `test_bypass4.py` -- covered
- `test_comment.py` -- covered
- `test_regex.py`, `test_regex2.py`, `test_regex_rm.py`, `test_rm_regex.py`, `test_rm.py` -- covered
- `test_clobber.py`, `test_extract.py`, `test_arithmetic.py` -- covered
- `test_piecewise.py` -- covered
- `test_crontab_regex.py`, `test_git_regex.py`, `test_git.py`, `test_git_clean.py` -- covered
- `test_chmod.py`, `test_chmod_2.py` -- covered

**Shell (all 23 safe to delete):**
All shell files are assertion-free exploration scripts. No unique test vectors.

**Other (safe to delete):**
- `test_project/` -- scratch sandbox
- `test_redirect.txt` -- trivial artifact

---

## 7. Files Requiring Migration Before Deletion (~8 files)

| File | Lines | Unique Content to Migrate |
|------|-------|--------------------------|
| `temp/test_edge_cases_v1.py` | 301 | 9 categories, ~30 unique test vectors (see Section 5) |
| `test_ansi.py` | 55 | Unicode 16/32-bit, control chars, octal variants for `_decode_ansi_c_strings` |
| `test_empty_quotes.py` | 22 | ANSI-C unicode/hex single-char obfuscation, escaped glob char class |
| `test_del.py` | 6 | `bash -c "rm -rf .git"` -- wrapper bypass vector |
| `test_bypass3.py` | 13 | Heredoc + unclosed quotes + `extract_redirection_targets` interaction |
| `test_bracket.py` | 10 | Glob `[x]` expansion (supplements `_expand_glob_chars` testing) |
| `test_brace.py` | 9 | Brace expansion scanning |
| `test_heredoc_bypass_top.py` | 35 | Top-level heredoc detection (verify against existing coverage) |

---

## 8. External Review Consensus

**Gemini 3.1 Pro (via clink):** Agreed that "DELETE ALL" is premature. Key points:
- "Deleting files without migrating unique test vectors introduces significant security blind spots"
- "Every obfuscation decoder/normalizer must have explicit unit tests. Testing parsers
  only via the public interface is a known anti-pattern [in security software]"
- Recommended migrate-then-delete, not permanent archival
- Cautioned that `tests/_archive/` as permanent storage is an anti-pattern (bit-rot)

**Codex:** Unavailable (rate limit)

---

## 9. Final Verdict

| Aspect | Decision Doc | This Review |
|--------|-------------|-------------|
| Delete all 60 files? | YES, immediately | NO -- migrate 8 files first |
| Coverage gaps? | "NONE" | 6 confirmed gaps |
| Risk of losing coverage? | "NONE" | MEDIUM for parser/decoder edge cases |
| `temp/test_edge_cases_v1.py`? | DELETE | MIGRATE FIRST (highest priority) |
| `test_ansi.py`? | DELETE | MIGRATE FIRST |
| Shell files? | DELETE | AGREE -- all safe to delete |
| Archival approach? | N/A | Temporary staging only, not permanent |

**Bottom line:** The structural goal is correct (consolidate into tests/). The execution
plan is flawed -- it skips the migration step, which would leave ~30 unique adversarial
test vectors without automated coverage in a security project where parser bypass is the
primary threat model.
