# Review: action-plans/interpreter-heredoc-bypass.md

**Reviewer**: Critical action plan reviewer
**Date**: 2026-02-22
**Verdict**: **NEEDS_FIX** (minor corrections required; no structural issues)

---

## 1. Factual Accuracy -- Line Number Verification

### Claim: `split_commands()` line 425-428 consumes heredoc bodies at depth-0 newlines

**CORRECT.** The actual code at lines 425-428:
```python
# Consume heredoc bodies after newline
if pending_heredocs:
    i = _consume_heredoc_bodies(command, i, pending_heredocs)
    pending_heredocs = []
```
These lines are inside the `if c == "\n":` block (line 421). Accurate.

### Claim: `_consume_heredoc_bodies()` at line 476-506

**CORRECT.** Function definition starts at line 476, the `return i` statement is at line 506. Accurate.

### Claim: Main guardian Layer 1 scan at "line 1437-1444"

**MINOR INACCURACY.** The Layer 1 section spans lines 1436-1448:
- Comment block: 1437-1441
- `scan_text` join: 1442-1444
- `scan_protected_paths()` call: 1445
- Verdict check: 1446-1448

The plan references "line 1437-1444" which omits the actual `scan_protected_paths()` call at line 1445 and the verdict application at 1446-1448. The plan's "Root Cause" section says "line 1437-1444" -- should be "line 1436-1448" or at minimum "line 1437-1448".

**Correction needed**: In the "Root Cause" section (plan line 62), change "line 1437-1444" to "line 1437-1448".

### Claim: Per-sub-command loop at "around line 1453"

**CORRECT.** The `for sub_cmd in sub_commands:` loop is at exactly line 1453.

### Claim: `is_delete_command()` at line 1019-1053

**CORRECT.** Function definition starts at line 1019, the `return any(...)` is at line 1053.

### Claim: "Body content is invisible to all guardian security layers"

**CORRECT.** Verified:
- Layer 1 (`scan_protected_paths`) operates on the joined sub-commands (line 1442-1445). Heredoc bodies are consumed by `_consume_heredoc_bodies()` before sub-commands are formed.
- Layer 3 (`extract_paths`) operates per sub-command (line 1458). The sub-command is `bash << EOF`, not the body content.
- Layer 4 (`is_delete_command` / `is_write_command`) operates per sub-command (lines 1454-1455). `bash << EOF` does not match any delete/write pattern.

The layer-by-layer bypass analysis table is accurate.

---

## 2. Completeness -- Comparison Against Original Finding (temp/verification-1b.md Section 2)

### Items from verification-1b.md Vector 2 covered in the action plan:
- `source /dev/stdin << EOF` -- covered (Vector B)
- `bash << EOF` -- covered (Vector A)
- `sh << EOF` -- covered (Vector D)
- `python3 << EOF` -- covered (Vector C)
- Layer-by-layer explanation of why it bypasses -- covered (table)
- Recommended fix: block/ask patterns -- covered

### Items from verification-1b.md NOT in the action plan:

**NONE MISSING.** The action plan actually expands on the original finding with additional vectors (perl, ruby, node, deno, bun, zsh, dash, ksh, csh, tcsh, fish), edge cases (`env` prefix, `command` prefix, full paths, `exec 3<<` false positive), and a fuller testing plan. The action plan is a superset of the original finding.

### Items from verification-1b.md Vector 1 (runtime path construction):

The action plan references this under "What This Does NOT Fix" (plan line 118: `printf` runtime path construction). This is appropriate -- it is a separate issue.

### Items from verification-1b.md Vector 3 (unbalanced quote delimiter):

Not mentioned in the action plan. This is acceptable since Vector 3 was rated LOW severity and is fail-closed. However, the plan could note the related `is_delete_command` regex gap for `\n`-preceded `rm` (verification-1b.md line 99) as a known adjacent issue.

**Suggestion (non-blocking)**: Add a brief mention of the verification-1b Vector 3 `is_delete_command` `\n` regex gap as a related item in the "Relationship to Existing Gaps" section.

---

## 3. Format Compliance

### YAML Frontmatter

The plan uses:
```yaml
---
status: not-started
progress: "Plan written, not yet implemented"
---
```

Comparison with existing plans:
- `action-plans/test-plan.md`: `status: active`, `progress: "P0 일부 완료, P1/P2 대부분 미착수"` -- matches format
- `action-plans/_done/heredoc-fix.md`: `status: done`, `progress: "전체 완료 — 788 tests pass, 0 bypasses"` -- matches format

**COMPLIANT.** The YAML frontmatter has both required fields (`status`, `progress`) in the correct format.

### General Structure

