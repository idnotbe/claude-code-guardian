# Verification Round 2a: Fresh Perspective Skeptic Review

**Verifier:** verify-2a (fresh perspective, no prior review context)
**Date:** 2026-02-22
**Verdict:** PASS (with notes)

---

## 1. Test Execution

```
python3 -m pytest tests/core/test_decoder_glob.py tests/core/test_tokenizer_edge_cases.py tests/security/test_bypass_vectors_extended.py -v --tb=long
```

**Result:** 168 passed in 0.18s. Zero failures, zero errors, zero skips.

---

## 2. Structural Review

### 2.1 Tautological / Vacuous Tests

Searched for `assertTrue(True)`, `assertFalse(False)`, and other patterns that would pass regardless of implementation. **None found.** All 203 assertions (60 + 71 + 72 across the three files) test concrete values returned by the functions under test.

### 2.2 Tests That Document Known Gaps (Intentionally Asserting Broken Behavior)

Three tests in `TestWrapperBypass` assert `assertFalse(result)` with `# GAP` comments:

- `test_bash_c_rm_rf` (line 329-334): Documents that `bash -c "rm -rf .git"` is NOT detected by `is_delete_command`. The test documents the gap rather than testing a fix.
- `test_sh_c_rm_rf` (line 337-339): Same for `sh -c`.
- `test_eval_rm_rf` (line 342-344): Same for `eval`.

**Assessment:** These are NOT broken tests -- they are deliberately documenting known detection gaps. This is good practice for security test suites because:
1. They will alert developers when the gap is fixed (test will fail, prompting update).
2. They create a paper trail of known limitations.

**However**, if someone "fixes" the gap, these tests will FAIL and must be flipped. Consider using `expectedFailure` decorator for cleaner semantics. This is a MINOR note, not a blocker.

### 2.3 Tests That Could Pass With Broken Functions

Checked each file for assertions that are too lenient:

- `test_unicode_32bit_out_of_range` (decoder_glob.py:145-148): Asserts `self.assertNotEqual(len(result), 1)`. This is a somewhat weak assertion -- it passes if the function returns ANY string of length != 1. However, the actual failure mode (out-of-range codepoint) would produce either a multi-character raw string or an exception, so this is reasonable.

- `test_very_long_input` (tokenizer_edge_cases.py:101-106): Checks `len(result) == 1` and `startswith("echo ")`. This is a smoke test against crashes/hangs, which is its stated purpose. The assertion is meaningful but minimal -- it doesn't verify the full 10K content is preserved. Verified manually that it is.

**No truly vacuous tests found.**

### 2.4 Missing Error/Exception Handling Tests

None of the three files test error paths:
- What happens when `_decode_ansi_c_strings` receives non-string input?
- What happens when `split_commands` encounters a malformed command with mismatched quotes?
- What happens when `scan_protected_paths` receives a config with missing keys?

**Assessment:** These are edge cases at the boundary of the functions' contracts. The functions are internal (prefixed with `_`) and called only by other guardian code with validated input. The migration plan did not call for error-handling tests, and the existing test files in `tests/core/` and `tests/security/` don't generally test Python-level exceptions. This is a MINOR gap but not in scope for this migration.

### 2.5 Implementation Detail Dependencies

Several tests depend on exact sub-command splitting behavior (e.g., `test_quote_trailing_both_terminators` expects exactly 4 sub-commands). Verified that these assertions match actual behavior. If the tokenizer implementation changes, these tests will rightfully break. This is appropriate for regression tests.

---

## 3. Consistency Review

### 3.1 SCAN_CONFIG Discrepancies

The three files use DIFFERENT `SCAN_CONFIG` dictionaries:

