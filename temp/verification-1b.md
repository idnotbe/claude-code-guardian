# Security Verification Report: verify-1b

**Verifier**: Independent adversarial security reviewer (verify-1b)
**Date**: 2026-02-22
**Scope**: Three new test files covering previously untested edge cases
**Verdict**: **PASS** (with 1 new HIGH-severity finding documented below)

---

## 1. Test Execution Results

```
python3 -m pytest tests/core/test_decoder_glob.py \
  tests/core/test_tokenizer_edge_cases.py \
  tests/security/test_bypass_vectors_extended.py -v --tb=long
```

**Result: 168/168 tests PASSED in 0.21s**

Breakdown by file:
- `tests/core/test_decoder_glob.py`: 59 tests (decoder + glob + integration)
- `tests/core/test_tokenizer_edge_cases.py`: 55 tests (boundaries + depth + interactions + wrappers + scan)
- `tests/security/test_bypass_vectors_extended.py`: 54 tests (heredoc + pipeline + proc-sub + depth + tab-strip + scan + write + combined)

All tests execute cleanly with no warnings, no skips, and no xfails.

---

## 2. New Bypass Vector Attempts

### Vector 1: Runtime path construction via printf/base64 (SEVERITY: MEDIUM)

**Attack**: Construct protected file paths at runtime using `printf`, `base64`, or other encoding utilities inside `$()` command substitution.

```bash
# printf with octal escapes -- .env reconstructed at runtime
cat $(printf '\056\145\156\166')

# base64-encoded .env path
cat $(echo LmVudg== | base64 -d)
```

**Result**: NOT DETECTED by any layer.
- `_decode_ansi_c_strings()` only decodes `$'...'` syntax, not `printf` arguments
- Layer 1 raw string scan sees the encoded text, not `.env`
- Layer 3 path extraction cannot resolve `$()` at static analysis time

**Mitigation assessment**: This is an inherent limitation of static analysis. Runtime-constructed paths cannot be resolved without executing the command. The threat model for Claude Code (LLM generates commands) makes this a lower risk since the LLM is unlikely to spontaneously generate base64-encoded paths. Severity is MEDIUM because a crafted prompt injection could instruct the LLM to use this pattern.

### Vector 2: Heredoc body injection via source/bash/sh (SEVERITY: HIGH)

**Attack**: Feed destructive commands through heredoc body to `source`, `bash`, or `sh`, which execute the body as a script.

```bash
source /dev/stdin << EOF
rm -rf .git
EOF

bash << EOF
rm -rf /
EOF

python3 << EOF
import os; os.remove('.env')
EOF
```

**Result**: NOT DETECTED by any layer. This is a genuine bypass.
- `split_commands()` correctly consumes the heredoc body (by design)
- The heredoc body text is excluded from Layer 1 scanning (by design, to prevent false positives)
- The command part (`source /dev/stdin << EOF`) does not match any block/ask pattern
- `is_delete_command()` and `is_write_command()` do not detect `source`, `bash <<`, or `sh <<` as dangerous wrappers

**Why this matters**: The heredoc body exclusion from scanning is correct for data-oriented heredocs (e.g., `cat << EOF`). But when the heredoc feeds an interpreter (`bash <<`, `source /dev/stdin <<`, `python3 <<`), the body IS code that will be executed. The guardian currently makes no distinction.

**Recommended fix**: Add block/ask patterns for interpreter-heredoc combinations:
- `source /dev/stdin << `
- `bash << `, `sh << `, `zsh << `
- `python3 << `, `python << `, `perl << `, `ruby << `, `node << `

### Vector 3: Unbalanced quote in heredoc delimiter (SEVERITY: LOW)

**Attack**: Use an opening `"` without a closing `"` in the heredoc delimiter to confuse `_parse_heredoc_delimiter`.

```bash
cat << "EOF
hidden
EOF
rm -rf .git
```

**Result**: FAIL-CLOSED (safe).
- `_parse_heredoc_delimiter` reads from `"` until end-of-string looking for closing `"`
- The entire remaining input becomes part of the delimiter token
- The heredoc body can never match this giant delimiter
- Result: unterminated heredoc consumes everything, including `rm -rf .git`
- The `rm -rf .git` is NOT exposed as a separate sub-command

**Caveat**: While fail-closed at the tokenizer level, `is_delete_command()` also fails to detect `rm` inside the combined text because its regex `(?:^|[;&|({]\s*)rm\s+` does not match `rm` preceded by `\n`. This is a minor secondary gap (the command is already fail-closed at the tokenizer level, so it does not create an exploitable path).

---

## 3. Known Gap Verification

All GAP comments in the test files were verified against actual guardian behavior:

