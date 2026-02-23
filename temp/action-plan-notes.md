# Action Plan Working Notes -- SessionStart Auto-Activate

## Date: 2026-02-22

## Process Followed
1. Read all 7 reference files (task-b-context, research report, hooks.json, plugin.json, init.md, action-plans README, test-plan.md)
2. Read guardian.recommended.json to understand the blast radius
3. Ran vibe-check skill before writing -- got green light with 2 adjustments:
   - Guard empty env vars first (adopted: first check in script)
   - Match output to outcome (adopted: echo only runs after successful mv)
4. Consulted Gemini 3 Pro via pal clink for edge case analysis
5. Consulted Codex 5.3 via pal clink for edge case analysis
6. Synthesized all inputs into the action plan
7. Self-reviewed the written plan end-to-end

## Key Design Choices Made During Planning

### Bash vs Python
Research report proposed bash. Both Gemini and Codex suggested Python for stronger atomicity guarantees (fsync, os.replace). I kept bash because:
- SessionStart hooks use `type: "command"` -- invoking Python adds startup latency (~100ms+)
- The cp+mv pattern is sufficient for a config file (not a database)
- Consistency with the "simple shell" expectation for non-security hooks

### Atomic write strategy
Gemini and Codex both strongly recommended temp file + atomic rename. Adopted this. The temp file uses `$$` (PID) suffix for uniqueness across concurrent sessions.

### Symlink checks
Both models flagged symlink attacks. Added `-L` checks on `.claude` and `.claude/guardian` path components. Did NOT add a check on config.json itself because it doesn't exist yet (we're creating it). The check on parent dirs is sufficient.

### Concurrency handling
Codex recommended a lock directory (mkdir-based lock). I opted for the simpler re-check pattern because:
- Both sessions copy the same source file, so last-writer-wins is fine
- Lock cleanup adds complexity (what if the locking session crashes?)
- The re-check after cp catches the common race window

### CI detection
Both models suggested checking `$CI` env var. Deferred for v1 because:
- Creating the config in CI is harmless
- CI environments benefit from the same protection
- Adding conditional logic increases failure surface

## External Model Consensus
Both Gemini and Codex converged on the same top priorities:
1. Validate env vars first (HIGH risk if missing)
2. Atomic writes (HIGH risk for partial/corrupt config)
3. Symlink safety (HIGH risk for write redirection)
4. Fail-open on all errors (CRITICAL -- never block sessions)

Divergence: Gemini was more opinionated about Python, Codex was more opinionated about lock directories. Neither is needed for v1 scope.

## Sections I'm Most Confident About
- Script implementation (well-tested pattern, fail-open throughout)
- Edge case coverage (comprehensive, risk-rated, mitigated)
- Testing plan (14 specific cases matching existing test patterns)

## Sections That May Need Review Feedback
- The exact context message text (UX-sensitive, may want team input)
- Whether `startup` is truly the correct matcher (need to verify against Claude Code docs)
- Whether the symlink check should also cover config.json itself (it's a new file, but what if someone pre-creates a symlink there?)
