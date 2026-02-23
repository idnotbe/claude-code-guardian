# Security Review: SessionStart Auto-Activate Action Plan

**Reviewer**: sec-plan-reviewer (Claude Opus 4.6)
**Date**: 2026-02-22
**Action Plan**: `action-plans/session-start-auto-activate.md`
**External Consultation**: Gemini 3.1 Pro (via pal clink, codereviewer role)
**Verdict**: APPROVE WITH REQUIRED FIXES (3 must-fix, 2 should-fix, 2 informational)

---

## Executive Summary

The action plan is well-structured and demonstrates strong security awareness. The fail-open design is correct for a SessionStart hook. The edge case table is thorough and covers most attack vectors. However, the proposed script has **three exploitable vulnerabilities** that must be fixed before implementation, all related to TOCTOU races and predictable temp file naming. The fixes are straightforward (5-10 lines changed) and do not alter the script's architecture.

---

## Findings

### MUST-FIX-1: Predictable Temp File Name Enables Symlink-Based Arbitrary File Overwrite

**Severity**: Critical
**Location**: Action plan script line `TMPFILE="$CONFIG_DIR/.config.json.tmp.$$"`
**Attack vector**: `$$` expands to the script's PID, which is predictable (sequential integers). An attacker with write access to `.claude/guardian/` can pre-create symlinks for likely PIDs:

```bash
# Attacker plants symlinks before victim starts a session
for pid in $(seq 1000 65535); do
  ln -sf ~/.ssh/authorized_keys ".claude/guardian/.config.json.tmp.$pid"
done
```

When the script runs `cp "$SOURCE" "$TMPFILE"`, `cp` follows the symlink by default, overwriting `~/.ssh/authorized_keys` with the guardian config JSON. This is an arbitrary file overwrite with attacker-chosen target.

**Fix**: Replace predictable PID with `mktemp`:

```bash
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX") || exit 0
```

`mktemp` creates the file atomically with `O_EXCL` (refuses to follow symlinks or overwrite existing files) and uses 6 random characters (>2 billion possibilities). The subsequent `cp` is no longer needed -- write directly:

```bash
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX") || exit 0
cat "$SOURCE" > "$TMPFILE" 2>/dev/null || { rm -f "$TMPFILE" 2>/dev/null; exit 0; }
```

**Gemini concurrence**: Yes -- identified as critical finding #1.

---

### MUST-FIX-2: TOCTOU Between Symlink Check and mkdir

**Severity**: High
**Location**: Action plan script lines checking `-L` then calling `mkdir -p`

```bash
# CHECK (time T1)
if [ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]; then
  exit 0
fi

# USE (time T2) -- attacker swaps directory for symlink between T1 and T2
mkdir -p "$CONFIG_DIR" 2>/dev/null
```

Between the symlink check and `mkdir -p`, an attacker can replace `.claude/guardian` with a symlink to an attacker-controlled directory. `mkdir -p` follows existing symlinks, so it succeeds, and subsequent writes go to the attacker's location.

**Fix**: Move the symlink validation to **after** `mkdir -p`:

```bash
# Create directory first
if ! mkdir -p "$CONFIG_DIR" 2>/dev/null; then
  exit 0
fi

# THEN validate no symlinks exist in the path
if [ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]; then
  exit 0
fi
```

This does not fully close the TOCTOU window (an attacker could still race between the post-mkdir check and the file write), but it significantly narrows it. For a complete fix in bash without `O_NOFOLLOW`, this is the best practical mitigation. The narrowed window combined with `mktemp` (MUST-FIX-1) makes exploitation extremely difficult.

**Gemini concurrence**: Yes -- identified as high finding #2.

---

### MUST-FIX-3: TOCTOU on Final mv Target

**Severity**: Medium
**Location**: Action plan script lines:

```bash
if [ -f "$CONFIG" ]; then   # CHECK (T1)
  exit 0
fi
if ! mv "$TMPFILE" "$CONFIG" 2>/dev/null; then   # USE (T2)
```

Between the existence check and `mv`, an attacker can create a symlink at `$CONFIG` pointing to a directory. `mv` will then place the temp file *inside* that directory instead of at the expected path, resulting in uncontrolled file placement.

