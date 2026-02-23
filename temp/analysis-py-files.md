# Python Test File Analysis - Root Directory Cleanup

**Analyst**: py-analyst
**Date**: 2026-02-22
**Scope**: 37 Python files in project root + extras (temp/test_edge_cases_v1.py, test_project/, test_redirect.txt)

## Summary

| Recommendation | Count | Files |
|---|---|---|
| DELETE | 33 | Scratch scripts, superseded by organized test suites |
| MOVE | 1 | temp/test_edge_cases_v1.py (valuable unique coverage) |
| DELETE (dir) | 1 | test_project/ (scratch directory) |
| DELETE (txt) | 1 | test_redirect.txt (stale artifact) |

All 37 root Python files are **scratch/one-off scripts** (no unittest classes, no pytest functions, no assertions). They print results to stdout and require manual inspection. The organized test suite in `tests/` already covers the same functionality with proper assertions.

---

## Detailed File Analysis

### Group 1: Parser/Tokenizer Scratch Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_parser.py` | 49 | Custom `((`/heredoc parser prototype (not actual bash_guardian code) | Scratch prototype | Superseded by `split_commands()` in tests/core/, tests/test_heredoc_fixes.py | DELETE |
| `test_parser2.py` | 48 | Same parser prototype with semicolon simulation | Scratch prototype | Same as above | DELETE |
| `test_parser3.py` | 48 | Same parser prototype with quote tracking + ANSI-C | Scratch prototype | Same as above | DELETE |
| `test_arithmetic.py` | 5 | One-liner: `split_commands('echo $(( 1 << 2 ))')` | Scratch one-liner | Covered by `tests/test_heredoc_fixes.py::TestArithmeticBypassPrevention` | DELETE |

**Rationale**: `test_parser.py`, `test_parser2.py`, `test_parser3.py` define their own `test_parser()` function (not from bash_guardian). They were prototyping ideas for the arithmetic-aware tokenizer. The final implementation lives in `split_commands()` and is thoroughly tested in `tests/test_heredoc_fixes.py` and `tests/core/`.

### Group 2: Heredoc Bypass Testing Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_heredoc_bypass.py` | 18 | `split_commands("bash <<EOF\nrm -rf /tmp/secret_file\nEOF")` | Scratch | Covered by `tests/test_heredoc_fixes.py::TestHeredocSplitting` + `tests/security/test_bypass_v2.py` | DELETE |
| `test_heredoc_bypass_review.py` | 31 | eval/source/bash -c heredoc bypass vectors | Scratch | Covered by `tests/security/test_bypass_v2.py` (heredoc bypass vectors section) | DELETE |
| `test_heredoc_bypass_top.py` | 35 | `bash <<EOF`, `eval "$(cat <<EOF)"`, `cat <<EOF | sh` bypass tests | Scratch | Covered by `tests/security/test_bypass_v2.py` and `tests/security/test_bypass_v2_deep.py` | DELETE |

**Rationale**: All three were exploratory during heredoc fix development. `tests/test_heredoc_fixes.py` has 30+ proper test methods covering these exact scenarios with assertions.

### Group 3: Scan/Protected Path Testing Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_scan.py` | 7 | `scan_protected_paths("bash <<EOF\ncat .env\nEOF", config)` | Scratch one-liner | Covered by `tests/test_heredoc_fixes.py::TestScanProtectedPathsHeredocAware` | DELETE |
| `test_scan2.py` | 7 | `scan_protected_paths('cat $(cat ~/.aws/credentials)', config)` | Scratch one-liner | Covered by `tests/core/test_p0p1_comprehensive.py` (scan tests) | DELETE |

