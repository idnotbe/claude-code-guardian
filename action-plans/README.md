# Action Plans

Execution plan management directory for `claude-code-guardian`.

## Structure

- Root `.md` files (excluding `README.md`) = active plans (`not-started`, `active`, `blocked`)
- `_done/` = completed plans
- `_ref/` = reference / historical multi-team plans

## Frontmatter Rules

All plan files must have YAML frontmatter at the top:

```yaml
---
status: not-started    # not-started | active | blocked | done
progress: "Not started"  # Current progress (free text)
---
```

## Status Values

- **not-started**: Work has not begun
- **active**: Currently in progress
- **blocked**: Waiting on unresolved dependencies
- **done**: Completed -> **must** move to `_done/`

## Action Plan File Structure

Action plan files must contain ordered actions (`phase1`, `phase2`... or `step1`, `step2`...).

Each step must have a progress checkmark:

- `[v]` = done
- `[ ]` = not started
- `[/]` = in progress

Example:

```markdown
## Phase 1: Initial Setup
- [v] Configure environment
- [v] Install dependencies

## Phase 2: Implementation
- [/] Develop core feature
- [ ] Write tests
```

When all steps are marked `[v]`, the entire plan is done. Update frontmatter to `status: done` and move the file to `_done/`.

## High-Risk Surface (defined once, referenced everywhere)

A plan is **high-risk** if it touches any of these paths:

- `hooks/scripts/` -- all guardian hooks (Bash/Edit/Read/Write/Stop/SessionStart logic)
- `assets/guardian.*.json` -- config schema, defaults, recommended (security contract)
- `hooks/hooks.json` -- hook registration (controls which guardians fire)
- `.claude-plugin/plugin.json` -- plugin metadata / discovery
- `tests/security/` -- tampering with security tests masks regressions
- `tests/conftest.py`, `tests/_bootstrap.py` -- test infrastructure (a `pytest.skip` here silently disables enforcement; protect the infra files without escalating every routine test edit)
- `CLAUDE.md`, `action-plans/README.md` -- governance recursion: these files *are* the rules, so weakening them via a "lightweight" edit would let the next plan exploit relaxed enforcement

Behavioral rule: any plan modifying these is high-risk and triggers stricter alignment, full test verification, security-invariant re-check, hard exclusion from lightweight, and mandatory 2-round verification (per the Teammate Execution Protocol below). The narrower CLAUDE.md test rule -- "any PR touching `hooks/scripts/*guardian*.py` or `_guardian_utils.py` MUST include tests" -- is a *behavior* rule (covered separately, see "Two Distinct Rules" below); high-risk surface is the *governance* rule.

## Lifecycle (Full Execution Protocol)

Every action plan follows this **mandatory multi-phase lifecycle**. Unless explicitly classified as a **Lightweight plan** (see below), skipping any phase is a blocking error.

```
Phase 0: Docs-Plan Alignment  -->  Gap list + Impact + Drafts in temp/
    |
Phase 1-N: Execution           -->  Document/system changes + temp/ working memory
    |
Phase F-1: Docs Sync           -->  Apply drafts to live docs, verify consistency
    |
Phase F: Commit & Push          -->  Commit impl+docs, flip status, commit closure, push
```

### Phase 0: Docs-Plan Alignment (GATE -- must complete before any plan execution)

1. **Read current docs** -- guardian's primary surfaces:
   - `CLAUDE.md` -- dev rules, testing requirements, security invariants, coverage table, known gaps. *(References to `action-plans/_done/` plans inside CLAUDE.md are historical anchors, not live constraints.)*
   - `README.md` -- plugin overview, repo layout
   - `CHANGELOG.md` -- user-facing release notes
   - `KNOWN-ISSUES.md` -- documented security gaps and workarounds
   - `tests/README.md` -- test layout, category boundaries, how to add tests
   - `assets/guardian.{schema,default,recommended}.json` -- config contract
   - **Situational** (read when plan touches hook wiring or plugin discovery):
     - `hooks/hooks.json` -- hook registration manifest
     - `.claude-plugin/plugin.json` -- plugin metadata

