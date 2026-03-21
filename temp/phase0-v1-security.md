# Phase 0 Security Verification Report

**Date**: 2026-03-21
**Verifier**: Claude Opus 4.6 (independent review)
**Scope**: `_parse_heredoc_delimiter()` changes in `bash_guardian.py` lines 443-507

---

## Verdict: FAIL

Phase 0 fixes the simple cases correctly (`\EOF` -> `EOF`, `\\EOF` -> `\EOF`, `$'EOF'` -> `EOF`) but introduces no protection against three confirmed bypass vectors that allow an attacker to **hide executable commands from the guardian** while bash still executes them.

---

## Issues Found

### CRITICAL-1: ANSI-C hex/octal escape sequences not decoded

**Location**: `bash_guardian.py:474-475`

The ANSI-C handler strips `$'` and `'` but does NOT interpret escape sequences. Bash expands `\xHH`, `\0NNN`, `\uHHHH`, `\n`, `\t`, etc. inside `$'...'`.

**Attack vector**:
```bash
cat << $'E\x4fF'
hello
EOF
rm -rf .git
```
- Bash decodes `\x4f` to `O`, delimiter = `EOF`, terminates on line 3, executes `rm -rf .git`
- Guardian stores delimiter as literal `E\x4fF`, never matches, treats heredoc as unterminated
- Guardian consumes `rm -rf .git` into body -> **command hidden from all scanning layers**

**Confirmed**: Layer 0 block patterns do NOT catch `rm -rf .git` after a newline (no `re.MULTILINE`), so this is a full bypass.

### CRITICAL-2: Backslash-escaped whitespace/metacharacters in bare-word delimiters

**Location**: `bash_guardian.py:492`

The bare-word token loop stops at whitespace and metacharacters BEFORE processing backslashes. But in bash, `\<space>` escapes the space, keeping it as part of the delimiter word.

**Attack vector**:
```bash
cat << E\ OF
hello
E OF
rm -rf .git
```
- Bash: delimiter = `E OF` (escaped space), terminates on `E OF`, executes `rm -rf .git`
- Guardian: stops tokenizing at space, delimiter = `E\`, `OF` is ignored
- Guardian never finds `E\` in body -> unterminated -> consumes everything -> **`rm -rf .git` hidden**

### HIGH-1: Inline quote concatenation not handled

**Location**: `bash_guardian.py:478` (quoted branch returns immediately without consuming trailing text)

Bash concatenates adjacent quoted/unquoted segments into one word: `E'O'F` -> `EOF`, `$'EO'F` -> `EOF`.

**Attack vector**:
```bash
cat << E'O'F
hello
EOF
rm -rf .git
```
- Bash: concatenates `E` + `O` + `F` = `EOF`, terminates on `EOF`, executes `rm -rf .git`
- Guardian: bare-word branch sees `E'O'F` as one token (quotes are inside bare word), delimiter = `E'O'F`
- Body line `EOF` doesn't match `E'O'F` -> unterminated -> **`rm -rf .git` hidden**

### HIGH-2: Escaped double-quotes inside double-quoted delimiters

**Location**: `bash_guardian.py:482`

The double-quote parsing loop does not handle `\"` escapes inside `"..."`. `cat << "EO\"F"` makes guardian yield `EO\` while bash yields `EO"F`.

### MEDIUM-1: ANSI-C $'E\nOF' with real newline

Guardian stores `E\nOF` (literal backslash-n). Bash decodes to a real newline, making a two-line delimiter that can never match line-by-line. Both guardian and bash treat this as unterminated -> **fail-closed, no bypass**. But the semantic mismatch means the guardian could terminate early if the body contains the literal string `E\nOF` (a false positive / body leak, not a bypass).

### NOTE: `$"..."` locale translation

Guardian treats `$"..."` identically to `$'...'`. In bash, `$"..."` performs locale-dependent translation (usually identity). The behavior is close enough for simple cases, but not formally correct.

---

## Trace Results

### Backslash processing (correct cases)

| Input | Guardian delim | Bash delim | Match? |
|-------|---------------|------------|--------|
| `\EOF` | `EOF` | `EOF` | YES |
| `\\EOF` | `\EOF` | `\EOF` | YES |
| `E\OF` | `EOF` | `EOF` | YES |
| `\END_MARKER` | `END_MARKER` | `END_MARKER` | YES |

### Backslash processing (incorrect cases)