### Group 4: Regex Testing Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_eval_regex.py` | 5 | eval + rm regex pattern matching | Standalone regex | Covered by `tests/core/test_p0p1_comprehensive.py::TestP0_1_ReDoS` | DELETE |
| `test_regex.py` | 18 | Redirect pattern `>\s*['\"]?[^|&;]+` vs `[^|&;>]+` | Standalone regex | Covered by `tests/test_heredoc_fixes.py::TestWriteCommandQuoteAwareness` | DELETE |
| `test_regex2.py` | 13 | Heredoc delimiter as .env false positive | Standalone regex | Covered by `tests/test_heredoc_fixes.py::TestScanProtectedPathsHeredocAware` | DELETE |
| `test_regex_rm.py` | 12 | Redirect pattern with heredoc `<< 'EOF'` interaction | Standalone regex | Covered by `tests/patterns/verify_write_patterns.py` | DELETE |
| `test_clobber.py` | 7 | `>|` (clobber) regex matching | Standalone regex | Covered by `tests/patterns/verify_write_patterns.py` | DELETE |
| `test_crontab_regex.py` | 23 | `crontab` pattern (`\bcrontab\b(?!\s+-l\b)`) | Standalone regex | Pattern exists in guardian.default.json; tested implicitly via `tests/core/test_p0p1_comprehensive.py` ask pattern tests | DELETE |
| `test_git_regex.py` | 11 | `git push --force` regex with `--force-with-lease` exclusion | Standalone regex | Covered by `tests/core/test_p0p1_comprehensive.py` and `tests/security/test_v2_adversarial.py` | DELETE |
| `test_rm_regex.py` | 8 | `rm -rf /` pattern (combined flags) | Standalone regex | Covered by `tests/core/test_p0p1_comprehensive.py` | DELETE |
| `test_chmod.py` | 9 | `chmod 777` regex pattern | Standalone regex | Covered by `tests/core/test_p0p1_comprehensive.py` (chmod 777 in ask patterns) | DELETE |
| `test_chmod_2.py` | 9 | `chmod 0777` with leading zero | Standalone regex (revision of test_chmod.py) | Same as above | DELETE |
| `test_git.py` | 12 | `git push --force` with `+refspec` detection | Standalone regex | Covered by `tests/security/test_v2_adversarial.py` | DELETE |
| `test_git_clean.py` | 8 | `git clean -fd` and `git clean -f -d` regex | Standalone regex | Covered by `tests/security/test_v2_adversarial.py::TestP1_1_GitRmBypass::test_git_clean_in_ask_patterns` | DELETE |
| `test_rm.py` | 11 | `rm --recursive -f /` with long flags | Standalone regex | Covered by `tests/core/test_p0p1_comprehensive.py` (rm detection tests) | DELETE |

**Rationale**: All are standalone regex testers that print match/no-match. The organized test suites in `tests/core/` and `tests/security/` cover all these patterns with proper unittest assertions.

### Group 5: Function-Level Scratch Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_del.py` | 6 | `is_delete_command('bash -c "rm -rf .git"')` | Scratch one-liner | Covered by `tests/core/test_p0p1_comprehensive.py` and `tests/security/` | DELETE |
| `test_sub.py` | 7 | `extract_paths('cat $(cat ~/.aws/credentials)', ...)` | Scratch one-liner | Covered by `tests/core/test_p0p1_comprehensive.py` | DELETE |
| `test_bg.py` | 6 | Reads file + `split_commands(f.read())` via argv | CLI wrapper | No unique value; just a utility script | DELETE |
| `test_comment.py` | 6 | `split_commands()` on file from argv | CLI wrapper | Identical to test_bg.py | DELETE |
| `test_extract.py` | 7 | `extract_redirection_targets("echo a >& b", ...)` | Scratch one-liner | Covered by `tests/core/test_p0p1_comprehensive.py` | DELETE |
| `test_bypass.py` | 11 | `is_write_command("echo bad >& ~/.bashrc")` | Scratch | Covered by `tests/core/test_p0p1_comprehensive.py` and `tests/test_heredoc_fixes.py` | DELETE |

### Group 6: Bypass Attempt Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_bypass_old.py` | 45 | Old `split_commands` prototype vs `is_delete_command` for heredoc bypass | Scratch with embedded old code | Completely superseded by `tests/security/test_bypass_v2.py` | DELETE |
| `test_bypass2.py` | 5 | `echo $( echo "\'" ) > /etc/passwd` quote confusion | Scratch one-liner | Covered by `tests/security/test_v2_crossmodel.py` | DELETE |
| `test_bypass3.py` | 14 | Heredoc with unclosed quotes in body + `is_write_command` | Scratch | Covered by `tests/test_heredoc_fixes.py` | DELETE |
| `test_bypass4.py` | 10 | `cat << 'EOF > /etc/passwd` (delimiter confusion) | Scratch | Covered by `tests/security/test_bypass_v2.py` | DELETE |

### Group 7: ANSI-C / Glob / Obfuscation Scripts (DELETE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `test_ansi.py` | 54 | `_decode_ansi_c_strings()` with hex, octal, unicode, ctrl chars | Scratch with print output | Covered by `tests/security/test_bypass_v2.py` (ANSI-C obfuscation section) and `tests/security/test_bypass_v2_deep.py` | DELETE |
| `test_bracket.py` | 10 | `_expand_glob_chars("cat [.]env")` single-char bracket | Scratch | Covered by `tests/security/test_bypass_v2.py` (glob expansion section) | DELETE |
| `test_brace.py` | 9 | `scan_protected_paths("cat .{e,x}nv", config)` brace expansion | Scratch one-liner | Covered by `tests/security/test_bypass_v2.py` (brace expansion section) | DELETE |
| `test_piecewise.py` | 9 | Piecewise ANSI-C string concatenation: `$'\x2e'$'\x65'...` | Scratch one-liner | Covered by `tests/security/test_bypass_v2.py` | DELETE |
| `test_empty_quotes.py` | 22 | `scan_protected_paths` with empty-quote obfuscation (.e""nv, .e\nv, etc.) | Scratch | Covered by `tests/security/test_bypass_v2.py` (obfuscation section) | DELETE |

### Group 8: Edge Case Verification Script (MOVE)

