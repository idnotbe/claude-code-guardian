# Security Review: New Test Files (v2)

**Reviewer:** review-security (automated security-focused reviewer)
**Date:** 2026-02-22
**Scope:** 3 new test files (140 tests total) covering previously untested edge cases
**Source under test:** `hooks/scripts/bash_guardian.py` (`_decode_ansi_c_strings`, `_expand_glob_chars`, `split_commands`, `is_delete_command`, `scan_protected_paths`)

---

## Overall Verdict: CONDITIONAL APPROVE

The 3 test files provide meaningful coverage for previously untested attack surfaces. The ANSI-C decoder tests and tokenizer boundary tests are strong. However, several tests in the heredoc/bypass file use weak assertions that verify "no crash" instead of "correct security behavior," and there are identifiable untested bypass vectors. Approve with the conditions documented below.

---

## 1. File-by-File Analysis

### 1.1 `tests/core/test_decoder_glob.py` (58 tests)

**Verdict: STRONG**

This file provides excellent direct unit test coverage for two internal functions that had zero prior test coverage.

**Strengths:**
- Comprehensive ANSI-C decoder coverage: hex (`\xHH`), octal without leading zero (`\NNN`), octal with leading zero (`\0NNN`), Unicode 16-bit (`\uHHHH`), Unicode 32-bit (`\UHHHHHHHH`)
- Critical edge case: `test_octal_leading_zero_max_3_digits` (line 94) correctly tests the 3-digit consumption limit -- an attacker might assume `\0145` decodes to `e` (octal 145) but it actually decodes to `\014` + literal `5`
- `\c` termination tested (line 152-159): V2-fix behavior where `\c` discards remaining content
- Piecewise concatenation tested (line 216-219): `$'\x2e'$'\x65'$'\x6e'$'\x76'` decoding to `.env`
- Integration tests (line 313+) verify the full pipeline: `scan_protected_paths` detecting obfuscated paths through ANSI-C and glob normalization
- False positive tests (lines 418-432): envsubst, "environment" word, ls -la correctly allowed
- Explicit documentation of layer boundaries (lines 398-414): tests correctly assert that empty-quote and brace expansion are NOT handled by `scan_protected_paths` (Layer 1)

**Concerns:**
- No test for `\x` with invalid hex digits (e.g., `$'\xZZ'`). The decoder should fall through gracefully, but this edge case is untested.
- No test for truncated `\u` or `\U` sequences (e.g., `$'\u00'` with only 2 hex digits). The source checks `i + 5 < len(content)` for `\u` and `i + 9 < len(content)` for `\U`, so short sequences should fall through, but no explicit test validates this.

### 1.2 `tests/core/test_tokenizer_edge_cases.py` (60 tests)

**Verdict: STRONG**

Excellent boundary condition testing for the tokenizer and nested depth tracking.

**Strengths:**
- Thorough empty/degenerate input testing (lines 51-106): empty string, whitespace-only, lone operators (`;`, `&`, `|`, `&&`, `||`), multiple semicolons
- Long input resilience tested (lines 101-112): 10K+ char input and 100-command split
- Critical depth desync attack tested (lines 161-176): `echo ${x:-$(echo })}; rm .env` correctly splits into 2 commands, ensuring `rm .env` is visible to security scanning
- Brace group, subshell, command substitution, backtick, `[[ ]]`, `(( ))`, extglob depth tracking all tested
- Feature interaction tests (lines 230-309): heredoc + brace group, extglob in conditional, backslash-escaped semicolon, fd redirection not treating `&` as separator
- GAP documentation (lines 316-344): wrapper bypass detection (`bash -c`, `sh -c`, `eval`) explicitly documented as known gaps with `assertFalse` marking actual (insecure) behavior

**Concerns:**
- `test_heredoc_followed_by_command` (line 243): Uses `assertIn("echo done", result)` which is correct but does not verify the heredoc command itself is also present
- Missing: no test for `split_commands` with deeply nested constructs (e.g., 100+ levels of `$($($(...))`)) -- could trigger stack-like issues in the iterative parser

### 1.3 `tests/security/test_bypass_vectors_extended.py` (22 tests)

**Verdict: NEEDS IMPROVEMENT -- Weak Assertions**

This file covers important heredoc edge cases and depth corruption attacks, but many tests use weak assertions that only verify "the function returned a list" rather than verifying security-relevant behavior.