2. **Diff against plan**: Compare current surfaces with plan goals. Produce a **gap list**:
   - New behavior (not in docs/config)
   - Changed behavior (docs and plan conflict)
   - Removed behavior (plan deprecates)

3. **Impact assessment**: Per gap, estimate change scope, affected scripts (`bash_guardian.py`, `_guardian_utils.py`, etc.), test surface, and risk to security invariants. Cross-reference the **High-Risk Surface** definition above; if any path matches, flag the plan as high-risk.

4. **Draft planned doc/config changes** in `temp/{plan-name}-phase0-drafts.md`. Do NOT mutate live docs at this stage -- keep all proposed content in `temp/` until Phase F-1 finalization.

   > **Mandatory drafts**: Any change to source code (`hooks/scripts/`) or tests requires a Phase 0 draft for at least the CLAUDE.md coverage-table update (LOC drift, test counts, or coverage status). "No documentation impact" is not a valid declaration when source or tests are touched.

   If the plan truly has no source/test/doc impact (e.g., reorganizing `_ref/`), record "No documentation impact" in the alignment doc -- a separate drafts file is then not required.

5. Write gap list and impact assessment to `temp/{plan-name}-phase0-alignment.md`.

6. **Gate check**: Alignment doc must exist (and drafts, if doc/config changes are planned) before Phase 1.

> **High-risk plans**: Phase 0 must explicitly enumerate which security invariants the change touches. For the authoritative list, see CLAUDE.md "Security Invariants" -- including both the fail-closed rules (Bash/Edit/Read/Write hooks, output contract, thin wrappers) and the fail-open-by-design rules (`auto_commit.py`, `session_start.sh`).

### Phase 1--N: Execution

- Standard lifecycle: `status: active`, update progress, mark `[v]/[/]/[ ]` per step.
- Use `temp/` as **working memory**: intermediate analysis, attack traces, verification reports, multi-model review notes.
- If changes affect **another active plan**, add: `> WARNING -- IMPACT: {this-plan-name} changed {script/contract}. Review required.`
- Tests are part of execution, not a separate phase. See "Two Distinct Rules" below for what counts.

> **Blocked plans**: Plans with `status: blocked` should document: (a) unblock condition, (b) next review date. Plans blocked >90 days should be reviewed for archival or dependency resolution.

### Phase F-1: Docs Sync (GATE -- must complete before commit)

1. **Reconcile execution-phase drift first**: Any deviation from the Phase 0 draft (new files touched, scope expansion, abandoned changes) **MUST** be reconciled into `temp/{plan-name}-phase0-drafts.md` BEFORE applying anything to live docs. The draft file is the source of truth for the live doc update; an unreconciled draft means the live update is wrong.

2. **Apply planned doc/config changes**: Integrate the (now-reconciled) draft into the live primary surfaces. Targets, by plan scope:

   | Live surface | Update when |
   |--------------|-------------|
   | `CLAUDE.md` -- coverage table | Test coverage, LOC, or known-gaps changed |
   | `CLAUDE.md` -- known gaps / security invariants | New gap discovered, or gap closed |
   | `KNOWN-ISSUES.md` | New user-visible gap or workaround surfaced |
   | `README.md` | Repo layout, hook surface, or onboarding flow changed |
   | `CHANGELOG.md` | Any user-visible behavior change shipped |
   | `tests/README.md` | Test directory layout or category boundaries changed |
   | `assets/guardian.{schema,default,recommended}.json` | Config keys added/removed/renamed |
   | `hooks/hooks.json` | Hook event registration changed -- which guardian fires when AND the exact command line that runs (a stray `\|\| true` here silently breaks fail-closed) |
   | `.claude-plugin/plugin.json` | Plugin metadata, version, or component declarations changed |

3. **Docs-plan consistency**: Verify all live surfaces match the completed plan state exactly.

