# Shell Test File Analysis (Root Directory)

**Analyst**: sh-analyst
**Date**: 2026-02-22
**Scope**: 23 shell (.sh) test files in project root + 2 in tests/

---

## Existing Coverage in tests/

Before categorizing root files, here is what the organized test suite already covers for heredoc/shell parsing:

- **tests/test_heredoc_fixes.py** (318 lines, 30+ test methods): Comprehensive coverage of heredoc-aware `split_commands()`, arithmetic bypass prevention, comment-heredoc regression, `_parse_heredoc_delimiter` helper, quote-aware `is_write_command()`, and heredoc-aware `scan_protected_paths()`. Covers: basic heredoc, quoted heredoc, `<<-` tab stripping, here-string `<<<`, multiple heredocs, semicolons in body, unterminated heredoc, heredoc inside `$()`, arithmetic shift vs heredoc, comment `# << EOF` bypass, `cat<<EOF` (no space), double-quoted delimiters.
- **tests/test_bash_behavior.sh**: 1-liner: `cat <<EOF ; echo "This is a command"` -- bash behavior demo.
- **tests/test_bash_syntax.sh**: 2-liner: `cat <<A ; cat <<B` -- multiple heredoc syntax demo.
- **tests/core/test_v2fixes.py** and **tests/security/test_bypass_v2.py**: Additional heredoc-related assertions in split_commands tests.
- **tests/review/test_code_review.py**: Unmatched parenthesis depth test.

---

## File-by-File Analysis

### 1. test_script.sh
```bash
((
  x = 1 # ))
  y << EOF
))
echo "I am executing a dangerous command: rm -rf /"
EOF
```
- **What it tests**: Arithmetic context `(( ))` with embedded `<<` -- tests whether guardian correctly distinguishes arithmetic shift from heredoc.
- **File type**: Manual exploration snippet (no assertions, no shebang).
- **Overlap**: Covered by `tests/test_heredoc_fixes.py::TestArithmeticBypassPrevention::test_arithmetic_shift_not_heredoc` and related tests.
- **Recommendation**: **DELETE** -- one-off exploration, scenario already tested.

### 2. test_heredoc_quote.sh
```bash
cat << E"O"F
echo "hidden"
EOF
echo "visible"
```
- **What it tests**: Heredoc with partially-quoted delimiter `E"O"F` -- tests whether guardian correctly handles quote concatenation in heredoc delimiters.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: Partially covered by `test_heredoc_fixes.py` (quoted delimiters with `'EOFZ'` and `"MARKER"`), but **quote concatenation** (mixing bare+quoted chars) is NOT explicitly tested.
- **Recommendation**: **MOVE** -- the quote concatenation pattern `E"O"F` is a genuine edge case not covered in existing tests. Should be added as a test case to `tests/test_heredoc_fixes.py::TestParseHeredocDelimiter` or `TestHeredocSplitting`.

### 3. test_heredoc_bs.sh
```bash
cat << \EOF
echo "hidden"
EOF
echo "visible"
```
- **What it tests**: Heredoc with backslash-escaped delimiter `\EOF` -- bash treats `\` as quoting the delimiter.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: NOT explicitly covered. The existing tests cover `'EOF'` and `"EOF"` but not `\EOF`.
- **Recommendation**: **MOVE** -- backslash-escaped delimiter is a valid bash syntax not yet tested. Add to `TestParseHeredocDelimiter`.

### 4. test_empty_delim.sh
```bash
cat << ''
echo "hidden"

echo "still hidden"

echo "visible"
```
- **What it tests**: Heredoc with empty string delimiter `''` -- empty delimiter means the heredoc terminates on the first empty line.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `TestParseHeredocDelimiter::test_empty_at_eof` tests empty-at-EOF but NOT the `''` empty-quoted-string delimiter behavior.
- **Recommendation**: **MOVE** -- empty delimiter is a tricky edge case. Add as test case.

### 5. test_bs_space.sh
```bash
cat << \
echo "hidden"