**Strengths:**
- Heredoc delimiter edge cases (lines 37-76): quote concatenation (`E"O"F`), backslash-escaped (`\EOF`), empty string delimiter, quote+trailing chars (`'EOF'Z`)
- Depth corruption attacks (lines 135-163): multiple parens in heredoc body, close-brace in heredoc body, command substitution with heredoc containing `)`, semicolons in heredoc body
- Tab-strip heredoc (`<<-`) tested (lines 169-188)
- False positive prevention (lines 194-215)
- Quote-aware write detection (lines 222-247)

**Critical Weakness -- Weak Assertions:**
The following tests use `assertIsInstance(result, list)` and `assertTrue(len(result) >= 1)`, which verify ONLY that the function does not crash. They do NOT verify correct parsing behavior:

| Test | Line | Assertion | Should Assert |
|------|------|-----------|---------------|
| `test_quote_concat_delimiter` | 48-49 | `assertIsInstance(result, list)` + `len >= 1` | Whether heredoc body is consumed and `echo visible` appears as separate command |
| `test_backslash_escaped_delimiter` | 57-59 | `assertIsInstance(result, list)` + `len >= 1` | Same -- verify body consumed, post-heredoc command separate |
| `test_empty_string_delimiter` | 63-66 | `assertIsInstance(result, list)` + `len >= 1` | Same |
| `test_quote_concat_trailing_chars` | 73-76 | `assertIsInstance(result, list)` + `len >= 1` | Same |
| `test_piped_multiple_heredocs` | 88-91 | `assertIsInstance(result, list)` | Whether both heredoc bodies are consumed |
| `test_pipeline_heredoc_interleave` | 94-97 | `assertIsInstance(result, list)` | Whether `echo visible` appears after heredoc |
| `test_heredoc_in_process_substitution` | 114-118 | `assertIsInstance(result, list)` + `len >= 1` | Whether heredoc body is consumed inside `<()` |
| `test_paren_in_heredoc_body_depth_confusion` | 126-128 | `assertIsInstance(result, list)` | Whether depth tracker is NOT confused by `)` in heredoc body |
| `test_multiple_parens_in_heredoc_body` | 140-141 | `assertIsInstance(result, list)` | Same |
| `test_command_sub_heredoc_with_close_paren` | 154-155 | `assertIsInstance(result, list)` | Whether `echo visible` appears as separate command |
| `test_space_indented_delimiter_not_matched` | 184-187 | `assertIsInstance(result, list)` | Whether this behaves as unterminated heredoc (consumes to end) |

These weak assertions mean an attacker could introduce a regression that causes the parser to incorrectly merge commands (hiding `rm .env` inside what looks like heredoc body), and these tests would still pass.

**Specific example of risk:** If `_parse_heredoc_delimiter` stopped handling quote-concatenated delimiters (e.g., `E"O"F` no longer resolves to `EOF`), the heredoc body would be unterminated, consuming everything after it -- including `echo visible`. `test_quote_concat_delimiter` would still pass because `len(result) >= 1` is trivially true even when the result is wrong.

---

## 2. Bypass Vector Coverage Matrix

