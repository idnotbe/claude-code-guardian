# V2 Adversarial Review: Heredoc Scanning Redesign (Post-V1 Fixes)

**Date**: 2026-03-21
**Reviewer**: Opus 4.6 (1M context) -- final adversarial pass
**External reviewer**: Gemini 3.1 Pro (via PAL clink codereviewer)
**Plan reviewed**: `action-plans/heredoc-scanning-redesign.md` (V1-fixed version)
**References**: `temp/v1-security-findings.md`, `temp/v1-completeness-findings.md`, `temp/draft-plan-technical.md`
**Method**: Independent code tracing, Python execution verification, cross-model adversarial review

---

## Overall Verdict: CONDITIONAL PASS

The plan is ready for implementation with 2 required fixes (1 new finding, 1 pseudocode alignment) and 1 documentation fix. All 6 V1 fixes are correctly incorporated in the plan prose. No CRITICAL issues remain.

---

## Section 1: V1 Fix Verification (6/6 incorporated)

### F1-1 (CRITICAL): Separator origin tracking -- INCORPORATED WITH CAVEAT

**Plan location**: Line 69 of `heredoc-scanning-redesign.md`
**Status**: Prose fix is correct. The plan clearly states: "Store heredoc origin metadata at `<<` parse time (line 415-417), NOT at body consumption time (line 426)."

**Caveat**: The technical reference pseudocode at `draft-plan-technical.md` lines 470-492 is STALE. It still shows `cmd_before_heredoc=cmd_text` evaluated at body consumption time (the newline handler). The pseudocode must be updated to store `origin_cmd` inside the `pending_heredocs` tuple at `<<` parse time as the prose describes. This was independently confirmed by Gemini.

**Impact of stale pseudocode**: If an implementer follows the pseudocode rather than the prose, F1-1 would not be fixed. The fix is: change `pending_heredocs` from `list[tuple[str, bool]]` to `list[tuple[str, bool, str]]` where the third element is `origin_cmd = "".join(current).strip()` captured at `<<` parse time.

### F1-2 (HIGH): tee removed from _PASSIVE_DATA_SINKS -- INCORPORATED WITH CAVEAT

**Plan location**: Line 79 of `heredoc-scanning-redesign.md`
**Status**: Correctly states `tee` REMOVED from `_PASSIVE_DATA_SINKS`.

**Caveat**: The technical reference pseudocode at `draft-plan-technical.md` line 304 still lists `tee` in the `_PASSIVE_DATA_SINKS` set. Must be removed to prevent implementation confusion. `sort` is also still present at line 305 despite the plan noting it should be excluded.

**False positive assessment**: With `tee` removed, `tee << EOF` (no file arg, stdout-only) falls to Rule 5 (unknown -> UNSAFE), retaining the body. This is a false positive (unnecessary body retention) but is the correct fail-closed behavior. Acceptable.

### F1-3 (MEDIUM): >& redirect operator added -- INCORPORATED

**Plan location**: Line 83 of `heredoc-scanning-redesign.md`
**Status**: Correctly adds `>&` with negative lookahead for digit/dash targets.

### F2-1 (CRITICAL): Path.relative_to() instead of str.startswith() -- INCORPORATED

**Plan location**: Line 128 of `heredoc-scanning-redesign.md`
**Status**: Correctly specifies `Path.relative_to()` and references existing codebase usage at lines 1008, 1114.

### F2-2 (MEDIUM): Interpolation filter for extracted literals -- INCORPORATED

**Plan location**: Line 129 of `heredoc-scanning-redesign.md`
**Status**: Correctly rejects literals containing `{}` and `$`.

### F3-1 (HIGH): Use _extract_base_command() for interpreter detection -- INCORPORATED

**Plan location**: Line 170 of `heredoc-scanning-redesign.md`
**Status**: Correctly specifies `_extract_base_command(sub_cmd) in _INTERPRETER_COMMANDS and '<<' in sub_cmd`.

---

## Section 2: Attacking the V1 Fixes

### F1-1 Attack: Dynamic origin commands

**Question**: What if the origin command itself is dynamic? E.g., `eval "cat << EOF"`

**Answer**: Safe. `eval` is in `_INTERPRETER_COMMANDS`. When `<<` is parsed inside `eval "cat << EOF"`, the `cmd_so_far` captured at that point includes `eval "cat`, and `_extract_base_command` extracts `eval` -> Rule 1 fires -> UNSAFE -> body retained. The deeper issue (eval parsing the inner string at runtime) is a pre-existing architectural limitation, not a regression.

### F1-2 Attack: tee false positive impact

**Question**: Does `tee << EOF` without a file argument (just stdout) create a problematic false positive?

