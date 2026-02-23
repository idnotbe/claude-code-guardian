# Code Quality Review: 3 New Test Files (v2)

**Reviewer**: review-quality (Phase 2)
**Date**: 2026-02-22
**Verdict**: **CONDITIONAL APPROVE**

## Summary

Three test files were created to cover previously untested edge cases in bash_guardian.py.
All 168 tests pass. The existing suite (770 tests) shows no regressions. The files are
well-structured, use proper unittest patterns, and document known gaps transparently.
One conditional item must be resolved before final merge.

**Test counts** (actual, verified via `pytest --collect-only`):

| File | Claimed | Actual |
|------|---------|--------|
| tests/core/test_decoder_glob.py | 58 | 58 |
| tests/core/test_tokenizer_edge_cases.py | 60 | 60 |
| tests/security/test_bypass_vectors_extended.py | 22 | **50** |
| **Total** | **140** | **168** |

The bypass_vectors_extended.py file was significantly expanded beyond the original 22-test
plan (adding sections 5-8: tab-strip heredoc, scan false positives, quote-aware write
detection, combined attack vectors). This is a positive development.

---

## File 1: tests/core/test_decoder_glob.py (58 tests)

### Correctness: PASS

All assertions verified against the actual `_decode_ansi_c_strings()` and
`_expand_glob_chars()` source code in `hooks/scripts/bash_guardian.py`.

**Octal parsing accuracy** (lines 89-112): The tricky octal-with-leading-zero tests are
correct. The source code (bash_guardian.py:620-633) reads at most 3 octal digits starting
from the digit after `\`. So `\0145` reads digits `014` (3 digits), producing chr(12),
leaving `5` as literal. The tests at lines 94-102 and 104-112 correctly document this.

**Unicode out-of-range** (line 145-148): `\U00110000` (> 0x10FFFF) correctly asserts
`len(result) != 1`, matching the source guard at line 614 (`if cp <= 0x10FFFF`).

**Control char `\c`** (lines 152-160): Correctly documents the V2-fix where `\c`
terminates the ANSI-C string.

### Naming: GOOD

Test names follow `test_<escape_type>_<behavior>` pattern consistently. Docstrings
include raw string examples showing the transformation (e.g., `$'\x2e\x65\x6e\x76' -> .env`).

### SCAN_CONFIG: CORRECT

Uses exact paths (`.env`, `id_rsa`) and prefix patterns (`.env.*`, `id_rsa.*`) that
produce valid literals from `glob_to_literals()`. The comment at line 25 correctly
explains why `*.env` is NOT used.

### Issues

None.

### Coverage Assessment

Covers all escape types in `_decode_ansi_c_strings()`:
- [x] `\xHH` hex
- [x] `\uHHHH` unicode-16
- [x] `\UHHHHHHHH` unicode-32
- [x] `\NNN` octal (no leading zero)
- [x] `\0NNN` octal (with leading zero)
- [x] `\c` control terminator
- [x] Standard escapes: `\n`, `\t`, `\r`, `\a`, `\b`, `\f`, `\v`, `\e`, `\E`, `\\`, `\'`
- [x] Mixed/piecewise concatenation
- [x] Passthrough (no ANSI-C)
- [x] Empty ANSI-C string

Covers `_expand_glob_chars()`:
- [x] Single-char bracket `[.]`
- [x] Escaped char `[\v]`
- [x] Multi-char unchanged `[abc]`
- [x] Range unchanged `[a-z]`
- [x] Negation unchanged `[!x]`, `[^x]`
- [x] Empty brackets
- [x] Multiple brackets
- [x] No brackets passthrough

Integration tests cover obfuscation detection via `scan_protected_paths()`:
- [x] ANSI-C hex, unicode-16, unicode-32, octal
- [x] Glob bracket
- [x] Piecewise concatenation
- [x] False positive prevention (envsubst, environment)
- [x] Negative tests (empty quotes, brace expansion -- correctly documents Layer 1 limitations)