echo "visible"
```
- **What it tests**: Heredoc with backslash-space delimiter `\ ` -- the delimiter is a single space character.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: NOT covered anywhere.
- **Recommendation**: **MOVE** -- exotic but valid bash syntax. Delimiter-is-whitespace is a security-relevant edge case. Add to `TestParseHeredocDelimiter`.

### 6. test_multiple_heredocs.sh
```bash
cat <<EOF | cat <<EOF2
body1
EOF
body2
EOF2
echo "visible"
```
- **What it tests**: Multiple heredocs on one line connected by pipe.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `test_heredoc_fixes.py::TestHeredocSplitting::test_multiple_heredocs_one_line` tests `cmd <<A <<'B'` (multiple heredocs to one command). This file tests `cmd <<EOF | cmd <<EOF2` (piped heredocs) -- different scenario.
- **Recommendation**: **MOVE** -- piped multiple heredocs is a distinct case from multiple heredocs to one command. Add to `TestHeredocSplitting`.

### 7. test_pipeline_heredoc.sh
```bash
cat <<EOF |
grep "b"
body
EOF
echo "visible"
```
- **What it tests**: Pipeline where heredoc's body appears after the pipe -- `grep "b"` is the pipe target, and `body\nEOF` is the heredoc content. This is a tricky parsing scenario.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: NOT explicitly tested. Existing tests cover basic heredocs but not heredoc-in-pipeline where the pipe command appears interleaved with heredoc body.
- **Recommendation**: **MOVE** -- pipeline+heredoc interleaving is security-relevant (commands could hide after pipe). Add to `TestHeredocSplitting`.

### 8. test_pipeline_heredoc2.sh
```bash
cat <<EOF |
grep "b"
body
EOF
echo "visible"
```
- **What it tests**: Identical to `test_pipeline_heredoc.sh`.
- **File type**: Duplicate of file #7.
- **Overlap**: Same as #7.
- **Recommendation**: **DELETE** -- exact duplicate.

### 9. test_pipeline_heredoc3.sh
```bash
cat <<EOF |
grep "b"
this is the body!
EOF
echo "visible"
```
- **What it tests**: Same pattern as #7 but with different body text ("this is the body!" vs "body").
- **File type**: Minor variation of #7.
- **Overlap**: Same scenario as #7, just different body content.
- **Recommendation**: **DELETE** -- trivial variation of #7, no additional test value.

### 10. test_pipeline_cat.sh
```bash
cat <<EOF |
cat -
hello
EOF
echo "visible"
```
- **What it tests**: Pipeline with heredoc, piping into `cat -`. Tests whether `cat -` is correctly identified as the pipe target vs heredoc body.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: Related to #7 but tests `cat -` as pipe target. Essentially same parsing challenge.
- **Recommendation**: **DELETE** -- same parsing scenario as #7, different pipe target is not meaningful for guardian logic.

### 11. test_pipeline_cat2.sh
```bash
cat <<EOF |
hello
EOF
cat -
echo "visible"
```
- **What it tests**: Heredoc piped to `cat -`, where `cat -` appears AFTER the EOF terminator. Tests whether `cat -` is treated as a separate command.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: Related to heredoc+pipeline parsing. Distinct from #7 because the pipe target appears after EOF.
- **Recommendation**: **DELETE** -- the post-EOF command parsing is covered by `test_heredoc_followed_by_command` in test_heredoc_fixes.py. The pipe is irrelevant to guardian scanning.

### 12. test_proc_sub.sh
```bash
diff <(cat <<EOF
body1
EOF
) <(cat <<EOF2
body2
EOF2
)
echo "visible"
```
- **What it tests**: Process substitution `<()` containing heredocs -- complex nesting of `<()` + `<<EOF`.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `tests/test_guardian_p0p1_comprehensive.py::test_process_substitution` tests basic process substitution. `tests/_archive/test_guardian_bypass.py` tests `cat <(echo hello)`. But **heredocs inside process substitution** is NOT tested.
- **Recommendation**: **MOVE** -- process substitution + heredoc nesting is a genuine edge case for the parser. Important for security (commands could hide in body).

### 13. test_unmatched_paren.sh
```bash
diff <(cat <<EOF
)
EOF
) file
echo "hidden command"
```
- **What it tests**: Unmatched/confusing parentheses -- heredoc body contains `)` which could confuse depth tracking of `<()`.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `tests/review/test_code_review.py` tests unmatched parenthesis depth generally, but NOT this specific scenario with heredoc body containing `)`.
- **Recommendation**: **MOVE** -- parenthesis-in-heredoc-body is a parser confusion attack vector. Security-relevant.

### 14. test_depth_bypass.sh
```bash
diff <(cat <<EOF
((((((((
EOF
) file
echo "hidden command"
```
- **What it tests**: Depth tracking bypass attempt -- heredoc body contains many `(` which could corrupt depth counter if body isn't properly masked.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: Related to #13 but with depth corruption via multiple `(` chars. NOT tested in existing suite.
- **Recommendation**: **MOVE** -- depth corruption via heredoc body is a security bypass vector. Should be tested alongside #13.

### 15. test_comment_bash.sh
```bash
# this is a comment with << EOF
rm -rf /
EOF
echo "visible"
```
- **What it tests**: `<< EOF` inside a comment -- tests that `#` prevents heredoc detection.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: **Fully covered** by `tests/test_heredoc_fixes.py::TestCommentHeredocRegression::test_comment_heredoc_not_consumed` which tests the exact same pattern.
- **Recommendation**: **DELETE** -- exact scenario already has proper assertions in the test suite.

### 16. test_depth_heredoc.sh
```bash
echo $(
cat <<EOF
)
rm -rf /
EOF
)
echo "visible"
```
- **What it tests**: Heredoc inside command substitution `$()` where heredoc body contains `)` -- tests depth tracking with heredoc interaction.
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `tests/test_heredoc_fixes.py::TestHeredocSplitting::test_heredoc_inside_command_substitution` tests `echo $(cat <<EOF\nbody\nEOF\n)` but the body does NOT contain `)`. This file's scenario is more adversarial.
- **Recommendation**: **MOVE** -- the `)` in heredoc body inside `$()` is a depth-confusion attack vector not tested. Security-relevant.

### 17. test_bash_heredoc.sh
```bash
cat << MYEOF
hello world
MYEOF
```
- **What it tests**: Basic heredoc with custom delimiter `MYEOF`.
- **File type**: Trivial manual snippet (no assertions).
- **Overlap**: **Fully covered** by `test_heredoc_fixes.py::test_basic_heredoc_not_split`.
- **Recommendation**: **DELETE** -- trivial, fully covered.

### 18. test_bash_heredoc2.sh
```bash
cat << MYEOF
hello \
world
MY\
```
- **What it tests**: Heredoc with line continuation `\` in body and an unterminated heredoc (delimiter starts with `MY\` but is incomplete).
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `test_heredoc_fixes.py::test_unterminated_heredoc` covers unterminated heredocs generally. Line continuation in heredoc body is NOT tested.
- **Recommendation**: **DELETE** -- the line continuation scenario is a bash rendering detail, not a security concern for the guardian's command splitting. Unterminated heredocs are already tested.

### 19. test_bash_syntax.sh (root)
```bash
# Testing bash arithmetic edge cases to ensure guardian logic aligns
echo foo$((1+1))
```
- **What it tests**: Arithmetic expansion `$((1+1))` inside echo -- tests that `$((...))` is not mistaken for heredoc or other construct.
- **File type**: Manual exploration snippet with comment (no assertions).
- **Overlap**: `test_heredoc_fixes.py::test_dollar_double_paren_not_affected` tests `echo $(( x << 2 ))`. Basic arithmetic expansion is implicitly tested in many places.
- **Recommendation**: **DELETE** -- trivial, covered by existing tests.

### 20. test_bash_sync.sh
```bash
cat <<- MYEOF
	hello
  MYEOF
```
- **What it tests**: `<<-` (tab-stripping heredoc) with tab-indented content and **space-indented** delimiter (which should NOT match with `<<-` since `<<-` only strips tabs).
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `test_heredoc_fixes.py::test_heredoc_tab_stripping` tests `<<-EOF` with tab-indented delimiter. But this file tests the FAILURE case: space-indented delimiter with `<<-`.
- **Recommendation**: **MOVE** -- the space-vs-tab indentation distinction for `<<-` is an important edge case. If guardian matches space-indented delimiter with `<<-`, it could incorrectly terminate the heredoc early, exposing hidden commands.

### 21. test_quote_concat.sh
```bash
cat << 'EOF'Z
echo "hidden"
EOFZ
echo "visible"
```
- **What it tests**: Quote concatenation in heredoc delimiter: `'EOF'Z` -- the final delimiter is `EOFZ` (quote removal + concatenation).
- **File type**: Manual exploration snippet (no assertions).
- **Overlap**: `test_heredoc_fixes.py::TestParseHeredocDelimiter::test_single_quoted` tests `'EOFZ'` but NOT the concatenation pattern `'EOF'Z`.
- **Recommendation**: **MOVE** -- quote concatenation in delimiter is a parsing edge case. Similar to #2 (`E"O"F`) but with trailing bare chars. Both should be added as test cases.

### 22. test_quote_concat_bg.sh
```bash
cat << 'EOF'Z
echo "hidden"
EOFZ
echo "visible"
```
- **What it tests**: Identical content to `test_quote_concat.sh`.
- **File type**: Duplicate of #21.
- **Overlap**: Same as #21.
- **Recommendation**: **DELETE** -- exact duplicate.

### 23. test_bypass.sh
```bash
#!/bin/bash
# << EOF
echo "THIS IS EXECUTED"
EOF
```
- **What it tests**: Comment containing `<< EOF` -- same scenario as #15, tests that `#` prevents heredoc detection.
- **File type**: Manual exploration snippet (has shebang but no assertions).
- **Overlap**: **Fully covered** by `tests/test_heredoc_fixes.py::TestCommentHeredocRegression::test_comment_heredoc_not_consumed`.
- **Recommendation**: **DELETE** -- exact scenario already tested.

---

## Files in tests/ (reference)

### tests/test_bash_behavior.sh
```bash
cat <<EOF ; echo "This is a command"
hello
EOF
```
- **What it tests**: Heredoc with command on same line after `;`.
- **File type**: Manual bash behavior reference.
- **Overlap**: Basic heredoc + semicolon parsing covered by `test_heredoc_fixes.py`.
- **Recommendation**: **DELETE** -- this is in tests/ but is a manual snippet, not an automated test. Its scenario is already covered.

### tests/test_bash_syntax.sh
```bash
#!/bin/bash
cat <<A ; cat <<B
hello A
A
hello B
B
```
- **What it tests**: Two heredocs separated by `;` on one line.
- **File type**: Manual bash behavior reference (has shebang).
- **Overlap**: Multiple heredocs scenario covered by `test_heredoc_fixes.py::test_multiple_heredocs_one_line`.
- **Recommendation**: **DELETE** -- manual snippet in tests/ with no assertions. Scenario already tested.

---

## Summary Table

| # | File | Category | Type | Overlap | Recommendation |
|---|------|----------|------|---------|----------------|
| 1 | test_script.sh | Arithmetic vs heredoc bypass | Exploration | Full | DELETE |
| 2 | test_heredoc_quote.sh | Quote concatenation delimiter | Exploration | Partial | **MOVE** |
| 3 | test_heredoc_bs.sh | Backslash-escaped delimiter | Exploration | None | **MOVE** |
| 4 | test_empty_delim.sh | Empty string delimiter | Exploration | Partial | **MOVE** |
| 5 | test_bs_space.sh | Backslash-space delimiter | Exploration | None | **MOVE** |
| 6 | test_multiple_heredocs.sh | Piped multiple heredocs | Exploration | Partial | **MOVE** |
| 7 | test_pipeline_heredoc.sh | Pipeline + heredoc interleave | Exploration | None | **MOVE** |
| 8 | test_pipeline_heredoc2.sh | Pipeline + heredoc (dup of 7) | Duplicate | Full | DELETE |
| 9 | test_pipeline_heredoc3.sh | Pipeline + heredoc (var of 7) | Duplicate | Full | DELETE |
| 10 | test_pipeline_cat.sh | Pipeline + heredoc + cat | Exploration | Related | DELETE |
| 11 | test_pipeline_cat2.sh | Pipeline + heredoc post-EOF | Exploration | Related | DELETE |
| 12 | test_proc_sub.sh | Process substitution + heredoc | Exploration | Partial | **MOVE** |
| 13 | test_unmatched_paren.sh | Paren in heredoc body | Exploration | Partial | **MOVE** |
| 14 | test_depth_bypass.sh | Depth corruption via heredoc | Exploration | None | **MOVE** |
| 15 | test_comment_bash.sh | Comment + heredoc | Exploration | Full | DELETE |
| 16 | test_depth_heredoc.sh | $() + heredoc + depth | Exploration | Partial | **MOVE** |
| 17 | test_bash_heredoc.sh | Basic heredoc | Exploration | Full | DELETE |
| 18 | test_bash_heredoc2.sh | Line continuation + unterminated | Exploration | Partial | DELETE |
| 19 | test_bash_syntax.sh (root) | Arithmetic expansion | Exploration | Full | DELETE |
| 20 | test_bash_sync.sh | <<- space vs tab indentation | Exploration | Partial | **MOVE** |
| 21 | test_quote_concat.sh | Quote concat delimiter | Exploration | Partial | **MOVE** |
| 22 | test_quote_concat_bg.sh | Quote concat (dup of 21) | Duplicate | Full | DELETE |
| 23 | test_bypass.sh | Comment + heredoc | Exploration | Full | DELETE |
| -- | tests/test_bash_behavior.sh | Heredoc + semicolon | Reference | Full | DELETE |
| -- | tests/test_bash_syntax.sh | Multiple heredocs | Reference | Full | DELETE |

---

## Aggregate Counts

- **DELETE**: 14 files (8 root duplicates/fully-covered + 3 trivial variations + 1 low-value + 2 in tests/)
- **MOVE**: 11 files (contain unique edge cases not covered by existing test suite)

## MOVE Target

All MOVE files should have their scenarios converted to Python assertions in `tests/test_heredoc_fixes.py` under the appropriate test class:

| MOVE File | Target Test Class | Edge Case |
|-----------|------------------|-----------|
| test_heredoc_quote.sh | TestParseHeredocDelimiter | Mixed quote concat: `E"O"F` |
| test_heredoc_bs.sh | TestParseHeredocDelimiter | Backslash-escaped: `\EOF` |
| test_empty_delim.sh | TestParseHeredocDelimiter | Empty string: `''` |
| test_bs_space.sh | TestParseHeredocDelimiter | Backslash-space: `\ ` |
| test_multiple_heredocs.sh | TestHeredocSplitting | Piped heredocs: `<<EOF \| <<EOF2` |
| test_pipeline_heredoc.sh | TestHeredocSplitting | Pipeline interleave: `<<EOF \|` on separate line |
| test_proc_sub.sh | TestHeredocSplitting (new) | `<()` with nested heredoc |
| test_unmatched_paren.sh | TestHeredocSplitting (new) | `)` in heredoc body inside `<()` |
| test_depth_bypass.sh | TestArithmeticBypassPrevention (new) | Depth corruption: `((((` in heredoc body |
| test_depth_heredoc.sh | TestHeredocSplitting | `$()` with `)` in heredoc body |
| test_bash_sync.sh | TestHeredocSplitting | `<<-` with space-indented delimiter |
| test_quote_concat.sh | TestParseHeredocDelimiter | Trailing bare chars: `'EOF'Z` |

## Security Relevance

Several of the MOVE files test security-relevant parsing edge cases:

1. **Depth corruption attacks** (#13, #14): If heredoc body chars `()` are not masked, they corrupt the depth counter, potentially hiding commands.
2. **Delimiter confusion attacks** (#2, #3, #4, #5, #21): Unusual delimiter quoting could cause the guardian to use wrong delimiter, failing to detect heredoc end properly.
3. **Pipeline interleaving** (#7): Commands after pipe in heredoc context could be misclassified as heredoc body.
4. **Nested context attacks** (#12, #16): Heredocs inside `<()` or `$()` with depth-confusing body content.

These should be converted to assertions with explicit security-bypass-prevention checks (assert that dangerous commands in these constructs are still detected).
