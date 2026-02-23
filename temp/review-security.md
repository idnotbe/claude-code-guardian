# Security Review of Root File Cleanup Plan

**Reviewer:** security-reviewer
**Date:** 2026-02-22
**Document reviewed:** temp/cleanup-decisions.md

---

## Executive Verdict

**CONDITIONAL APPROVAL** -- The cleanup plan is safe to proceed with 3 mandatory conditions.

The organized `tests/` directory covers the vast majority of bypass vectors. However, I identified **3 specific gaps** where deleting root scratch files would lose coverage for untested bypass vectors. These must be addressed before or during deletion.

---

## Finding 1: CRITICAL -- Piecewise ANSI-C Concatenation Bypass Untested

**Root file:** `test_piecewise.py` (line 8)
**Vector:** `cat $'\x2e'$'\x65'$'\x6e'$'\x76'` -- splits the encoded `.env` across multiple consecutive `$'...'` segments.

**Current organized test coverage:**
- `tests/security/test_bypass_v2.py:259` tests `$'\x2e\x65\x6e\x76'` (all hex in ONE segment) -- PASS
- `tests/security/test_bypass_v2.py:349` tests `$'\056env'` (octal in ONE segment) -- PASS
- `tests/security/test_bypass_v2_deep.py:161` traces hex-encoded `.env` through all layers -- PASS
- **NO test covers the piecewise concatenation vector** where each character is in a SEPARATE `$'...'` segment

**Why this matters:** The regex in `bash_guardian.py:654` (`re.sub(r"\$'((?:[^'\\]|\\.)*)'", ...)`) processes each `$'...'` block independently. The piecewise vector works because the regex replaces each segment, and adjacent decoded characters naturally concatenate in the output string. If the regex were ever changed to anchor or limit matches differently, this bypass vector would silently regress.

**Risk:** HIGH -- Silent regression during refactoring of the ANSI-C decoder.

**Required action:** Add a unittest to `tests/security/test_bypass_v2.py` or `test_v2_adversarial.py` asserting that `scan_protected_paths("cat $'\\x2e'$'\\x65'$'\\x6e'$'\\x76'", config)` returns `"deny"`.

---

## Finding 2: HIGH -- Unicode and Ctrl-Char ANSI-C Paths Untested

**Root file:** `test_ansi.py` (lines 52-55)
**Vectors not covered in organized tests:**

| Vector | Payload | Coverage |
|--------|---------|----------|
| 16-bit Unicode `\uHHHH` | `$'\u002e\u0065\u006e\u0076'` | **UNTESTED** (decoder exists at `bash_guardian.py:598-606`) |
| 32-bit Unicode `\UHHHHHHHH` | `$'\U0000002e\U00000065\U0000006e\U00000076'` | **UNTESTED** (decoder exists at `bash_guardian.py:608-618`) |
| Control char `\cX` | `$'\cE'` | **UNTESTED** (decoder exists at `bash_guardian.py:634-636`) |
| Non-leading-zero octal `\NNN` | `$'\56\145\156\166'` | **UNTESTED** (decoder handles at `bash_guardian.py:620-632`) |

**Current test coverage:** Only `\xHH` hex escapes and `\0NNN` leading-zero octals are exercised by `tests/security/test_bypass_v2.py`.

**Gemini review note:** The `\c` handler at `bash_guardian.py:634` contains a potential semantic issue. Bash evaluates `$'\cE'` as the byte `\x05` (Ctrl-E), but the current code does a `break` which terminates the entire `$'...'` string. While this is actually more conservative (fail-closed -- discards remaining content), it is not semantically correct and should be verified. The existing `test_ansi.py` scratch file was the only place this behavior was explored.

**Risk:** HIGH -- Four separate decoder code paths have no automated test coverage.

**Required action:** Add unittests covering `\uHHHH`, `\UHHHHHHHH`, `\NNN` (no leading zero), and `\cX` decoding through `scan_protected_paths()`.

---

## Finding 3: ADVISORY -- Shell Scripts Document Heredoc Edge Cases

**Root files:** 23 `.sh` files (no assertions, exploration scripts)
**Examples:**
- `test_depth_bypass.sh` -- Nested parens `((((((((` inside process substitution + heredoc
- `test_depth_heredoc.sh` -- Nested `$()` + heredoc with `rm -rf /` hidden in body
- `test_unmatched_paren.sh` -- `)` inside heredoc body confusing depth tracking
- `test_proc_sub.sh` -- Process substitution with multiple heredocs
- `test_pipeline_cat.sh` -- Heredoc piped to cat (pipeline heredoc)

**Current organized test coverage:**
- `tests/test_heredoc_fixes.py` -- 28+ tests covering heredoc-aware `split_commands()`, including arithmetic bypass prevention, comment injection, and delimiter parsing
- `tests/security/test_v2fixes_adversarial.py:154` -- Heredoc write bypass
- `tests/security/test_bypass_v2.py:142-146` -- Heredoc semicolon splitting

The organized tests cover the *security-critical* heredoc behaviors (bypass prevention, comment injection, arithmetic disambiguation). The shell scripts document edge cases at the bash syntax level that are not directly exploitable but represent institutional knowledge about parser quirks.

**Risk:** LOW -- These are bash syntax exploration artifacts. The security-critical heredoc behaviors are all covered in the organized test suite.

**Required action:** None mandatory. OPTIONAL: relocate to `tests/_archive/shell_exploration/` for future reference. These are in git history regardless.

---

## Files Verified Safe to Delete

The following security-sensitive root files have **confirmed full coverage** in organized tests:

