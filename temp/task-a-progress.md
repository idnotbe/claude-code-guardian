# Task A Progress: Polish Deviations + Fix ln Tests

## Status: COMPLETE

## Changes Made

### Part 1: Deviation Polish

**Deviation 1 - Regex `[^|&;>]+` -- Test added**
- File: `tests/test_heredoc_fixes.py`
- Added `test_redirect_regex_negated_gt_prevents_overconsumption` with detailed docstring
- Added `test_redirect_regex_single_quoted_gt_then_real` for single-quote variant
- Analysis: Without `>` in negated class, `[^|&;]+` matches across the second `>` in `'echo "data > temp" > output.txt'`, consuming everything as one match. The first match starts inside quotes and gets skipped, but the real redirect is already consumed. With `>` in the negated class, each `>` starts a fresh match.

**Deviation 2 - Comment tracking -- Edge cases tested + false positive fixed**
- File: `tests/test_heredoc_fixes.py`
- Added `test_dollar_brace_hash_not_comment` (`${#}` -- argument count)
- Added `test_dollar_brace_hash_array_not_comment` (`${#array[@]}` -- array length)
- Added `test_comment_at_line_start` (standalone comment line)
- Updated `test_comment_text_in_sub_commands` to verify scan filtering
- Edge case analysis:
  - `${#}` -- correctly NOT treated as comment (depth tracking handles `${`)
  - `$#` -- correctly NOT a comment (`$` not in whitespace/separator set)
  - `echo foo#bar` -- correctly NOT a comment (# preceded by non-whitespace)

**Deviation 2 - Comment-text false positive fix**
- File: `hooks/scripts/bash_guardian.py:1140`
- Changed `scan_text = ' '.join(sub_commands)` to filter out comment-only sub-commands
- Comment-only sub-commands (lines starting with `#`) are now excluded from Layer 1 scan
- This prevents false positives like `# .env` triggering protected path alerts
- Safe because bash comments are inert and never execute

**Deviation 3 - Extra tests comprehensive**
- Existing TestCommentHeredocRegression tests already cover the core cases
- Added 4 new edge case tests as documented above

### Part 2: ln Test Fixes

**Failure 1: `tests/core/test_v2fixes.py::TestF2_LnWritePattern::test_ln_pattern_in_source`**
- Changed assertion from `\bln\s+` to `(?<![A-Za-z-])ln\s+` to match actual code pattern

**Failure 2: `tests/security/test_v2_adversarial.py::TestP1_4_MetadataBypass::test_ln_symlink_not_detected`**
- Renamed to `test_ln_symlink_detected`
- Flipped from `assertFalse` to `assertTrue`
- Updated docstring: `ln` is now detected via `(?<![A-Za-z-])ln\s+` pattern

**Failure 3: `tests/security/test_v2_adversarial.py::TestKnownGaps::test_ln_symlink_gap`**
- Renamed to `test_ln_symlink_detected`
- Flipped from `assertFalse` to `assertTrue`
- Updated docstring: no longer a gap

## Validation Results

- All 50 targeted tests pass
- All 630 core + security tests pass (1 pre-existing error in `test_bypass_v2.py` fixture)
- No regressions

## Files Modified

| File | Changes |
|------|---------|
| `hooks/scripts/bash_guardian.py` | Filter comment-only sub-commands from Layer 1 scan text |
| `tests/test_heredoc_fixes.py` | Added 6 new tests (deviation 1 + deviation 2/3 edge cases) |
| `tests/core/test_v2fixes.py` | Fixed ln pattern assertion |
| `tests/security/test_v2_adversarial.py` | Fixed 2 ln assertion tests |
