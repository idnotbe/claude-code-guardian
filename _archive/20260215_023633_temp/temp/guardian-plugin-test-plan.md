# Guardian Plugin Installation & Verification Test Plan

**Date**: 2026-02-11
**Plugin**: claude-code-guardian v1.0.0
**Repo**: https://github.com/idnotbe/claude-code-guardian
**Plugin Path**: C:\claude-code-guardian\
**Test Environment**: C:\ops\ (Windows 11, Python 3.13)

---

## Pre-Test Checklist

- [x] **BACKUP-01**: Copy `C:\ops\.claude\settings.json` to `C:\ops\temp\settings.json.backup` -- DONE
- [x] **BACKUP-02**: Copy `C:\ops\.claude\hooks\_protection\` to `C:\ops\temp\_protection.backup\` -- DONE
- [x] **BACKUP-03**: Verify `python3 --version` works (need 3.10+) -- Python 3.13.12
- [x] **BACKUP-04**: Verify `git` is available -- DONE
- [x] **BACKUP-05**: Confirm current commit hash of ops repo (for rollback) -- `a96cd9f`

---

## Phase 1: Diagnostic Probe (BEFORE removing old hooks)

> **Rationale** (from vibe-check + Gemini): Do NOT remove working protection until the plugin mechanism is verified. A minimal "probe hook" answers 5 critical unknowns without risk.

### Step 1.1: Create Probe Plugin

Create a minimal probe plugin at `C:\guardian-probe\` that dumps environment info to verify the plugin hook mechanism works.

```
C:\guardian-probe\
  .claude-plugin\
    plugin.json
  hooks\
    hooks.json
    scripts\
      probe.py
