# impl-security: Extended Bypass Vectors & Heredoc Edge Cases

## File Created
`tests/security/test_bypass_vectors_extended.py` -- 50 tests across 8 test classes

## Test Classes & Coverage

| Class | Tests | Coverage Area |
|-------|-------|---------------|
| `TestHeredocDelimiterEdgeCases` | 7 | Quote concatenation (E"O"F), backslash-escaped, empty string (''), trailing chars ('EOF'Z), backslash-space delimiters |
| `TestPipelineHeredocInterleave` | 4 | Piped heredocs, body consumption after pipe, pipe chars in heredoc body |
| `TestProcessSubstitutionHeredoc` | 4 | Heredoc inside <(), dangerous body containment, depth confusion with ) in body |
| `TestDepthCorruptionAttacks` | 5 | Parenthesis depth corruption via (((( in body, $() heredoc body leaks, brace safety |
| `TestTabStripHeredoc` | 5 | <<- tab-strip matching, space-indented delimiter rejection, mixed indentation |
| `TestScanFalsePositives` | 7 | ??? globs, quoted .env detection, word boundary checks, safe command allowlist |
| `TestQuoteAwareWriteDetection` | 11 | Quoted redirect targets, _is_inside_quotes checks, extract_redirection_targets |
| `TestCombinedAttackVectors` | 8 | Heredoc + scan interaction, semicolons/pipes/& in body, unterminated failclosed |

## Security Findings Documented

### Known Limitations (documented with `NOTE:` comments in tests)

1. **Depth Corruption Attack** (`test_multiple_parens_corrupt_depth`): `(((((((` in heredoc body inside `<()` corrupts the depth counter from 1 to 9. The closing `)` only decrements to 8, absorbing subsequent commands into one combined command. **Mitigated** by Layer 1 raw string scan which still sees the hidden command text.

2. **$() Heredoc Body Leak** (`test_dollar_paren_heredoc_body_leaks`): Inside `$()` at depth=1, heredoc body consumption only happens at depth-0 newlines. `)` in heredoc body closes `$()` prematurely, leaking body lines as separate sub-commands. **Actually SAFE** for blocking: leaked commands (like `rm -rf /`) become visible to the guardian's per-command analysis.

3. **Quote Concatenation Divergence** (`test_quote_concat_delimiter_unterminated_is_failclosed`): Guardian treats `E"O"F` as literal delimiter (with quotes), while bash treats it as `EOF`. **SAFE**: Guardian is more restrictive -- if only `EOF` exists as terminator, the heredoc is unterminated and fails closed.

4. **'EOF'Z Trailing Chars** (`test_quote_trailing_chars_failclosed`): Guardian parses `'EOF'` and ignores trailing `Z`, using `EOF` as delimiter. Bash concatenates to `EOFZ`. **SAFE**: If only `EOFZ` exists, guardian's `EOF` never matches -> unterminated -> fail-closed.

### Confirmed Correct Behaviors

- Empty string delimiter `''` correctly terminates on empty line
- `<<-` correctly strips only tabs, not spaces (space-indented = unterminated = fail-closed)
- Unterminated heredocs always fail closed (consume all remaining input)
- Semicolons, pipes, and `&` in heredoc body do not cause command splitting
- `scan_protected_paths` does not false-positive on `???` globs or `environment` word
- Quoted redirect targets (> '/etc/passwd') are correctly detected as writes

## Test Results
```
50 passed in 0.06s
Full suite: 798 passed, 1 pre-existing error (unrelated test_bypass_v2.py fixture issue)
```