| Root File | Organized Test Coverage |
|-----------|------------------------|
| `test_empty_quotes.py` | `tests/security/test_v2_crossmodel.py:67-84` (empty quote obfuscation), `test_bypass_v2.py:252-254` (`.e""nv`) |
| `test_heredoc_bypass.py` | `tests/test_heredoc_fixes.py:31-33` (basic heredoc not split), `test_bypass_v2.py:142-146` |
| `test_heredoc_bypass_review.py` | `tests/test_heredoc_fixes.py:84-89` (heredoc inside `$()`), `test_v2fixes_adversarial.py:154-161` |
| `test_heredoc_bypass_top.py` | `tests/test_heredoc_fixes.py:56-58` (heredoc followed by command), `tests/security/test_bypass_v2_deep.py:258-262` |
| `test_bypass.py` | `tests/security/test_v2_adversarial.py:107-117` (redirect `>&` detection) |
| `test_bypass2.py` | `tests/security/test_v2_crossmodel.py:67-84` (quote in cmd substitution) |
| `test_bypass3.py` | `tests/test_heredoc_fixes.py:39-41` (heredoc with unclosed quotes) |
| `test_bypass4.py` | `tests/test_heredoc_fixes.py:74-76` (heredoc delimiter confusion) |
| `test_bypass_old.py` | Historical comparison script, superseded by v2 tests |
| `test_del.py` | `tests/core/test_p0p1_comprehensive.py` (is_delete_command tests) |
| `test_scan.py` | `tests/core/test_p0p1_comprehensive.py` (scan_protected_paths tests) |
| `test_scan2.py` | `tests/core/test_p0p1_comprehensive.py` (AWS credentials scanning) |
| `test_comment.py` | `tests/test_heredoc_fixes.py:137-203` (comment handling) |
| `test_clobber.py` | `tests/security/test_v2fixes_adversarial.py:246-310` (F3 clobber tests) |
| `test_extract.py` | `tests/security/test_bypass_v2.py:520-543` (redirection extraction) |
| `test_arithmetic.py` | `tests/test_heredoc_fixes.py:101-134` (arithmetic vs heredoc disambiguation) |
| `test_bracket.py` | `tests/core/test_p0p1_comprehensive.py:242-303` (glob expansion) |
| `test_brace.py` | `tests/core/test_p0p1_comprehensive.py:532-533` (brace expansion) |
| `test_parser*.py` (3 files) | Scratch prototypes, parsing fully covered by core/security suites |
| `test_regex*.py` (4 files) | Pattern tests covered by `tests/patterns/` verification scripts |
| `test_git*.py` (3 files) | Covered by `tests/patterns/` |
| `test_chmod*.py` (2 files) | Covered by `tests/patterns/` |
| `test_rm*.py` (2 files) | Covered by core/security suites |
| All `.sh` files | See Finding 3 above |

---

## Bypass Vector Completeness Check

### Vectors in root files vs organized tests:

| Bypass Vector | Root File | Organized Test | Gap? |
|---------------|-----------|----------------|------|
| Hex ANSI-C `\xHH` | test_ansi.py | test_bypass_v2.py:259 | No |
| Octal `\0NNN` | test_ansi.py | test_bypass_v2.py:349 | No |
| Octal `\NNN` (no leading zero) | test_ansi.py | -- | **YES** |
| Unicode `\uHHHH` | test_ansi.py | -- | **YES** |
| Unicode `\UHHHHHHHH` | test_ansi.py | -- | **YES** |
| Ctrl char `\cX` | test_ansi.py | -- | **YES** |
| Piecewise ANSI-C concat | test_piecewise.py | -- | **YES** |
| Empty quote obfuscation `.''env` | test_empty_quotes.py | test_v2_crossmodel.py:70-84 | No |
| Empty double quotes `.""env` | test_empty_quotes.py | test_v2_crossmodel.py:80-84 | No |
| Backslash in filename | test_empty_quotes.py | test_bypass_v2.py:252 | No |
| Glob `?` bypass | test_empty_quotes.py | test_v2_adversarial.py:138-145 | No |
| Heredoc in `split_commands` | test_heredoc_bypass.py | test_heredoc_fixes.py | No |
| `eval/source/bash -c` heredoc | test_heredoc_bypass_review.py | test_heredoc_fixes.py:84+ | No |
| Redirect `>&` | test_bypass.py | test_v2_adversarial.py:107+ | No |
| Heredoc delimiter confusion | test_bypass4.py | test_heredoc_fixes.py:74+ | No |
| Process sub heredoc | test_proc_sub.sh | test_v2fixes_adversarial.py:580+ | No |
| Pipeline heredoc | test_pipeline_cat.sh | test_heredoc_fixes.py:52-54 | No |
| Depth tracking bypass | test_depth_bypass.sh | test_v2fixes_adversarial.py:1336+ | No |

**5 gaps identified** -- all in the ANSI-C decoding path (Findings 1 and 2).

---

## Summary of Required Actions

Before executing the cleanup:

1. **MUST** Add piecewise ANSI-C concatenation test to organized security suite
2. **MUST** Add `\uHHHH` and `\UHHHHHHHH` unicode escape tests
3. **MUST** Add `\NNN` (no leading zero) octal test
4. **SHOULD** Add `\cX` control character test (existing code is fail-closed, but the decoder path is untested)
5. **OPTIONAL** Archive `.sh` exploration scripts to `tests/_archive/shell_exploration/`

After these 4 mandatory tests are added, ALL root files are safe to delete.