```

**probe.py** logs: timestamp, CWD, sys.argv, CLAUDE_* env vars, stdin payload, python version.
**hooks.json** registers one PreToolUse:Bash hook pointing to probe.py.

- [x] **PROBE-01**: Create probe plugin structure -- DONE at `C:\guardian-probe\`
- [x] **PROBE-02**: Start Claude Code with `claude --plugin-dir C:\guardian-probe` in `C:\test\` -- DONE
- [x] **PROBE-03**: Run `echo hello` -- DONE
- [x] **PROBE-04**: Check probe log -- DONE, log exists at `C:\ops\temp\guardian-probe-results.log`

### Step 1.2: Verify Probe Results

From the probe log, confirm:

- [x] **PV-01**: `${CLAUDE_PLUGIN_ROOT}` expanded correctly -- `C:\guardian-probe`
- [x] **PV-02a**: stdin contains JSON with tool input -- keys: session_id, transcript_path, cwd, permission_mode, hook_event_name, tool_name, tool_input, tool_use_id
- [x] **PV-02b**: tool_input format: `{"command": "echo hello", "description": "Print hello"}`
- [x] **PROBE-05**: `python3` invoked successfully -- Python 3.13.12 (MSC v.1944 64 bit)
- [x] **PROBE-06**: CWD = `C:\test` (project directory)
- [x] **PROBE-07**: CLAUDE_* vars: CLAUDE_CODE_ENTRYPOINT=cli, CLAUDE_PLUGIN_ROOT, CLAUDE_PROJECT_DIR

### Step 1.3: Verify Hook Response Protocol

Modify probe.py to output a JSON response on stdout (allow decision) and verify Claude Code respects it.

- [x] **PROBE-08**: Probe outputs `{"hookSpecificOutput": {"permissionDecision": "allow"}}` on stdout -- confirmed
- [x] **PROBE-09**: The bash command (`echo hello`) executed normally -- confirmed
- [ ] **PROBE-10**: (Skipped -- deny test deferred to full guardian test)
- [ ] **PROBE-11**: (Skipped -- deny test deferred to full guardian test)

### Phase 1 Decision Gate

If all PROBE tests pass:
- `${CLAUDE_PLUGIN_ROOT}` expands -> **proceed to Phase 2**
- stdin JSON format matches our implementation -> **proceed to Phase 2**
- `python3` works -> **proceed to Phase 2**
- Response protocol works -> **proceed to Phase 2**

If ANY probe test fails:
- **DO NOT proceed to Phase 2**
- Document what failed and why
- Fix the plugin to match actual Claude Code behavior
- Re-run probe

---

## Phase 2: Remove Old Hooks & Install Guardian Plugin

> Only proceed here after Phase 1 passes.

### Step 2.1: Remove Old Hooks from settings.json

Edit `C:\ops\.claude\settings.json` to remove guardian-related hooks:

**REMOVE** from `PreToolUse`:
- Bash matcher hook (bash_protection.py)
- Edit matcher hook (edit_protection.py)
- Write matcher hook (write_protection.py)

**REMOVE** from `Stop`:
- auto_commit.py command hook

**KEEP** in `Stop`:
- active-context.md prompt hook (line 84-85)
- on_stop.wav sound hook (line 91-93)

**KEEP** intact:
- `Notification` hooks (sound)
- `env`, `permissions`, `enabledMcpjsonServers`, `statusLine`, `enabledPlugins`

- [x] **REMOVE-01**: Edit settings.json -- remove 3 PreToolUse hooks -- DONE (verified R1+R2)
- [x] **REMOVE-02**: Edit settings.json -- remove auto_commit.py from Stop hooks -- DONE (verified R1+R2)
- [x] **REMOVE-03**: Verify settings.json is valid JSON after editing -- DONE (python json.load() passed)
- [ ] **REMOVE-04**: Rename `C:\ops\.claude\hooks\_protection\` to `C:\ops\.claude\hooks\_protection.disabled\` (don't delete, just disable) -- DO BEFORE RESTART
- [x] **REMOVE-05**: Record in this document what was removed -- DONE (see R1+R2 review docs)

### Step 2.2: Restart Claude Code

- [ ] **RESTART-01**: Exit current Claude Code session
- [ ] **RESTART-02**: Start new session: `claude --dangerously-skip-permissions --plugin-dir C:\claude-code-guardian`
- [ ] **RESTART-03**: Verify Claude Code starts without errors

### Step 2.3: Verify Plugin Loaded

- [ ] **LOAD-01**: Check for any plugin loading errors in startup output
- [ ] **LOAD-02**: Test hook is active: try to read a `.env` file (should be blocked if hooks loaded)
- [ ] **LOAD-03**: If LOAD-02 fails (not blocked), hooks did NOT load -- STOP and rollback

---

## Phase 3: Platform Verification Tests (PV-01 through PV-05)

### PV-01: CLAUDE_PLUGIN_ROOT Expansion

- [ ] **PV-01**: All 4 hooks fire (confirmed by LOAD-02 and subsequent tests)
- **If FAIL**: hooks.json commands couldn't find scripts -> `${CLAUDE_PLUGIN_ROOT}` didn't expand

### PV-02: Hook JSON Protocol

- [ ] **PV-02a**: Try reading `.env` file -> should be DENIED (zero-access path)
- [ ] **PV-02b**: Try `git reset --hard` -> should ASK for confirmation
- [ ] **PV-02c**: Try writing to a read-only path like `package-lock.json` -> should be DENIED
- **If FAIL**: JSON stdout protocol doesn't match -> check probe log from Phase 1

### PV-03: Skill and Agent Discovery

- [ ] **PV-03a**: Ask "show me the guardian configuration guide" -> should trigger config-guide skill
- [ ] **PV-03b**: Ask "help me configure guardian protection rules" -> should trigger config-assistant agent
- **If FAIL**: plugin.json skills/agents arrays not auto-discovered

### PV-04: Marketplace Resolution

- [ ] **PV-04**: Try `/plugin marketplace add idnotbe/claude-code-guardian` (informational only -- expect this to fail or not exist)
- **Note**: Marketplace is documented as experimental. FAIL here is acceptable.

### PV-05: Command Registration

- [ ] **PV-05a**: Type `/guardian:init` -> should start the setup wizard
- [ ] **PV-05b**: If wizard starts, verify it creates `.claude/guardian/protection.json`
- **If FAIL**: Commands from plugin.json not registered as slash commands

---

## Phase 4: Functional Tests

### 4.1 Bash Protection (PreToolUse:Bash)

**Block patterns** (should be DENIED):

- [ ] **BASH-B01**: `echo "test" && rm -rf /tmp/test` (contains rm -rf pattern)
- [ ] **BASH-B02**: `git push --force origin main` (force push)
- [ ] **BASH-B03**: `cat .env` (reading secret file via bash -- may or may not be caught by bash hook vs file hook)

**Ask patterns** (should PROMPT for confirmation):

- [ ] **BASH-A01**: `git reset --hard HEAD~1` (hard reset)
- [ ] **BASH-A02**: `git branch -D feature-branch` (branch deletion)
- [ ] **BASH-A03**: `git stash drop` (stash deletion)

**Allow patterns** (should execute silently):

- [ ] **BASH-OK01**: `ls` (safe command)
- [ ] **BASH-OK02**: `git status` (safe git command)
- [ ] **BASH-OK03**: `python --version` (safe command)

### 4.2 Edit Protection (PreToolUse:Edit)

- [ ] **EDIT-Z01**: Try editing `.env` -> DENIED (zero-access)
- [ ] **EDIT-R01**: Try editing `package-lock.json` (if exists) -> DENIED (read-only)
- [ ] **EDIT-OK01**: Try editing a normal file -> ALLOWED

### 4.3 Write Protection (PreToolUse:Write)

- [ ] **WRITE-Z01**: Try writing to `.env` -> DENIED (zero-access)
- [ ] **WRITE-EXT01**: Try writing to a path outside project -> DENIED
- [ ] **WRITE-OK01**: Try writing to a normal temp file -> ALLOWED

### 4.4 Auto-Commit (Stop Hook)

- [ ] **STOP-01**: Make a small change to a tracked file
- [ ] **STOP-02**: End the Claude Code session (type /exit or Ctrl+C)
- [ ] **STOP-03**: Check `git log -1` -- should show an auto-commit
- [ ] **STOP-04**: Verify commit message contains "auto-checkpoint" or similar

### 4.5 Config Resolution

- [ ] **CFG-01**: With NO `.claude/guardian/protection.json`, plugin uses default config (verify by checking blocked patterns match `assets/protection.default.json`)
- [ ] **CFG-02**: Run `/guardian:init` to create project config
- [ ] **CFG-03**: Verify project config is created at `.claude/guardian/protection.json`
- [ ] **CFG-04**: Modify project config (e.g., add a custom block pattern), restart, verify custom pattern is enforced

---

## Phase 5: Edge Cases

- [ ] **EDGE-01**: Very long command (>10000 chars) -> should be BLOCKED (fail-closed per F-02 fix)
- [ ] **EDGE-02**: Command with Unicode characters -> should not crash the hook
- [ ] **EDGE-03**: Empty command string -> should be handled gracefully
- [ ] **EDGE-04**: Simultaneous rapid commands -> hooks should not race-condition

---

## Rollback Plan

If plugin doesn't work or causes problems:

1. Exit Claude Code
2. Copy backup: `copy C:\ops\temp\settings.json.backup C:\ops\.claude\settings.json`
3. Rename: `C:\ops\.claude\hooks\_protection.disabled\` back to `_protection\`
4. Restart Claude Code normally (without --plugin-dir)
5. Verify old hooks work

---

## Known Risks

| Risk | Mitigation |
|------|-----------|
| `python3` might not work in hook runner context | Verified works in shell; probe test confirms |
| `${CLAUDE_PLUGIN_ROOT}` might not expand | Probe test Phase 1 catches this before any changes |
| Plugin hooks.json format might differ from official spec | Probe test validates actual format |
| Both old hooks and plugin hooks might conflict | Old hooks removed before plugin test (Phase 2) |
| Plugin fails to load silently | LOAD-02 test catches this immediately |
| Windows path issues (backslash vs forward slash) | Probe logs CWD and paths for verification |
| hooks.json `command` format may need `hooks` array wrapper | Probe test validates; see settings.json format as reference |

---

## Expected settings.json After Hook Removal (Phase 2)

The hooks section should look like this after removing guardian-related hooks:

```json
{
  "hooks": {
    "PreToolUse": [],
    "PostToolUse": [],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "powershell -NoProfile -c \"$p = Join-Path $env:CLAUDE_PROJECT_DIR 'on_notification.wav'; if(!(Test-Path $p)){ exit 0 }; $sp = New-Object System.Media.SoundPlayer($p); $sp.PlaySync()\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Check if this session resulted in any of the following:\n1. A new decision about architecture, governance, or infrastructure\n2. Completion or significant progress on a milestone or task\n3. Discovery of a new blocker, constraint, or risk\n4. A change in project direction or priorities\n\nIf NONE of the above apply, do NOT update strategy/active-context.md.\n\nIf ANY apply, update strategy/active-context.md to reflect the current project state. Use this exact structure:\n\n# Active Context — AGNTPOD\n> Current project state snapshot. Updated by prompt hook each significant session.\n\n## Phase\n[1-2 lines: current milestone/phase]\n\n## Current State\n[5-10 undated bullets: what is true RIGHT NOW. Overwrite previous content.]\n\n## In Progress\n[Incomplete/mid-stream work. Remove completed items.]\n\n## Next Steps\n[3-5 immediate priorities. High-level only. Do not duplicate current-focus.md.]\n\n## Blockers & Constraints\n[Active limitations or warnings for the next session. Remove resolved items.]\n\n## Session Handoff\n[3-5 bullets: what THIS session accomplished. Overwrite previous handoff.]\n\nRULES:\n- Total file must stay under 50 lines.\n- This is a STATE SNAPSHOT, not a history log. No dates, no session IDs.\n- Prune aggressively: if it's done and doesn't create an ongoing constraint, remove it.\n- If the file doesn't exist, create it.\n- Preserve the header and section structure exactly.\n- Do NOT list 'updated active-context.md' as an accomplishment in Session Handoff."
          },
          {
            "type": "command",
            "command": "powershell -NoProfile -c \"$p = Join-Path $env:CLAUDE_PROJECT_DIR 'on_stop.wav'; if(!(Test-Path $p)){ exit 0 }; $sp = New-Object System.Media.SoundPlayer($p); $sp.PlaySync()\""
          }
        ]
      }
    ]
  }
}
```

Note: Only the `hooks` section is shown. All other fields (env, permissions, enabledMcpjsonServers, statusLine, enabledPlugins) remain unchanged.

---

## Important: hooks.json Format Risk

**Current plugin hooks.json format**:
```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/...\""}
    ]
  }
}
```

**Current settings.json format** (known working):
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "powershell ..."}
        ]
      }
    ]
  }
}
```

**The formats are different!** The plugin hooks.json uses a flat `command` field directly on the matcher object, while settings.json wraps in a `hooks` array with `type: "command"` objects. The probe test (Phase 1) will reveal which format the plugin system actually expects. If the plugin format is wrong, we'll need to fix hooks.json before Phase 2.

---

## Test Results Summary

| Phase | Test ID | Result | Notes |
|-------|---------|--------|-------|
| 1 | PROBE-01~11 | | |
| 2 | REMOVE-01~05 | | |
| 2 | LOAD-01~03 | | |
| 3 | PV-01~05 | | |
| 4 | BASH-B01~B03 | | |
| 4 | BASH-A01~A03 | | |
| 4 | BASH-OK01~OK03 | | |
| 4 | EDIT-Z01, R01, OK01 | | |
| 4 | WRITE-Z01, EXT01, OK01 | | |
| 4 | STOP-01~04 | | |
| 4 | CFG-01~04 | | |
| 5 | EDGE-01~04 | | |