| Input | Guardian delim | Bash delim | Match? | Risk |
|-------|---------------|------------|--------|------|
| `E\ OF` | `E\` | `E OF` | NO | BYPASS (hide) |
| `E\;OF` | `E\` | `E;OF` | NO | BYPASS (hide) |

### ANSI-C quoting (correct cases)

| Input | Guardian delim | Bash delim | Match? |
|-------|---------------|------------|--------|
| `$'EOF'` | `EOF` | `EOF` | YES |
| `$''` | `` (empty) | `` (empty) | YES |

### ANSI-C quoting (incorrect cases)

| Input | Guardian delim | Bash delim | Match? | Risk |
|-------|---------------|------------|--------|------|
| `$'E\x4fF'` | `E\x4fF` | `EOF` | NO | BYPASS (hide) |
| `$'E\nOF'` | `E\nOF` | `E<newline>OF` | NO | Fail-closed (no bypass) |
| `$'E\101F'` | `E\101F` | `EAF` | NO | BYPASS (hide) |

### Inline concatenation (all incorrect)

| Input | Guardian delim | Bash delim | Match? | Risk |
|-------|---------------|------------|--------|------|
| `E'O'F` | `E'O'F` | `EOF` | NO | BYPASS (hide) |
| `'EOF'Z` | `EOF` | `EOFZ` | NO | Fail-closed (existing known gap) |

---

## Cross-Model Review

### Gemini (gemini-3.1-pro-preview) via PAL clink

Identified three issues matching our findings:
1. **ANSI-C escape sequences not decoded** (Critical) - confirmed
2. **Escaped metacharacters in bare-word loop** (High) - confirmed
3. **Inline/escaped quote concatenation** (High) - confirmed

Gemini also noted the `$'E\x4fF'` hex-escape attack specifically.

### Codex (OpenAI o4-mini) via PAL clink

Identified the same three categories plus additional nuance:
1. **ANSI-C escape sequences** - confirmed, recommended fail-closed for `$'...'` with escape chars
2. **Backslash-escaped whitespace/metacharacters** - confirmed
3. **Shell-word concatenation** - confirmed, noted that existing test `test_quote_trailing_both_terminators` encodes buggy behavior

Both models agreed that unterminated-heredoc fail-closed behavior is correct and should be preserved.

---

## Test Coverage Assessment

The 20 new tests in `test_delimiter_parsing.py` cover the CORRECT simple cases well:
- Backslash stripping for bare words (5 tests)
- ANSI-C basic parsing (4 tests)
- Locale translation (2 tests)
- Existing form regression (5 tests)
- Body consumption security (4 tests)

**Missing test coverage for bypass vectors**:
- No test for `$'E\x4fF'` hex escape
- No test for `$'E\101F'` octal escape
- No test for `E\ OF` (escaped space in bare word)
- No test for `E'O'F` inline concatenation hiding commands
- No test for `"EO\"F"` escaped quotes inside double-quoted delimiter

The 2 updated tests in `test_bypass_vectors_extended.py` (lines 73-134) are consistent with the Phase 0 implementation but do not cover the bypass vectors above.

---

## re.MULTILINE Audit Assessment

The audit in `temp/phase0-multiline-audit.md` is **correct**:
- Accurately identifies 5 patterns using `$` and 2 using `^` that would be affected
- Correctly concludes that adding `re.MULTILINE` NOW would increase false positives
- Correctly defers to post-Phase-1 when heredoc body redaction will make it safe
- However, the audit does not note that the LACK of `re.MULTILINE` is what makes the bypass vectors above exploitable (Layer 0 doesn't catch `rm -rf .git` after a newline)

---

## Recommendations

### Immediate (before merging Phase 0)

1. **Bare-word tokenizer**: Move backslash processing INTO the token-scanning loop so `\<space>` and `\;` etc. are consumed as part of the token, not as terminators. This is a one-line fix in the `while` condition at line 492.

2. **ANSI-C fail-closed**: If the content between `$'` and `'` contains ANY backslash escape, treat the delimiter as unparseable and force fail-closed (deny or ask). This avoids needing a full ANSI-C decoder while preventing bypass.

3. **Double-quote escape handling**: Add `\"` escape awareness to the double-quote branch (line 482).

### Phase 1 (full fix)

4. **Full shell-word lexer**: Parse the entire heredoc word as a sequence of quoted/unquoted fragments, then concatenate after quote removal. This fixes inline concatenation (`E'O'F`).

5. **ANSI-C decoder**: Implement proper `$'...'` decoding for `\xHH`, `\0NNN`, `\n`, `\t`, `\\`, etc. If the decoded result contains newline/CR, force fail-closed.

6. **re.MULTILINE**: After Phase 1 body redaction ships, add `re.MULTILINE` to close the Layer 0 gap for newline-embedded dangerous commands.
