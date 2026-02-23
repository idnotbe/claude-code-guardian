# impl-tokenizer: Tokenizer Edge Case Tests - Result

## File Created

`tests/core/test_tokenizer_edge_cases.py` -- **60 tests, all passing**

## Test Classes and Coverage

### 1. TestTokenizerBoundaries (16 tests)
Covers `split_commands()` with edge case inputs that had zero prior coverage:
- Empty string, whitespace-only, tab-only, newline-only
- Lone operators: `;`, `&`, `|`, `&&`, `||`
- Multiple semicolons `;;;`
- Very long input (10K+ chars) -- confirms no crash/hang
- Very long input with 100 separators -- confirms correct split count
- Trailing/leading semicolons -- confirms no empty elements
- Trailing backslash -- confirms no crash at string boundary

### 2. TestNestedConstructDepth (14 tests)
Covers nested construct depth tracking (CRITICAL gap):
- `${VAR:-$(echo;echo)}` -- semicolon inside `$()` inside `${}` stays as 1 command
- `${arr[$((i+1))]}` -- arithmetic inside parameter expansion
- `${A:-${B:-default}}` -- nested `${}`
- **Depth desync attack**: `echo ${x:-$(echo })}; rm .env` -- correctly splits into 2 commands. The `}` inside `$()` has depth > 0 so it doesn't close `${}`. Security-positive: `rm .env` is exposed for scanning.
- Brace groups `{ ...; }`, subshells `(...)`, `$(...)`, backticks, `[[ || ]]`, `(( | ))`, extglob `+(a|b)`, process substitution `<(...)`, double-quoted `$()` -- all confirmed to suppress internal splitting.

### 3. TestFeatureInteractions (14 tests)
Complex interactions between tokenizer features:
- Brace group with `${VAR:-default}` inside
- Extglob inside `[[ ]]` conditional
- Heredoc followed by command, heredoc followed by brace group
- Heredoc inside `$()` with nested `${VAR:-$(...)}`
- Backslash-escaped semicolons
- Quoted semicolons (single and double)
- Pipe + semicolon multi-split
- Background `&` as separator
- `2>&1` and `&>` NOT treated as separators

### 4. TestWrapperBypass (14 tests)
Tests `is_delete_command` with shell wrapper patterns (CRITICAL gap):
- **CONFIRMED GAPS** (documented with `assertFalse` + comments):
  - `bash -c "rm -rf .git"` -- NOT detected (regex requires `^|[;&|({]` before `rm`)
  - `sh -c "rm -rf /tmp"` -- NOT detected (same reason)
  - `eval "rm -rf .git"` -- NOT detected (eval not tracked)
- Baseline sanity: direct `rm`, `rm` after `;|&`, `rm` inside `{}`/`()`, `git rm`, `rmdir`, truncation redirect, python `os.remove`
- `is_write_command` basic sanity checks

### 5. TestScanProtectedPathsEdgeCases (4 tests)
- `.env` detected, `./.env` detected (I-4 fix), clean command allowed, disabled scan allowed

## Security Gaps Documented

| Gap | Severity | Test |
|-----|----------|------|
| `bash -c "rm -rf ..."` not detected by `is_delete_command` | HIGH | `test_bash_c_rm_rf` |
| `sh -c "rm -rf ..."` not detected | HIGH | `test_sh_c_rm_rf` |
| `eval "rm -rf ..."` not detected | HIGH | `test_eval_rm_rf` |

These are documented as `assertFalse` with `# GAP:` comments so they serve as regression markers -- when the gap is fixed, the test will fail and need updating to `assertTrue`.

## Pre-existing Failures (NOT caused by this change)

10 failures in `test_decoder_glob.py` and 1 error in `test_bypass_v2.py` are pre-existing and unrelated to tokenizer edge cases.