4. **Test verification (canonical command)**: For high-risk plans, run the **full** test suite, not a subset:

   ```
   python -m pytest tests/ -v
   bash tests/test_bash_behavior.sh
   bash tests/test_bash_syntax.sh
   ```

   The pytest invocation is intentionally broader than CLAUDE.md's Quick Reference (`tests/core/ tests/security/ -v` and `tests/core/ tests/security/ tests/regression/ -v`); those are the unittest-compatible *subset* used during development, while plan finalization needs the full `tests/` directory so `usability/`, `patterns/`, `review/`, and any future subdirectories aren't silently skipped. The two `bash` scripts are required because pytest's discovery only matches `test_*.py` and ignores `.sh` files entirely. Standalone `.py` verification scripts under `tests/patterns/` (e.g., `verify_bypass.py`) are also outside pytest's filename pattern and must be run explicitly when the plan touches a pattern they cover.

5. **Security-invariant re-check** (high-risk plans only): Re-verify against CLAUDE.md "Security Invariants" -- both the fail-closed rules (Bash/Edit/Read/Write deny on error/timeout, JSON `permissionDecision` contract, thin wrapper rule) and the fail-open-by-design rules (auto-commit and SessionStart must not block on internal failures). Use CLAUDE.md as the source of truth, not this README.

6. **Cross-plan check**: Confirm changes don't break other active plans' assumptions; update if needed.

7. **Staleness check**: If the plan was blocked or dormant for >2 weeks, re-verify `temp/` drafts against current live docs/code before applying.

### Phase F: Commit & Push (GATE -- final, commit-implementation-first)

The order matters. A session crash mid-finalization must never leave a "done" plan with no implementation in HEAD.

1. **Commit implementation + doc changes** (Phase F-1 outputs first):
   - `git add` -- by name -- all source/test/doc changes produced during Phase 1-N and Phase F-1.
   - `git commit` -- message describes the implementation + doc-sync work.

2. **Flip plan status** (atomic pair with step 3 -- no other operations between): Update frontmatter to `status: done`, set `progress` to a final summary. `git mv` the plan file to `_done/`.

3. **Commit plan closure** (atomic pair with step 2 -- no other operations between): `git add` the moved plan + any `_done/` index updates; `git commit` with a message like `chore: mark {plan-name} done`. Steps 2 and 3 must run back-to-back so a Stop event between them cannot leave the move staged-but-uncommitted on disk while the remote still shows the plan active.

4. **Pre-push self-check**: Run `git status` -- the working tree must be clean. If it is *not* clean, the most likely cause is that auto-commit fired between steps 2 and 3 and already created the closure commit; in that case, push the auto-commit's result rather than creating a duplicate commit. Do not amend or rewrite history to "tidy" the auto-commit -- just push.

5. **Push**: `git push` to remote.

> The Stop-event auto-commit hook (`auto_commit.py`) **may create a checkpoint commit if it is enabled and tracked changes still remain at session end** (it skips otherwise). If `includeUntracked` is enabled in guardian config, untracked files are also staged. Auto-commit aborts entirely with no checkpoint created if `git_add_filtered` detects unstaged secrets in the changeset -- secret-abort takes precedence over checkpointing. If a checkpoint does fire after the explicit pushes above, it can leave a second local commit out of sync with the remote -- a follow-up `git push` may be needed. Auto-commit is fail-open by design, so this is best-effort hygiene, not a correctness boundary; the explicit two-commit ordering above is what guarantees plan closure is durable.

### Lightweight Plans

A plan may use the abbreviated lifecycle **only if all** of the following hold:

- It does not touch any path in **High-Risk Surface** (above). This is hard-exclusion: any change under `hooks/scripts/`, `assets/guardian.*.json`, `hooks/hooks.json`, `.claude-plugin/plugin.json`, anywhere under `tests/`, `CLAUDE.md`, or this `action-plans/README.md` makes the plan ineligible.
- It has no security-invariant impact.
- It is bounded to single-doc updates, typo fixes, comment-only changes, or `_ref/` housekeeping.

Lightweight steps:

- **Phase 0**: brief alignment check inline in the plan file (no separate `temp/` alignment doc required) -- list which primary surfaces are affected.
- **Phase 1-N**: as normal.
- **Phase F-1**: single verification round; skip security-invariant re-check.
- **Phase F**: same commit-implementation-first ordering as the full lifecycle.

