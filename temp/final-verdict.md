# Final Verdict: Action Plan Assessment

**Date**: 2026-03-21
**Process**: 2-round review, 5 teammates, 4 external model consultations (Codex 5.2, Gemini 3.1 Pro)
**Working files**: temp/r1-*.md, temp/r2-*.md

---

## Executive Verdict

Both plans are **rational and address real problems**, but neither is shippable as written. Plan A has one confirmed CRITICAL flaw (curl|bash regression). Plan B was over-rejected by initial review — the adversarial round found that its dismissal ignored the very alert fatigue problem the reviewers themselves identified.

---

## Plan A: Heredoc Pattern False Positives

### What's genuinely broken (CONFIRMED across all rounds)

| Issue | Severity | Details |
|-------|----------|---------|
| **Per-sub-command Layer 0/0b breaks curl\|bash** | CRITICAL | `split_commands()` splits on `\|` before newline handler. Cross-pipe patterns like `(?:curl\|wget)[^|]*\|\s*(?:bash\|sh)` can never match split sub-commands. Regression from DENY to ALLOW. |
| **Pipe-to-interpreter mitigation broken** | CRITICAL (same root cause) | For `cat << EOF \| bash`, `cmd_so_far` is `"bash"` not `"cat << EOF \| bash"` — pipe check fails. |
| **`_is_data_heredoc_command()` fail-open default** | HIGH | Returns `True` when no `<<` found. Should be `False`. |
| **Subsumption claim invalid** | HIGH | `[^|&\n]*` in block patterns stops at newlines. Even retained interpreter heredoc bodies can't match multiline destructive content. `interpreter-heredoc-bypass.md` remains needed as complementary defense. |
| **ANSI-C quoting not handled** | MEDIUM | `$'EOF'`, `$"EOF"` in `_parse_heredoc_delimiter()` — genuine gap. |

### What was OVERCLAIMED by Round 1 (corrected by adversarial review)

| R1 Claim | Adversarial Correction | Impact |
|----------|----------------------|--------|
| **Scenarios A/B are catastrophic DENY false positives** | Empirically tested: `rm -rf /` in heredoc body does NOT match block pattern because `$` anchor (without `re.MULTILINE`) requires end-of-string. Scenario A/B are NOT actually false positives today. | Reduces the severity of the problem. Real false positives exist (Scenarios C-I) but the two most dramatic examples were wrong. |
| **re.MULTILINE is a "pre-existing bug"** | Adding `re.MULTILINE` would INCREASE false positives (heredoc body content would suddenly match). The absence is an accidental defense-in-depth. False negatives are mitigated by later layers. | **Do NOT blindly add re.MULTILINE.** Requires pattern-by-pattern audit. |
| **"Generated executable bypass" is a Plan A regression** | `cat > script.sh << 'EOF'\nrm -rf /\nEOF\nbash script.sh` is NOT caught by Layer 0 today (same `$` anchor issue). Pre-existing architectural limitation, not a regression. | Remove from Plan A's blocking issues. |

### What's correct and valuable in Plan A

- `_DATA_HEREDOC_COMMANDS` allowlist concept with fail-closed default
- Removal of sed, mysql, psql, sqlite3 from allowlist (shell escape capabilities)
- Wrapper-flag handling is appropriately conservative
- Backslash delimiter fix is a genuine bug fix
- The test structure is reusable

### Verdict: Rational plan, CRITICAL architecture flaw, overclaimed problem severity

The core mechanism (selective heredoc body handling) is sound. The per-sub-command Layer 0/0b architecture is not. Needs redesign — but the redesign is smaller than R1 suggested because fewer scenarios are actually affected.

---

## Plan B: Interpreter Path Resolution

### R1 vs R2 Assessment

