# Team A Fixes Report

## Summary

Applied 3 fixes to `README.md` as specified in the master plan (Fix 2, Fix 3, Fix 4).

---

## Fix 4: Terminology consistency (lines 84, 86)

**Problem**: Line 84 said "sensible defaults" while line 86 said "built-in defaults" -- inconsistent terminology.

**Change**: Replaced "sensible defaults" with "built-in defaults" on line 84. Both lines now consistently use "built-in defaults".

**Before (line 84)**:
> This generates a `config.json` configuration file in your project with sensible defaults.

**After (line 84)**:
> This generates a `config.json` configuration file in your project with built-in defaults.

---

## Fix 2: Config example warning (line 101)

**Problem**: The prose paragraph before the JSON config example was easy to overlook, risking users copy-pasting a partial config without required fields.

**Change**: Replaced the plain paragraph with a blockquote callout using `> **Note**:` formatting. The warning now clearly states the example is partial, names the two required fields (`version` and `hookBehavior`), and directs users to copy the default config as a starting point.

**Before (line 101)**:
> The following shows a partial custom configuration. Your config must also include `version` and `hookBehavior` (both required by the schema). See `assets/guardian.default.json` for the complete config with all required fields.

**After (line 101)**:
> > **Note**: The example below is a partial configuration showing only custom patterns. A valid config file **must** also include `version` and `hookBehavior`. Copy `assets/guardian.default.json` as your starting point and modify from there.

---

## Fix 3: Hook verification test (lines 153, 185)

**Problem**: Both the "Important" callout (line 153) and the troubleshooting section (line 185) assumed the user has a `.env` file, which not all projects have.

**Changes**:

### Line 153 (Important callout)

**Before**:
> Verify hooks are loaded at the start of your session by attempting to read a `.env` file -- Guardian should block the operation.

**After**:
> Verify hooks are loaded at the start of your session by running a blocked command -- for example, ask Claude to `cat .env` (even if the file doesn't exist, Guardian should block the attempt).

### Line 185 (Troubleshooting section)

**Before**:
> At the start of your session, try to read a `.env` file or run a known-blocked command like `cat .env`. If Guardian is active, the operation will be blocked. If it succeeds silently, hooks are not loaded.

**After**:
> At the start of your session, run a known-blocked command like `cat .env` (the file does not need to exist -- Guardian intercepts the command before it executes). If Guardian is active, the operation will be blocked. If it succeeds silently, hooks are not loaded.

---

## Verification

All changed sections re-read for natural flow and correctness:
- Line 84 and 86 now both say "built-in defaults" -- consistent
- Line 101 blockquote callout is visually distinct and actionable
- Lines 153 and 185 both clarify that the `.env` file does not need to exist; the test works regardless