**Fix**: Use `mv -n` (no-clobber) which refuses to overwrite existing targets:

```bash
# Remove the separate [ -f ] check entirely -- mv -n handles it atomically
if ! mv -n "$TMPFILE" "$CONFIG" 2>/dev/null; then
  exit 0
fi
```

Note: `mv -n` is supported on Linux (coreutils) and macOS. On systems where it is not supported, `mv` without `-n` is still safe because the worst case is overwriting with an identical file (since the source is always `guardian.recommended.json`). The action plan should document this portability consideration.

**Gemini concurrence**: Yes -- identified as medium finding #3.

---

### SHOULD-FIX-1: Silent Failure Hides Missing Protection

**Severity**: Low-Medium (architectural)
**Location**: All failure paths exit silently

If the script fails to create the config (e.g., read-only filesystem, permission denied), the user enters a `--dangerously-skip-permissions` session believing Guardian is fully active. In reality, they fall back to hardcoded minimal defaults which provide weaker protection.

**Current behavior**: Complete silence on failure.
**Recommended**: Emit a warning on failure paths where config creation was attempted but failed:

```bash
# After failed mkdir, cp, or mv:
echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
echo "Run /guardian:init to set up full protection."
exit 0
```

This maintains fail-open (exit 0) while ensuring the user/Claude is aware of degraded protection. The warning should NOT appear for "normal" early exits (env vars missing, config already exists) -- only for paths where creation was attempted and failed.

**Gemini concurrence**: Yes -- identified as low finding #4.

---

### SHOULD-FIX-2: Missing Validation of CLAUDE_PROJECT_DIR Content

**Severity**: Low
**Location**: Action plan script line `CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"`

The script validates that `CLAUDE_PROJECT_DIR` is non-empty but does not validate that it is an absolute path or that it exists as a directory. If `CLAUDE_PROJECT_DIR` is set to a relative path or a non-existent path, the script could create directories in unexpected locations.

The Python guardians (`_guardian_utils.py:449`) validate `os.path.isdir(project_dir)`. The bash script should do the same:

```bash
if [ -z "$CLAUDE_PROJECT_DIR" ] || [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

# Validate paths are absolute directories
if [ ! -d "$CLAUDE_PROJECT_DIR" ] || [ ! -d "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

# Reject relative paths
case "$CLAUDE_PROJECT_DIR" in
  /*) ;; # absolute -- OK
  *) exit 0 ;;
esac
```

This brings the bash script to parity with the Python guardian's validation.

---

### INFO-1: Concurrent Session Race is Benign (Confirmed)

**Severity**: Informational (no action needed)
**Assessment**: The action plan correctly identifies that concurrent sessions both copying the same source file is a benign race. The worst case is two `mv` operations writing the identical file content sequentially. With `mv -n` (MUST-FIX-3), the second session's `mv` simply fails and exits silently. No data corruption is possible.

---

### INFO-2: Supply Chain Risk of guardian.recommended.json

**Severity**: Informational (accepted risk)
**Assessment**: The recommended config is version-controlled in the plugin repository. A supply chain attack would require compromising the git repository or the plugin distribution mechanism. This is the same trust boundary as the plugin code itself (bash_guardian.py, _guardian_utils.py, etc.). Since the script only copies from `$CLAUDE_PLUGIN_ROOT/assets/`, it cannot be injected via user-controlled paths. **No additional mitigation needed** -- the supply chain risk is inherent to the plugin model.

---

## Threat Model Assessment