| Dimension | R1 Assessment | R2 Adversarial Correction |
|-----------|--------------|--------------------------|
| Overall | FAIL, dismiss entirely | **Too aggressive.** Implement with constraints. |
| Decoy literal attack | HIGH, blocking | Valid in theory but **violates the stated threat model** (AI agents don't generate obfuscated code). |
| Alert fatigue | Identified as security failure | R1 then recommended preserving the exact F1 ASK behavior causing it. **Direct contradiction.** |
| "Improve F1 messages" alternative | Sufficient | Does NOT reduce interruption count. 5-10 ASKs per session regardless of message quality. |
| glob.glob() concern | MEDIUM, novel attack surface | `glob.glob()` already exists in baseline `extract_paths()` at `bash_guardian.py:971`. **Not a novel attack surface.** |
| Regex limitations | Blocking | Documented as fail-closed. f-strings, triple-quotes fall back to F1 ASK. Acceptable. |

### Key adversarial insight

> "R1 identified 'alert fatigue is a security failure' but then recommended preserving the exact behavior that causes it. If .staging/ cleanup fires F1 ASK 5-10 times per session, the user IS conditioned to auto-allow. Improving the message doesn't reduce the frequency."

Both Codex R2 and Gemini R2 independently reached this conclusion.

### Verdict: Rational plan, implement with two constraints

1. Restrict `glob.glob()` to project-internal paths
2. Accept regex extraction limitations as documented (fail-closed to F1 ASK for unresolvable cases)

The decoy literal concern is valid in theory but irrelevant to the AI-agent-makes-mistakes threat model. Alert fatigue from preserved F1 ASK is a more concrete and immediate security risk.

---

## Optimal Path Forward (Both Perspectives Reconciled)

### Guardian perspective priorities
1. Don't break curl|bash detection
2. Maintain fail-closed for unknown/ambiguous commands
3. Don't add re.MULTILINE without pattern audit

### Memory/operational perspective priorities
1. Eliminate heredoc body DENY false positives (Scenarios C-I)
2. Reduce F1 ASK frequency for legitimate interpreter cleanup
3. Don't require human intervention for routine .staging/ operations

### Recommended Implementation Order

**Phase 0: Bug fixes (no dependencies)**
- Fix `_parse_heredoc_delimiter()` for backslash + ANSI-C quoting
- Fix `_is_data_heredoc_command()` fail-open default → `return False`
- Audit re.MULTILINE impact pattern-by-pattern (DO NOT blindly add)

**Phase 1: Heredoc body redaction (Plan A redesigned)**
- Build `redact_safe_heredocs(raw_command) -> str` that:
  - Replaces data heredoc bodies with empty strings in the raw command
  - Preserves ALL operators (|, ;, &&, etc.)
  - Retains interpreter/unknown/piped/write-to-file heredoc bodies
- Run Layer 0/0b on redacted string (NOT per-sub-command)
- Uses hybrid classifier: allowlist of passive data sinks + blocklist of interpreters + pattern detection for write-to-file and pipeline cases
- **NOTE from R2-adversarial**: This approach was recommended by R1 but never designed or attacked. Hold it to the same standard as Plan A before shipping. Design concretely, trace edge cases, attack it.

**Phase 2: F1 improvement (Plan B modified)**
- Implement `extract_paths_from_interpreter_payload()` with project-internal glob restriction
- Accept regex limitations (f-strings etc. fail-closed to ASK)
- Optionally: promote Python AST extraction to Phase 1 for better coverage
- Enrich F1 ASK messages with detected API + payload excerpt regardless

**Phase 3: Interpreter+heredoc backstop (from interpreter-heredoc-bypass.md)**
- Pattern-based ASK for interpreter commands with heredoc operators
- Defense-in-depth since block patterns can't match multiline retained bodies
- Plan A does NOT subsume this — implement independently

### Alternative worth investigating (from R2-adversarial)

**Redirection-based heredoc exemption**: Instead of a command allowlist, exempt heredoc bodies when a file redirection (`>`) is present. Simpler than the full allowlist approach. Naturally handles `cat > file.md << EOF` without enumerating safe commands. Still retains bodies for `bash << EOF` (no redirection) and `cat << EOF | bash` (pipeline). Worth evaluating as a simpler Phase 1 alternative.

---

## Paradigm Settlement

**Hybrid model**: Small allowlist of proven passive data sinks (cat, tee, grep, etc.) for heredoc body redaction + blocklist of known interpreters for explicit retention + pattern detection for write-to-file and pipeline cases + fail-closed default for unknown commands.

This is Codex's "sink capability" model simplified into actionable rules, with Gemini's observation that the AI threat model means exotic interpreters are low risk (but we still fail-closed on them).

---

## Process Learnings

| Issue | Lesson |
|-------|--------|
| Scenarios A/B were wrong | **Empirically test regex claims** against the actual engine |
| re.MULTILINE overcalled as bug | **Trace second-order effects** before recommending flag changes |
| Generated executable attributed to Plan A | **Distinguish new regressions from pre-existing limitations** |
| Plan B dismissed too aggressively | **Don't let theoretical attacks override real operational costs** when they violate the stated threat model |
| Cross-model "consensus" | Shared framing biases toward agreement. **Preserve dissent, frame neutrally.** |
| R1 alternative held to lower standard | **Hold proposed alternatives to the same scrutiny as rejected plans** |

---

## Summary Table

| Plan | Rational? | Shippable? | Core Problem | Fix |
|------|-----------|------------|--------------|-----|
| Plan A | Yes | No — CRITICAL curl\|bash regression | Per-sub-command Layer 0/0b | Redesign: whole-command redaction |
| Plan B | Yes | No — HIGH decoy literal (but overcalled) | F1 suppression too broad | Implement with constraints; accept threat model boundary |
| interpreter-heredoc-bypass | Yes | Independently needed | Plan A doesn't subsume it | Implement as Phase 3 |
