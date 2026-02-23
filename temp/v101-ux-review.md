# v1.0.1 UX Review

**Reviewer:** ux-reviewer
**Date:** 2026-02-22
**Scope:** Beginner clarity, false positive friction, organization, comment quality
**External input:** Gemini 3.1 Pro via pal clink

---

## Overall Assessment

The v1.0.1 fixes are well-targeted security hardening. Most changes will be invisible to typical workflows. Two patterns have notable UX friction that deserves discussion: the `crontab` ASK breadth and the `rm --force` long-flag ASK sensitivity.

---

## Pattern-by-Pattern Review

### 1. `crontab` ASK pattern -- `\bcrontab\b`

**Verdict: ADJUST -- narrow or improve reason text**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Reason clarity | Needs work | "persistence vector" is security jargon |
| False positive risk | Medium-High | `crontab -l` is read-only but triggers ask |
| Placement | Good | End of ask array, logically grouped |

**The problem:** `crontab -l` only lists existing cron jobs. Prompting the user to confirm a read-only listing operation will cause prompt fatigue, especially for sysadmins or devops users who check cron schedules frequently.

**Gemini agrees:** Rated this as "High" false positive risk and suggested narrowing to modification flags only.

**My UX recommendation (pick one):**

- **Option A (preferred):** Narrow the regex to skip `-l`: `\bcrontab\b(?!\s+-l)` -- this still catches `crontab -e` (edit), `crontab -r` (remove), `crontab file` (install from file), and `echo ... | crontab` (piped install). Only excludes the harmless list operation.
- **Option B:** Keep `\bcrontab\b` but improve the reason text. Remove jargon: `"'crontab' -- edits or installs scheduled tasks; confirm this is intended (use -l to safely list without this prompt)"`. This educates the user about why it triggered and how to avoid it.
- **Option C (Gemini's suggestion):** Narrow to `\bcrontab\s+(?:-[er]|.*<)` -- but this misses `crontab myfile` (installing from a file without flags) and piped stdin attacks (`echo "..." | crontab`), which was the explicit reason the fixer simplified the pattern.

**Recommendation:** Option A. It preserves the security coverage the fixer intended (catches piped stdin, file install, edit, remove) while eliminating the single most common false positive (`crontab -l`).

**Reason text improvement (regardless of regex choice):**
```
Current:  "'crontab' -- manages scheduled tasks (persistence vector), verify this is intended"
Proposed: "'crontab' -- can install or modify scheduled tasks, confirm this is intended"
```
Drop "persistence vector" -- it means nothing to most developers.

---

### 2. `LD_PRELOAD` / `DYLD_INSERT_LIBRARIES` BLOCK pattern

**Verdict: KEEP AS-IS (BLOCK is appropriate)**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Reason clarity | Excellent | "library injection that can intercept any system call" is clear |
| False positive risk | Low | Only matches assignment (`=`), not reads (`echo $LD_PRELOAD`) |
| Placement | Good | End of block array, with other system-level threats |

**Why BLOCK, not ASK (disagreeing with Gemini here):** Gemini suggested downgrading to ASK because systems developers use `LD_PRELOAD` for profiling (jemalloc, tcmalloc). However:

1. This config targets Claude Code's `--dangerously-skip-permissions` mode. In that context, an AI agent setting `LD_PRELOAD=` is almost certainly a prompt injection attack, not legitimate profiling.
2. A developer who needs `LD_PRELOAD` for profiling would run that command themselves outside of Claude Code, not ask an AI agent to do it.
3. The `=` requirement already prevents false positives on `echo $LD_PRELOAD`, `unset LD_PRELOAD`, `printenv | grep LD_PRELOAD`, etc.

The pattern is well-scoped. BLOCK is the right tier here.

**No changes needed to reason text.** It is clear and accurate.

---

### 3. `rm --recursive/--force` long flags ASK pattern

**Verdict: KEEP -- consistent with existing short-flag pattern**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Reason clarity | Good | Clear connection to `rm -rf` |
| False positive risk | Medium | Same as existing `rm -rf` pattern (accepted since v1.0.0) |
| Placement | Good | Near end of ask array, after existing rm patterns |

**Gemini rated this "Extremely High" false positive risk** and suggested dropping it entirely. I disagree:

1. The existing short-flag pattern `rm\s+-[rRf]+` (line 252, present since v1.0.0) already triggers ask on `rm -rf dist/`, `rm -f stale-file.txt`, etc. The new long-flag pattern is just covering the same behavior for `rm --recursive` and `rm --force`. Consistency matters -- if short flags prompt, long flags should too.
2. In the context of an AI agent running with `--dangerously-skip-permissions`, prompting on `rm --force` is appropriate. The user already opted into this guardrail system.
3. Claude Code agents rarely use `rm --force` (they typically use `rm -f`). Long-flag usage is more likely to come from scripts or unusual commands where an extra confirmation is reasonable.

**One minor reason text improvement:**
```
Current:  "'rm --recursive/--force' (long flags) -- same as 'rm -rf', review the target path"
Proposed: "'rm --recursive/--force' (long flags) -- review the target path before confirming"
```
The "(long flags)" parenthetical is slightly confusing for beginners who may not know what "long flags" means. But this is a very minor point -- the current text is acceptable.

---

### 4. Strengthened `curl|bash` BLOCK pattern

**Verdict: KEEP AS-IS (excellent improvement)**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Reason clarity | Good | "remote script execution" is widely understood |
| False positive risk | Low | Trailing `(?:\s|$)` prevents `bash-formatter` etc. |
| Placement | Good | Same position as before, just strengthened |

**Gemini suggested downgrading to ASK** because `curl | bash` is used for installing nvm, rustup, poetry, etc. I disagree for the same reason as LD_PRELOAD: in `--dangerously-skip-permissions` mode, an AI agent piping curl to bash is a high-severity prompt injection risk. Users who need to install tools this way can do so outside of the AI session.

The trailing boundary fix (`(?:\s|$)`) is a meaningful UX improvement -- it prevents false positives on commands like `curl ... | bash-completion-helper` or `curl ... | bashcov`. Well done.

**No changes needed.**

---

### 5. `rm` long-flags root deletion BLOCK pattern

**Verdict: KEEP AS-IS**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Reason clarity | Good | "root filesystem deletion using long flags" is clear |
| False positive risk | Zero | No legitimate use of `rm --recursive / ` |
| Placement | Good | Right after existing `rm -rf /` block pattern |

No concerns. Zero false positive risk. Reason text is clear. Logical placement in the config.

---

### 6. `.git/hooks/**` in readOnlyPaths

**Verdict: KEEP AS-IS (good scoping)**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Clarity | Good | Scoped to hooks only, not all of .git/ |
| False positive risk | Very Low | Developers rarely edit git hooks via AI agent |
| Placement | Good | End of readOnlyPaths, after `.venv/**` and `vendor/**` |

The fix notes explain the scoping decision well: `.git/hooks/**` rather than `.git/**` because users may need to edit `.git/config` or `.git/info/exclude`. This is thoughtful.

---

## Organization Review

The new entries are placed logically:
- **Block patterns:** New entries (rm long-flags root, LD_PRELOAD) are at the end of the block array, which is fine. They could arguably be grouped with related patterns (LD_PRELOAD near other system-level blocks, rm near other rm blocks), but end-of-list is acceptable and avoids churn.
- **Ask patterns:** New entries (rm long-flags, crontab) are at the end of the ask array. Same comment applies.
- **readOnlyPaths:** `.git/hooks/**` is at the end, after vendor paths. Fine.

**Minor suggestion:** If a future reorganization happens, consider grouping patterns by category (filesystem, git, network, system) within each tier. Not urgent.

---

## Comment Quality Review

The top-level `$comment` in `bashToolPatterns` is comprehensive and helpful. It explains what block vs. ask means, mentions regex101.com for testing, and tells users they probably don't need to edit these. Good for beginners.

Individual pattern `reason` fields are generally clear. Only one needs adjustment:
- **crontab:** Remove "persistence vector" jargon (see recommendation above).

---

## Summary of Recommendations

| Pattern | Action | Priority |
|---------|--------|----------|
| crontab ASK | Narrow regex to `\bcrontab\b(?!\s+-l)` and remove "persistence vector" from reason | Medium |
| LD_PRELOAD BLOCK | Keep as-is | -- |
| rm long-flags ASK | Keep as-is (minor reason text tweak optional) | Low |
| curl\|bash BLOCK | Keep as-is | -- |
| rm long-flags root BLOCK | Keep as-is | -- |
| .git/hooks readOnly | Keep as-is | -- |

**Overall: 1 medium-priority change (crontab), 1 low-priority optional tweak (rm reason text), 4 patterns approved as-is.**

---

## Gemini Feedback Integration Notes

Gemini provided useful perspective but several suggestions were too permissive for the threat model:
- **Downgrading `curl|bash` to ASK:** Rejected. In `--dangerously-skip-permissions` mode, AI agent piping curl to a shell interpreter is almost always a prompt injection, not a legitimate install workflow.
- **Downgrading `LD_PRELOAD` to ASK:** Rejected. Same reasoning -- legitimate profiling happens outside AI agent sessions.
- **Dropping `rm --force` long-flag ASK:** Rejected. Inconsistent with the existing short-flag `rm -rf` ASK pattern that has been present since v1.0.0.
- **Narrowing crontab regex:** Partially adopted. Gemini's specific regex suggestion (`\bcrontab\s+(?:-[er]|.*<)`) was too narrow (misses `crontab myfile`), but the core insight about `crontab -l` false positives is valid. Proposed `\bcrontab\b(?!\s+-l)` as a better middle ground.
