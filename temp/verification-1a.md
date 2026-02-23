# Verification Report: verify-1a

**Verifier**: verify-1a (independent fresh-eyes verifier)
**Date**: 2026-02-22
**Scope**: 3 new test files covering previously untested edge cases in bash_guardian.py
**Model**: claude-opus-4-6

---

## VERDICT: PASS

All 168 new tests pass. The full core + security suite (798 tests) passes with no regressions. The one error (`test_bypass_v2.py`) is a pre-existing fixture compatibility issue unrelated to the new files. All 15 spot-checked tests have correct assertions verified against the source code. All migration plan items are covered.

---

## 1. Test Execution Results

### New test files (168 tests)

```
python3 -m pytest tests/core/test_decoder_glob.py tests/core/test_tokenizer_edge_cases.py tests/security/test_bypass_vectors_extended.py -v --tb=long
```

**Result: 168 passed in 0.17s**

| File | Tests | Status |
|------|-------|--------|
| tests/core/test_decoder_glob.py | 58 | ALL PASS |
| tests/core/test_tokenizer_edge_cases.py | 60 | ALL PASS |
| tests/security/test_bypass_vectors_extended.py | 50 | ALL PASS |

### Full suite regression check

```
python3 -m pytest tests/core/ tests/security/ -v --tb=short
```

**Result: 798 passed, 1 error in 4.24s**

The single error is in `tests/security/test_bypass_v2.py::test` -- a pre-existing pytest fixture incompatibility (the file defines `def test(name, actual, expected, category="general")` which pytest misinterprets as requiring a `name` fixture). This file was last modified in commit `2eb481b` (initial test suite addition) and is unrelated to the 3 new files.

**No regressions introduced by the new test files.**

---

## 2. Spot-Check Results (15 tests)

Selection criteria: 5 tests from each file, chosen to cover different categories and risk levels, with emphasis on security-critical assertions. Each assertion was traced to the corresponding source code path in `hooks/scripts/bash_guardian.py`.

### File 1: tests/core/test_decoder_glob.py

| # | Test | Assertion | Source Trace | Verdict |
|---|------|-----------|-------------|---------|
| 1 | `test_hex_null_byte_becomes_space` | `_decode_ansi_c_strings("$'\\x00'") == " "` | bash_guardian.py:587-596. `int("00", 16) = 0`, val == 0, appends space per V2-fix at line 593. | CORRECT |
| 2 | `test_octal_leading_zero_max_3_digits` | `_decode_ansi_c_strings("$'\\0145'") == chr(0o014) + "5"` | bash_guardian.py:620-633. Loop reads 3 octal digits: `0`, `1`, `4`. oct_str = "014", chr(12) = form-feed. `5` is leftover literal. | CORRECT |
| 3 | `test_unicode_32bit_out_of_range` | `_decode_ansi_c_strings("$'\\U00110000'")` has len != 1 | bash_guardian.py:608-619. cp = 0x110000 > 0x10FFFF, guard at line 614 fails, raw `\` appended. Multiple chars output. | CORRECT |
| 4 | `test_escaped_char_in_brackets` | `_expand_glob_chars("[\\v]env") == "venv"` | bash_guardian.py:674. Regex `\[\\?([^\]\[\\])\]` matches `[\v]`, captures `v`. Replacement: `v`. Result: `venv`. | CORRECT |
| 5 | `test_envsubst_not_false_positive` | `scan_protected_paths("envsubst < template", ...) == ("allow", "")` | bash_guardian.py:703-815. `".env"` literal searched with word boundaries. `envsubst` does not contain `.env` substring. No match. | CORRECT |

### File 2: tests/core/test_tokenizer_edge_cases.py

| # | Test | Assertion | Source Trace | Verdict |
|---|------|-----------|-------------|---------|
| 6 | `test_lone_ampersand` | `split_commands("&") == []` | bash_guardian.py:366-387. `&` at depth 0 flushes empty current. Line 440 filters empties. | CORRECT |
| 7 | `test_depth_desync_attack` | `split_commands("echo ${x:-$(echo })}; rm .env")` returns `["echo ${x:-$(echo })}", "rm .env"]` | bash_guardian.py:194-202. `}` inside `$()` (depth=1) does NOT decrement param_expansion_depth. After `)` closes `$()`, `}` at depth=0 closes `${}`. `;` splits into 2 commands. **CRITICAL SECURITY PROPERTY VERIFIED.** | CORRECT |
| 8 | `test_fd_redirection_not_separator` | `split_commands("echo error 2>&1")` returns 1 command | bash_guardian.py:374-377. `prev_c` is `>`, so `prev_c in (">", "<")` is True. `&` treated as part of redirect, not separator. | CORRECT |
| 9 | `test_bash_c_rm_rf` | `is_delete_command('bash -c "rm -rf .git"') == False` | bash_guardian.py:1030-1053. `rm` preceded by `"` which is not in pattern `[;&|({]`. No match. Documented as known gap. | CORRECT |
| 10 | `test_scan_disabled` | `scan_protected_paths("cat .env", {bashPathScan: {enabled: False}})` returns `("allow", "")` | bash_guardian.py:703-705. `enabled` is False, early return `("allow", "")`. | CORRECT |