**Self-grading fallback**: When in doubt, default to the full lifecycle. If any test fails during development, the plan **automatically loses lightweight eligibility** regardless of original file scope -- promote it to full lifecycle and run Phase F-1 step 4 in full.

## Two Distinct Rules (Tests vs Verification)

These are often confused. Keep them separate.

**Rule A -- Tests required for behavior changes** (per CLAUDE.md): any PR touching `hooks/scripts/*guardian*.py` or `_guardian_utils.py` MUST include tests covering the changed behavior. This is a *PR-level* behavior rule and applies regardless of lightweight/full classification. It governs the *content* of the change.

**Rule B -- 2-round verification required for high-risk surface changes** (per High-Risk Surface above): plans modifying high-risk surface require two independent verification rounds (per the Teammate Execution Protocol below). This is a *process* rule. It governs the *workflow* of the change.

In practice, **Rule A always implies Rule B**: every `*guardian*.py` and `_guardian_utils.py` file lives under `hooks/scripts/`, which is high-risk, so any A-triggering change is automatically B-triggering as well. The reverse is not true -- Rule B can fire without Rule A. Example: reorganizing `tests/security/` triggers Rule B (high-risk path) but not Rule A (no `*guardian*.py` change). Keeping the rules nominally separate matters because they answer different questions: A is "did you write tests for the new behavior?", B is "did two independent reviewers verify the workflow?"

## Teammate Execution Protocol

Non-trivial action plans use **subagent spawn**-based parallel work and multi-round verification.

**This section is normative for high-risk plans** (per High-Risk Surface). For lightweight plans, it is recommended-but-optional -- vibe-check and a single PAL clink are still good practice, but full subagent orchestration is not required.

### Subagent Spawn Rules

- Spawn specialist subagents per task (e.g., `research`, `docs-sync`, `verifier-1`, `verifier-2`).
- Each subagent **actively uses its own sub-tools** for independent exploration/analysis/drafting.
- **Minimize context transfer**:
  - Long content -> `temp/{topic}.md`.
  - Inter-subagent messages: **1-2 line summary + file link only**.

### Vibe Check & Multi-Model Verification (PAL MCP Clink)

At every critical decision point, each subagent **independently** performs:

1. **Vibe Check**: Self-critique against the following checklist:
   - **Gaps**: Missing requirements or unhandled bypass cases?
   - **Contradictions**: Conflicts between CLAUDE.md, plan, and config schema?
   - **Edge cases**: Hook timing, fail-closed boundaries, interpreter-mediated bypass, heredoc/quoting tricks?
   - **Security**: Does this preserve fail-closed end-to-end? Does it weaken any deny path? Does it weaken the fail-open boundary on auto-commit / SessionStart?
   - **Tests**: Is the new behavior covered? Do existing tests still pass?
2. **PAL MCP Clink**: Multi-model comparison via the `pal` MCP server (e.g., codereview, precommit, debug). Compare own reasoning with at least one other model -> produce **final recommendation**.
3. Results -> `temp/{plan-name}-vibecheck-{n}.md`.

### 2-Round Verification (mandatory for high-risk plans)

| Round | Performer | Scope |
|-------|-----------|-------|
| Round 1 | `verifier-1` (spawned) | Multi-perspective verification. Includes vibe check + PAL clink. |
| Round 2 | `verifier-2` (spawned) | **Different perspective** from Round 1 (e.g., adversarial / bypass-hunter). Includes vibe check + PAL clink. |

Results -> `temp/{plan-name}-verification-round{n}.md`.

> **Lightweight plans**: a single verification round is sufficient (vibe check + one clink), and even that is recommended rather than required.

### temp/ as Working Memory

`temp/` is gitignored ephemeral storage and serves as action-plan execution **working memory**:

- Phase 0 alignment docs, gap lists, impact assessments
- Shared analysis between subagents
- Vibe check / PAL clink results
- Verification round results
- Attack traces, bypass PoCs, intermediate test runs, draft doc content

> `temp/` files may be cleaned after plan completion; promote to `action-plans/_ref/` if worth preserving as historical reference.

## Currently Active

No active plans.

> Update this list when plans are created or moved to `_done/`.
