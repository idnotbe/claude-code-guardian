# Phase 3 V2 Adversarial Test Results

**Date**: 2026-03-21
**Test script**: `temp/phase3_v2_adversarial_test.py`
**Results**: 45/46 PASS, 1 FAIL (regex bug found)

---

## Summary

| Category | Tests | Pass | Fail | Notes |
|----------|-------|------|------|-------|
| V1 Fix Validation | 7 | 7 | 0 | All V1 fixes working correctly |
| Accepted Limitations | 5 | 5 | 0 | Limitations confirmed and documented |
| Bypass Attempts | 10 | 9 | 1 | `python3.` regex false positive |
| Regex Edge Cases | 8 | 8 | 0 | Includes Unicode digit finding |
| Integration (subprocess) | 7 | 7 | 0 | Full pipeline confirms unit test results |
| Compound Commands | 3 | 3 | 0 | split_commands interaction correct |
| Adversarial Encodings | 6 | 6 | 0 | Tabs, spaces, paths all handled |

---

## BUG FOUND: `python3.` Matches Versioned Regex

**Severity**: Low (false positive, not false negative)
**Pattern**: `_VERSIONED_INTERPRETER_RE = r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)\d[\d.]*$'`

**Bug**: `python3.` (trailing dot, no version digit) matches the regex.

**Root cause**: `[\d.]*` allows dots at the end of the string. The regex matches `python3.` because:
- `python[23]?` matches `python` (skipping the optional `[23]?`)
- `\d` matches `3`
- `[\d.]*` matches `.`
- `$` matches end of string

**Impact**: Minor false positive. `python3.` is not a real command name, so this would only trigger
an unnecessary ASK prompt, never a false negative. Fail-closed behavior preserved.

**Recommended fix**: Change `\d[\d.]*` to `\d+(\.\d+)*` to enforce proper version format:
```python
_VERSIONED_INTERPRETER_RE = re.compile(
    r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)\d+(\.\d+)*$'
)
```

This rejects:
- `python3.` (trailing dot)
- `python3..10` (double dot)
- `python3.10.` (trailing dot after version)

While correctly matching:
- `python3.10`, `python3.10.2`, `bash5.1`, `ksh93`, `perl5.34.1`

---

## FINDING: Unicode Digit Bypass (Theoretical)

**Severity**: Negligible (theoretical only)

Python's `\d` in regex matches Unicode digits by default. This means `python3\u0661`
(Arabic-Indic digit 1) would match the versioned regex.

**Impact**: Negligible. Unicode digits in executable filenames are essentially non-existent
in practice. An attacker would need to somehow get a Unicode-named interpreter onto the
system, which requires far more access than a heredoc bypass would provide.

**Mitigation (optional)**: Add `re.ASCII` flag to restrict `\d` to `[0-9]`:
```python
_VERSIONED_INTERPRETER_RE = re.compile(
    r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)\d+(\.\d+)*$',
    re.ASCII
)
```

---

## Accepted Limitations (Confirmed)

### 1. `nice -n 5 bash << EOF` -- Phase 3 misses

**Confirmed**: `_extract_base_command('nice -n 5 bash')` returns `'-n'` because `nice` is
in `skip_prefixes` but has no flag-handling logic (unlike `sudo`). After skipping `nice`,
`-n` is treated as the command.

**Mitigation**: Phase 1's `_classify_heredoc_safety()` correctly returns `False` (unsafe /
retain body), so the heredoc body is NOT redacted. The body content remains visible for
pattern-based blocking.

**Note**: `nice bash << EOF` (without flags) DOES work correctly because `nice` is skipped
and `bash` is the next token. Only `nice` with short flags (`-n 5`) breaks.

### 2. Subshell grouping: `(python << EOF\nbody\nEOF)`

**Confirmed**: `_extract_base_command('(python')` returns `'(python'` (parenthesis included).
Not in frozenset, not matched by regex. Phase 3 misses this.

**Mitigation**: Same as above -- Phase 1 retains the body. Additionally, the full pipeline
returns `decision=None` (allow) for this case, which means the body content is visible for
pattern-based blocking in other checks.

### 3. Curly brace grouping: `{ python << EOF ... ; }`

**Confirmed**: `_extract_base_command('{ python')` returns `'{'`. Missed by Phase 3.