### File 3: tests/security/test_bypass_vectors_extended.py

| # | Test | Assertion | Source Trace | Verdict |
|---|------|-----------|-------------|---------|
| 11 | `test_quote_concat_delimiter_unterminated_is_failclosed` | `split_commands('cat << E"O"F\nhidden\nEOF\necho visible')` returns 1 command | bash_guardian.py:468-473. Bare word parser consumes `E"O"F` (quotes not in stop-set). Delimiter = `E"O"F`. Body lines `hidden`, `EOF`, `echo visible` all != `E"O"F`. Unterminated. **FAIL-CLOSED VERIFIED.** | CORRECT |
| 12 | `test_tab_indented_delimiter_matches` | `split_commands("cat <<-MYEOF\n\thello\n\tMYEOF")` returns 1 command with `<<-MYEOF` | bash_guardian.py:476-506. strip_tabs=True. `"\tMYEOF".lstrip('\t')` = `"MYEOF"` == delimiter. Body consumed. | CORRECT |
| 13 | `test_gt_inside_single_quotes_not_write` | `is_write_command("echo 'data > file'") == False` | bash_guardian.py:1071-1092. `>` found at pos 11. `_is_inside_quotes(command, 11)` returns True (inside single quotes opened at pos 5). Match skipped. | CORRECT |
| 14 | `test_heredoc_hides_env_from_scan` | Joined sub-commands do NOT contain `.env` | bash_guardian.py:476-506. Heredoc body `{"secret": ".env"}` consumed by `_consume_heredoc_bodies`. Never appears in sub-command output. | CORRECT |
| 15 | `test_unterminated_heredoc_failclosed` | `split_commands("cat <<NEVERENDS\nrm -rf /\necho hidden")` returns 1 command; neither `rm -rf /` nor `echo hidden` leak | bash_guardian.py:476-506. Delimiter `NEVERENDS` never matched. All body lines consumed to end of input. **FAIL-CLOSED VERIFIED.** | CORRECT |

**Spot-check summary: 15/15 correct. All assertions match expected source code behavior.**

---

## 3. Prior Review Conditions Check

### Security Review (review-security-v2) Conditions

| Condition | Status | Evidence |
|-----------|--------|----------|
| **Required**: Strengthen 11 weak assertions in test_bypass_vectors_extended.py | RESOLVED | File was rewritten from 22 to 50 tests. All tests now use `assertEqual(len(result), N)`, `assertIn`, `assertFalse` with specific conditions. No `assertIsInstance(result, list)` weak assertions remain. |
| **Recommended**: Add GAP test for `printf` obfuscation | NOT ADDRESSED | No `printf` obfuscation test exists. This is tracked as a known untested vector in the security review. Low urgency since it is the same class of issue as `bash -c` wrapper gap. |
| **Recommended**: Add mixed-obfuscation test (ANSI-C + glob) | NOT ADDRESSED | No test combines `$'\x2e'[e]nv` in a single command. Minor gap. |
| **Nice-to-have**: Truncated escape sequence tests | NOT ADDRESSED | No `$'\u00'` or `$'\xZ'` tests. Very low risk. |