| GAP | Location | Claim | Verified |
|-----|----------|-------|----------|
| bash -c wrapper bypass | test_tokenizer_edge_cases.py:334 | `is_delete_command('bash -c "rm -rf .git"')` returns False | CONFIRMED |
| sh -c wrapper bypass | test_tokenizer_edge_cases.py:339 | `is_delete_command('sh -c "rm -rf /tmp"')` returns False | CONFIRMED |
| eval wrapper bypass | test_tokenizer_edge_cases.py:344 | `is_delete_command('eval "rm -rf .git"')` returns False | CONFIRMED |
| python open(w) truncation | test_v2_adversarial.py:481 | Not caught as delete | CONFIRMED |
| perl truncate | test_v2_adversarial.py:488 | Not caught | CONFIRMED |
| setfacl not detected | test_v2_adversarial.py:492 | Not caught as write | CONFIRMED |
| install command (I-2 tradeoff) | test_v2_adversarial.py:500 | Intentionally not detected | CONFIRMED |

**Assessment**: All GAP comments accurately document real gaps. Severity assessments in the comments are reasonable. No false claims were found.

---

## 4. Fail-Closed Behavior Analysis

Every test claiming fail-closed behavior was independently verified:

### Unterminated Heredoc Tests

| Test | Scenario | Expected | Actual | Status |
|------|----------|----------|--------|--------|
| `test_unterminated_heredoc_failclosed` | `cat <<NEVERENDS` with no terminator | 1 command, nothing leaks | 1 command, nothing leaks | PASS |
| `test_quote_concat_delimiter_unterminated_is_failclosed` | `E"O"F` with only `EOF` terminator | 1 command (unterminated) | 1 command | PASS |
| `test_quote_trailing_chars_failclosed` | `'EOF'Z` with only `EOFZ` terminator | 1 command (unterminated) | 1 command | PASS |
| `test_space_indented_with_trailing_cmd_consumed` | `<<-` with spaces not tabs | 1 command (unterminated) | 1 command | PASS |
| `test_mixed_tab_space_no_match` | `<<-` with tab+space on delimiter | 1 command (unterminated) | 1 command | PASS |

### Depth Corruption Tests

| Test | Scenario | Expected | Actual | Status |
|------|----------|----------|--------|--------|
| `test_multiple_parens_corrupt_depth` | `((((((((` in heredoc body in `<()` | 1 combined command, hidden text IS in combined text | Confirmed | PASS |
| `test_dollar_paren_heredoc_body_leaks` | `)` in heredoc body in `$()` | `rm -rf /` IS visible (safe direction) | `rm -rf /` visible | PASS |
| `test_depth_confusion_close_paren_in_heredoc` | `)` in heredoc body in `<()` | `echo hidden` IS visible (depth confusion) | Visible | PASS |

### Key Security Properties Verified

1. **Unterminated heredocs always consume remaining input** -- confirmed for all 5 unterminated scenarios. No dangerous commands leak as separate sub-commands.

2. **Depth corruption from heredoc bodies inside `<()`/`$()` either hides commands inside a combined blob (still scanned by Layer 1) or exposes them as separate commands (caught by per-sub-command analysis)**. Both directions are safe for security.

3. **Heredoc body content (semicolons, pipes, ampersands, newlines) is never treated as command separators** -- confirmed for all heredoc body containment tests.

---

## 5. Test Quality Assessment

### Strengths

- **Thorough boundary testing**: Empty strings, whitespace-only, lone separators, very long inputs, trailing/leading separators -- all covered.
- **Excellent documentation**: Every test has a docstring explaining expected behavior, divergence from bash, and security implications.
- **Defense-in-depth awareness**: Tests explicitly document which layer catches what, and what other layers serve as backup.
- **Honest gap documentation**: Tests that document gaps use `assertFalse` (not `assertTrue`) to pin current behavior, preventing accidental silent regression.

### Minor Observations

1. **test_decoder_glob.py:100-102**: The `test_octal_leading_zero_max_3_digits` test is particularly valuable -- it catches a subtle off-by-one in octal parsing that could affect security if the decoder ever changes.

2. **test_bypass_vectors_extended.py:109-114**: The `test_quote_trailing_both_terminators` test verifies a nuanced interaction (guardian terminates on EOF before EOFZ). This is correctly identified as safe but more restrictive than bash.

3. **No negative test for `_decode_ansi_c_strings` with malformed hex**: e.g., `$'\xGG'` (invalid hex). This is a very minor gap -- the decoder's `try/except ValueError` handles it, and the existing tests implicitly cover the happy path.

---

## 6. Summary

### Verdict: PASS

The three new test files are well-constructed, accurately document both working behavior and known gaps, and correctly verify fail-closed properties. All 168 tests pass.

### New Findings

| Finding | Severity | Exploitable? | Recommendation |
|---------|----------|-------------|----------------|
| `source/bash/sh << heredoc` body injection | HIGH | Yes -- bypasses all layers | Add block/ask patterns for interpreter+heredoc |
| `printf`/`base64` runtime path construction | MEDIUM | Requires prompt injection | Inherent static analysis limitation; document |
| `is_delete_command` regex misses `rm` after `\n` | LOW | Only in combined-command context (already fail-closed at tokenizer) | Consider adding `\n` to regex alternation |

### Recommendation

The test files should be merged. The Vector 2 finding (source/bash heredoc injection) should be filed as a separate security issue for remediation.
