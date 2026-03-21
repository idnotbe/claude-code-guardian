# V1 Completeness Verification: heredoc-scanning-redesign.md

**Date**: 2026-03-21
**Verifier**: Claude Opus 4.6 (1M context)
**Cross-model**: Gemini 3.1 Pro (via PAL clink)
**Overall Verdict**: PASS WITH CONCERNS (2 minor, 0 blocking)

---

## 1. Format Compliance

**Verdict: PASS**

- Frontmatter present with `status: not-started` and `progress` field -- correct.
- Checkmark format uses `- [ ]` for not-started items -- matches README spec (`[ ]` = not started).
  - Note: When marking items done, use `[v]` per README, not `[x]`.
- Phases are clearly ordered (Phase 0, 1, 2, 3) with dependencies stated.
- Each phase has sub-items with progress checkmarks.

## 2. Supersession Completeness

**Verdict: PASS**

### Plan A (heredoc-pattern-false-positives.md) -- fully superseded

| Plan A Element | Unified Plan Location | Status |
|----------------|----------------------|--------|
| `_DATA_HEREDOC_COMMANDS` allowlist | Phase 1b `_PASSIVE_DATA_SINKS` | Kept, renamed |
| `_is_data_heredoc_command()` | Phase 1b `_classify_heredoc_safety()` + `_extract_base_command()` | Replaced with better design |
| Removal of sed/mysql/psql/sqlite3 | Phase 1b -- these are absent from `_PASSIVE_DATA_SINKS` | Kept |
| Backslash delimiter fix | Phase 0a | Kept |
| ANSI-C quoting fix | Phase 0a | Kept (Plan A mentioned it only in edge cases; unified plan promotes to Phase 0) |
| Wrapper-flag handling (fail-closed) | Phase 1b `_extract_base_command()` rule 5 | Kept |
| Pipe-to-interpreter mitigation | Phase 1b Rule 3 (pipeline member -> UNSAFE) | Redesigned (Plan A's was structurally broken) |
| Per-sub-command Layer 0/0b | Phase 1c whole-command redaction | Discarded (caused curl\|bash regression) |
| Unterminated heredoc fail-closed | Phase 1d traced attack: "Unterminated heredoc: fail-closed, body retained" | Kept |
| Test structure | Phase 1e | Kept, expanded |
| `_is_data_heredoc_command()` fail-open default | Phase 1b Rule 5 (unknown -> UNSAFE) | Fixed architecturally |

**No valuable Plan A content missing.**

### Plan B (interpreter-path-resolution.md) -- fully superseded

| Plan B Element | Unified Plan Location | Status |
|----------------|----------------------|--------|
| `extract_paths_from_interpreter_payload()` | Phase 2a | Kept |
| Regex string literal extraction | Phase 2a | Kept |
| URL filtering | Phase 2a | Kept |
| Path validation within project | Phase 2a | Kept |
| Glob expansion | Phase 2a -- restricted to project-internal only | Constrained (security improvement) |
| F1 block modification | Phase 2b | Kept |
| Enriched F1 ASK messages | Phase 2c | Kept (can ship independently) |
| Fail-closed design | Phase 2a/2b | Kept |
| AST-based Python extraction (optional) | Not in unified plan | Dropped -- acceptable (was optional Phase 2 in Plan B) |
| Documented regex limitations | Phase 2a line 127 | Kept |
| Decoy literal analysis | Phase 2 design notes | Kept with threat model justification |

**One minor omission**: Plan B's optional "AST-based extraction for Python" (Phase 2 enhancement) is not mentioned. This was explicitly optional in Plan B, so omission is acceptable. Not blocking.

### interpreter-heredoc-bypass.md -- correctly NOT superseded

The unified plan incorporates it as Phase 3 while explicitly stating "NOT superseded, incorporated as Phase 3" and "The original plan document remains valid." This is correct per the final-verdict.md finding that Plan A's subsumption claim was invalid.

## 3. Phase Dependencies

**Verdict: PASS**

| Dependency Claim | Verification | Correct? |
|-----------------|--------------|----------|
| Phase 0 has no dependencies | Bug fixes in `_parse_heredoc_delimiter()` and re.MULTILINE audit are independent | Yes |
| Phase 1 depends on Phase 0 | Phase 1 modifies `split_commands()` which calls `_parse_heredoc_delimiter()`. The backslash fix must land first. | Yes |
| Phase 2 is independent of Phase 1 | Phase 2 modifies F1 block (lines 1474-1481) in the per-sub-command loop. Phase 1 modifies Layer 0/0b input (whole-command redaction). They touch different code paths. | Yes -- confirmed by both code analysis and Gemini review |
| Phase 3 depends on Phase 1 | Phase 3 adds ASK for interpreter heredocs in the per-sub-command loop. Phase 1 changes what bodies are retained in sub-commands. Phase 3's `_is_interpreter_heredoc()` checks the sub-command string, which is unaffected by Phase 1's redaction (redaction only affects the string passed to Layer 0/0b). | **Weak dependency** -- Phase 3 could technically run independently. The stated dependency is conservative (safe). |

## 4. Test Coverage

**Verdict: PASS**

### Plan A false positive scenarios addressed:

| Scenario | Unified Plan Test Coverage |
|----------|--------------------------|
| C: git push --force in tutorials | Phase 1e: "git push --force... still detected" (line 111) |
| D: find -delete in cleanup notes | Phase 1e: safe redaction tests for `cat << EOF` with dangerous body |
| E: shred in security docs | Covered by general safe redaction test pattern |
| F: curl\|bash in install docs | Phase 1e: "Pipeline preservation: curl ... \| bash unchanged in redacted string" (line 108) |
| G: rm -rf in cleanup docs | Phase 1e: safe redaction tests |
| H: git reset --hard in troubleshooting | Covered by general safe redaction test pattern |
| I: SQL in seed data | Covered by general safe redaction test pattern |
| A/B: rm -rf / in heredoc | Correctly identified as NOT actual false positives. Not tested as FP fixes. |

### Plan B edge cases addressed:

| Edge Case | Unified Plan Coverage |
|-----------|----------------------|
| Variable-only paths (fail-closed) | Phase 2d line 144 |
| Obfuscated paths (fail-closed) | Phase 2d line 145 |
| URL strings (filtered) | Phase 2d line 146 |
| Non-interpreter commands | Phase 2d line 147 |
| Security regression (single-line) | Phase 2d line 148 |

**All critical false positive scenarios from Plan A are addressed. All edge cases from Plan B are addressed.**

## 5. Consistency (File Paths, Line Numbers, Function Names)

**Verdict: CONCERN (minor)**

### Line number audit:

| Plan Reference | Actual Codebase | Match? |
|---------------|----------------|--------|
| `_parse_heredoc_delimiter()` lines 443-473 | Lines 443-473 | Yes -- exact |
| `_consume_heredoc_bodies()` lines 476-506 | Lines 476-506 | Yes -- exact |
| `split_commands()` lines 270-441 | Function defined at line 82, body extends to ~441 | **Partial** -- "270-441" refers to the mid-body section being modified, not the function start. Ambiguous but defensible. The heredoc-related logic within split_commands is indeed in this range. |
| `main()` lines 1419-1442 | Lines 1419-1442 confirmed | Yes -- exact |
| F1 block lines 1474-1481 | Lines 1474-1481 confirmed | Yes -- exact |
| `extract_paths()` near line 980 | `extract_paths()` defined at line 898; `glob.glob()` at line 971 | **Minor mismatch** -- plan says "near line 980" for the new function location, referring to where it should be placed. The existing `extract_paths()` ends at line 988, so placing the new function near line 980-989 is reasonable. |
| `match_block_patterns` at `_guardian_utils.py` line 872 | Line 872 confirmed (re.DOTALL usage) | Yes -- but this is Plan A's reference, not in the unified plan |
| Block patterns in config lines 11-83 | Lines 11-84 (block array) | Yes -- close enough (off by 1 on closing bracket) |
| Ask patterns in config lines 85-158 | Lines 85-158 | Yes -- exact |
| Per-sub-command loop line 1461 | Line 1461 confirmed | Yes -- exact |

### Function names:

| Plan Function Name | Exists in Codebase? | Notes |
|-------------------|-------------------|-------|
| `_parse_heredoc_delimiter()` | Yes (line 443) | Correctly referenced for Phase 0 fix |
| `split_commands()` | Yes (line 82) | Correctly referenced for Phase 1 modification |
| `_consume_heredoc_bodies()` | Yes (line 476) | Correctly referenced |
| `_classify_heredoc_safety()` | New (Phase 1b) | Clearly marked as new |
| `_extract_base_command()` | New (Phase 1b) | Clearly marked as new |
| `extract_paths_from_interpreter_payload()` | New (Phase 2a) | Clearly marked as new |
| `_is_interpreter_heredoc()` | New (Phase 3a) | Clearly marked as new |
| `extract_paths()` | Yes (line 898) | Correctly referenced |
| `match_block_patterns()` | Yes (_guardian_utils.py:841) | Referenced indirectly |
| `match_ask_patterns()` | Yes (_guardian_utils.py:1013) | Referenced indirectly |

**The `split_commands()` line range "270-441" is ambiguous.** It appears to reference the section of the function body being modified rather than the function definition start. Should be clarified as "within split_commands() (defined at line 82), specifically the heredoc handling section at lines 270-441" or simply cite the specific modification points (lines 398-428 for heredoc detection, 420-428 for newline handler).

## 6. Adversarial Corrections from final-verdict.md

**Verdict: PASS**

| Correction | Where in Unified Plan | Incorporated? |
|-----------|----------------------|---------------|
| Scenarios A/B are NOT actual FPs | Section "What is NOT broken" lines 28-29 | Yes -- explicitly stated with rationale |
| re.MULTILINE is double-edged | Phase 0b (audit, defer to after Phase 1) + "What is NOT broken" line 30 | Yes -- correctly deferred with per-pattern audit |
| Generated executable bypass is pre-existing | "What is NOT broken" line 29 | Yes -- explicitly called out |
| Plan B not dismissed | Phase 2 exists; Supersedes section "Not discarded" (line 251) | Yes -- with explicit justification about alert fatigue vs theoretical attack |
| interpreter-heredoc-bypass.md NOT subsumed | Phase 3 + Supersedes section line 255-257 | Yes -- "NOT superseded, incorporated as Phase 3" |
| `_is_data_heredoc_command()` fail-open | Architectural fix via Rule 5 (unknown -> UNSAFE) in `_classify_heredoc_safety()` | Yes -- fixed by design |

**All 6 corrections from final-verdict.md are properly incorporated.**

## 7. Missing Items

**Verdict: PASS WITH CONCERN (1 minor)**

### Items from final-verdict.md NOT in unified plan:

1. **"Alternative worth investigating" -- redirection-based heredoc exemption** (final-verdict.md lines 117-118): The final verdict suggested evaluating a simpler alternative: exempt heredoc bodies when `>` is present instead of maintaining a full command allowlist. The unified plan incorporates this as Rule 2 of the classifier but does NOT discuss it as a potential simplification of the overall approach. This is acceptable -- the plan chose the hybrid approach which is strictly more capable.

2. **Plan B's optional AST-based Python extraction**: Mentioned above in Section 2. Not blocking.

3. **"Process Learnings" from final-verdict.md** (lines 132-139): These are meta-process observations, not implementation requirements. Not expected in an action plan.

### Items from original plans NOT in unified plan:

1. **Plan A's `less` and `more` in data command list**: Plan A included `less`, `more` in `_DATA_HEREDOC_COMMANDS`. The unified plan's `_PASSIVE_DATA_SINKS` does NOT include `less` or `more`. This is a deliberate omission (these are interactive pagers, less relevant for heredoc use). Acceptable.

2. **Plan A's `csvtool`**: Present in Plan A but absent from unified plan's `_PASSIVE_DATA_SINKS`. Minor -- `csvtool` is uncommon. Fails closed (treated as unknown -> UNSAFE).

## 8. Effort Estimates

**Verdict: PASS**

| Phase | Plan Estimate (Code LOC) | Assessment |
|-------|-------------------------|------------|
| Phase 0: ~20 LOC | Backslash fix (~5 lines) + ANSI-C handler (~10 lines) = ~15 lines. Audit is documentation, not code. | Reasonable |
| Phase 1: ~150 LOC | New `_classify_heredoc_safety()` (~30), `_PASSIVE_DATA_SINKS` + `_INTERPRETER_COMMANDS` (~10), `_extract_base_command()` (~25), `_OUTPUT_REDIR_PATTERN` (~5), `split_commands()` modifications (~30), `_consume_heredoc_bodies()` modification (~20), `main()` changes (~15) = ~135 | Reasonable -- slightly conservative |
| Phase 2: ~80 LOC | `extract_paths_from_interpreter_payload()` (~40), F1 block modification (~20), ASK enrichment (~10) = ~70 | Reasonable |
| Phase 3: ~25 LOC | `_is_interpreter_heredoc()` (~20) + loop integration (~5) = ~25 | Accurate |
| Test LOC: ~440 total | 10 + 25 + 15 + 10 = 60 methods. At ~7 LOC/method average = ~420. | Reasonable |

**Session estimates (3-4 total) appear realistic for a careful implementation with testing.**

---

## Summary

| Section | Verdict | Notes |
|---------|---------|-------|
| 1. Format compliance | PASS | Uses correct checkmark format |
| 2. Supersession completeness | PASS | All Plan A and Plan B content accounted for |
| 3. Phase dependencies | PASS | Dependencies correct; Phase 3 dependency is conservative |
| 4. Test coverage | PASS | All FP scenarios and edge cases addressed |
| 5. Consistency | CONCERN (minor) | `split_commands()` line range "270-441" is ambiguous; should clarify it refers to the mid-body modification zone, not the function start (line 82) |
| 6. Adversarial corrections | PASS | All 6 corrections from final-verdict.md incorporated |
| 7. Missing items | CONCERN (minor) | Plan B's optional AST extraction not mentioned; `less`/`more`/`csvtool` dropped from allowlist (all acceptable, all fail-closed) |
| 8. Effort estimates | PASS | Reasonable and conservative |

### Cross-model validation (Gemini 3.1 Pro)

Gemini independently confirmed:
1. Whole-command redaction avoids curl|bash regression -- CONFIRMED
2. Phase 2 loses nothing important from Plan B -- CONFIRMED (glob restriction is deliberate security improvement)
3. Phase 1/Phase 2 independence is correct -- CONFIRMED
4. No goals from either original plan are unaddressed -- CONFIRMED

Two low-risk implementation notes from Gemini:
- Phase 1b pipeline rule: verify `piped_heredocs` correctly distinguishes "heredoc feeds a pipe" from "heredoc after a pipe"
- Ensure no token merging from newline-replaced body content

### Final Verdict

**PASS WITH CONCERNS (2 minor, 0 blocking)**

The unified plan is complete, architecturally sound, and ready for implementation. The two minor concerns (ambiguous line range reference, dropped optional items) do not affect correctness or security.