| Threat | Covered? | Notes |
|--------|----------|-------|
| **Path traversal via CLAUDE_PROJECT_DIR** | Partial | Script trusts env var from Claude Code. SHOULD-FIX-2 adds validation. |
| **Symlink attack on temp file** | NO | MUST-FIX-1 required. |
| **Symlink attack on directory** | Partial | Checks exist but have TOCTOU. MUST-FIX-2 narrows window. |
| **Symlink attack on final target** | NO | MUST-FIX-3 required. |
| **Concurrent session corruption** | Yes | Benign race -- identical content. |
| **Privilege escalation** | N/A | Script runs as user, no setuid/sudo. |
| **Supply chain (malicious config)** | Accepted | Same trust boundary as plugin code. |
| **Fail-open safety** | Yes | Correct for SessionStart. SHOULD-FIX-1 improves observability. |
| **Denial of service** | N/A | Fail-open means failures cannot block sessions. |
| **Config overwrite (existing config)** | Yes | Early `-f` check prevents overwrite. |
| **Dangling symlink at config path** | Yes | `-L` check catches dangling symlinks. |

---

## Comparison with Existing Guardian Security Patterns

| Aspect | Python Guardians | Proposed Bash Script | Assessment |
|--------|-----------------|---------------------|------------|
| Fail mode | Fail-closed (deny) | Fail-open (exit 0) | Correct -- security hooks must fail-closed, but session bootstrap should fail-open |
| Path validation | `os.path.isdir()` check | Missing | SHOULD-FIX-2 |
| Symlink handling | `is_symlink_escape()` with `resolve()` | `[ -L ]` checks | Acceptable for bash; Python's `resolve()` is stronger but unavailable in pure bash |
| Config loading | 3-step fallback chain | N/A (creates config for future loads) | Correct separation of concerns |
| Error reporting | JSON on stdout | Plain text on stdout | Correct -- SessionStart uses different output contract than PreToolUse |

---

## Revised Script (Incorporating All Fixes)

For reference, here is the script with all MUST-FIX and SHOULD-FIX changes applied:

```bash
#!/bin/bash
# Guardian SessionStart Hook -- Auto-activate recommended config on first session.
# Fail-open: all errors exit 0 silently. Never block session startup.

# --- Environment validation ---
if [ -z "$CLAUDE_PROJECT_DIR" ] || [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

# Validate paths are absolute directories
case "$CLAUDE_PROJECT_DIR" in /*) ;; *) exit 0 ;; esac
if [ ! -d "$CLAUDE_PROJECT_DIR" ] || [ ! -d "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"
SOURCE="$CLAUDE_PLUGIN_ROOT/assets/guardian.recommended.json"

# --- Already configured? Exit silently. ---
if [ -f "$CONFIG" ] || [ -L "$CONFIG" ]; then
  exit 0
fi

# --- Source file must exist ---
if [ ! -f "$SOURCE" ]; then
  exit 0
fi

# --- Create directory (fail silently on permission/read-only errors) ---
CONFIG_DIR="$(dirname "$CONFIG")"
if ! mkdir -p "$CONFIG_DIR" 2>/dev/null; then
  exit 0
fi

# --- Post-creation symlink validation (TOCTOU mitigation) ---
if [ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]; then
  exit 0
fi

# --- Atomic write: mktemp + mv -n ---
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX" 2>/dev/null) || exit 0
cleanup() { rm -f "$TMPFILE" 2>/dev/null; }
trap cleanup EXIT

if ! cat "$SOURCE" > "$TMPFILE" 2>/dev/null; then
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
fi

# Atomic move (no-clobber prevents overwrite and symlink-to-directory redirect)
if ! mv -n "$TMPFILE" "$CONFIG" 2>/dev/null; then
  # mv -n failure means config was created by another session (benign race) or symlink attack
  exit 0
fi

# --- Success: print context message ---
echo "[Guardian] Activated recommended security config for this project."
echo "Protecting against: destructive commands, secret exposure, critical file deletion, force pushes."
echo "Config saved to .claude/guardian/config.json (safe to commit)."
echo "Review: 'show guardian config' | Customize: /guardian:init | Modify: 'block X' or 'allow Y'"
exit 0
```

---

## Verdict

The action plan demonstrates solid security thinking with its edge case analysis, atomic write strategy, and symlink checks. The three MUST-FIX issues are real exploitable vulnerabilities but are straightforward to address. Once these fixes are incorporated into the action plan, the implementation is safe to proceed.

**APPROVE** contingent on MUST-FIX-1, MUST-FIX-2, and MUST-FIX-3 being incorporated into the action plan before implementation begins.
