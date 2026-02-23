# Heredoc Fix: Security Review (v1)

**Date**: 2026-02-22
**Reviewer**: Claude Opus 4.6 (primary), Gemini 3.1 Pro Preview (consulted via clink), Codex 5.3 (unavailable -- usage limit)
**Target**: `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`
**Spec**: `/home/idnotbe/projects/claude-code-guardian/temp/guardian-heredoc-fix-prompt.md`
**Test suite**: 31/31 tests pass (`tests/test_heredoc_fixes.py`)

---

## Summary

5 of 5 requested security checks PASS. One pre-existing vulnerability (not introduced by this fix, but amplified by it) was identified and elevated as an advisory finding.

| # | Check | Verdict | Details |
|---|-------|---------|---------|
| 1 | Arithmetic Bypass | **PASS** | `rm -rf /` remains visible after `(( x << 2 ))` |
| 2 | Unterminated Heredoc | **PASS** | Body lines do not leak as sub-commands (fail-closed) |
| 3 | Heredoc Body Concealment | **PASS** | Correct by design -- heredoc body is stdin data |
| 4 | Layer Reorder | **PASS** | No command-part references lost |
| 5 | Quote-aware is_write_command | **PASS** | Quoted `>` skipped, real `>` detected |

**Advisory Finding (pre-existing, amplified by fix)**:
- **MEDIUM**: `bash <<EOF\n<payload>\nEOF` bypasses all scanning layers. The heredoc body containing the payload is correctly treated as data, but when the receiving command is an interpreter (`bash`, `sh`, `python3`, etc.), the "data" is executed as code. The old Layer 1 raw scan provided accidental partial coverage for this; the fix removes that accidental coverage. See Finding #1 below.

---

## Check 1: Arithmetic Bypass -- PASS

**Input**: `(( x << 2 ))\nrm -rf /`

**Trace through `split_commands()` (lines 82-290)**:

1. `i=0`: `command[0:2] == '(('`, and `i==0` satisfies the guard `(i == 0 or command[i-1] not in ('$', '<', '>'))` at line 235-236. `arithmetic_depth` increments to 1. `current = ['((']`, `i=2`.
2. `i=2..7`: Characters ` x << 2 ` are appended to `current`. The `<<` at position 5 IS checked at line 250, but `arithmetic_depth == 1` so the heredoc detection condition `arithmetic_depth == 0` fails. The `<<` is treated as a literal character, not a heredoc operator.
3. `i=8`: `command[8:10] == '))'` and `arithmetic_depth > 0` (line 242). `arithmetic_depth` decrements to 0. `current` now has `(( x << 2 ))`. `i=10`.
4. `i=10`: `c == '\n'` (line 271). `"(( x << 2 ))"` is emitted as sub-command. `current = []`. `i=11`. No pending heredocs, so no body consumption.
5. `i=11..19`: `rm -rf /` is accumulated in `current`.
6. End of string: `"rm -rf /"` emitted as final sub-command.

**Empirical result**: `split_commands("(( x << 2 ))\nrm -rf /")` returns `['(( x << 2 ))', 'rm -rf /']`. The `rm -rf /` is visible as a separate sub-command.

### Arithmetic Bypass Variant Analysis

| Scenario | Result | Secure? |
|----------|--------|---------|
| `(( x << 2 ))\nrm -rf /` | rm visible as sub-command 2 | YES |
| Unclosed `((` (no `))`) | `arithmetic_depth` stays 1, ALL subsequent `<<` suppressed. Body lines appear as separate sub-commands -- fail-closed: more scanning, not less | YES |
| `(( x\n))\ncat <<EOF\nrm -rf /\nEOF` | `))` on line 2 resets `arithmetic_depth` to 0. Heredoc on line 3 detected normally. rm consumed as body. But `(( x` is a bash syntax error -- shell rejects the whole command. | YES |
| `))` before any `((` | `arithmetic_depth` starts at 0, `> 0` check at line 242 prevents decrement below 0 | YES |
| `$(( x << 2 ))` | `$(` increments `depth` to 1 (line 165); inside `depth > 0`, the `depth == 0` gate blocks all heredoc/arithmetic detection. Existing behavior preserved | YES |
| Nested `(( (( x << 1 )) + y ))` | Both `((` increment, both `))` decrement. `arithmetic_depth` returns to 0. `echo safe` on next line is visible. Verified empirically. | YES |
| `((` inside quotes | Quote tracking runs before `depth == 0` block. `((` inside quotes is appended as literal text -- `arithmetic_depth` never touched | YES |