### Quality Review (review-quality-v2) Conditions

| Condition | Status | Evidence |
|-----------|--------|----------|
| **CONDITIONAL-1**: Fix misleading comment at test_tokenizer_edge_cases.py:216-218 | RESOLVED | Current comment (lines 216-217): "The $() depth tracking works inside double quotes, keeping the semicolon from splitting." This is accurate and non-misleading. |

---

## 4. Migration Plan Coverage Checklist

Source: `temp/migration-master-plan.md`

### Plan Item 1: tests/core/test_decoder_glob.py

| Planned Coverage | Covered? | Notes |
|-----------------|----------|-------|
| `_decode_ansi_c_strings()` hex (`\xHH`) | YES | Tests: test_hex_decodes_dotenv, test_hex_single_char, test_hex_null_byte_becomes_space |
| `_decode_ansi_c_strings()` octal without leading zero (`\NNN`) | YES | Tests: test_octal_no_leading_zero_dotenv, test_octal_single_digit, test_octal_two_digit |
| `_decode_ansi_c_strings()` octal with leading zero (`\0NNN`) | YES | Tests: test_octal_leading_zero_dot, test_octal_leading_zero_max_3_digits, test_octal_leading_zero_full_sequence_not_dotenv |
| `_decode_ansi_c_strings()` unicode 16-bit (`\uHHHH`) | YES | Tests: test_unicode_16bit_dotenv, test_unicode_16bit_single, test_unicode_16bit_non_ascii |
| `_decode_ansi_c_strings()` unicode 32-bit (`\UHHHHHHHH`) | YES | Tests: test_unicode_32bit_dotenv, test_unicode_32bit_emoji, test_unicode_32bit_out_of_range |
| `_decode_ansi_c_strings()` control chars | YES | Tests: test_control_c_terminates_string, test_control_c_truncates_remaining |
| `_decode_ansi_c_strings()` mixed/piecewise | YES | Tests: test_mixed_partial_ansi_c, test_piecewise_concatenation, test_mixed_ansi_and_plain |
| `_expand_glob_chars()` single-char brackets | YES | Tests: test_single_char_bracket_dot, test_single_char_bracket_letter |
| `_expand_glob_chars()` negated classes | YES | Tests: test_negated_class_unchanged, test_posix_negation_unchanged |
| `_expand_glob_chars()` ranges | YES | Test: test_range_unchanged |
| `_expand_glob_chars()` escaped chars | YES | Test: test_escaped_char_in_brackets |
| Piecewise ANSI-C concatenation | YES | Test: test_piecewise_concatenation + integration test_piecewise_ansi_detected |

**Status: FULLY COVERED**

### Plan Item 2: tests/core/test_tokenizer_edge_cases.py

| Planned Coverage | Covered? | Notes |
|-----------------|----------|-------|
| Empty input, whitespace, lone operators | YES | 15 tests in TestTokenizerBoundaries |
| Very long input (10K chars) | YES | test_very_long_input, test_very_long_input_with_separators |
| `${VAR:-$(echo;echo)}` depth tracking | YES | test_command_subst_inside_param_expansion |
| `${arr[$((i+1))]}` depth tracking | YES | test_arithmetic_inside_param_expansion |
| `${x:-$(echo })}; rm .env` depth desync | YES | test_depth_desync_attack |
| Brace group detection | YES | test_brace_group_keeps_semicolons_together |
| Feature interactions (extglob+conditional, arithmetic+param) | YES | test_extglob_in_conditional, test_arithmetic_plus_pipe, and 12 more interaction tests |

**Status: FULLY COVERED**

### Plan Item 3: tests/security/test_bypass_vectors_extended.py

