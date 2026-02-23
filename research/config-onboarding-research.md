# Config Onboarding Research Report

## Executive Summary

This report evaluates six approaches for improving Guardian's new-user onboarding experience -- the critical moment between plugin installation and effective security protection. Our analysis draws on Claude Code's plugin architecture documentation, UX patterns from developer tools (ESLint, Prettier, Docker, Husky), patterns from other Claude Code plugins, and creative proposals from external AI consultations (Gemini 3.1 Pro, Claude Sonnet 4.6).

**Top Recommendation: Option D -- SessionStart Auto-Activate with Recommended Config ("Instant-On")**

This approach copies `guardian.recommended.json` to the project config path on first session if no config exists, then injects a one-line status message into Claude's context. Users get full protection immediately with zero friction. The existing `/guardian:init` wizard becomes a customization tool rather than a mandatory setup gate.

**Why**: Security tools must default to ON, not OFF. The recommended config already exists, is batteries-included, and is fail-closed. The implementation requires only a ~15-line shell script added as a SessionStart hook -- the lowest effort of any option that meaningfully improves onboarding.

---

## Current State Analysis

### What Exists Today

Guardian ships with three onboarding components:

| Component | Type | Discoverable? | When Active |
|-----------|------|--------------|-------------|
| `/guardian:init` | Command | Only if user knows to type it | User-invoked |
| `config-guide` | Skill | Auto-activates on relevant discussion | When user discusses config |
| `config-assistant` | Agent | Auto-triggers on guardian-related topics | When user mentions blocking/protection |

### The Problem

After `claude plugins install`, Guardian's security hooks activate immediately -- but without a project-specific `config.json`, the hooks fall back to a hardcoded minimal set of rules in `_guardian_utils.py`. The user has **no proactive indication** that:

1. A richer set of guardrails is available via configuration
2. `/guardian:init` exists as a command
3. What defaults are currently in effect
4. They should customize anything for their specific project

The gap is between installation (hooks active) and effective protection (full config customized for the project). During this gap, users get minimal protection and no awareness that more is available.

### Technical Context

**SessionStart hooks** are the key enabler. Claude Code fires SessionStart on every new session (matcher: `startup`), resume, clear, and compact. SessionStart hooks:

- Can execute shell commands (`type: "command"` only)
- **Stdout is added as context that Claude can see and act on** (one of only two events where this is true)
- Can persist environment variables via `$CLAUDE_ENV_FILE`
- Have access to `$CLAUDE_PROJECT_DIR` and `$CLAUDE_PLUGIN_ROOT`
- Should be kept fast since they run on every session

Guardian currently has **no SessionStart hook configured**. This is the primary technical gap.

---

## Alternatives Comparison

### Option A: Keep Current Approach (Manual /guardian:init)

**Description**: No changes. Users must discover and run `/guardian:init` on their own.

| Criterion | Score | Notes |
|-----------|-------|-------|
| Ease of use | 2/5 | User must know the command exists |
| Flexibility | 5/5 | Full wizard customization |
| Discoverability | 1/5 | No proactive notification |
| Implementation effort | 5/5 | Already done |
| Maintenance cost | 5/5 | Nothing to maintain |
| **Total** | **18/25** | |

**Security implications**: Users without config get minimal hardcoded defaults. Many users will never discover `/guardian:init` and remain under-protected.

**Pros**: Zero implementation work. No risk of introducing bugs.
**Cons**: Worst discoverability of all options. Users silently under-protected.

---

### Option B: SessionStart Hook for First-Run Detection + Guided Setup

**Description**: Add a SessionStart hook that checks for config existence and prints a helpful message suggesting `/guardian:init`. Does NOT auto-create any files.

**SessionStart hook behavior**:
```
Config exists    -> exit 0, no output (silent)
Config missing   -> print: "Guardian is active with minimal defaults. Run /guardian:init
                    to set up project-specific security rules, or say 'help me configure
                    guardian' for guided setup."
```

| Criterion | Score | Notes |
|-----------|-------|-------|
| Ease of use | 3/5 | User still must take action |
| Flexibility | 5/5 | Full wizard available |
| Discoverability | 4/5 | Proactive notification every session |
| Implementation effort | 4/5 | ~10 lines of bash |
| Maintenance cost | 5/5 | Trivial script |
| **Total** | **21/25** | |