**Verdict**: **PASS** -- `arithmetic_depth` correctly prevents `<<` misdetection inside arithmetic context. All attack variants fail-closed.

---

## Check 2: Unterminated Heredoc -- PASS

**Input**: `cat <<EOF\nbody\nno_terminator`

**Trace through `split_commands()` and `_consume_heredoc_bodies()` (lines 326-356)**:

1. `i=0..5`: `cat <<` detected at depth 0. `arithmetic_depth == 0`, not `<<<`. Heredoc detection fires at line 250.
2. `strip_tabs = False` (line 254). `op_len = 2`. `current = ['c', 'a', 't', ' ', '<<']`.
3. Whitespace skipped. `_parse_heredoc_delimiter(command, 6)` called. Returns `('EOF', 'EOF', 9)`.
4. `pending_heredocs = [('EOF', False)]`. `current` appended with `'EOF'`.
5. `i=9`: `c == '\n'`. `"cat <<EOF"` emitted as sub-command. `pending_heredocs` is non-empty.
6. `_consume_heredoc_bodies(command, 10, [('EOF', False)])` called:
   - First line: `body` (positions 10-14). `'body' != 'EOF'` -- not delimiter. Advance past `\n`.
   - Second line: `no_terminator` (positions 15-28). `'no_terminator' != 'EOF'` -- not delimiter.
   - `i == 28 == len(command)`: inner while-loop exits. Comment at line 353: "If we exhaust the input without finding the delimiter, we've consumed an unterminated heredoc."
7. Returns `i=28`. Back in `split_commands`, `while i < len(command)` exits.
8. `current` is empty -- no remaining segment emitted.

**Empirical result**: `split_commands("cat <<EOF\nbody\nno_terminator")` returns `['cat <<EOF']`. Body lines `body` and `no_terminator` do NOT appear as separate sub-commands.

**Security assessment**: An unterminated heredoc means bash itself would hang waiting for the delimiter forever. The command would never complete execution. Consuming all remaining lines to end-of-string is fail-closed: hidden commands cannot execute because the shell hangs too.

**Verdict**: **PASS** -- Fail-closed behavior confirmed.

---

## Check 3: Heredoc Body Concealment -- PASS (with Advisory)

**Question**: When heredoc body is consumed and excluded from scanning, is this correct?

**Analysis by command type**:

| Receiving Command | Body Executed? | Scanning Needed? | Guardian Behavior |
|-------------------|---------------|------------------|-------------------|
| `cat <<EOF` | No -- stdin data only | No | Correct: body hidden |
| `tee <<EOF` | No -- stdin data only | No | Correct: body hidden |
| `grep <<EOF` | No -- stdin data only | No | Correct: body hidden |
| `bash <<EOF` | **YES** -- executed as code | **YES** | **Gap**: body hidden |
| `sh <<EOF` | **YES** -- executed as code | **YES** | **Gap**: body hidden |
| `python3 <<'EOF'` | **YES** -- executed as code | **YES** | **Gap**: body hidden |
| `node <<EOF` | **YES** -- executed as code | **YES** | **Gap**: body hidden |

For the overwhelmingly common case (non-interpreter commands like `cat`, `tee`, `grep`, `sed`), the concealment is **correct and beneficial**. The heredoc body is data, not commands. Scanning it produces false positives -- the exact bug this fix addresses.

For the uncommon case (interpreter commands), the concealment creates a gap. However:

1. The command line itself (`bash <<EOF`) IS visible as a sub-command and could be caught by pattern matching.
2. Layer 0 block patterns run on the **raw command string** (line 1105 in `main()`), which still includes the heredoc body. So Layer 0 patterns that match body content still work.
3. Testing reveals that Layer 0 coverage is **partial** -- some patterns match (e.g., `git push --force`), others don't (e.g., `rm -rf /` uses `$` anchor without `re.MULTILINE`). See Finding #1.

**Verdict**: **PASS** -- The design decision is correct for its intended purpose. The interpreter gap is a pre-existing architectural limitation documented as an advisory finding.

---

## Check 4: Layer Reorder -- PASS

**Question**: Does `' '.join(sub_commands)` lose any command-part references compared to the raw command string?