The plan follows the same pattern as existing plans: Problem, Fix Approach, Testing Plan, Scope. The `_done/heredoc-fix.md` has a more Phase-oriented structure suited to a completed plan. The new plan's structure is appropriate for a not-started plan.

**COMPLIANT.**

---

## 4. Technical Accuracy of the Fix Approach

### Regex Pattern Analysis

#### Pattern 1: Shell interpreters
```python
r"^\s*(?:bash|sh|zsh|dash|ksh|csh|tcsh|fish)\s+.*<<"
```

**ISSUE: Overly broad `.*` between interpreter and `<<`.** This pattern would match:
- `bash << EOF` -- CORRECT (intended)
- `bash -x << EOF` -- CORRECT (intended, flags between interpreter and heredoc)
- `bash script.sh << EOF` -- FALSE POSITIVE. This runs `script.sh` with heredoc input to `script.sh`, not to `bash` itself as an interpreter of body content. However, this is arguably still worth flagging since `script.sh` would receive the heredoc body as stdin, which could be malicious.
- `bash -c "echo hello" << EOF` -- MIXED. The `-c` takes precedence over stdin heredoc in bash; the heredoc body is actually ignored. This would be a false positive, but the `-c` wrapper is already a separate known gap.

**Verdict on this pattern**: The `.*` is acceptable. False positives in this context are safe-direction (triggering "ask" for suspicious patterns). The `\s+` before `.*` ensures at least one space after the interpreter name.

#### Pattern 2: source/dot with /dev/stdin
```python
r"^\s*(?:source|\.)\s+/dev/stdin\s*<<"
```

**CORRECT.** This is tight and specific. No false positive risk.

#### Pattern 3-4: Script interpreters
```python
r"^\s*(?:python[23]?|python\d[\d.]*|py)\s+.*<<"
r"^\s*(?:perl|ruby|node|deno|bun)\s+.*<<"
```

**SAME `.*` consideration as Pattern 1.** Acceptable for same reasons.

**ISSUE with `python\d[\d.]*`**: This would match `python310` (no dots) but also `python3.10.1`. The intent is good. However, `python\d[\d.]*` would also match `python3..` (double dots), which is not a real interpreter name but will never appear in practice. Cosmetic only.

#### Pattern 5: Full paths to interpreters
```python
r"^\s*(?:/usr)?/(?:s?bin|local/bin)/(?:bash|sh|zsh|python[23]?|perl|ruby|node)\s+.*<<"
```

**INCOMPLETE.** Missing several interpreters that are listed in patterns 3-4:
- Missing: `dash`, `ksh`, `csh`, `tcsh`, `fish`, `deno`, `bun`, `py`
- The full-path pattern should be consistent with the name-based patterns.

**Correction needed**: Add the missing interpreters to Pattern 5, or consolidate the interpreter list into a shared constant.

### Implementation Location

The plan proposes adding the check inside the per-sub-command loop at line 1453:
```python
for sub_cmd in sub_commands:
    # NEW: Check for interpreter+heredoc bypass
    if _is_interpreter_heredoc(sub_cmd):
        ...
```

**CORRECT location but subtle issue.** The sub-command from `split_commands` for `bash << EOF` will be the string `"bash << EOF"` (with the `<<` operator and delimiter included in the sub-command text). The proposed regex patterns check for `<<` in the sub-command, which WILL match because `split_commands` includes the heredoc operator in the sub-command text. Verified by reading lines 398-418: the `<<` and delimiter are appended to `current`, which becomes the sub-command.

**However**, there is an alternative location that would be simpler and more robust: between Layer 1 and Layer 3+4 (around line 1449), as a standalone check over all sub_commands before entering the loop. This would be cleaner but functionally equivalent. The proposed location inside the loop works fine.

### Verdict choice ("ask" not "deny")

**APPROPRIATE.** `bash << EOF` has legitimate uses (e.g., running a setup script). Denying would cause usability issues. "Ask" correctly escalates to user confirmation.

### `_stronger_verdict` usage

**CORRECT.** `_stronger_verdict` is defined at line 1345 and implements deny > ask > allow ordering. Using it with `("ask", ...)` is the correct pattern seen throughout the main function.

---

## 5. Missing Edge Cases

### Covered by the plan:
1. `env bash << EOF` -- env prefix
2. `command bash << EOF` -- command builtin prefix
3. `/usr/bin/bash << EOF` -- full path
4. `bash -x << EOF` -- flags
5. `exec 3<< EOF` -- fd redirection (correctly identified as NOT an interpreter heredoc)
6. `cat << EOF | bash` -- pipe variant (correctly deferred to separate analysis)

### NOT covered by the plan:

#### A. `sudo bash << EOF`
The `sudo` prefix before an interpreter is not handled. The proposed patterns start with `^\s*(?:bash|...)`, so `sudo bash << EOF` would NOT match. This is a real gap.

