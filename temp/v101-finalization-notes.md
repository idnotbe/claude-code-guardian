# v1.0.1 Config Finalization Notes

**Date:** 2026-02-22
**Finalizer:** config-finalizer
**Config:** `assets/guardian.recommended.json`
**Inputs:** Security review, UX review, fixer notes, Gemini 3.1 Pro (via pal clink)

---

## Changes Applied

### 1. Version bump: `1.0.0` -> `1.0.1`
Required to mark this as the v1.0.1 release config.

### 2. Crontab regex narrowed (MEDIUM priority)
- **Old:** `\bcrontab\b`
- **New:** `\bcrontab\b(?!\s+-l\b)`
- **Source:** UX review (Option A), refined by Gemini word-boundary fix
- **Rationale:** `crontab -l` is a read-only listing operation. Prompting on it causes prompt fatigue, especially for devops users who check cron schedules frequently. The negative lookahead with word boundary `\b` excludes only the isolated `-l` flag while still catching:
  - `crontab -e` (edit) -- MATCH
  - `crontab -r` (remove) -- MATCH
  - `crontab -lr` (combined flags with destructive action) -- MATCH
  - `crontab mycronfile` (install from file) -- MATCH
  - `echo "..." | crontab` (piped stdin attack) -- MATCH
  - `crontab -l; crontab -e` (chained commands) -- MATCH (second crontab caught)
  - `crontab -l` (list only) -- NO MATCH (correctly excluded)
  - `crontab -l -u root` (list for user) -- NO MATCH (correctly excluded)
  - `crontab -l | grep job` (list piped to grep) -- NO MATCH (correctly excluded)
- **Gemini contribution:** Identified that the UX-proposed `(?!\s+-l)` (without word boundary) would bypass on `crontab -lr`. The `\b` fix closes this gap.

### 3. Crontab reason text improved (MEDIUM priority)
- **Old:** `"'crontab' -- manages scheduled tasks (persistence vector), verify this is intended"`
- **New:** `"'crontab' -- can install or modify scheduled tasks, confirm this is intended"`
- **Source:** UX review
- **Rationale:** "persistence vector" is security jargon that means nothing to most developers. The new text is clearer and accurately describes the risk since we now exclude the read-only `-l` operation.

---

## Changes NOT Applied (with rationale)

### rm long-flags reason text tweak (LOW priority, optional)
- UX review suggested: `"'rm --recursive/--force' (long flags) -- review the target path before confirming"`
- Decision: Keep current text. The existing text `"same as 'rm -rf', review the target path"` is clear and the improvement is marginal. Avoids unnecessary churn.

### All other patterns (approved as-is by both reviews)
- LD_PRELOAD BLOCK -- keep (security + UX agree BLOCK is correct tier)
- curl|bash BLOCK -- keep (security + UX agree BLOCK is correct tier)
- rm long-flags root BLOCK -- keep (zero false positive risk)
- rm long-flags ASK -- keep (consistent with existing short-flag pattern)
- .git/hooks readOnly -- keep (well-scoped, approved by both)

---

## Conflict Resolution

**No conflicts between security and UX reviews.** Both approved all 4 original fixes. The only actionable feedback was from UX (narrow crontab regex), which security also noted as a LOW false positive. Gemini provided the critical word-boundary refinement that made the crontab narrowing safe.

---

## Validation Results

| Check | Result |
|-------|--------|
| JSON valid | PASS |
| Version = 1.0.1 | PASS |
| All 56 regex patterns compile | PASS |
| Zero false positives (27 safe commands) | PASS |
| Crontab -l excluded | PASS |
| Crontab -lr still caught | PASS |
| Crontab piped stdin still caught | PASS |
| Block patterns: 27 | Correct |
| Ask patterns: 29 | Correct |
| readOnlyPaths: 19 | Correct |
| zeroAccessPaths: 41 | Correct |
| noDeletePaths: 33 | Correct |

---

## Summary

Three changes applied to `guardian.recommended.json`:
1. Version bump to 1.0.1
2. Crontab regex narrowed with word-boundary-safe negative lookahead
3. Crontab reason text de-jargoned

The config is ready for v1.0.1 release.