| Planned Coverage | Covered? | Notes |
|-----------------|----------|-------|
| `bash -c "rm -rf .git"` wrapper pattern | YES | In test_tokenizer_edge_cases.py: test_bash_c_rm_rf (documented as known gap) |
| Heredoc + unclosed quotes + redirect interaction | YES | TestHeredocDelimiterEdgeCases (7 tests) |
| Obfuscation: ANSI-C unicode, hex single-char, glob bracket | YES | In test_decoder_glob.py integration tests |
| Scan false positive prevention | YES | TestScanFalsePositives (7 tests) |
| Security bypass via new features | YES | TestQuoteAwareWriteDetection (11 tests), TestCombinedAttackVectors (8 tests) |

**Status: FULLY COVERED (and exceeded plan scope)**

### Plan Item 4: Heredoc edge cases

| Planned Coverage | Covered? | Notes |
|-----------------|----------|-------|
| Quote concat delimiter: `E"O"F`, `'EOF'Z` | YES | test_quote_concat_delimiter_literal_match, test_quote_trailing_chars_failclosed, test_quote_trailing_both_terminators |
| Backslash-escaped delimiter: `\EOF` | YES | test_backslash_escaped_delimiter |
| Empty string delimiter: `''` | YES | test_empty_string_delimiter |
| Backslash-space delimiter | YES | test_backslash_space_delimiter |
| Piped multiple heredocs: `<<EOF \| <<EOF2` | YES | test_piped_heredocs_split_at_pipe |
| Pipeline+heredoc interleave | YES | TestPipelineHeredocInterleave (4 tests) |
| Process substitution + heredoc nesting | YES | TestProcessSubstitutionHeredoc (4 tests) |
| `)` in heredoc body inside `<()` | YES | test_depth_confusion_close_paren_in_heredoc |
| Depth corruption: `((((` in heredoc body | YES | test_multiple_parens_corrupt_depth |
| `$()` with `)` in heredoc body | YES | test_dollar_paren_heredoc_body_leaks |
| `<<-` space vs tab indentation | YES | TestTabStripHeredoc (5 tests) |

**Status: FULLY COVERED**

---

## 5. Concerns

### Minor Concerns (non-blocking)

1. **Untested `printf` obfuscation**: `printf '\x2e\x65\x6e\x76'` is a real bypass vector that is neither tested nor documented as a gap in the new files. This is the same class of issue as the `bash -c` wrapper gap. Recommended: add a GAP-documented test following the pattern in TestWrapperBypass.

2. **No mixed-obfuscation test**: No test combines ANSI-C + glob in one command (e.g., `cat $'\x2e'[e]nv`). The pipeline handles both transformations, but the interaction is untested. Low risk since both decoders run in sequence.

3. **No invalid escape sequence tests**: `$'\xGG'` (invalid hex) and `$'\u00'` (truncated unicode) are not tested. The source code falls through gracefully, but explicit tests would strengthen coverage.

4. **Pre-existing test_bypass_v2.py error**: The `fixture 'name' not found` error in `tests/security/test_bypass_v2.py` predates these changes but should be tracked for cleanup.

### No Blocking Concerns

All security-critical properties verified:
- Fail-closed behavior on unterminated heredocs
- Depth tracking prevents desync attacks from hiding commands
- Heredoc body content excluded from sub-command output
- Quote-aware detection prevents false positives on `>` inside strings
- Known gaps (wrapper bypass, depth corruption) are honestly documented

---

## 6. Summary

| Dimension | Assessment |
|-----------|-----------|
| Test execution | 168/168 pass, 0 failures |
| Regression check | 798 pass, 0 new errors |
| Spot-check correctness | 15/15 correct (source-traced) |
| Migration plan coverage | 4/4 items fully covered |
| Prior review conditions | 2/2 required conditions resolved; 3 recommended items not addressed (non-blocking) |
| Security properties | Fail-closed, depth tracking, heredoc isolation all verified |

**PASS** -- These 168 tests meaningfully improve coverage of previously untested attack surfaces. All assertions are correct when traced against source code. All migration plan items are covered. No regressions introduced.