**Security implications**: Still relies on user taking action. Minimal defaults remain the active protection until user acts.

**Pros**: Non-intrusive. Leverages existing components. Fast implementation.
**Cons**: Still requires user initiative. Some users will dismiss the message and never set up config.

---

### Option C: Recommended Config File + Easy Copy

**Description**: Ship `guardian.recommended.json` in `assets/` (already done). SessionStart hook tells users they can copy it. Does not auto-copy.

**SessionStart hook behavior**:
```
Config missing   -> print: "Guardian is active with minimal defaults. For full protection:
                    copy the recommended config with:
                    cp $PLUGIN_ROOT/assets/guardian.recommended.json .claude/guardian/config.json
                    Or run /guardian:init for a custom setup."
```

| Criterion | Score | Notes |
|-----------|-------|-------|
| Ease of use | 3/5 | One command, but user must copy/paste |
| Flexibility | 4/5 | Copy recommended, then customize via skill/agent |
| Discoverability | 4/5 | Proactive notification with actionable command |
| Implementation effort | 4/5 | ~15 lines of bash |
| Maintenance cost | 4/5 | Must keep recommended config updated |
| **Total** | **19/25** | |

**Security implications**: Better than B because it tells users exactly what to do. But still requires user action.

**Pros**: Provides a concrete action. Recommended config is well-curated.
**Cons**: User must still execute a command. Path in message may be confusing.

---

### Option D: SessionStart Auto-Activate with Recommended Config ("Instant-On") -- RECOMMENDED

**Description**: SessionStart hook automatically copies `guardian.recommended.json` to `.claude/guardian/config.json` if no config exists, then injects a status message into Claude's context.

**SessionStart hook behavior**:
```bash
#!/bin/bash
CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"

if [ ! -f "$CONFIG" ]; then
  mkdir -p "$(dirname "$CONFIG")"
  cp "${CLAUDE_PLUGIN_ROOT}/assets/guardian.recommended.json" "$CONFIG"
  echo "[Guardian] Auto-activated recommended security config ($(date +%Y-%m-%d))."
  echo "Review with 'show guardian config' or customize with /guardian:init."
else
  exit 0  # Config exists, stay silent
fi
```

| Criterion | Score | Notes |
|-----------|-------|-------|
| Ease of use | 5/5 | Zero user action needed |
| Flexibility | 4/5 | Can customize after auto-activation |
| Discoverability | 5/5 | User informed of active protection |
| Implementation effort | 4/5 | ~15 lines of bash + hooks.json update |
| Maintenance cost | 4/5 | Must keep recommended config current |
| **Total** | **22/25** | |

**Security implications**: STRONGEST security posture of all options. Users get full recommended protection from session 1. Fail-closed by design. The recommended config is opinionated on safety.

**Pros**:
- Zero friction -- works immediately
- Security is opt-out, not opt-in (the correct model for security tools)
- Config file is in the project, so teammates benefit too
- `/guardian:init` becomes a tuning tool, not a mandatory gate
- Single-file implementation

**Cons**:
- Creates a file in user's project without explicit confirmation
- Recommended config may not perfectly match all projects (but is safe by default)
- User might be surprised by auto-created file (mitigated by context message)

---

### Option E: Tiered Configs (minimal, recommended, paranoid)

**Description**: Ship three pre-built configs at different security levels. SessionStart hook presents a choice.

```
guardian.minimal.json     -- Basic protections only (secrets, rm -rf /)
guardian.recommended.json -- Full standard protections (current default.json scope)
guardian.paranoid.json    -- Maximum restrictions (ask on all rm, all git operations, etc.)
```

| Criterion | Score | Notes |
|-----------|-------|-------|
| Ease of use | 3/5 | User must choose a tier |
| Flexibility | 5/5 | Three starting points + full customization |
| Discoverability | 4/5 | Proactive notification with clear options |
| Implementation effort | 3/5 | Three config files + selection logic |
| Maintenance cost | 2/5 | Must maintain three configs in sync |
| **Total** | **17/25** | |

