#!/bin/bash
# Guardian SessionStart Hook -- Auto-activate recommended config on first session.
# Fail-open: all errors exit 0. Never block session startup.
# Warning emitted only when config creation is attempted but fails.

# --- Environment validation ---
# If either env var is missing/empty, exit silently (can't do anything useful).
if [ -z "$CLAUDE_PROJECT_DIR" ] || [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

# Validate paths are absolute directories (defense-in-depth, matches Python guardians)
case "$CLAUDE_PROJECT_DIR" in /*) ;; *) exit 0 ;; esac
if [ ! -d "$CLAUDE_PROJECT_DIR" ] || [ ! -d "$CLAUDE_PLUGIN_ROOT" ]; then
  exit 0
fi

CONFIG="$CLAUDE_PROJECT_DIR/.claude/guardian/config.json"
SOURCE="$CLAUDE_PLUGIN_ROOT/assets/guardian.recommended.json"

# --- Already configured? Exit silently. ---
# Also reject if config.json is a symlink (even dangling) -- prevents write redirection.
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
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
fi

# --- Post-creation symlink validation (TOCTOU mitigation) ---
# Checked AFTER mkdir to narrow the race window between check and use.
if [ -L "$CLAUDE_PROJECT_DIR/.claude" ] || [ -L "$CLAUDE_PROJECT_DIR/.claude/guardian" ]; then
  exit 0
fi

# --- Atomic write: mktemp (secure temp) + mv -n (no-clobber) ---
# mktemp uses O_EXCL, preventing symlink preemption (fixes CWE-377).
TMPFILE=$(mktemp "$CONFIG_DIR/.config.json.tmp.XXXXXX" 2>/dev/null) || {
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
}
cleanup() { rm -f "$TMPFILE" 2>/dev/null; }
trap cleanup EXIT

# cp to mktemp file inherits the temp file's permissions (0600 from O_EXCL).
if ! cp "$SOURCE" "$TMPFILE" 2>/dev/null; then
  echo "[Guardian] Could not auto-activate recommended config. Using minimal defaults."
  echo "Run /guardian:init to set up full protection."
  exit 0
fi

# Atomic move: mv -n refuses to overwrite existing targets, preventing both
# concurrent-session clobber and symlink-to-directory redirect attacks.
if ! mv -n "$TMPFILE" "$CONFIG" 2>/dev/null; then
  # mv -n failure means config was created by another session (benign race) or attack
  exit 0
fi

# Match source file permissions (0644) instead of mktemp's restrictive 0600.
chmod 644 "$CONFIG" 2>/dev/null

# --- Success: print context message (stdout goes into Claude's context) ---
echo "[Guardian] Activated recommended security config for this project."
echo "Protecting against: destructive commands, secret exposure, critical file deletion, force pushes."
echo "Config saved to .claude/guardian/config.json (safe to commit)."
echo "Review: 'show guardian config' | Customize: /guardian:init | Modify: 'block X' or 'allow Y'"
exit 0