**Correction needed**: Add `sudo` to the edge cases and patterns. Either:
- Add a dedicated pattern: `r"^\s*sudo\s+(?:bash|sh|...)\s+.*<<"`
- Or expand the patterns to optionally match a `sudo` prefix.

#### B. `nohup bash << EOF`, `nice bash << EOF`, `time bash << EOF`
Similar to `env` and `command`, other command prefixes like `nohup`, `nice`, `time`, `timeout`, `strace`, etc. could precede an interpreter. The plan covers `env` and `command` but not these.

**Suggestion (non-blocking)**: Consider a more general prefix pattern: `r"^\s*(?:env|command|sudo|nohup|nice|time|timeout|strace|ltrace|exec)\s+.*(?:bash|sh|...)\s+.*<<"`. Alternatively, document this as a known limitation and address in a follow-up.

#### C. `bash <<< "rm -rf .git"` (here-string)
The `<<<` (here-string) operator feeds a single string as stdin to the command. For `bash <<< "rm -rf .git"`, the string is executed by bash. The heredoc parser explicitly excludes `<<<` (line 401: `command[i:i+3] != '<<<'`), so the string content would remain in the sub-command text and be visible to Layer 1 scanning. However, whether `rm -rf .git` inside a here-string is actually detected depends on the scan patterns.

**Suggestion (non-blocking)**: Add a test case for `bash <<< "rm -rf .git"` to confirm it IS detected by existing layers (it likely is, since the content stays in the sub-command text). Document this as a handled case.

#### D. Here-string with variable: `bash <<< "$cmd"` where `cmd="rm -rf .git"`
This is a runtime construction variant (same class as `printf`/`base64` bypass). Not detectable by static analysis. Already implicitly covered by the "What This Does NOT Fix" section.

#### E. `eval "$(cat << EOF\nrm -rf .git\nEOF\n)"`
Nested command substitution containing a heredoc. The `$()` creates a depth > 0 context, so the `<<` inside `$()` would be processed at depth > 0. Looking at line 400-402: the heredoc detection requires `arithmetic_depth == 0`, but there is no check for `depth == 0`. This means heredocs inside `$()` ARE detected and consumed. The sub-command would be the full `eval "$(cat << EOF ... EOF)"` string. The body would be consumed, making `rm -rf .git` invisible.

**Finding**: This is an additional bypass variant that the plan does not mention. The `eval` wrapper is noted as a separate gap, but the specific `eval "$(cat << EOF)"` form combines both the `eval` wrapper and heredoc body injection.

**Suggestion (non-blocking)**: Add this as a documented variant in the "What This Does NOT Fix" section.

#### F. Multiple heredocs on one line: `bash << EOF1; sh << EOF2`
When multiple heredocs appear on one command line, `split_commands` would split at `;` first, producing two sub-commands: `bash << EOF1` and `sh << EOF2`. The bodies would be consumed for both. Each sub-command would independently match the proposed interpreter-heredoc pattern. This is correctly handled.

#### G. `ash << EOF` (BusyBox shell)
Alpine Linux and embedded systems use `ash` as the default shell. Not included in the interpreter list.

**Suggestion (non-blocking)**: Add `ash` to the shell interpreter list.

---

## 6. Summary of Required Corrections

| # | Location in Plan | Issue | Severity |
|---|-----------------|-------|----------|
| 1 | Line 62, "Root Cause" | Line reference "1437-1444" should be "1437-1448" | Low (cosmetic) |
| 2 | Line 84, Pattern 5 | Missing interpreters in full-path pattern (dash, ksh, csh, tcsh, fish, deno, bun) | Medium (incomplete detection) |
| 3 | Edge Cases section | Missing `sudo bash << EOF` variant | Medium (bypass variant not covered) |

## 7. Non-Blocking Suggestions

| # | Suggestion |
|---|-----------|
| 1 | Add `ash` to shell interpreter list (BusyBox/Alpine) |
| 2 | Consider general prefix pattern for `nohup`, `nice`, `time`, `timeout`, etc. |
| 3 | Add `bash <<< "rm -rf .git"` here-string test case to confirm existing detection |
| 4 | Document `eval "$(cat << EOF)"` as a combined variant in "What This Does NOT Fix" |
| 5 | Mention verification-1b Vector 3 `is_delete_command` `\n` regex gap as related |
| 6 | Consolidate interpreter names into a single shared constant to avoid divergence between patterns |

## 8. Final Verdict

**NEEDS_FIX** -- Three specific corrections are required (see section 6). The core analysis is factually accurate and the fix approach is sound. After these corrections, the plan is ready for implementation.