### 4. Backtick and $() substitution

**Confirmed**: Both `` `bash << EOF...` `` and `$(bash << EOF...)` return `False` from
`_is_interpreter_heredoc()`. These are command substitution contexts that Phase 3 doesn't
parse into.

---

## V1 Fix Validation (All Pass)

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| `.` in `_INTERPRETER_COMMANDS` | present | present | PASS |
| `source` in `_INTERPRETER_COMMANDS` | present | present | PASS |
| `. /dev/stdin << EOF` | triggers | triggers | PASS |
| `. << EOF` | triggers | triggers | PASS |
| `python3.10 << EOF` | triggers | triggers | PASS |
| `/usr/bin/python3.12 << EOF` | triggers | triggers | PASS |
| `nodemon << EOF` | no trigger | no trigger | PASS |

---

## Bypass Attempt Results

| Attempt | Expected | Actual | Status |
|---------|----------|--------|--------|
| `python3. << EOF` | no trigger | **triggers** | **FAIL** (regex bug) |
| `python3.10.2 << EOF` | triggers | triggers | PASS |
| `python3a << EOF` | no trigger | no trigger | PASS |
| `bash5.1 << EOF` | triggers | triggers | PASS |
| `.. /dev/stdin << EOF` | no trigger | no trigger | PASS |
| `source << EOF` | triggers | triggers | PASS |
| `. << EOF` | triggers | triggers | PASS |
| `sh1 << EOF` | triggers (regex) | triggers | PASS |
| `ksh93 << EOF` | triggers | triggers | PASS |

---

## Regex Edge Case Results

| Input | Frozenset? | Regex? | Notes |
|-------|-----------|--------|-------|
| `python3` | YES | also matches | Frozenset checked first (efficient) |
| `python`, `bash`, `sh`, etc. | YES | no | Pure names rejected by regex (correct) |
| `python3.10` | no | YES | Standard versioned match |
| `python3.10.2` | no | YES | Micro version supported |
| `cat3`, `grep2`, `npm10` | no | no | Non-interpreters correctly rejected |
| `node20` | no | no | node not in regex prefix (intentional) |
| `csh6.24` | no | no | csh not in regex prefix (minor gap) |
| `python3\u0661` (Unicode) | no | YES | Unicode digit match (negligible risk) |

---

## Integration Test Results (Subprocess)

All 7 integration tests PASS. The full `bash_guardian.py` pipeline correctly:
- Returns `ask` for `. /dev/stdin << EOF`
- Returns `ask` for `python3.10 << EOF`
- Returns `ask` for `/usr/bin/python3.12 << EOF`
- Returns `ask` for `bash5.1 << EOF`
- Returns `ask` for `env python3.10 << EOF`
- Returns `ask` for `sudo python3.11 << EOF`
- Does NOT return interpreter-heredoc ask for `nodemon << EOF`

---

## Adversarial Encoding Results

| Encoding | Triggers? | Notes |
|----------|-----------|-------|
| Tab separator: `python3.10\t<< EOF` | YES | `shlex.split` handles tabs |
| Multi-space: `python3.10    <<    EOF` | YES | `shlex.split` handles whitespace |
| `<<-` variant: `python3.10 <<- EOF` | YES | `'<<' in sub_cmd` matches `<<-` |
| pyenv path: `~/.pyenv/.../python3.10` | YES | `Path.name` extracts basename |
| homebrew path: `/opt/homebrew/bin/python3.12` | YES | Absolute path handled |
| Relative path: `./python3.10` | YES | `Path.name` extracts basename |

---

## Recommended Actions

1. **Fix regex** (Low priority): Change `\d[\d.]*` to `\d+(\.\d+)*` in `_VERSIONED_INTERPRETER_RE`
   to reject trailing dots like `python3.`

2. **Optional**: Add `re.ASCII` flag to prevent Unicode digit matching (negligible risk)

3. **Document**: The `nice -n 5`, subshell `()`, and brace `{}` limitations are inherent to
   `_extract_base_command()`'s prefix-skipping design. They are mitigated by Phase 1 body
   retention. A future enhancement could add flag-skipping for `nice`, `ionice`, `chrt`, etc.

4. **Not needed**: The `csh`/`tcsh`/`fish` gap in the versioned regex is acceptable -- these
   shells don't commonly appear with versioned binary names.