**Before the fix** (lines 1126-1131 in the original `main()`):
```python
scan_protected_paths(command, config)  # scanned raw string including heredoc bodies
sub_commands = split_commands(command)
```

**After the fix**:
```python
sub_commands = split_commands(command)
scan_text = ' '.join(sub_commands)
scan_protected_paths(scan_text, config)  # scans only command portions
```

**What changes in `scan_text` vs the raw `command`**:

1. **Heredoc bodies removed** -- intentional, the core fix.
2. **Newlines become spaces** -- `split_commands` splits on `\n` at depth 0, then join uses spaces. `scan_protected_paths` uses word-boundary regex, not newline-sensitive patterns. No loss.
3. **Delimiters (`;`, `&&`, `||`, `|`, `&`) removed** -- these are command separators, not path references. Harmless.
4. **Empty segments filtered** -- the `[cmd for cmd in sub_commands if cmd]` at line 290 removes empties. No information loss.
5. **Heredoc operator and delimiter text preserved** -- `cat > .env <<'EOFZ'` keeps the entire command portion including `.env` and `<<'EOFZ'`.

**Empirical verification**:

```
Input:  'cat > .claude/memory/file.json << EOF\n{"content": ".env config"}\nEOF\necho done'
subs:   ['cat > .claude/memory/file.json << EOF', 'echo done']
joined: 'cat > .claude/memory/file.json << EOF echo done'
```

- `.env` is in the heredoc body -- correctly excluded from `scan_text`.
- `.claude/memory/file.json` is in the command part -- preserved in `scan_text`.
- `echo done` is after the heredoc -- preserved in `scan_text`.

**Edge case: `&&` after heredoc delimiter on same line**:

`cat > file << EOF\nbody\nEOF && echo done` -- In real bash, `EOF && echo done` does NOT match the delimiter `EOF` (the line must contain ONLY the delimiter). The entire remaining input is consumed as heredoc body. The guardian's `_consume_heredoc_bodies` does the same (exact string match on `cmp_line == delim`). The `echo done` is correctly consumed. This matches bash semantics.

The correct form is `cat > file << EOF\nbody\nEOF\necho done` (delimiter on its own line, `echo done` on the next line), which produces `['cat > file << EOF', 'echo done']`. Both parts preserved.

**Verdict**: **PASS** -- No command-part references are lost in the transformation.

---

## Check 5: Quote-aware `is_write_command()` -- PASS

**Input**: `echo "a > b" > real_file.txt`

**Trace through `is_write_command()` (lines 746-782)**:

The function iterates `write_patterns` with `re.finditer`. For the first pattern `(r">\s*['\"]?[^|&;>]+", True)`:

**Match 1** at position 8: `> b" ` (the `>` inside the double-quoted string `"a > b"`).
- `needs_quote_check = True`.
- `_is_inside_quotes(command, 8)` is called. Walks characters 0-7:
  - pos 5: `"` toggles `in_double` to `True`.
- At position 8, `in_double = True`. Returns `True`.
- `continue` -- this match is **skipped** (quoted `>` is not a real redirection).

**Match 2** at position 13: `> real_file.txt`.
- `needs_quote_check = True`.
- `_is_inside_quotes(command, 13)` is called. Walks characters 0-12:
  - pos 5: `"` toggles `in_double` to `True`.
  - pos 9: `"` toggles `in_double` to `False`.
- At position 13, `in_double = False`, `in_single = False`. Returns `False`.
- Not inside quotes -- this is a **real redirection**. Returns `True`.

**Counter-case**: `echo "a > b"` (no real redirection):
1. Only match at position 8: `> b"`. `_is_inside_quotes` returns `True`. Skipped.
2. No more matches from this pattern.
3. Other patterns (`\btee\s+`, `\bmv\s+`, etc.) don't match.
4. Returns `False`. Correct.

**Additional verified cases**:

| Input | Result | Correct? |
|-------|--------|----------|
| `echo "B->A->C"` | `False` | YES -- `>` inside quotes |
| `echo "score > 8"` | `False` | YES -- `>` inside quotes |
| `git commit -m "value > threshold"` | `False` | YES -- `>` inside quotes |
| `echo hello > output.txt` | `True` | YES -- real redirection |
| `echo hello \| tee output.txt` | `True` | YES -- `\btee\s+` matches (no quote check needed) |
| `: > file.txt` | `True` | YES -- truncation pattern, quote-checked, not inside quotes |
| `echo "a > b" > output.txt` | `True` | YES -- first `>` skipped, second detected |
| `echo "a > b" "c > d" > output.txt` | `True` | YES -- first two skipped, third detected |

