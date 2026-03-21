# Round 1: Cross-Model Validation Analysis

**Date**: 2026-03-21
**Analyst**: Opus 4.6 (1M context)
**Models consulted**: Codex (via PAL clink), Gemini 3.1 Pro Preview (via PAL clink)
**Plans evaluated**: Plan A (heredoc-pattern-false-positives.md), Plan B (interpreter-path-resolution.md)

---

## Table of Contents

1. [Full Model Responses - Plan Evaluation](#1-full-model-responses---plan-evaluation)
2. [Full Model Responses - Paradigm Questions](#2-full-model-responses---paradigm-questions)
3. [Cross-Model Agreement Matrix](#3-cross-model-agreement-matrix)
4. [Cross-Model Disagreement Analysis](#4-cross-model-disagreement-analysis)
5. [Unique Insights by Model](#5-unique-insights-by-model)
6. [Synthesis and Recommendations](#6-synthesis-and-recommendations)

---

## 1. Full Model Responses - Plan Evaluation

### 1.1 Codex Response (Plan Evaluation)

**Provider**: Codex (OpenAI)
**Role**: Code Reviewer
**Duration**: 299s

#### Findings

- **High: Plan A's Step 4/5 would weaken Layer 0/0b by scanning per sub-command after tokenization, which breaks cross-command regexes.** The plan explicitly moves `match_block_patterns()` / `match_ask_patterns()` to `for sub_cmd in sub_commands` and claims "no pattern modifications are needed". That is incorrect for patterns like the existing remote-script-exec block regex: `(?:curl|wget)[^|]*\|\s*(?:bash|sh|zsh|python|perl|ruby|node)`. `split_commands()` deliberately splits on `|`, so `curl ... | bash` becomes separate fragments and the block regex no longer matches. Impact: a current deny can turn into an allow/ask regression. Fix: do not move Layer 0/0b to per-sub-command fragments; keep a shell-structure-preserving scan string and only redact safe heredoc bodies inside that whole-command view.

- **High: Plan B's F1 suppression rule is unsafe because "any extracted path-like literal" can disable the fail-closed ask.** The extractor accepts any string containing `/` or starting `.`, then converts it to a `Path` and treats project-relative results as valid. The F1 block then suppresses the ask whenever `interpreter_paths` is non-empty. This is broader than the stated "decoy literal" concern: ordinary literals like `"https://example.com/api"` or `"application/json"` also satisfy the heuristic and resolve under the project root, so a destructive payload with a dynamic target can downgrade from ask to allow without any malicious decoy. Fix: do not use generic string-literal extraction to suppress F1. At most, use it to enrich diagnostics, or require source-to-sink binding for each destructive call.

- **Medium: Plan A does not actually subsume the interpreter-heredoc plan safely.** It claims the dedicated interpreter-heredoc detection becomes unnecessary, but that assumes the tokenizer is shell-accurate. It is not yet. `_parse_heredoc_delimiter()` only understands bare, single-quoted, and double-quoted delimiters; current `split_commands()` mishandles valid forms like `<<$'EOF'` and `<<$"EOF"`, and the codebase already documents unresolved heredoc/depth parsing edge cases. The plan only addresses the backslash case. Fix: keep a cheap interpreter+heredoc `ask` backstop until the tokenizer covers the full delimiter surface.

#### Answers to Specific Questions

**Plan A allowlist**: Only sound as a very small usability allowlist, not as a primary security boundary. `cat`, `tee`, and the pure read-only filters are reasonable. `less`, `more`, `echo`, and `printf` do not buy much and widen the differential surface. Be conservative with `yq`/`csvtool` unless the exact implementation is pinned.

**Pipe-to-interpreter**: Not sufficient by itself. The bigger problem is that Plan A changes scan granularity and breaks existing pipeline-aware block rules. Fix pipeline scanning first; then pipeline retention can be handled against the whole parsed command, including `|&`.

**Backslash-delimiter**: Not enough. Also need tests for `<<$'EOF'`, `<<$"EOF"`, `<<\\EOF`, and `<< \\EOF`, because those do not behave the same in `bash`. Verified locally with `bash -lc` probes.

**Plan B regex extraction**: Not reliable enough for a security decision. AST is only worth it if you narrow scope to direct Python patterns like `os.remove("literal")` or `for f in glob.glob("literal"): os.remove(f)`. AST alone does not solve the decoy/source-to-sink problem.

**General**: Implement separately. Do Plan A first, but redesign it so Layer 0/0b still evaluate a whole-command representation. Would not implement Plan B as written. The 80/20 alternative is: keep F1 fail-closed, add a narrow Python-only recognizer for direct literal/glob deletes if the staging cleanup case is worth special-casing, and otherwise improve the F1 reason text instead of changing the verdict.

#### Positives Noted
- Plan A's removal of `sed`, `mysql`, `psql`, and `sqlite3` from the allowlist is the right instinct.
- The wrapper-flag handling in `_is_data_heredoc_command()` is appropriately fail-closed.
- Plan B at least scopes itself to the F1 path rather than weakening the main path validators.

---

### 1.2 Gemini Response (Plan Evaluation)

**Provider**: Gemini 3.1 Pro Preview (Google)
**Role**: Code Reviewer
**Duration**: 265s

#### Findings (by severity)

**CRITICAL:**

1. **F1 Safety Net Downgraded to Fail-Open (Plan B: Decoy Literal Attack)**: The F1 safety net guarantees a fail-closed response (`ask`) if an interpreter delete/write operation is detected but no targets are resolved. Plan B proposes extracting any path-like string literal to populate targets. If an AI dynamically targets a protected path (e.g., `os.remove(os.getenv('TARGET'))`) but the script also contains a benign string literal (`files = ['safe.txt']`), Plan B extracts `safe.txt`, adds it to `sub_paths`, and validates it as safe. Because `sub_paths` is no longer empty, the F1 safety net is **skipped**, allowing the obfuscated destructive operation silently. This violates the core fail-closed design principle. Fix: Discard Plan B's regex extraction. Keep F1 purely fail-closed.

2. **Complete Blindness to Generated Executables (Plan A: Order of Operations)**: Currently, Layer 0 scans the raw command string, catching catastrophic patterns anywhere. By moving `split_commands()` before Layer 0 and stripping data heredoc bodies, Plan A creates a trivial bypass: `cat << 'EOF' > run.sh\nrm -rf /\nEOF\nbash run.sh`. The `cat` command strips the `rm` payload, blinding Layer 0. Since `bash run.sh` is not an inline script, F1 also ignores it. Fix: Do not move `split_commands()` before Layer 0. Layer 0 must scan the raw, unmodified string.

**HIGH:**

3. **False Subsumption of Interpreter Bypass due to Regex Anchors (Plan A)**: Plan A claims interpreter heredoc bodies will be retained and scanned by Layer 0. However, `match_block_patterns()` uses regexes with the `$` anchor (e.g., `rm\s+-[rRf]+\s+/(?:\s*$|\*)`) without the `re.MULTILINE` flag. Thus, `$` only matches the end of the entire string. Destructive commands in the middle of a retained multi-line string will not match. Fix: Add `re.MULTILINE` to `match_block_patterns()` flags.

4. **Delimiter Parsing Bypass via ANSI-C Quoting (Plan A)**: Plan A proposes fixing `\EOF` delimiters but ignores Bash's ANSI-C quoting (`$'EOF'`) and locale translation (`$"EOF"`). If an agent uses `cat << $'EOF'`, the parser treats the literal string `$'EOF'` as the delimiter, consuming the entire remainder as body. Because `cat` is allowlisted, the remainder is stripped and never scanned. Fix: Update `_parse_heredoc_delimiter()` to strip `$` prefixes before `'` or `"`.

**MEDIUM:**

5. **Incomplete Pipeline Mitigation (Plan A)**: The fix checks for `|` but misses sequential file execution bypasses (e.g., `cat << EOF > script.sh; bash script.sh`). The body is stripped by `cat` and executed blindly by `bash script.sh`.

**LOW:**

6. **Filesystem Oracle Risk / Missing String Formatting (Plan B)**: The regex misses f-strings and triple-quotes, which fails closed. The `glob.glob()` oracle is minimal risk since the AI already executes locally.

#### Answers to Specific Questions

**Plan A allowlist**: Mostly sound. Removing GNU `sed` is excellent threat modeling. Omitted commands like `awk` fail-closed.

**Pipe-to-interpreter**: Incomplete. Catches `cat << EOF | bash` but misses sequential execution (`cat > script.sh && bash script.sh`).

**Delimiter fix**: No. Misses ANSI-C `$'EOF'` and locale `$"EOF"`.

**Interpreter subsumption**: False. Due to missing `re.MULTILINE` flags, destructive commands in multi-line retained payloads will not be caught.

**Security of moving split_commands**: Completely blinds Layer 0 to commands embedded in data heredocs (e.g., `cat > run.sh`).

**Plan B regex**: Not reliable. Misses f-strings, concatenation, dynamically generated variables.

**Decoy literal**: Yes, critical risk. Any safe string literal bypasses F1.

**Phase 2 AST**: Not worth it. Building AST parsers for every interpreter is untenable complexity.

**General**: Neither plan should be implemented as proposed. Both must be redesigned. 80/20 alternative for Plan A: leave Layer 0 scanning raw string, fix `re.MULTILINE` bug, handle heredoc FPs via lightweight pre-filter. For Plan B: use system prompts to restrict agents to standard CLI tools.

---

## 2. Full Model Responses - Paradigm Questions

### 2.1 Codex Response (Paradigm Questions)

**Provider**: Codex (OpenAI)
**Role**: Code Reviewer
**Duration**: 174s

#### On Fail-Closed vs. Usability

- **High finding**: Raw Layer 0/0b scanning is still conflating fail-closed policy with human-confirmation UX. `match_block_patterns(command)` is called before heredoc-aware splitting, and `match_ask_patterns(command)` does the same, while heredoc bodies are only stripped later. A doc heredoc containing `git push --force` is denied and one containing `git reset --hard` asks.

- **Key insight**: `deny` is tolerable when confidence is high because the user cannot click through, but `ask` on inert text trains users to auto-allow and is therefore a **human-factors fail-open**.

- **Fix recommendation**: Split the policy by confidence and consequence, not by "block vs ask regex". Reserve pre-parse hard-deny rules for high-confidence irreversible primitives. Run `ask` rules only after you can attribute text to an execution sink, or downgrade uncertain textual matches to log/telemetry.

#### On Allowlist vs. Blocklist

- **Medium finding**: The proposed heredoc allowlist is using the wrong security abstraction. "Data command vs interpreter command" will keep expanding, still miss escape-capable tools, and puts security decisions on a brittle command taxonomy.

- **Better model**: Classify the heredoc consumer by **sink capability** instead: `passive_data_sink`, `write_sink`, `exec_sink`, `unknown_sink`. Only strip bodies for proven passive sinks. For unknown or execution-capable sinks, retain body scanning. That is the better hybrid than pure allowlist or pure blocklist.

#### Positives
- Moving Layer 1 to post-split scanning is the right shape.
- The explicit F1 unresolved-target safeguard is a good invariant to preserve.
- Tests openly documenting tokenizer limitations are valuable.

---

### 2.2 Gemini Response (Paradigm Questions)

**Provider**: Gemini 3.1 Pro Preview (Google)
**Role**: Code Reviewer
**Duration**: 138s

#### On Fail-Closed vs. Usability

- **Critical finding**: A pure "fail-closed" approach that defaults to user confirmation (`ASK`) for ambiguous patterns creates severe alert fatigue. Users reflexively type "y" or click "allow", conditioning them to bypass protections. **Usability is security.**

- **Framework**: Since the actor is an AI agent, the tool must differentiate between DENY and ASK:
  - **DENY (Hard Block)**: Use aggressively for high-confidence, catastrophic operations. Zero fatigue for the human; AI gets error and tries another approach.
  - **ASK (Soft Block)**: Treat every ASK as a strictly budgeted resource. Reserve exclusively for high-impact actions where intent is genuinely ambiguous but frequently legitimate. Shift low-confidence ASKs to ALLOWs with silent logging.

#### On Allowlist vs. Blocklist

- **High finding**: Plan A proposes an Allowlist of "safe data commands". However, AI agents frequently pipe heredocs into hundreds of unknown CLI tools (`aws`, `kubectl`, `psql`, custom scripts). Treating all unknown tools as interpreters generates massive false positives. **Given the AI threat model, a Blocklist is vastly superior.**

- **Better abstraction**: Frame as "Host OS Execution" vs. "Domain Execution". `bash` runs on the Host OS; scan its heredoc. `psql` runs in a database domain; treat its heredoc as data. The risk of an AI accidentally generating a Host OS filesystem attack via `\!` escape inside `mysql` is negligible compared to daily friction of scanning all SQL code.

#### Positives
- The architecture of `split_commands` is excellent.
- Performing command decomposition before layered pattern matching prevents trivial bypasses and reduces false positives.

---

## 3. Cross-Model Agreement Matrix

| Topic | Codex | Gemini | Agreement? |
|-------|-------|--------|------------|
| **Plan B decoy literal is critical risk** | YES (High) | YES (Critical) | STRONG AGREE |
| **Plan B should not suppress F1 with regex extraction** | YES | YES | STRONG AGREE |
| **Plan A per-sub-command Layer 0 breaks pipeline patterns** | YES (High - curl\|bash) | YES (Critical - cat>run.sh bypass) | AGREE (different vectors) |
| **Plan A subsumption claim is unjustified** | YES (Medium - delimiter gaps) | YES (High - re.MULTILINE missing) | AGREE (different reasons) |
| **Backslash delimiter fix is insufficient** | YES ($'EOF', $"EOF") | YES ($'EOF', $"EOF") | STRONG AGREE |
| **Plan A allowlist removals (sed, mysql, etc.) are correct** | YES | YES | STRONG AGREE |
| **ASK fatigue is a human-factors fail-open** | YES | YES | STRONG AGREE |
| **DENY vs ASK need different treatment** | YES | YES | STRONG AGREE |
| **Phase 2 AST not worth complexity** | YES (unless narrow Python-only) | YES (untenable for all interpreters) | AGREE |
| **Neither plan should be implemented as-is** | YES (redesign Plan A, don't implement Plan B) | YES (neither as proposed) | STRONG AGREE |
| **Allowlist vs Blocklist paradigm** | Neither (use sink capability) | Blocklist preferred | **DISAGREE** |
| **Plan B 80/20 alternative** | Narrow Python-only recognizer | System prompt engineering | **DISAGREE** |
| **Should Layer 0 scan raw string?** | YES (keep whole-command, redact safe bodies) | YES (do not move split_commands before Layer 0) | AGREE |
| **glob.glob() oracle concern** | Not explicitly addressed | Low risk (AI has filesystem access) | AGREE (low concern) |

---

## 4. Cross-Model Disagreement Analysis

### 4.1 Allowlist vs. Blocklist vs. Sink Capability

**Codex position**: Neither pure allowlist nor blocklist. Proposes **sink capability classification**: `passive_data_sink`, `write_sink`, `exec_sink`, `unknown_sink`. Only strip bodies for proven passive sinks.

**Gemini position**: **Blocklist is vastly superior** for the AI threat model. Only scan bodies for known Host OS interpreters (bash, python, node, ruby, sh, perl). Treat everything else (aws, kubectl, psql, custom scripts) as data/domain execution.

**Analysis**: This is the most significant disagreement. Codex takes the security-conservative position (unknown = retain = scan), while Gemini takes the usability-optimized position (unknown = likely data = strip). Both have merit:

- Codex's sink capability model is more principled but harder to implement and maintain. The categories need clear definitions.
- Gemini's blocklist is simpler and better matches the threat model (AI agents use standard interpreters, not exotic ones). However, it fails-open for novel interpreters.
- **My assessment**: The threat model tips the scale. AI agents generating heredocs will use standard interpreters. A blocklist of ~15-20 known interpreters covers the realistic threat surface. The fail-open risk for novel interpreters is low when the actor is an AI using common patterns. However, Codex's point about `write_sink` (commands that write to files, like `cat > script.sh`) deserves consideration as a separate category.

### 4.2 Plan B Alternative Approach

**Codex position**: Add a narrow Python-only recognizer for direct literal/glob deletes if the staging cleanup case is worth special-casing. Otherwise, improve F1 reason text.

**Gemini position**: Discard Plan B entirely. Use system prompt engineering to instruct agents to use standard CLI tools instead of interpreter scripts.

**Analysis**: Both agree Plan B as written is unsafe. The disagreement is on what to do instead:
- Codex's narrow recognizer is technically achievable but adds complexity for a single use case.
- Gemini's prompt engineering is zero-code but depends on AI compliance and can't be enforced.
- **My assessment**: Gemini's prompt engineering is the better first step (zero risk, zero code). If the problem persists, Codex's narrow Python AST recognizer (not regex) could be a targeted Phase 2. But neither should change F1's fail-closed verdict -- at most, improve the ASK message to help users decide faster.

---

## 5. Unique Insights by Model

### 5.1 Codex Unique Insights

1. **URL strings as false paths**: Ordinary literals like `"https://example.com/api"` or `"application/json"` satisfy the path heuristic (contains `/`) and resolve under the project root. This is a broader weakness than the documented decoy attack. Plan B doesn't just have a "decoy literal" problem -- it has a "any string with a slash" problem.

2. **Whole-command scan with safe body redaction**: Rather than moving Layer 0 to per-sub-command, keep Layer 0 on a whole-command view but redact only proven-safe heredoc bodies within that view. This preserves cross-command pattern matching (curl|bash) while eliminating false positives.

3. **Sink capability taxonomy**: The four-category model (`passive_data_sink`, `write_sink`, `exec_sink`, `unknown_sink`) is a more principled abstraction than data-vs-interpreter.

4. **`|&` handling**: The pipe-to-interpreter mitigation needs to also handle `|&` (bash's stderr+stdout pipe), not just `|`.

### 5.2 Gemini Unique Insights

1. **Generated executable bypass**: `cat << 'EOF' > run.sh\nrm -rf /\nEOF\nbash run.sh` -- if `cat` is in the data allowlist and its body is stripped, then the destructive content written to `run.sh` becomes invisible to Layer 0, and `bash run.sh` passes because it's just running a file, not inline code. This is the most concrete and damaging bypass vector identified.

2. **re.MULTILINE flag gap**: Even if interpreter heredoc bodies ARE retained and appended to sub-commands, the existing block regexes use `$` anchors without `re.MULTILINE`. In a multi-line retained body, `rm -rf /` in the middle won't match `rm\s+-[rRf]+\s+/(?:\s*$|\*)` because `$` only matches end-of-string. This is a pre-existing bug that Plan A exposes but doesn't fix.

3. **Host OS vs. Domain Execution**: Reframing the classification as "does this command execute on the host OS?" vs. "does it operate in a domain-specific sandbox?" is more intuitive and maintainable than "data vs. interpreter".

4. **Sequential execution bypass**: `cat << EOF > script.sh; bash script.sh` bypasses the pipe check (no `|`), and the generated file execution is invisible to the guardian.

5. **Alert fatigue as the primary risk**: Gemini explicitly argues that the biggest risk to the project is not an edge-case bypass but rather alert fatigue destroying the tool's security value. This reframes the entire discussion from "how to catch more" to "how to alert less but better."

---

## 6. Synthesis and Recommendations

### 6.1 Plan A: Heredoc Pattern False Positives

**Consensus verdict**: The plan correctly identifies a real problem but the proposed implementation is unsafe. Both models agree it must be redesigned.

**Critical issues requiring redesign**:

1. **Do NOT move Layer 0/0b to per-sub-command scanning.** This breaks cross-command patterns (curl|bash) and creates the generated-executable bypass (cat > script.sh). Instead, keep Layer 0/0b on a whole-command string but with safe heredoc bodies redacted.

2. **The subsumption claim is premature.** Two independent reasons: (a) `_parse_heredoc_delimiter()` has ANSI-C quoting gaps (`$'EOF'`, `$"EOF"`), and (b) even with retained bodies, `re.MULTILINE` is missing from block pattern flags. Keep the interpreter+heredoc ASK backstop from `interpreter-heredoc-bypass.md` until both are fixed.

3. **Backslash delimiter fix is necessary but insufficient.** Must also handle `$'EOF'` and `$"EOF"` variants.

**Allowlist design**: Both models agree the allowlist removals (sed, mysql, psql, sqlite3) are correct. The disagreement is on the paradigm:
- Codex: sink capability classification (most principled but complex)
- Gemini: blocklist of known interpreters (simpler, matches threat model)
- **Recommendation**: Start with a small, conservative allowlist (cat, tee, grep, and pure-read text processors). This is effectively Codex's `passive_data_sink` category. Layer on the interpreter blocklist as a secondary check if the allowlist proves too restrictive. The key insight from both models is that the `write_sink` category (commands that create files) needs special handling regardless of paradigm.

**Recommended redesigned approach**:
1. Keep Layer 0/0b scanning the raw command string
2. Build a "heredoc-redacted" version of the command that replaces safe heredoc bodies with empty strings
3. Run Layer 0/0b on the redacted string (preserves pipeline structure, removes false positive content)
4. Fix `_parse_heredoc_delimiter()` to handle backslash, `$'...'`, and `$"..."`
5. Add `re.MULTILINE` to block/ask pattern flags
6. Keep interpreter+heredoc ASK backstop as defense-in-depth

### 6.2 Plan B: Interpreter Path Resolution

**Consensus verdict**: Plan B should NOT be implemented as proposed. Both models rate the decoy literal attack as critical/high risk. The regex extraction approach fundamentally violates the fail-closed principle.

**Why it's unsafe (expanded)**:
- Any string literal containing `/` (URLs, MIME types, format strings) can suppress F1
- Even without malicious intent, incidental literals in AI-generated code will routinely suppress F1
- The fail-closed guarantee of F1 is one of the guardian's strongest safety properties

**Recommended alternatives** (in priority order):
1. **Improve F1 message quality** (zero risk): When F1 fires for interpreter commands, include the detected destructive API and payload excerpt in the ASK message so users can make faster decisions.
2. **System prompt guidance** (zero code risk): Guide AI agents to use standard CLI tools for filesystem operations rather than interpreter one-liners.
3. **Narrow Python AST recognizer** (Phase 2, if needed): Only for the specific pattern `os.remove(string_literal)` / `glob.glob(string_literal)` where source-to-sink binding can be proven. Must NOT suppress F1 -- instead, add the extracted paths to the ASK message for context.

### 6.3 Implementation Order

1. **Fix pre-existing bugs first**: `re.MULTILINE` in block/ask pattern flags, `_parse_heredoc_delimiter()` ANSI-C quoting support
2. **Redesigned Plan A**: Heredoc body redaction in whole-command scan string
3. **F1 message improvement**: Better ASK messages for interpreter commands
4. **Reassess Plan B need**: After Plan A reduces heredoc false positives, measure remaining F1 false positive rate before deciding on further work

### 6.4 Key Paradigm Takeaways

**On fail-closed vs. usability**:
- Both models strongly agree: **alert fatigue from false ASKs is itself a security failure** (conditions users to auto-allow)
- DENY is immune to fatigue (user can't bypass); ASK is fatigue-inducing
- Framework: Reserve pre-parse DENY for high-confidence catastrophic patterns. Run ASK patterns only after attributing text to an execution sink. Consider downgrading low-confidence uncertain matches to log-only.

**On heredoc command classification**:
- Pure allowlist (Plan A) is too restrictive for unknown commands
- Pure blocklist risks missing novel interpreters
- Best hybrid: small allowlist of proven passive data sinks (cat, tee, text filters) combined with a blocklist of known interpreters. Unknown commands retain bodies (fail-closed) but this should be rare given the AI agent threat model.
- The write-to-file case (cat > script.sh) needs special handling in ANY paradigm -- both models identify this as the most dangerous edge case.

---

## Appendix: Model Metadata

| Model | Call | Duration | Input Tokens | Output Tokens |
|-------|------|----------|-------------|--------------|
| Codex | Plan evaluation | 299s | 1,360,328 (1,266,304 cached) | 14,189 |
| Gemini 3.1 Pro Preview | Plan evaluation | 265s | 93,228 (671,102 cached) | 3,824 |
| Codex | Paradigm questions | 174s | 656,058 (553,600 cached) | 8,345 |
| Gemini 3.1 Pro Preview | Paradigm questions | 138s | 73,071 (154,492 cached) | 1,812 |

Note: Gemini actively ran shell commands to verify claims against the actual codebase (31 tool calls in the first session, 8 in the second). Codex also verified locally but with fewer tool calls.