| Bypass Vector | test_decoder_glob | test_tokenizer | test_bypass_extended | Existing Tests | Status |
|--------------|:-:|:-:|:-:|:-:|--------|
| ANSI-C hex (`\xHH`) | YES (direct + integration) | - | - | test_bypass_v2 | COVERED |
| ANSI-C octal (`\NNN`) | YES (direct + integration) | - | - | - | NEW COVERAGE |
| ANSI-C octal leading zero (`\0NNN`) | YES (edge cases) | - | - | - | NEW COVERAGE |
| ANSI-C unicode 16-bit (`\uHHHH`) | YES (direct + integration) | - | - | - | NEW COVERAGE |
| ANSI-C unicode 32-bit (`\UHHHHHHHH`) | YES (direct + integration) | - | - | - | NEW COVERAGE |
| ANSI-C `\c` termination | YES | - | - | - | NEW COVERAGE |
| ANSI-C piecewise concatenation | YES (direct + integration) | - | - | - | NEW COVERAGE |
| Glob single-char brackets (`[.]`) | YES (direct + integration) | - | - | test_bypass_v2 | COVERED |
| Glob `?` wildcard (`.en?`) | - | - | - | test_bypass_v2 | COVERED |
| Empty-quote obfuscation (`.e""nv`) | YES (documents not-handled) | - | - | test_bypass_v2 | DOCUMENTED GAP |
| Brace expansion (`.{e,x}nv`) | YES (documents not-handled) | - | - | test_bypass_v2 | DOCUMENTED GAP |
| `bash -c` wrapper | - | YES (GAP documented) | - | - | **GAP DOCUMENTED** |
| `sh -c` wrapper | - | YES (GAP documented) | - | - | **GAP DOCUMENTED** |
| `eval` wrapper | - | YES (GAP documented) | - | - | **GAP DOCUMENTED** |
| Heredoc body hiding | - | - | YES (weak asserts) | test_bypass_v2 | WEAK COVERAGE |
| Heredoc quote-concat delimiter | - | - | YES (weak asserts) | - | WEAK COVERAGE |
| Heredoc depth corruption | - | - | YES (some weak) | - | PARTIAL |
| `<<-` tab-strip heredoc | - | - | YES (weak assert) | - | WEAK COVERAGE |
| `${VAR:-;}` depth desync | - | YES (strong) | - | test_bypass_v2 | COVERED |
| Tokenizer boundary inputs | - | YES (strong) | - | - | NEW COVERAGE |
| Process substitution depth | - | YES | YES (weak assert) | - | PARTIAL |
| `printf` hex/octal obfuscation | - | - | - | - | **NOT TESTED** |
| `xxd -r` / `base64 -d` pipe bypass | - | - | - | test_bypass_v2 (base64 only) | **NOT TESTED (printf, xxd)** |
| Variable indirection (`${!var}`) | - | - | - | - | **NOT TESTED** |
| `$'\x2e'` inside `bash -c` wrapper | - | - | - | - | **NOT TESTED (compound)** |
| `source`/`.` command | - | - | - | - | **NOT TESTED** |
| `exec` command | - | - | - | - | **NOT TESTED** |
| Command substitution output as filename (`cat $(echo .env)`) | - | - | - | test_bypass_v2 (backtick) | PARTIAL |
| Aliasing (`alias cat=...`) | - | - | - | - | **NOT TESTED (but low risk -- aliases disabled in non-interactive)** |
| `env -i bash -c 'rm .env'` | - | - | - | - | **NOT TESTED** |
| Parameter expansion substring (`${var:0:4}`) | - | - | - | - | **NOT TESTED** |

---

## 3. Known Gap Documentation Assessment

**Well-documented gaps (GOOD):**
- `bash -c`, `sh -c`, `eval` wrapper bypass: Explicitly documented in `test_tokenizer_edge_cases.py` lines 316-344 with `# GAP:` comments and `assertFalse(result)` marking actual insecure behavior. This is the right pattern -- documenting known limitations with tests that track whether behavior changes.
- Empty-quote obfuscation: Documented in `test_decoder_glob.py` lines 400-406 as "caught at other layers, not Layer 1"
- Brace expansion: Documented in `test_decoder_glob.py` lines 408-414 as "caught at other layers, not Layer 1"

**Undocumented gaps:**
- `printf '\x2e\x65\x6e\x76'` -- printf can decode hex/octal just like `$'...'` but through a separate mechanism. The guardian does not decode printf output. No test documents this gap.
- Variable indirection (`${!var}`) -- can reference arbitrary variable names. No test or comment addresses this.
- `source`/`.` command executing scripts that access protected paths -- no test or documentation.

---

## 4. False Positive/Negative Analysis

### False Positive Tests (Preventing over-blocking)

| Test | File | Status |
|------|------|--------|
| `envsubst < template` | decoder_glob (line 423) | GOOD |
| `echo environment` | decoder_glob (line 429), bypass_extended (line 198) | GOOD |
| `ls -la` | decoder_glob (line 419), bypass_extended (line 202) | GOOD |
| `echo hello world` | bypass_extended (line 208) | GOOD |
| `grep 'error' logfile.txt` | bypass_extended (line 213) | GOOD |
| `echo hello` (is_write_command) | tokenizer (line 391) | GOOD |
| `.e""nv` not detected at Layer 1 | decoder_glob (line 401) | GOOD (correct layer boundary) |
| `.{e,x}nv` not detected at Layer 1 | decoder_glob (line 409) | GOOD (correct layer boundary) |