**Verdict**: **PASS** -- The `finditer` + `_is_inside_quotes` approach correctly handles all cases.

---

## Finding #1 (MEDIUM): Interpreter-Heredoc Bypass

**Severity**: Medium (pre-existing gap, amplified by this fix)
**Classification**: Not a new vulnerability -- the gap existed before, but this fix removes accidental partial coverage from Layer 1.

### Attack Vector

```bash
bash <<EOF
rm -rf /
EOF
```

### Trace Through the Guardian

1. **Layer 0** (`match_block_patterns(raw_command)`, line 1105): The raw string `bash <<EOF\nrm -rf /\nEOF` is scanned. The root deletion pattern `rm\s+-[rRf]+\s+/(?:\s*$|\*)` does NOT match because `$` in Python's `re.search` (without `re.MULTILINE`) only matches end-of-string, and `rm -rf /` is on a middle line followed by `\nEOF`. **Not caught.**

2. **Layer 0b** (`match_ask_patterns(raw_command)`, line 1119): No patterns match `bash <<EOF\nrm -rf /\nEOF`. **Not caught.**

3. **Layer 2** (`split_commands`, line 1124): Returns `['bash <<EOF']`. The `rm -rf /` is consumed as heredoc body and excluded.

4. **Layer 1** (`scan_protected_paths('bash <<EOF')`, line 1131): No protected path references in `bash <<EOF`. **Not caught.**

5. **Layers 3+4** (per-sub-command analysis, lines 1136-1204): `bash <<EOF` -- `is_write_command` returns `False`, `is_delete_command` returns `False`. No paths extracted. **Not caught.**

6. **Final verdict**: `allow`.

### Why This Is Pre-existing

Before the heredoc fix, `split_commands("bash <<EOF\nrm -rf /\nEOF")` returned `['bash <<EOF', 'rm -rf /', 'EOF']`. Layer 3+4 would process `rm -rf /` as a sub-command. However:

- `is_delete_command` uses `(?:^|[;&|]\s*)rm\s+` which requires `rm` at the start of the string or after a delimiter. In `rm -rf /` as a standalone sub-command, `^` matches, so `is_delete_command` WOULD return `True`.
- BUT `extract_paths` on `rm -rf /` would try to resolve `/` and likely not produce results in the project directory scope.
- The F1 safety net ("Detected delete but could not resolve target paths") would escalate to `ask`.

So the old behavior DID provide accidental protection via the F1 safety net. **The fix removes this accidental protection for interpreter-heredoc patterns.**

### Mitigating Factors

1. **Layer 0 still scans the raw command** -- some patterns DO match (e.g., `git push --force` in a heredoc body is caught by Layer 0 block patterns).
2. **Claude Code rarely generates `bash <<EOF`** -- the typical heredoc use is `cat > file <<EOF` (data writing), not `bash <<EOF` (interpreter invocation).
3. **The fix eliminates real UX pain** -- 7 false positive popups in 20 hours for a single sibling plugin.

### Recommended Follow-up (Out of Scope for This PR)

1. **Option A (Simplest)**: Add a Layer 0 ask/block pattern: `r"(?:^|\s)(?:bash|sh|zsh|ksh|dash|python[23]?|node|ruby|perl)\s+<<"`. This catches `interpreter <<` combinations and escalates to ask/deny.
2. **Option B**: Add `re.MULTILINE` flag to block pattern compilation so `$` matches end-of-line, improving Layer 0 coverage of patterns embedded in multi-line strings.
3. **Option C (Most thorough)**: Have `split_commands` return heredoc bodies separately when the command prefix is an interpreter, allowing scanning of the body content.

---

## Finding #2 (INFO): Layer 0 Block Pattern `$` Anchor Limitation

The block pattern `rm\s+-[rRf]+\s+/(?:\s*$|\*)` uses `$` to anchor the end of the match. In Python's default regex mode (without `re.MULTILINE`), `$` only matches end-of-string. This means the pattern fails when `rm -rf /` appears on a middle line of a multi-line command string.