**Answer**: No. `tee << EOF` with no file arg just echoes stdin to stdout -- the heredoc body is harmless data. Retaining it (false positive) means Layer 0/0b scan it unnecessarily. If the body contains `rm -rf /`, Layer 0 would fire on it -- but that is a false positive on innocuous data. This is acceptable: the cost is a spurious ASK/DENY, not a security gap. Fail-closed is correct here.

### F3-1 Attack: shlex.split() interaction with heredoc-containing sub_cmd strings

**Question**: Does `shlex.split()` inside `_extract_base_command()` break on sub_cmd strings containing `<<`?

**Answer**: Verified by execution. `split_commands()` produces sub_cmds WITHOUT heredoc bodies (bodies are consumed separately at lines 426-428). Typical sub_cmds are:
- `"bash << EOF"` -> `shlex.split` returns `['bash', '<<', 'EOF']` -- works fine
- `"bash << 'EOF'"` -> returns `['bash', '<<', 'EOF']` -- works fine
- `"cat > file.txt << EOF"` -> returns `['cat', '>', 'file.txt', '<<', 'EOF']` -- works fine

Gemini's concern about unterminated quotes in heredoc bodies causing `shlex.split` ValueError is a **false alarm for Phase 3** because `split_commands()` strips bodies before Phase 3 sees sub_cmds. However, see new finding F2-1 below for a related real issue.

---

## Section 3: New Findings (V1 Missed)

### NEW F2-1 (MEDIUM): _extract_base_command() does not skip I/O redirection tokens

**Severity**: MEDIUM (Phase 1: fail-closed; Phase 3: defense-in-depth bypass)
**Found by**: Gemini 3.1 Pro (confirmed by execution)

**The problem**: `_extract_base_command()` does not handle I/O redirection tokens (`<`, `>`, `<<`, etc.) in its skip loop. When a command has an input redirect before the command name (e.g., `< /dev/null bash`), `shlex.split` produces `['<', '/dev/null', 'bash', '<<', 'EOF']`, and the function returns `<` as the base command.

**Verified by execution**:
```
_extract_base_command('< /dev/null bash << EOF') = '<'   # Should be 'bash'
_extract_base_command('<< EOF bash')             = '<<'  # Should be 'bash'
_extract_base_command('bash << EOF')             = 'bash' # Correct
_extract_base_command('cat > file.txt << EOF')   = 'cat'  # Correct (> comes after cmd)
```

**Impact analysis**:

- **Phase 1 (classifier)**: `cmd_before_heredoc` for `< /dev/null bash` is `"< /dev/null bash"`. `_extract_base_command` returns `<`. Rule 1: `<` not in `_INTERPRETER_COMMANDS`. Rule 2: no output redirect. Rule 4: `<` not in `_PASSIVE_DATA_SINKS`. Rule 5: unknown -> UNSAFE -> body retained. **FAIL-CLOSED. No false negative.** The body is unnecessarily retained (false positive) but no security impact.

- **Phase 3 (backstop)**: `_extract_base_command("< /dev/null bash << EOF")` returns `<`, which is not in `_INTERPRETER_COMMANDS`. Phase 3 backstop does NOT fire. **Defense-in-depth gap.** However, Phase 1 already retains the body (fail-closed), so the practical impact is limited.

**Fix**: Add I/O redirect skipping to `_extract_base_command()`:
```python
# After variable assignment check, before prefix command check:
# Skip I/O redirection tokens and their targets
if part in ('<', '>', '>>', '<<', '<<-', '<<<', '>&', '<&', '>|', '&>'):
    i += 1  # skip the token
    if i < len(parts):
        i += 1  # skip the target (filename/fd)
    continue
```

**Note**: This must be carefully implemented to not skip the `<<` that is part of the heredoc operator and its delimiter. In practice, since Phase 3 checks `'<<' in sub_cmd` separately, the base command extraction only needs to find the actual command name. Skipping `<<` and its following token (`EOF`) is correct -- we want `bash`, not `<<`.

### NEW F2-2 (LOW): Pseudocode/plan misalignment on `sort` exclusion

**Severity**: LOW (documentation inconsistency)
**Found by**: Direct comparison

The plan at line 79 says `sort` is "excluded" alongside `tee`, but the plan's `_PASSIVE_DATA_SINKS` list at line 78 does not include `sort` (correctly). However, the technical reference at `draft-plan-technical.md` line 305 still has `sort` in the set. Stale reference. Fix: remove from pseudocode.

---

## Section 4: Cross-Phase Boundary Analysis

### Redacted string construction: range ordering and overlaps

**Verified safe**. `_consume_heredoc_bodies()` processes heredocs sequentially, moving `i` monotonically forward. Body ranges cannot overlap. The `sorted(body_ranges)` call in the construction code is defensive but correct. Empty bodies (start == end) produce `command[x:x]` = `""` and `newline_count = 0`, which is handled correctly. No issue.