**Minor gap**: No test for `\x` with invalid hex digits (e.g., `$'\xGG'`). The source
falls through to appending the raw `\` character. Low risk since this is not a bypass
vector.

---

## File 2: tests/core/test_tokenizer_edge_cases.py (60 tests)

### Correctness: PASS

All assertions verified against `split_commands()`, `is_delete_command()`,
`is_write_command()`, and `scan_protected_paths()` source code.

**Depth desync attack** (lines 161-176): Correctly documents that `${x:-$(echo })}; rm .env`
splits into 2 commands. The `}` inside `$()` does not close `${}` because of depth
tracking. This is a critical security property.

**Wrapper bypass documentation** (lines 316-345): Honestly documents that `bash -c "rm -rf .git"`
is NOT detected by `is_delete_command()`. Tests assert `False` and comment `# GAP: wrapper
bypass not detected`. This is excellent practice -- documenting known gaps as tests prevents
future confusion about whether a bypass is intentional or a regression.

**Process substitution** (lines 220-223): Correctly tests that `<()` semicolons don't split.

### Naming: GOOD

Follows `test_<construct>_<behavior>` pattern. Section headers clearly delineate categories
(Tokenizer Boundaries, Nested Construct Depth, Feature Interactions, Wrapper/Eval Bypass).

### SCAN_CONFIG: CORRECT

Uses the same pattern as test_decoder_glob.py with exact paths and prefix patterns.
Includes `~/.ssh/**` which is correctly skipped by scan_protected_paths (the `**` check
at line 744 of bash_guardian.py filters out directory patterns).

### Issues

**CONDITIONAL-1** (line 216, TestNestedConstructDepth.test_nested_command_subst_in_double_quotes):

The comment on lines 216-218 is misleading:
```python
# Inside double quotes, so the $( won't increment depth (quotes
# are handled first). But the ; is still inside quotes. Should be 1.
```

This comment suggests `$()` inside double quotes doesn't increment depth, which is
incorrect for the actual bash behavior and potentially incorrect about the guardian's
behavior. The test assertion (`len(result) == 1`) is correct -- the command IS one
unit -- but the reasoning in the comment may confuse future maintainers. The real
reason it doesn't split is that the semicolon is inside `$()` (which IS tracked
even inside double quotes in the guardian), not because "quotes are handled first."

**Recommendation**: Fix the comment to accurately describe why the test passes.

### Coverage Assessment

Tokenizer boundary conditions:
- [x] Empty string, whitespace, tab, newline
- [x] Lone operators: `;`, `&`, `|`, `&&`, `||`
- [x] Multiple semicolons
- [x] Very long input (10K chars)
- [x] Very long input with separators (100 commands)
- [x] Single command (no separator)
- [x] Trailing/leading semicolon
- [x] Trailing backslash

Nested construct depth:
- [x] `$()` inside `${}`
- [x] `$(())` inside `${}`
- [x] Nested `${}`
- [x] Depth desync attack
- [x] Brace groups
- [x] Subshells
- [x] Command substitution (`$()` and backticks)
- [x] `[[ ]]` conditional
- [x] `(( ))` arithmetic
- [x] Extglob
- [x] `$()` in double quotes
- [x] Process substitution `<()`

Feature interactions:
- [x] Brace group + param expansion
- [x] Extglob in conditional
- [x] Heredoc + command after
- [x] Heredoc + brace group after
- [x] Nested heredoc in `$()`
- [x] Complex nesting (heredoc + param expansion + command subst)
- [x] Backslash-escaped semicolon
- [x] Semicolons inside single/double quotes
- [x] Pipe then semicolon
- [x] Background `&` then command
- [x] FD redirection `2>&1`
- [x] Ampersand redirect `&>`

Wrapper bypass:
- [x] `bash -c` (documents gap)
- [x] `sh -c` (documents gap)
- [x] `eval` (documents gap)
- [x] Direct rm, after `;`, `|`, `&`, inside `{}`, `()`
- [x] git rm, rmdir, truncation redirect, python os.remove

---

## File 3: tests/security/test_bypass_vectors_extended.py (50 tests)

### Correctness: PASS

All assertions verified against source code. This file is the most security-critical
and has the best documentation of any of the three files.

**Heredoc delimiter edge cases** (lines 41-124): Excellent documentation of divergences
between bash and guardian behavior. Each test explains whether the divergence is SAFE
(guardian is more restrictive) or represents a gap.

**Depth corruption attacks** (lines 235-309): The `test_multiple_parens_corrupt_depth`
test (line 242) correctly documents that `((((((((` in heredoc body corrupts the depth
counter, causing subsequent commands to be swallowed into one combined command. The
SECURITY NOTE correctly explains that Layer 1 raw string scan still catches dangerous
content.

**Dollar-paren heredoc body leak** (line 274): Correctly documents that `)` in heredoc body
inside `$()` causes body lines to leak as separate commands, and that this is SAFE because
leaked dangerous commands ARE visible for scanning.

**Combined attack vectors** (lines 489-557): Excellent section testing multi-technique
bypass chains. The `test_unterminated_heredoc_failclosed` test (line 539) verifies the
critical fail-closed property.

### Naming: GOOD

Test names are descriptive and follow consistent patterns. Section numbering (1-8) matches
the logical progression from simple to complex.

### SCAN_CONFIG: CORRECT

Uses `.env`, `.env.*`, `*.pem`, `id_rsa`, `id_rsa.*` -- all producing valid literals.
Includes `exactMatchAction` and `patternMatchAction` set to `"ask"`, which is necessary
for the detection tests in section 6 that assert `verdict == "ask"`.

### Issues

None. This is the strongest file of the three.

### Coverage Assessment

Heredoc delimiter edge cases:
- [x] Quote concatenation (`E"O"F`)
- [x] Quote concat fail-closed (unterminated)
- [x] Backslash-escaped delimiter (`\EOF`)
- [x] Empty string delimiter (`''`)
- [x] Quote trailing chars (`'EOF'Z`)
- [x] Quote trailing with both terminators
- [x] Backslash-space delimiter

Pipeline + heredoc:
- [x] Piped multiple heredocs
- [x] Pipeline heredoc body after pipe
- [x] Pipe then heredoc body consumed
- [x] Pipe chars in heredoc body

Process substitution + heredoc:
- [x] `<()` with heredoc
- [x] Dangerous body contained
- [x] Trailing command separation
- [x] Depth confusion (`)` in body)

Depth corruption:
- [x] Multiple `(` in body
- [x] Clean vs corrupted contrast
- [x] `$()` with `)` leak
- [x] `}` in body at depth 0
- [x] Semicolons in body

Tab-strip heredoc (`<<-`):
- [x] Tab-indented delimiter matches
- [x] Space-indented no match
- [x] Space-indented with trailing command consumed
- [x] Tab delimiter with trailing command
- [x] Mixed tab+space no match

Scan false positives:
- [x] All-`?` tokens
- [x] Quoted text detection (intentional false positive)
- [x] Word-in-text detection
- [x] Word boundary (`environment` vs `.env`)
- [x] Exact match (`id_rsa`)
- [x] Suffix match (`*.pem`)
- [x] Safe commands batch test

Quote-aware write detection:
- [x] Quoted redirect target (single/double)
- [x] `>` inside quotes not write
- [x] Redirect after quoted `>`
- [x] `extract_redirection_targets` with quotes
- [x] Append redirect
- [x] Heredoc operator not write
- [x] Here-string not write

Combined attack vectors:
- [x] Heredoc hides .env from scan
- [x] Command part .env still visible
- [x] Semicolons in body not split
- [x] Newlines in body consumed
- [x] `&` in body contained
- [x] `rm` in body not flagged by `is_delete_command`
- [x] Unterminated heredoc fail-closed
- [x] Multiple heredocs then command

---

## SCAN_CONFIG Consistency

| File | Config Patterns | Valid Literals? |
|------|----------------|----------------|
| test_decoder_glob.py | `.env`, `.env.*`, `.env*.local`, `*.pem`, `id_rsa`, `id_rsa.*`, `id_ed25519`, `id_ed25519.*` | Yes |
| test_tokenizer_edge_cases.py | Same as above + `~/.ssh/**` | Yes (ssh pattern skipped correctly) |
| test_bypass_vectors_extended.py | `.env`, `.env.*`, `*.pem`, `id_rsa`, `id_rsa.*` | Yes |

All three files use configs that produce valid literals from `glob_to_literals()`.
The patterns are consistent -- bypass_vectors uses a subset of the decoder_glob patterns,
which is fine since it only needs `.env`/`id_rsa`/`*.pem` for its specific tests.

---

## Coverage Gap Assessment vs Migration Plan

### Migration Plan Item 1: tests/core/test_decoder_glob.py
**Status**: FULLY COVERED

All planned items implemented:
- `_decode_ansi_c_strings()`: hex, octal (with/without leading 0), unicode 16/32-bit, control chars, mixed
- `_expand_glob_chars()`: single-char brackets, negated classes, ranges, escaped chars
- Piecewise ANSI-C concatenation

### Migration Plan Item 2: tests/core/test_tokenizer_edge_cases.py
**Status**: FULLY COVERED

All planned items implemented:
- Empty input, whitespace, lone operators
- Very long input (10K chars)
- Nested construct depth (all listed patterns)
- Depth tracking attacks
- Brace group detection
- Feature interactions (extglob+conditional, arithmetic+param expansion)

### Migration Plan Item 3: tests/security/test_bypass_vectors_extended.py
**Status**: FULLY COVERED (and exceeded)

All planned items implemented:
- `bash -c "rm -rf .git"` wrapper pattern (documented as known gap in tokenizer file)
- Scan false positive prevention
- Security bypass documentation

Additionally covered (not in plan):
- Quote-aware write detection (section 7)
- Combined attack vectors (section 8)
- `extract_redirection_targets` with quoted paths

### Migration Plan Item 4: Heredoc edge cases
**Status**: FULLY COVERED (merged into test_bypass_vectors_extended.py)

All planned heredoc items covered:
- [x] Quote concat delimiter: `E"O"F`, `'EOF'Z`
- [x] Backslash-escaped delimiter: `\EOF`
- [x] Empty string delimiter: `''`
- [x] Backslash-space delimiter
- [x] Piped multiple heredocs: `<<EOF | <<EOF2`
- [x] Pipeline+heredoc interleave
- [x] Process substitution + heredoc nesting
- [x] `)` in heredoc body inside `<()` (depth confusion)
- [x] Depth corruption: `((((` in heredoc body
- [x] `$()` with `)` in heredoc body
- [x] `<<-` space vs tab indentation

---

## Conditional Items

### CONDITIONAL-1: Misleading comment in test_tokenizer_edge_cases.py

**File**: `/home/idnotbe/projects/claude-code-guardian/tests/core/test_tokenizer_edge_cases.py`
**Line**: 216-218
**Severity**: Low (comment-only, does not affect test correctness)

The comment on `test_nested_command_subst_in_double_quotes` incorrectly explains why
the test passes. Replace:
```python
# Inside double quotes, so the $( won't increment depth (quotes
# are handled first). But the ; is still inside quotes. Should be 1.
```
With:
```python
# The semicolon is inside $() command substitution, which the
# tokenizer tracks even inside double quotes. Should be 1.
```

This is low severity and should not block merge, but should be fixed.

---

## Anti-Pattern Check

- [x] No `setUp`/`tearDown` abuse (tests are stateless)
- [x] No shared mutable state between tests
- [x] No test interdependencies
- [x] No `time.sleep` or non-determinism
- [x] No file I/O or network calls
- [x] Each test has exactly one assertion focus
- [x] Proper use of `self.assertEqual` / `self.assertIn` / `self.assertTrue`
- [x] All files have `if __name__ == "__main__": unittest.main()` for standalone execution
- [x] Proper bootstrap import pattern (`sys.path.insert` + `_bootstrap`)
- [x] No hardcoded paths or environment assumptions

---

## Final Verdict: CONDITIONAL APPROVE

The three test files are high quality. They:
1. Cover all items from the migration master plan
2. Exceed the plan scope with additional security tests
3. Document known gaps honestly (wrapper bypass, depth corruption)
4. Use correct SCAN_CONFIG patterns that produce valid literals
5. Follow consistent naming and documentation conventions
6. Are stateless and independent

**Condition**: Fix the misleading comment at test_tokenizer_edge_cases.py:216-218.
This is low-severity and should not block work, but should be addressed before final merge.