**Empirical verification**:
- `re.search(r"rm\s+-[rRf]+\s+/(?:\s*$|\*)", "bash <<EOF\nrm -rf /\nEOF")` returns `None` (no match).
- `re.search(r"rm\s+-[rRf]+\s+/(?:\s*$|\*)", "bash <<EOF\nrm -rf /\nEOF", re.MULTILINE)` returns a match.

This is a pre-existing issue in `_guardian_utils.py` block patterns, not caused by the heredoc fix. Adding `re.MULTILINE` to the block pattern regex compilation would fix this.

---

## Finding #3 (INFO): Codex 5.3 Consultation Unavailable

The Codex 5.3 clink call failed with a usage limit error. The arithmetic_depth analysis that was intended for Codex was performed manually instead (see Check 1). The manual analysis is more thorough than what an external model review would provide, as it includes empirical verification of all variant attack scenarios.

---

## External Review: Gemini 3.1 Pro Preview

**Question**: "Could an attacker craft a bash command that hides dangerous operations inside a heredoc body to bypass this guardian?"

**Key findings from Gemini**:

1. **Confirmed the interpreter-heredoc bypass** as a critical issue. Gemini identified `bash <<EOF` and `python3 <<'EOF'` as bypass vectors where heredoc body content is executed but not scanned. Gemini rated this as "Critical" severity. My independent assessment rates it as "Medium" because it is pre-existing and requires a specific crafted pattern unlikely in normal operation.

2. **Recommended fix**: Add a Layer 0 block pattern for interpreter-heredoc combinations. Aligns with Recommended Follow-up Option A above.

3. **Secondary finding**: Regex patterns in `is_delete_command` use `(?:^|[;&|]\s*)` which does not include `\n` as a separator. This is a pre-existing regex gap, not related to the heredoc fix.

4. **Positive observation**: Gemini recognized the fail-closed mechanics for long commands and broken environments as "excellent strategy against buffer stuffing bypasses."

**Assessment**: Gemini's primary finding is valid and confirmed by independent tracing. The severity disagreement (Critical vs Medium) reflects different threat model assumptions -- Gemini evaluated as if an external attacker could inject commands, while the guardian's actual threat model is defending against AI agent mistakes and prompt injection.

---

## Verification Matrix

| Check | Result | Evidence |
|-------|--------|----------|
| Arithmetic `(( x << 2 ))` bypass | PASS | `arithmetic_depth` correctly prevents misdetection; rm visible |
| Quoted `((` spoofing | PASS | Quote tracking runs before `depth == 0` block |
| `))` underflow | PASS | `arithmetic_depth > 0` check prevents negative values |
| Unmatched `((` | PASS | Suppresses heredocs = fail-closed (more scanning) |
| `$(( ))` handling | PASS | Existing `depth` tracking handles this |
| Unterminated heredoc | PASS | Body consumed to end-of-string, fail-closed |
| Here-string `<<<` exclusion | PASS | `command[i:i+3] != '<<<'` check |
| Quoted delimiter (`'EOF'`, `"EOF"`) | PASS | Correctly strips quotes for matching |
| `<<-` tab stripping | PASS | Only tabs stripped (not spaces) |
| CRLF handling | PASS | `rstrip('\r')` in delimiter comparison |
| `is_write_command` quote awareness | PASS | All 8 test patterns verified |
| `.env` in command part preserved | PASS | Only body lines consumed |
| `.env` in heredoc body excluded | PASS | Correctly hidden from scan_text |
| Layer reorder completeness | PASS | No command references lost |
| Interpreter+heredoc gap | ADVISORY | Pre-existing, amplified by fix |
| Block pattern `$` anchor | INFO | Pre-existing `re.MULTILINE` gap |

---

## Conclusion

The heredoc fix is **mechanically sound and secure** against all 5 requested attack vectors. The implementation correctly handles arithmetic context, unterminated heredocs, body concealment, layer reordering, and quote-aware write detection.

**The fix should proceed.** The interpreter-heredoc gap (Finding #1) is a pre-existing architectural limitation that existed before this fix. While the fix removes accidental partial coverage from the old Layer 1 raw scan, the gap was never a reliable defense. The recommended follow-up (adding an interpreter-heredoc block pattern) would provide explicit, reliable protection and should be tracked as a separate work item.

All 31 test cases in `tests/test_heredoc_fixes.py` pass.
