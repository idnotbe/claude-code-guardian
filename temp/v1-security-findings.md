# Security Verification: Heredoc Scanning Redesign (v1)

**Date**: 2026-03-21
**Reviewer**: Opus 4.6 (1M context)
**Plan reviewed**: `action-plans/heredoc-scanning-redesign.md`
**Technical reference**: `temp/draft-plan-technical.md`
**External reviewers**: Codex 5.2 (clink codereviewer), Gemini 3.1 Pro (clink codereviewer)
**Method**: Independent code tracing against `hooks/scripts/bash_guardian.py` + external multi-model review

---

## Phase 0: Bug Fixes

### Verdict: PASS

**0a. `_parse_heredoc_delimiter()` backslash + ANSI-C fix**

Confirmed bugs exist. Independently verified against current source (lines 443-473):

```
>>> _parse_heredoc_delimiter(r'\EOF test', 0)
('\\EOF', '\\EOF', 4)        # Bug: should be ('EOF', '\\EOF', 4)

>>> _parse_heredoc_delimiter("$'EOF' test", 0)
("$'EOF'", "$'EOF'", 6)     # Bug: should be ('EOF', "$'EOF'", 6)
```

Consequence verified: `cat << \EOF\nsafe content\nEOF\nrm -rf .git` produces `['cat << \\EOF']` only -- the `rm -rf .git` is silently consumed as heredoc body because the terminator `\EOF` never matches `EOF`.

The proposed fix (inserting ANSI-C handler before existing branch, stripping backslashes from bare words) is correct and minimal. Line references accurate (443-473).

**0b. `re.MULTILINE` audit**

Decision to defer until after Phase 1 is correct. Adding `re.MULTILINE` simultaneously with redaction compounds risk. No security concern.

**0c. Tests**

Proposed test cases cover the three delimiter forms. Adequate.

---

## Phase 1: Heredoc Body Redaction

### Verdict: FAIL -- 3 security issues found

### CRITICAL: F1-1. Separator-induced context loss (all separators, not just pipes)

**Severity**: CRITICAL (false negative -- dangerous body redacted)
**Found by**: Codex 5.2, independently confirmed by code tracing
**Source lines**: bash_guardian.py 341-387 (separator handling), 421-428 (newline/heredoc consumption)

**The problem**: The plan's `piped_heredocs` flag only tracks pipe (`|`) separators. But `split_commands()` splits on ALL separators (`;`, `&&`, `||`, `|`, `&`) BEFORE the newline handler consumes heredoc bodies. When `pending_heredocs` persists across ANY separator, the `cmd_before_heredoc` seen by the classifier belongs to the WRONG segment.

**Traced code path for `bash << EOF ; cat\nrm -rf .git\nEOF`**:
1. Parser accumulates `bash << EOF`, detects `<<` at line 400, adds `('EOF', False)` to `pending_heredocs`
2. `;` hit at line 341 (depth==0): emits `"bash << EOF"` as sub-command, resets `current=[]`
3. ` cat` accumulated in `current`
4. `\n` hit at line 421: emits `"cat"` as sub-command, then `pending_heredocs` is non-empty
5. Body consumed. `cmd_before_heredoc` = `"cat"` (NOT `"bash"`)
6. Classifier: `cat` is in `_PASSIVE_DATA_SINKS` -> SAFE -> body REDACTED
7. **Result**: `rm -rf .git` hidden from Layer 0/0b -- FALSE NEGATIVE

**Verified independently**:
```python
>>> split_commands('bash << EOF ; cat\nrm -rf .git\nEOF\necho after')
['bash << EOF', 'cat', 'echo after']
# 'rm -rf .git' consumed as body, context lost
```

Same issue affects `&&`, `||`, and `&` separators.

**Fix**: Store origin metadata per pending heredoc at parse time (the `cmd_before_heredoc` text must be captured when `<<` is parsed at line 415-417, NOT when the body is consumed at line 426). The `piped_heredocs` boolean is insufficient; it must be per-heredoc origin tracking.

### HIGH: F1-2. `tee` in `_PASSIVE_DATA_SINKS` creates false negative

**Severity**: HIGH (false negative -- body written to file)
**Found by**: Gemini 3.1 Pro, independently confirmed via bash execution

`tee` writes heredoc body content to files WITHOUT using any `>` redirect operator. Rule 2 (`_OUTPUT_REDIR_PATTERN`) does not catch it:

```bash
tee script.sh << EOF
rm -rf /
EOF
# tee writes "rm -rf /\n" to script.sh
```