**Security implications**: Offering "minimal" as an option may encourage users to choose less protection. Choice paralysis could delay setup.

**Pros**: Respects different user preferences. Clear security posture per tier.
**Cons**: Three configs to maintain. Choice paralysis. "minimal" option weakens security posture. More complex SessionStart logic.

---

### Option F: Progressive JIT Interception ("Just-In-Time" Config Building)

**Description**: Start with recommended config auto-activated. When Guardian blocks something the user wants to allow, Claude offers to whitelist it conversationally. Config grows organically.

This combines Option D (auto-activate) with the existing `config-assistant` agent's capability to modify config through natural language.

**Flow**:
```
1. SessionStart: auto-activate recommended config
2. User works normally
3. Guardian blocks something user needs: "rm -rf dist/"
4. Claude says: "Guardian blocked this (recursive deletion). Want me to add
   an exception for dist/ cleanup?"
5. User: "yes, allow deleting dist/"
6. config-assistant adds pattern, config grows organically
```

| Criterion | Score | Notes |
|-----------|-------|-------|
| Ease of use | 5/5 | Zero setup + natural customization |
| Flexibility | 5/5 | Config adapts to actual usage |
| Discoverability | 5/5 | Self-teaching through interception |
| Implementation effort | 3/5 | Requires enhanced denial messages |
| Maintenance cost | 3/5 | Config evolves per-project |
| **Total** | **21/25** | |

**Security implications**: Strong starting posture (recommended config). Each relaxation is explicit and conversational. Risk: if user reflexively says "yes, allow that" without thinking, security weakens. Mitigated by `config-assistant`'s built-in safety warnings.

**Pros**: Most natural UX. Config reflects actual project needs. Leverages existing agent.
**Cons**: Requires enhanced denial message format. Users might weaken config without understanding implications.

---

## Scoring Matrix

| Option | Ease | Flex | Discover | Impl | Maint | Total | Security |
|--------|------|------|----------|------|-------|-------|----------|
| A: Manual init | 2 | 5 | 1 | 5 | 5 | 18 | Weakest |
| B: SessionStart + message | 3 | 5 | 4 | 4 | 5 | 21 | Weak |
| C: Recommended + copy | 3 | 4 | 4 | 4 | 4 | 19 | Weak |
| **D: Auto-activate** | **5** | **4** | **5** | **4** | **4** | **22** | **Strongest** |
| E: Tiered configs | 3 | 5 | 4 | 3 | 2 | 17 | Mixed |
| F: JIT interception | 5 | 5 | 5 | 3 | 3 | 21 | Strong |

---

## Recommendation with Justification

### Primary Recommendation: Option D (Auto-Activate Recommended Config)

**Justification**:

1. **Security tools should default to ON.** Prettier can work without config because formatting errors are harmless. Guardian protects against `rm -rf /`, secret exposure, and force pushes. The cost of no config is catastrophic risk. The cost of auto-activating is a config file in the project directory.

2. **The recommended config already exists.** Team 1 is drafting `guardian.recommended.json` specifically to be a batteries-included, safe-by-default configuration. Using it as the auto-activation target is its intended purpose.

3. **Lowest implementation effort for highest impact.** A ~15-line shell script + one addition to `hooks.json` gives every new user full protection from session 1. No other option achieves this ratio.

4. **Existing components handle customization.** After auto-activation, users can:
   - Run `/guardian:init` for full wizard customization
   - Say "show guardian config" to review (skill activates)
   - Say "unblock X" or "allow Y" (config-assistant activates)
   - Manually edit the JSON file

5. **Auto-created file concern is minor.** The file goes in `.claude/guardian/config.json` -- a directory explicitly for Claude Code plugin state. The context message clearly informs the user. The file is safe to commit to version control.

### Enhancement: Combine D + F for Long-term

After implementing Option D, the natural next step is Option F (JIT interception). When Guardian blocks something, enhanced denial messages can suggest talking to the config-assistant to whitelist it. This creates a complete lifecycle:

```
Install -> Auto-activate recommended -> Work normally -> Hit a block ->
Conversationally whitelist -> Config grows to match project
```