**Assessment:** False positive coverage is adequate for the tested functions. The tests correctly verify that common benign commands are not blocked.

### False Negative Tests (Ensuring detection)

These are well-covered in `test_decoder_glob.py` integration tests (lines 328-396) for ANSI-C and glob obfuscation. The `test_bypass_v2.py` file in existing tests provides broader false-negative coverage.

**Gap:** No false-negative test for mixed obfuscation techniques in a single command (e.g., ANSI-C hex for the dot + glob bracket for a letter: `$'\x2e'[e]nv`).

---

## 5. Untested Attack Vectors (Priority Order)

### P0 (High -- should be addressed before merge or immediately after)

1. **`printf` obfuscation**: `printf '\x2e\x65\x6e\x76'` or `printf '\56\145\156\166'` produces `.env` via a completely different mechanism than ANSI-C `$'...'`. The `_decode_ansi_c_strings` function does not decode printf output. This is a real bypass if piped to another command: `cat $(printf '\x2e\x65\x6e\x76')`. However, the literal `.env` never appears in the raw command, so Layer 1 scan would miss it. This is the same class of issue as the `bash -c` wrapper gap -- the inner command is opaque to static analysis. Should be documented as a GAP test.

2. **Weak assertions in `test_bypass_vectors_extended.py`**: 11 of 22 tests use assertions that verify only "no crash" behavior. These tests cannot detect regressions in parsing correctness. Each should be strengthened to assert specific expected output (e.g., `assertIn("echo visible", result)` or `assertEqual(len(result), 2)`).

### P1 (Medium -- should be tracked)

3. **`source`/`.` command**: `source malicious_script.sh` or `. malicious_script.sh` can execute arbitrary commands including accessing protected paths. No detection in `is_delete_command` or `is_write_command` for script sourcing.

4. **Mixed obfuscation**: No test combines ANSI-C decode + glob expansion in one command (e.g., `cat $'\x2e'[e]nv`). The pipeline handles both, but the interaction is untested.

5. **`exec` command**: `exec 3< .env; cat <&3` uses file descriptor manipulation to read protected paths. The `exec` opener would contain `.env` literally (so Layer 1 catches it), but `cat <&3` would not.

### P2 (Low -- for completeness)

6. **Parameter expansion substring**: `v=".env"; cat ${v:0:4}` -- variable never contains the literal in the command. Same fundamental limitation as any runtime variable expansion.

7. **`env -i bash -c 'rm .env'`**: Variant of the `bash -c` wrapper gap, already documented conceptually.

---

## 6. Conditions for Full Approval

1. **Required:** Strengthen assertions in `test_bypass_vectors_extended.py` for the 11 weak-assertion tests identified in Section 1.3. At minimum, each test should verify:
   - The number of split commands produced
   - That post-heredoc commands (e.g., `echo visible`) appear as separate commands
   - That heredoc body content does not leak into the command list

2. **Recommended:** Add a GAP-documented test for `printf` obfuscation (P0 item 1), following the same pattern used for `bash -c`/`eval` in `test_tokenizer_edge_cases.py`.

3. **Recommended:** Add one mixed-obfuscation integration test combining ANSI-C + glob in a single command.

4. **Nice-to-have:** Add truncated escape sequence tests (`$'\u00'`, `$'\xZ'`) to the decoder unit tests for completeness.

---

## 7. Summary

| Dimension | Score | Notes |
|-----------|-------|-------|
| Bypass vector coverage | 7/10 | ANSI-C comprehensive; heredoc edge cases present but weakly asserted |
| Assertion strength | 6/10 | decoder_glob and tokenizer strong; bypass_extended weak |
| Gap documentation | 8/10 | bash -c/eval/sh -c well-documented; printf/source missing |
| False positive prevention | 8/10 | Adequate for Layer 1; correct layer boundary documentation |
| Novel vector discovery | 5/10 | Tests cover known vectors; no new vectors discovered by these tests |
| Overall test quality | 7/10 | Good foundation with specific fixable weaknesses |

**Bottom line:** These 140 tests meaningfully improve coverage of previously untested attack surfaces. The ANSI-C decoder and tokenizer boundary tests are production-quality. The heredoc/bypass extended tests need assertion strengthening before they can reliably catch regressions. With the weak assertions fixed, this is a solid approve.