| File | zeroAccessPaths | Extra fields |
|------|----------------|--------------|
| test_decoder_glob.py | 8 patterns (includes id_ed25519, id_ed25519.*) | None |
| test_tokenizer_edge_cases.py | 9 patterns (adds ~/.ssh/**) | None |
| test_bypass_vectors_extended.py | 5 patterns (minimal set) | readOnlyPaths, noDeletePaths |

**Assessment:** This is intentional and acceptable. Each file uses the minimal config needed for its tests:
- `test_decoder_glob.py` tests ANSI-C decoding, needs the obfuscation-target patterns.
- `test_tokenizer_edge_cases.py` has a broader set because it tests scan_protected_paths edge cases including path-in-directory (`~/.ssh/**`).
- `test_bypass_vectors_extended.py` uses a minimal set plus additional tiers for its cross-tier scanning tests.

The configs are NOT meant to be identical -- they are test fixtures. No issue here.

### 3.2 Docstring Accuracy

Spot-checked 15 docstrings against actual test logic. All accurately describe what the test does. Notable high-quality examples:
- `test_octal_leading_zero_max_3_digits` (line 94-101): Explains the 3-digit parsing limit and why `\0145` produces `chr(0o014) + "5"` instead of `"e"`.
- `test_depth_desync_attack` (line 161-176): Explains the security significance of depth tracking.
- `test_depth_confusion_close_paren_in_heredoc` (line 214-229): Documents a known limitation and explains why the behavior is still safe.

### 3.3 Import Cleanliness

Ran static analysis on all three files. **All imports are used.** No unused imports found.

---

## 4. Completeness Gap Analysis vs. Migration Master Plan

Checking each bullet from `temp/migration-master-plan.md`:

### Section 1: tests/core/test_decoder_glob.py

| Plan Bullet | Test Coverage | Status |
|------------|--------------|--------|
| Hex escapes | test_hex_decodes_dotenv, test_hex_single_char, test_hex_null_byte_becomes_space | COVERED |
| Octal (with/without leading 0) | test_octal_no_leading_zero_dotenv, test_octal_single_digit, test_octal_two_digit, test_octal_leading_zero_dot, test_octal_leading_zero_max_3_digits, test_octal_leading_zero_full_sequence_not_dotenv | COVERED |
| Unicode 16-bit | test_unicode_16bit_dotenv, test_unicode_16bit_single, test_unicode_16bit_non_ascii | COVERED |
| Unicode 32-bit | test_unicode_32bit_dotenv, test_unicode_32bit_emoji, test_unicode_32bit_out_of_range | COVERED |
| Control chars | test_control_c_terminates_string, test_control_c_truncates_remaining | COVERED |
| Mixed | test_mixed_partial_ansi_c, test_mixed_ansi_and_plain, test_multiple_ansi_c_strings, test_empty_ansi_c_string | COVERED |
| Single-char brackets | test_single_char_bracket_dot, test_single_char_bracket_letter | COVERED |
| Negated classes | test_negated_class_unchanged, test_posix_negation_unchanged | COVERED |
| Ranges | test_range_unchanged | COVERED |
| Escaped chars | test_escaped_char_in_brackets | COVERED |
| Piecewise ANSI-C | test_piecewise_concatenation, test_piecewise_ansi_detected | COVERED |

### Section 2: tests/core/test_tokenizer_edge_cases.py

| Plan Bullet | Test Coverage | Status |
|------------|--------------|--------|
| Empty input, whitespace | test_empty_string, test_whitespace_only, test_tab_only, test_newline_only | COVERED |
| Lone operators | test_lone_semicolon, test_lone_ampersand, test_lone_pipe, test_lone_double_ampersand, test_lone_double_pipe | COVERED |
| Very long input (10K) | test_very_long_input, test_very_long_input_with_separators | COVERED |
| ${VAR:-$(echo;echo)} | test_command_subst_inside_param_expansion | COVERED |
| ${arr[$((i+1))]} | test_arithmetic_inside_param_expansion | COVERED |
| Depth tracking: ${x:-$(echo })}; rm .env | test_depth_desync_attack | COVERED |
| Brace group | test_brace_group_keeps_semicolons_together | COVERED |
| Feature interactions | test_extglob_in_conditional, test_brace_group_with_param_expansion, etc. | COVERED |

### Section 3: tests/security/test_bypass_vectors_extended.py

| Plan Bullet | Test Coverage | Status |
|------------|--------------|--------|
| bash -c wrapper | test_bash_c_rm_rf, test_sh_c_rm_rf, test_eval_rm_rf (documents gap) | COVERED |
| Heredoc + unclosed quotes + redirect | Not directly tested as a combined vector | PARTIAL GAP |
| ANSI-C unicode obfuscation | In test_decoder_glob.py integration tests | COVERED |
| Hex single-char obfuscation | In test_decoder_glob.py | COVERED |
| Escaped glob bracket | In test_decoder_glob.py | COVERED |
| Scan false positive prevention | TestScanFalsePositives class (7 tests) | COVERED |
| All-? tokens | test_all_question_marks_no_false_positive | COVERED |
| Security bypass via new features | No specific test found | GAP |

### Section 4: Heredoc edge cases (in test_bypass_vectors_extended.py)

| Plan Bullet | Test Coverage | Status |
|------------|--------------|--------|
| Quote concat delimiter (E"O"F) | test_quote_concat_delimiter_literal_match, test_quote_concat_delimiter_unterminated_is_failclosed | COVERED |
| 'EOF'Z | test_quote_trailing_chars_failclosed, test_quote_trailing_both_terminators | COVERED |
| \EOF | test_backslash_escaped_delimiter | COVERED |
| Empty '' delimiter | test_empty_string_delimiter | COVERED |
| Backslash-space delimiter | test_backslash_space_delimiter | COVERED |
| Piped heredocs (<<EOF \| <<EOF2) | test_piped_heredocs_split_at_pipe | COVERED |
| Pipeline+heredoc interleave | TestPipelineHeredocInterleave (4 tests) | COVERED |
| Process substitution + heredoc | TestProcessSubstitutionHeredoc (4 tests) | COVERED |
| ) in heredoc body inside <() | test_depth_confusion_close_paren_in_heredoc | COVERED |
| Depth corruption (((((( in body) | test_multiple_parens_corrupt_depth | COVERED |
| $() with ) in heredoc body | test_dollar_paren_heredoc_body_leaks | COVERED |
| <<- space vs tab | TestTabStripHeredoc (5 tests) | COVERED |

### Summary of Gaps

1. **"Heredoc + unclosed quotes + redirect interaction"** -- The plan mentions this as a bullet under Section 3, but there is no single test that combines all three elements (heredoc with an unclosed quote AND a redirect). The heredoc tests and redirect tests exist independently. This is a MINOR gap.

2. **"Security bypass via new features"** -- The plan mentions this as a generic bullet. No test specifically targets a "new feature bypass". This was likely too vague to implement as a concrete test. Not actionable.

---

## 5. Additional Skeptic Findings

### 5.1 Assertion Strength on scan_protected_paths

In `test_decoder_glob.py`, the obfuscation integration tests use `assertNotEqual(verdict, "allow")` rather than `assertEqual(verdict, "ask")`. This is intentional (documented in class docstring: config uses "ask" action) but slightly looser than necessary. If the implementation were to return "deny" instead of "ask" for these cases, the tests would still pass, masking a behavioral change.

**Assessment:** This is a defensible choice -- the tests care about "not allowed" rather than the specific escalation level. But it means the tests would not catch a severity regression (ask -> deny). MINOR.

### 5.2 No Test for scan_protected_paths with Normalized vs Original Command Divergence

`scan_protected_paths` scans THREE text variants: original, glob-expanded original, and fully normalized (ANSI-C decoded + glob expanded). There's no test that specifically verifies the deduplication logic (lines 733-737 of bash_guardian.py) where the function builds `scan_texts` and deduplicates. If the deduplication were removed, scan would still work but be slower. No functional impact.

### 5.3 TestWrapperBypass tests are valuable but one-sided

The `TestWrapperBypass` class documents that `bash -c`, `sh -c`, and `eval` wrappers are NOT detected by `is_delete_command`. These tests pass because the function is known-broken for wrappers. But there's no test verifying that split_commands + is_delete_command TOGETHER handle wrappers (since split_commands might expose the inner command). This gap exists because is_delete_command operates on the whole string, not on split sub-commands.

---

## Final Verdict: PASS

All 168 tests pass. The test code is well-structured with accurate docstrings, clean imports, no tautological assertions, and thorough coverage of the migration plan's bullets. The SCAN_CONFIG differences are intentional and appropriate.

**Minor notes (non-blocking):**
1. Three `# GAP` tests could use `@unittest.expectedFailure` for cleaner semantics.
2. Two migration plan bullets have partial/no coverage: "heredoc + unclosed quotes + redirect interaction" (combined vector) and "security bypass via new features" (too vague to test).
3. Obfuscation integration tests use `assertNotEqual(verdict, "allow")` instead of exact verdict matching -- defensible but slightly loose.
4. No error/exception handling tests for the internal functions -- appropriate for this migration scope.