This is the ideal long-term state but Option D alone is the critical first step.

---

## Proposed Implementation Plan

### Phase 1: SessionStart Hook (Estimated: 1-2 hours)

1. **Create the hook script**: `hooks/scripts/session_start.sh`
   ```bash
   #!/bin/bash
   CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"

   if [ ! -f "$CONFIG" ]; then
     mkdir -p "$(dirname "$CONFIG")"
     cp "${CLAUDE_PLUGIN_ROOT}/assets/guardian.recommended.json" "$CONFIG"
     echo "[Guardian] Activated recommended security config for this project."
     echo "Guardian will block dangerous commands, protect secrets, and checkpoint your work."
     echo "Say 'show guardian status' to see what's protected. Config saved to .claude/guardian/config.json (safe to commit)."
   fi
   exit 0
   ```

   **Opt-out**: Users who do not want auto-activation can create any `.claude/guardian/config.json` file (even a minimal one) before their first session. The hook will see the existing file and stay silent.

   **Blast radius note**: Since every new user gets the same recommended config, any false-positive regex in that config affects all new users. Ensure `guardian.recommended.json` has thorough test coverage before using it as the auto-activation source.

2. **Update hooks.json** to add SessionStart event:
   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "matcher": "startup",
           "hooks": [
             {
               "type": "command",
               "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session_start.sh\""
             }
           ]
         }
       ],
       "PreToolUse": [ ... existing ... ],
       "Stop": [ ... existing ... ]
     }
   }
   ```

3. **Ensure `guardian.recommended.json` exists** in `assets/` (already in progress by Team 1).

### Phase 2: Enhanced Init Wizard (Estimated: 2-3 hours)

4. **Update `/guardian:init` to handle existing config**: The wizard should detect that `config.json` already exists (auto-created) and offer to review/customize it rather than creating from scratch. The current init.md already handles this case (Step 1: "Check for Existing Config").

5. **Add "quick customize" mode**: When config exists, offer targeted customization:
   - "What type of project is this?" -> add language-specific patterns
   - "Any paths that need special protection?" -> add to zeroAccess/noDelete
   - "Skip" -> keep recommended config as-is

### Phase 3: JIT Interception Messages (Future Enhancement)

6. **Enhance denial messages** in `bash_guardian.py` and `_guardian_utils.py`:
   - When a rule blocks a command, include in the system message: "To allow this in the future, say 'guardian, allow [description]'"
   - This triggers the `config-assistant` agent naturally

7. **Update config-assistant agent** to handle "allow that last command" pattern

### Testing

- Test SessionStart hook: config exists (silent), config missing (creates + messages)
- Test hook idempotency: running twice does not overwrite existing config
- Test file permissions: created config is readable/writable
- Test with various project structures
- Test that `/guardian:init` works correctly with auto-created config

---

## Mock User Journey

### Scenario: New user installs Guardian for a Node.js project

**Step 1: Installation**
```
> claude plugins install claude-code-guardian
Plugin installed: claude-code-guardian v1.0.0
```

**Step 2: Start a new session**
```
> claude
```
Behind the scenes: SessionStart hook fires, detects no config, copies `guardian.recommended.json`, injects context.

Claude sees in its context:
```
[Guardian] Auto-activated recommended security config.
Protecting against: destructive commands, secret exposure, critical file deletion.
Review: 'show guardian config' | Customize: /guardian:init | Modify: 'block X' or 'allow Y'
```

**Step 3: User starts working normally**
```
User: "Refactor the auth module to use JWT tokens"
```
Claude works normally. Guardian silently monitors Bash/Read/Edit/Write tool calls. The recommended config blocks dangerous operations and protects secrets.

**Step 4: User hits a guardian rule (natural discovery)**
```
Claude tries: rm -rf dist/
Guardian: [ask] "Recursive/force deletion -- confirm?"
User: "Yes, that's fine for dist/"
```
User now understands Guardian is active and protecting them.

**Step 5: User wants to customize (optional)**
```
User: "Block npm publish in this project"
```
Config-assistant agent activates, adds the pattern to config.json.

**Step 6: Or user runs full wizard (optional)**
```
User: /guardian:init
```
Wizard detects existing config, offers to review and customize for Node.js project.

**Step 7: Session ends**
Auto-commit hook creates safety checkpoint (if git integration enabled in config).

### Key Observation

The user never HAD to do anything. Protection was active from session 1. Every interaction with Guardian (reviewing, customizing, hitting rules) happened naturally through conversation, not through a mandatory setup gate.

---

## Appendix A: External Model Opinions

### Gemini 3.1 Pro (via pal clink)

**Top 3 recommendations:**

1. **Progressive Disclosure via "Just-In-Time" (JIT) Interception**: Ship strict recommended config, intercept dynamically, let users whitelist conversationally. "Amortizes setup cost over the entire project lifecycle."

2. **Gamified "Red Team" Calibration**: Replace Q&A wizard with scenario-based binary choices. "I am attempting to force-push to main. Allow or Block?" Compiles answers into config.

3. **Shadow Mode Telemetry with AI Auto-Tuning**: First sessions run in observation mode, logging "would block" events. After 3 sessions, auto-generates custom config based on observed behavior.

**Key insight from Gemini**: "Beginners never have to learn regex; they just talk to the assistant when they hit a wall."

### Claude Sonnet 4.6 (via pal clink)

**Top 3 recommendations:**

1. **Instant-On Auto-Activation**: Copy recommended config on first run. "If you have guardian.recommended.json sitting unused in assets/, you already built the solution -- you just haven't made it the first-run path yet."

2. **Shadow Mode Dry Run**: Non-blocking first session with end-of-session report. "The biggest barrier to adopting security tooling is 'will this break my workflow?'"

3. **One-Question Bootstrap**: Ask one high-signal question: "What's the one thing that would be a disaster if Claude accidentally did it here?" Seed config from that answer + recommended baseline.

**Key insight from Claude**: "Security becomes opt-out, not opt-in. The /init wizard becomes a tuning tool, not a mandatory gate."

### Consensus Across Models

Both models independently converged on the same core principle: **auto-activate recommended config with zero friction, then let users customize through conversation**. The specific mechanisms differ (JIT interception vs. one-question bootstrap) but the philosophy is identical. Neither model recommended keeping the current manual-only approach.

---

## Appendix B: Verification Notes

### Round 1 Considerations

Key questions for verification:
- Does auto-creating files in the user's project violate expectations?
- What if the user is in a read-only or CI/CD environment?
- Should the SessionStart hook also fire on `resume` or only `startup`?
- What happens if `guardian.recommended.json` is malformed?

### Mitigations

1. **File creation concern**: The file goes in `.claude/guardian/` -- an explicitly plugin-managed directory. The context message clearly communicates what happened. This is identical to how other tools create `.eslintrc`, `.prettierrc`, etc.

2. **Read-only environments**: The `mkdir -p` and `cp` would fail silently (exit 0 still runs). Guardian falls back to hardcoded defaults. No worse than current behavior.

3. **Resume vs. startup**: Only fire on `startup` (new sessions). On `resume`, the config should already exist from the previous session. Using `matcher: "startup"` handles this.

4. **Malformed recommended config**: Add a basic JSON validation step in the hook, or rely on the guardian scripts' existing error handling (which falls back to hardcoded defaults on parse failure).

---

## Appendix C: Implementation Reference

### Files to Create

| File | Purpose |
|------|---------|
| `hooks/scripts/session_start.sh` | SessionStart hook script |

### Files to Modify

| File | Change |
|------|--------|
| `hooks/hooks.json` | Add SessionStart event configuration |

### Files Required (Dependency)

| File | Status |
|------|--------|
| `assets/guardian.recommended.json` | In progress (Team 1) |

### No Changes Needed

| File | Reason |
|------|--------|
| `commands/init.md` | Already handles existing config case |
| `skills/config-guide/SKILL.md` | Already auto-activates on discussion |
| `agents/config-assistant.md` | Already handles config modification |
| `hooks/scripts/bash_guardian.py` | No changes for Phase 1 |
| `hooks/scripts/_guardian_utils.py` | No changes for Phase 1 |
