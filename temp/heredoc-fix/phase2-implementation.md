# Phase 2: Implementation Notes

## Summary

All 3 fixes implemented in `hooks/scripts/bash_guardian.py`. 31/31 new tests pass.
No regressions in existing test suite (627 passed, 3 pre-existing failures, 1 pre-existing error).

## What Was Changed

### Fix 2: Quote-aware is_write_command() (lines 650-671)

**Change**: Replaced flat pattern list with `(pattern, needs_quote_check)` tuples.
Patterns matching `>` now use `_is_inside_quotes()` to skip matches inside quoted strings.

**Key detail**: The original spec regex `r">\s*['\"]?[^|&;]+"` was too greedy --
the `[^|&;]+` consumed through `>` characters, causing `finditer` to merge multiple
`>` matches into one. Fixed by adding `>` to the exclusion set: `r">\s*['\"]?[^|&;>]+"`.
This ensures each `>` is found as a separate match, allowing the quote check to correctly
pass for the first (quoted) `>` and then detect the second (real) `>`.

**Lines modified**: 650-671 (is_write_command function body)

### Fix 1: Heredoc-aware split_commands() (lines 114-115, 231-279, 293-359)

**Status**: Already implemented prior to this session (found in working tree after git stash pop).

**What exists**:
- State variables `pending_heredocs` and `arithmetic_depth` at lines 114-115
- Arithmetic context tracking `((` / `))` at lines 231-246
- Heredoc detection `<<` / `<<-` (excluding `<<<`) at lines 248-268
- Updated newline handler with `_consume_heredoc_bodies()` call at lines 270-279
- Helper `_parse_heredoc_delimiter()` at lines 293-323
- Helper `_consume_heredoc_bodies()` at lines 326-359

### Fix 3: Layer reorder in main() (lines 1123-1137)

**Status**: Already implemented prior to this session.

**What exists**:
- Layer 2 (split_commands) moved before Layer 1 at line 1123-1124
- Layer 1 (scan_protected_paths) now scans `scan_text = ' '.join(sub_commands)` at lines 1130-1134
- Duplicate `sub_commands = split_commands(command)` removed from Layer 3+4 section

## Test Results

### New tests (tests/test_heredoc_fixes.py): 31/31 PASSED
- TestHeredocSplitting: 13 passed
- TestArithmeticBypassPrevention: 4 passed
- TestParseHeredocDelimiter: 4 passed
- TestWriteCommandQuoteAwareness: 8 passed
- TestScanProtectedPathsHeredocAware: 2 passed

### Existing tests (tests/core/ + tests/security/): 627 passed, 3 failed, 1 error
All failures are PRE-EXISTING (verified by running against git stash of original code):
- test_ln_pattern_in_source: checks for `\bln\s+` literal in source (was already `(?<\![A-Za-z-])ln\s+`)
- test_ln_symlink_not_detected: expects ln not detected as write (but it IS detected)
- test_ln_symlink_gap: same as above

### Compile check: PASSED
### test_bypass_v2.py standalone: No heredoc-related failures remain

## Edge Cases Verified

| Case | Result |
|------|--------|
| `cat <<EOF\nhello\nEOF` | 1 sub-command (PASS) |
| `cat << 'EOFZ'\ncontent\nEOFZ` | 1 sub-command (PASS) |
| `cat > file << 'EOF'\nJSON\nEOF` | 1 sub-command (PASS) |
| `<<- with tab-indented delimiter` | 1 sub-command (PASS) |
| `<<<` here-string | Not treated as heredoc (PASS) |
| Multiple heredocs on one line | 1 sub-command (PASS) |
| Heredoc followed by command | 2 sub-commands (PASS) |
| Unterminated heredoc | 1 sub-command, fail-closed (PASS) |
| `(( x << 2 ))` arithmetic | NOT heredoc, command visible (PASS) |
| `$(( x << 2 ))` dollar arithmetic | NOT heredoc (PASS) |
| `let val<<1` | IS heredoc (bash behavior) (PASS) |
| `cat<<EOF` no space | IS heredoc (PASS) |
| `.env` in heredoc body | Excluded from sub-commands (PASS) |
| `echo "B->A->C"` quoted arrow | NOT a write (PASS) |
| `echo "a > b" > file` mixed | IS a write (PASS) |