| File | LOC | What It Tests | Type | Overlap | Recommendation |
|---|---|---|---|---|---|
| `temp/test_edge_cases_v1.py` | 301 | Comprehensive edge cases: nested constructs, depth tracking, ANSI-C decoder, glob expansion, tokenizer boundaries, feature interactions, scan false positives, quote-aware writes, bypass attempts | Structured test script with pass/fail tracking | **Partially unique**: Tests nested `$()` inside `${}`, depth tracking attacks, empty/whitespace inputs, extglob interactions, `_expand_glob_chars` edge cases. Some overlap with `tests/security/test_bypass_v2.py` but many cases are NOT covered elsewhere. | **MOVE** to `tests/usability/test_edge_cases_v2.py` or `tests/core/test_edge_cases_tokenizer.py` |

**Rationale**: This is the only file with significant unique test coverage. It has 40+ test cases with proper assertions via a `test()` helper. The edge cases for tokenizer boundary conditions (empty input, whitespace, lone semicolons/pipes), nested construct depth tracking, and `_expand_glob_chars` corner cases are not covered in the existing test suite. Should be converted to unittest format and moved.

### Group 9: Non-Python / Directory Artifacts (DELETE)

| File | What It Is | Recommendation |
|---|---|---|
| `test_project/` | Directory with single `bypass_test.sh` (6 lines: sets DRY_RUN=1 and calls bash_guardian.py with heredoc rm -rf) | DELETE (superseded by tests/security/ subprocess integration tests) |
| `test_redirect.txt` | Contains just "hello" (1 line) | DELETE (stale output artifact from redirect testing) |

---

## Overlap Analysis with Existing Test Suite

The existing organized test suite provides comprehensive coverage:

| Existing Suite | Coverage Area | Root Files It Supersedes |
|---|---|---|
| `tests/test_heredoc_fixes.py` (318 lines, 30+ tests) | Heredoc splitting, arithmetic bypass, comment bypass, quote-aware writes, scan awareness | test_parser*.py, test_heredoc_bypass*.py, test_arithmetic.py, test_regex.py, test_bypass3.py |
| `tests/core/test_p0p1_comprehensive.py` (extensive unittest) | ReDoS, eval patterns, split_commands, scan_protected_paths, is_write/is_delete, all fix categories | test_eval_regex.py, test_scan*.py, test_del.py, test_sub.py, test_extract.py, test_rm*.py, test_chmod*.py |
| `tests/core/test_v2fixes.py` (extensive unittest) | F1-F10 fixes, fail-closed, archive safety, path scanning | test_bypass.py, test_comment.py |
| `tests/security/test_bypass_v2.py` (extensive, 250+ tests) | ANSI-C obfuscation, glob/bracket/brace expansion, heredoc bypass, piecewise concatenation | test_ansi.py, test_bracket.py, test_brace.py, test_piecewise.py, test_empty_quotes.py |
| `tests/security/test_v2_adversarial.py` (unittest) | Git rm bypass, truncation, chmod, force push | test_git*.py, test_chmod*.py |
| `tests/security/test_bypass_v2_deep.py` | End-to-end layer tracing | test_heredoc_bypass_top.py, test_bypass_old.py |
| `tests/security/test_v2_crossmodel.py` (unittest) | Cross-model red-team (Gemini/Codex) bypass attempts | test_bypass2.py, test_bypass4.py |

---

## Unique Coverage in temp/test_edge_cases_v1.py (Justification for MOVE)

These test cases in `temp/test_edge_cases_v1.py` are **not found** in the existing test suite:

1. **Tokenizer boundary conditions**: `split_commands("")`, `split_commands("   ")`, `split_commands(";")`, `split_commands("&")`, `split_commands("|")`, 10K char input
2. **Nested construct depth tracking**: `${x:-$(echo })}; rm .env` (depth desync attack), `{ rm -rf /; echo done; }` (brace group detection)
3. **`_expand_glob_chars` edge cases**: `[\\v]` (escaped char in brackets), empty brackets `[]`, negated classes `[!x]`
4. **Feature interaction tests**: `${arr[$((i+1))]}` (arithmetic inside param expansion), extglob inside brace groups, heredoc followed by brace group
5. **Scan false positive prevention**: all-`?` tokens, `?` in non-path context

---

## Final Recommendation Summary

**DELETE (36 items)**:
- All 37 root Python test files (scratch scripts, no assertions, all superseded)
- `test_project/` directory (scratch)
- `test_redirect.txt` (stale artifact)

**MOVE (1 item)**:
- `temp/test_edge_cases_v1.py` -> `tests/core/test_tokenizer_edge_cases.py` (convert to unittest format)

**Note on MOVE**: The file at `temp/test_edge_cases_v1.py` uses a custom `test(name, actual, expected)` helper instead of unittest. When moving, it should be refactored into a proper `unittest.TestCase` class with the standard `_bootstrap` import pattern used by other files in `tests/`.
