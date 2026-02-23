# Phase 1: Test File Creation (TDD Baseline)

## File Created

`tests/test_heredoc_fixes.py` -- 31 tests across 6 test classes

## Test Classes and Coverage

### TestHeredocSplitting (13 tests)
Tests for Fix 1: heredoc-aware `split_commands()`.

| Test | What It Covers |
|------|---------------|
| `test_basic_heredoc_not_split` | `cat <<EOF\nhello\nEOF` -> 1 sub-command |
| `test_quoted_heredoc_not_split` | `cat << 'EOFZ'\ncontent\nEOFZ` -> 1 sub-command |
| `test_heredoc_with_redirection` | `cat > file << 'EOF'\n{...}\nEOF` -> 1 sub-command |
| `test_heredoc_tab_stripping` | `<<-` with tab-indented delimiter |
| `test_here_string_not_heredoc` | `<<<` excluded (not heredoc) |
| `test_multiple_heredocs_one_line` | `cmd <<A <<'B'` queued processing |
| `test_heredoc_followed_by_command` | `cat <<EOF\n...\nEOF\necho done` -> 2 sub-commands |
| `test_heredoc_with_arrows_in_body` | `->` in body doesn't trigger write detection on body |
| `test_heredoc_with_semicolon_in_body` | `;` in body doesn't cause splitting (was known limitation) |
| `test_heredoc_with_double_quoted_delimiter` | `<<"MARKER"` works |
| `test_unterminated_heredoc` | Body consumed to end (fail-closed) |
| `test_heredoc_inside_command_substitution` | `$()` depth tracking prevents detection |
| `test_real_memory_plugin_command` | Exact production command that caused 7 false positives |

### TestArithmeticBypassPrevention (4 tests)
CRITICAL SECURITY: Ensures `(( x << 2 ))` arithmetic shift is NOT misdetected as heredoc.

| Test | What It Covers |
|------|---------------|
| `test_arithmetic_shift_not_heredoc` | `(( x << 2 ))\nrm -rf /` -- rm must remain visible |
| `test_let_shift_is_heredoc` | `let val<<1` IS heredoc in bash (correct behavior) |
| `test_no_space_heredoc` | `cat<<EOF` (no space) detected as heredoc |
| `test_dollar_double_paren_not_affected` | `$(( x << 2 ))` handled by existing depth tracking |

### TestParseHeredocDelimiter (4 tests)
Tests for `_parse_heredoc_delimiter()` helper function.

| Test | What It Covers |
|------|---------------|
| `test_bare_word` | `EOF` -> delimiter "EOF" |
| `test_single_quoted` | `'EOFZ'` -> delimiter "EOFZ" |
| `test_double_quoted` | `"END"` -> delimiter "END" |
| `test_empty_at_eof` | Empty string -> empty delimiter |

### TestWriteCommandQuoteAwareness (8 tests)
Tests for Fix 2: quote-aware `is_write_command()`.

| Test | What It Covers |
|------|---------------|
| `test_arrow_in_double_quotes_not_write` | `echo "B->A->C"` NOT write |
| `test_score_comparison_in_quotes_not_write` | `echo "score > 8"` NOT write |
| `test_git_commit_message_with_gt` | `git commit -m "value > threshold"` NOT write |
| `test_real_redirection_still_detected` | `echo hello > output.txt` IS write |
| `test_tee_still_detected` | `echo hello | tee output.txt` IS write |
| `test_truncation_outside_quotes_detected` | `: > file.txt` IS write |
| `test_quoted_gt_then_real_redirect` | `echo "value > threshold" > output.txt` IS write |
| `test_multiple_quoted_gt_then_real_redirect` | Multiple quoted `>` then real redirect IS write |

### TestScanProtectedPathsHeredocAware (2 tests)
Tests for Fix 3: heredoc-aware protected path scanning via layer reorder.

| Test | What It Covers |
|------|---------------|
| `test_env_in_heredoc_body_not_flagged` | `.env` in heredoc body excluded from sub-commands |
| `test_env_in_command_still_present` | `.env` in actual command part still in sub-commands |

## TDD Baseline Results

```
21 failed, 10 passed (31 total)
```

### Passing Tests (10) -- Existing behavior already works:
- `test_here_string_not_heredoc` -- `<<<` already handled
- `test_heredoc_inside_command_substitution` -- `$()` depth tracking works
- `test_arithmetic_shift_not_heredoc` -- `(( ))` not currently misdetected
- `test_dollar_double_paren_not_affected` -- `$(( ))` depth tracking works
- `test_real_redirection_still_detected` -- Real `>` already detected
- `test_tee_still_detected` -- `tee` pattern works
- `test_truncation_outside_quotes_detected` -- `: >` pattern works
- `test_quoted_gt_then_real_redirect` -- Real redirect after quotes works
- `test_multiple_quoted_gt_then_real_redirect` -- Same as above
- `test_env_in_command_still_present` -- `.env` in command works

### Failing Tests (21) -- Need the 3 fixes:
- 11 TestHeredocSplitting tests (Fix 1: heredoc-aware split_commands)
- `test_let_shift_is_heredoc`, `test_no_space_heredoc` (Fix 1)
- All 4 TestParseHeredocDelimiter tests (Fix 1: new helper function)
- 3 TestWriteCommandQuoteAwareness quote-awareness tests (Fix 2)
- `test_env_in_heredoc_body_not_flagged` (Fix 3)

## Gemini Review Findings

Consulted gemini-3-pro-preview via pal clink (codereviewer role). Key findings:

### Noted Edge Cases (informational -- already handled or out of scope)
1. **Commands after delimiter on same line** (`cat <<EOF ; rm -rf /`): The existing `split_commands()` already handles `;` splitting before the newline handler, so the `rm -rf /` portion is already split as a separate sub-command. The heredoc body consumption only starts after the newline. Correctly handled by existing parser flow.
2. **Heredoc inside standard subshells `()`**: The existing `depth` tracking in `split_commands()` already increments on `(` and decrements on `)`, which prevents heredoc detection at depth > 0. Same mechanism as `$()`.
3. **Single quotes in is_write_command**: The `_is_inside_quotes()` function already handles both single and double quotes. The spec's Fix 2 uses this function, so single quotes are covered.
4. **Mixed quoting in delimiters** (`cat << "E"O'F'`): Exotic edge case. The parser handles the first quote style it encounters. Fails closed (consumes to end of string if delimiter not found). Explicitly out of scope.
5. **Protected path as delimiter**: The delimiter token remains in the sub-command string, so `scan_protected_paths()` still sees it. Not a gap.

### Conclusion
The test file as specified covers all the edge cases relevant to the three fixes. The Gemini review identified some theoretical edge cases that are either already handled by existing parser mechanics or explicitly out of scope for this fix.

## Linter Modifications
The file was auto-modified by a linter after creation:
- Escaped `!` characters in assertion messages (line 113: `bypass\!`, line 122: `\!=`)
- No functional changes to test logic

## Status: COMPLETE