### Phase 1 + Phase 3 interaction after redaction

**Verified safe**. Phase 3 operates on sub_commands (from `split_commands()`), not on the redacted string. Sub_commands contain the heredoc operator text (`bash << EOF`) but NOT the body. `_is_interpreter_heredoc()` checks the sub_cmd string. This is unaffected by Phase 1 redaction.

### Newline preservation in redacted string

**Verified safe**. The construction replaces safe body content with `'\n' * newline_count`. This preserves line count, preventing:
- Token merging (e.g., `EOF` delimiter merging with next command)
- `^`/`$` anchor drift for patterns
- Synthetic adjacency creating new matches

---

## Section 5: Assessment

### Required fixes before implementation (2):

1. **NEW F2-1**: Add I/O redirection token skipping to `_extract_base_command()`. Without this, `< /dev/null bash << EOF` is misclassified in the base command extractor. Phase 1 is fail-closed (no security impact) but Phase 3 backstop is bypassed.

2. **Pseudocode alignment**: Update `draft-plan-technical.md` to:
   - Store `origin_cmd` in `pending_heredocs` tuple at `<<` parse time (F1-1 pseudocode fix)
   - Remove `tee` and `sort` from `_PASSIVE_DATA_SINKS` set (F1-2 pseudocode fix)

### No fix required (documentation only):

3. The plan prose at `heredoc-scanning-redesign.md` line 81 should note that `_extract_base_command()` must skip I/O redirect tokens in its skip loop, not just env prefixes, variable assignments, sudo, and paths.

### Items confirmed safe:

- Redacted string construction (monotonic ranges, no overlap possible)
- Newline preservation (correct count, no token merging)
- shlex.split on sub_cmd strings (bodies stripped, no ValueError risk for normal cases)
- F1-1 prose description (correct, pseudocode stale)
- F1-2 tee removal (correct, acceptable false positive)
- F2-1 Path.relative_to (correct fix)
- F2-2 interpolation filter (correct fix)
- F3-1 _extract_base_command reuse (correct approach, needs I/O redirect handling)
- Phase 1 + Phase 3 interaction (no interference)
- Phase 1 + Phase 2 interaction (independent code paths)

---

## Summary Table

| ID | Severity | Type | Description | Action |
|----|----------|------|-------------|--------|
| NEW F2-1 | MEDIUM | New finding | `_extract_base_command()` doesn't skip I/O redirect tokens; `< /dev/null bash << EOF` returns `<` instead of `bash` | Add redirect token skipping to skip loop |
| F1-1 pseudo | HIGH | Pseudocode stale | Technical ref still passes `cmd_before_heredoc` at consumption time, not parse time | Update pseudocode to match prose |
| F1-2 pseudo | LOW | Pseudocode stale | Technical ref still has `tee` and `sort` in `_PASSIVE_DATA_SINKS` | Remove from pseudocode |
| V1 F1-1 | -- | Verified | Separator origin tracking -- prose correct | No action |
| V1 F1-2 | -- | Verified | tee removed -- correct | No action |
| V1 F1-3 | -- | Verified | >& added -- correct | No action |
| V1 F2-1 | -- | Verified | Path.relative_to -- correct | No action |
| V1 F2-2 | -- | Verified | Interpolation filter -- correct | No action |
| V1 F3-1 | -- | Verified | _extract_base_command reuse -- correct (with F2-1 addition) | No action |

### Gemini findings assessment:

| Gemini Finding | Our Assessment | Agreement |
|---------------|---------------|-----------|
| shlex.split bypass via unterminated quotes in body | **False alarm for Phase 3** -- split_commands strips bodies before Phase 3 sees sub_cmds. Verified by execution. | DISAGREE (Gemini assumed sub_cmd contains body) |
| Input redirect prefix bypass (`< /dev/null bash`) | **Valid** -- confirmed by execution. `_extract_base_command` returns `<`. | AGREE (new finding F2-1) |
| Separator origin pseudocode mismatch | **Valid** -- pseudocode stale, prose correct. | AGREE |
| Stale tee/sort in pseudocode | **Valid** -- documentation fix needed. | AGREE |
| Redacted string construction robust | **Confirmed** -- monotonic parsing prevents overlaps. | AGREE |

---

## Final Verdict

**CONDITIONAL PASS**: The plan is architecturally sound and all 6 V1 fixes are correctly incorporated in the prose. Two items must be addressed before implementation begins:

1. Add I/O redirect handling to `_extract_base_command()` (new finding, MEDIUM severity)
2. Align technical reference pseudocode with plan prose (stale code, HIGH implementation risk)

Neither item changes the plan's architecture. Both are localized fixes to existing components. The plan is ready for implementation once these are applied.