Verified: `tee script.sh << EOF\necho PAYLOAD\nEOF` creates `script.sh` with content `echo PAYLOAD\n`.

Under the plan's classifier: `tee` is in `_PASSIVE_DATA_SINKS`, no `>` operator present -> Rule 4 fires -> SAFE -> body redacted -> Layer 0/0b never see `rm -rf /`.

Similarly, `sort -o file.txt << EOF` writes to files without `>`.

**Fix**: Remove `tee` from `_PASSIVE_DATA_SINKS`. Also remove `sort` or add argument scanning for `-o`. `tee` is fundamentally a file writer, not a passive data sink.

### MEDIUM: F1-3. `>&` redirect operator not matched by `_OUTPUT_REDIR_PATTERN`

**Severity**: MEDIUM (false negative for exotic redirect form)
**Found by**: Gemini 3.1 Pro, independently confirmed via regex testing

The proposed regex:
```python
r'(?:[0-9]*>{1,2}|[0-9]*>\||&>)\s*[^\s&|;)>]'
```

Does NOT match `cat >& script.sh` (bash redirect-both-stdout-and-stderr-to-file operator). Verified:
```python
>>> _OUTPUT_REDIR_PATTERN.search('cat >& script.sh')
None  # Should match
```

The `[^\s&|;)>]` lookahead excludes `&` after `>`, which is correct for fd duplication (`1>&2`) but incorrect for `>&` followed by a filename.

**Fix**: Add `>&` as a separate alternative with a negative lookahead for digit/dash (fd duplication targets):
```python
r'[0-9]*>&(?!\s*(?:[0-9]+|-)(?:[\s;&|)]|$))'
```

---

## Phase 2: F1 Interpreter Path Resolution

### Verdict: CONCERN -- 2 issues found

### CRITICAL: F2-1. Project boundary check uses `str.startswith()` instead of `Path.relative_to()`

**Severity**: CRITICAL (path escape)
**Found by**: Codex 5.2, independently confirmed via Python execution

The plan's `extract_paths_from_interpreter_payload()` at draft-plan-technical.md:847 uses:
```python
if not str(resolved).startswith(str(project_dir.resolve())):
    continue
```

This is vulnerable to path-prefix confusion:
```python
>>> project_dir = Path('/tmp/proj')
>>> evil = Path('/tmp/proj_evil/secret.txt')
>>> str(evil.resolve()).startswith(str(project_dir.resolve()))
True   # WRONG: /tmp/proj_evil is outside /tmp/proj
```

The existing codebase ALREADY uses the correct approach at lines 1008 and 1114:
```python
resolved.relative_to(resolved_project)  # Raises ValueError if not within
```

**Fix**: Replace all `startswith()` boundary checks with `resolved.relative_to(project_dir.resolve())` or call the existing `_is_within_project_or_would_be()` helper.

### MEDIUM: F2-2. F-string interpolation extracted as literal path

**Severity**: MEDIUM (theoretical bypass, requires specific conditions)
**Found by**: Gemini 3.1 Pro, independently confirmed via regex testing

The plan's regex extracts double-quoted content from f-strings:
```python
>>> payload = 'os.remove(f"{target}/.env")'
>>> re.findall(string_literal_regex, payload)
[('', '{target}/.env')]
```

The `f` prefix is outside the quotes, so the regex captures `{target}/.env`. This resolves to `project_dir/{target}/.env` (literal curly braces), which:
- Passes project-internal check (within project)
- Does NOT exist on disk (but `allow_nonexistent=True` for delete commands)
- Suppresses F1 ASK because paths list is non-empty

At runtime, `{target}` could resolve to anything. However, this requires:
1. An AI agent generating f-string code (common)
2. The variable resolving to a dangerous path (uncommon in the threat model)
3. The literal `{target}/.env` passing zeroAccess checks (it contains `.env`, so it would actually be caught)

**Fix**: Add post-extraction check rejecting literals containing interpolation markers:
```python
if any(c in literal for c in '{}$'):
    continue
```

---

## Phase 3: Interpreter+Heredoc Backstop

### Verdict: CONCERN -- 1 issue found

### HIGH: F3-1. Regex patterns miss common wrapper variants

**Severity**: HIGH (backstop gap -- defense-in-depth weakened)
**Found by**: Codex 5.2, independently confirmed via regex testing

Phase 3 patterns fail to match:

