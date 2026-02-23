# Plan Finalization Notes -- SessionStart Auto-Activate

## Date: 2026-02-22
## Finalizer: plan-finalizer (Claude Opus 4.6)

## Process Followed

1. Read all 4 input files: action plan, implementation review, security review, author's notes
2. Ran vibe-check skill -- validated triage approach, got 3 minor adjustments
3. Consulted Gemini 3 Pro (via pal clink, planner role) on 4 tension points between reviews
4. Triaged all findings: 4 CRITICAL, 4 HIGH, 2 MEDIUM, 1 LOW
5. Applied changes to action plan using Edit tool (8 edits)
6. Verified final plan reads correctly end-to-end

## Triage Methodology

- **CRITICAL**: Both reviews agree, or single reviewer flags as must-fix with security impact
- **HIGH**: Should-fix from either reviewer with clear benefit
- **MEDIUM**: Notes/informational items worth documenting
- **LOW**: Stale notes or documentation-only items

## Key Decisions

### 1. Failure Warning (SHOULD-FIX-1) -- ADOPTED (scoped)

**Tension**: Security reviewer wanted failure warnings. Implementation reviewer's design principles said "silent in steady state."

**Resolution**: These aren't actually in tension. "Silent in steady state" means silence when config exists. The security reviewer's concern is about attempted-but-failed creation. The warning only fires on three paths: mkdir failure, mktemp failure, cp failure. Early exits (env vars missing, config exists, source missing) remain silent.

**Gemini concurrence**: Confirmed this is the right balance.

### 2. cp vs cat > for temp file (MUST-FIX-1 detail)

**Tension**: Security reviewer recommended `cat "$SOURCE" > "$TMPFILE"`. Implementation reviewer kept `cp`.

**Resolution**: Used `cp` because it preserves source file permissions (G1 finding). `cat >` creates files with umask-derived permissions, which could inadvertently restrict access.

**Gemini concurrence**: Confirmed `cp` is correct.

### 3. Trap Scope (C3) -- NOT ADOPTED

**Tension**: Implementation reviewer recommended `trap cleanup EXIT INT TERM HUP`. Security reviewer used `trap cleanup EXIT`.

**Resolution**: Kept `trap cleanup EXIT`. Gemini 3 Pro explained that bash's EXIT trap already fires on signal-induced exits. The broader set can cause double-execution (signal trap runs, then EXIT trap runs when the shell exits). `rm -f` is idempotent so double-execution is harmless, but simpler is better.

### 4. Startup Matcher (C4) -- ADOPTED with fallback

Both reviewers flagged this as high risk. Added:
- BLOCKING label in dependency table
- Verification steps (3-step process)
- Fallback strategy: omit matcher, rely on idempotency
- Callout block in Step 2

## What Changed in the Plan

### Script changes (Step 1):
- Added absolute path validation (`case` + `[ ! -d ]`)
- Moved symlink checks after `mkdir -p` (TOCTOU mitigation)
- Replaced `$$` PID with `mktemp` (CWE-377 fix)
- Replaced re-check + `mv` with `mv -n` (race condition fix)
- Added warning messages on mkdir/mktemp/cp failure paths
- Added permission-preservation comment on `cp` line
- Updated design principles to document warning behavior

### Edge case table:
- Updated 4 existing rows (concurrent, symlink, read-only, disk full)
- Added 3 new rows (relative path, non-existent path, empty config)

### Testing plan:
- Added 5 new test cases (20 total, up from 15)
- Added rationale for tests/regression/ placement

### Dependencies:
- Upgraded startup matcher to BLOCKING with verification steps and fallback

### Acceptance criteria:
- Updated 4 existing criteria
- Added 2 new criteria (relative path rejection, warning on failed creation)

### Appendices:
- Added Appendix C documenting all post-review changes with disposition
- Updated Appendix B entries to reflect adopted changes

## Frontmatter Status

Kept as `not-started` per instructions. The plan is finalized and ready for implementation, but implementation hasn't begun.

## Confidence Level

High. Both reviews converged on the same critical findings (mktemp, mv -n). The only genuine tension (failure warning scope) was resolved cleanly. All other changes are additive hardening with no architectural impact.