| Command | Expected | Actual |
|---------|----------|--------|
| `exec bash << EOF` | MATCH | MISS (exec not in prefix group) |
| `sudo -u root bash << EOF` | MATCH | MISS (-u root not matched) |
| `env -i bash << EOF` | MATCH | MISS (-i breaks pattern) |

The root cause: the prefix group `(?:env|command|builtin|sudo|nice|nohup)\s+` expects a single word followed by whitespace, but `sudo -u root` has intermediate flags and `env -i` has options.

**Fix**: Either:
1. Use `_extract_base_command()` (which already handles sudo flags and env options) instead of regex
2. Make the prefix group more permissive: `(?:(?:env|sudo|command|...)\s+(?:-\S+\s+)*)*`

Since Phase 3 is defense-in-depth (not the primary defense), this is HIGH not CRITICAL -- but the whole point of Phase 3 is catching what Phase 1 misses, so it should be robust.

---

## Cross-Phase Interaction Analysis

### Phase 1 + Phase 3 interaction

**Question**: Does `_is_interpreter_heredoc()` work correctly after Phase 1 redaction?

**Answer**: Yes. The function operates on sub-commands from `split_commands()`, which contain the heredoc operator text (e.g., `"bash << EOF"`) but NOT the body. Since `_is_interpreter_heredoc()` checks for `<<` in the sub-command string, and `split_commands()` preserves the operator text, this works correctly.

For `cat << EOF | bash`, the sub-commands are `["cat << EOF", "bash"]`. Phase 3 would NOT fire on `"bash"` (no `<<`). This case depends entirely on Phase 1's piped_heredocs flag -- which works for pipes but is the exact scenario where F1-1 (separator context loss) is not an issue since pipes ARE tracked.

### Phase 1 + Phase 2 interaction

No interaction -- Phase 2 operates on the original sub-commands in the per-sub-command loop, not on the redacted string.

---

## Line Number Verification

| Plan Reference | Claimed Line | Actual Line | Status |
|---------------|-------------|------------|--------|
| `_parse_heredoc_delimiter()` | 443-473 | 443-473 | CORRECT |
| `_consume_heredoc_bodies()` | 476-506 | 476-506 | CORRECT |
| `split_commands()` | 270-441 | ~100-441 (starts earlier) | INACCURATE (function starts at line ~97, not 270) |
| Pipe handler | 359 | 359 | CORRECT |
| Newline handler | 421 | 421 | CORRECT |
| `main()` Layer 0 | 1422-1437 | 1422-1437 | CORRECT |
| F1 safety net | 1474-1481 | 1474-1481 | CORRECT |
| Per-sub-command loop | 1461 | 1461 | CORRECT |
| `match_block_patterns()` | ~872 | 872 | CORRECT |

Note: `split_commands()` line 270 in the plan refers to the section of code starting at that line within the function, not the function definition. The function definition is at line 97. The plan's range 270-441 refers to the code within the parser loop, which is accurate for the relevant section.

---

## Summary

| Phase | Verdict | Issues |
|-------|---------|--------|
| Phase 0 | **PASS** | No security issues. Bug fixes correct and minimal. |
| Phase 1 | **FAIL** | F1-1 CRITICAL (separator context loss), F1-2 HIGH (tee in allowlist), F1-3 MEDIUM (>& regex gap) |
| Phase 2 | **CONCERN** | F2-1 CRITICAL (startswith path escape), F2-2 MEDIUM (f-string interpolation) |
| Phase 3 | **CONCERN** | F3-1 HIGH (regex misses wrapper variants) |

### Critical issues requiring fix before implementation:
1. **F1-1**: Store heredoc origin metadata at parse time, not at consumption time
2. **F2-1**: Use `Path.relative_to()` instead of `str.startswith()` for project boundary checks

### High issues requiring fix before implementation:
3. **F1-2**: Remove `tee` (and consider `sort`) from `_PASSIVE_DATA_SINKS`
4. **F3-1**: Use `_extract_base_command()` instead of regex for interpreter detection

### Medium issues (should fix, can ship with documentation):
5. **F1-3**: Add `>&` to `_OUTPUT_REDIR_PATTERN`
6. **F2-2**: Add interpolation marker rejection in literal extraction

### Architectural positives confirmed by all three reviewers:
- Single-parser design (no parsing differential) is correct
- Whole-command Layer 0/0b scanning preserves pipeline detection
- Fail-closed defaults throughout are correct
- `shlex.split()` ValueError path in `_extract_base_command()` correctly fails closed
- Deferred `re.MULTILINE` audit is the right sequencing decision
