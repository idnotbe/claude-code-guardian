# Verification Round 1: Accuracy Report
## Teammate V1

---

### Fix 1: PASS
**Spec**: All 21 entries in the Fixed Issues table should have descriptive text (not just "Round 2"). Each description should be self-contained and match the detail in the body entries above.

**Evidence**: Counted 21 entries in the Fixed Issues table (KNOWN-ISSUES.md lines 138-160). All entries have self-contained, descriptive text in the Description column. None contain bare labels like "Round 2" -- the Fixed In column still notes which round/version, but the Description column now explains the actual issue. Examples:

- F-01: "bash_guardian.py failed open on unhandled crash, allowing commands through without checks"
- COMPAT-01: "plugin.json missing skills and agents declarations, preventing discovery"
- COMPAT-02: "hooks.json used `python` instead of `python3`, failing on Linux/WSL systems"
- COMPAT-13: "Circuit breaker recovery guidance suggested Windows `del` command on all platforms"

Cross-checked representative entries against their body counterparts:
- COMPAT-06 table says "normalize_path() resolved relative paths against CWD instead of project directory" -- matches the body entry at line 71-73 which states the same issue and fix.
- COMPAT-07 table says "fnmatch case sensitivity incorrect on macOS HFS+ (case-insensitive filesystem)" -- matches the body entry at lines 76-78.
- UX-08 table says "--force-with-lease (safe force push) was blocked instead of prompting ask" -- matches the body entry at lines 94-96.

All 21/21 entries verified as descriptive and self-contained.

---

### Fix 2: PASS
**Spec**: Lines ~99-101 of README.md should have a prominent warning that the config example is partial. Must mention that `version` and `hookBehavior` are required. Must suggest copying `assets/guardian.default.json` as starting point.

**Evidence**: README.md line 101 reads:

> `> **Note**: The example below is a partial configuration showing only custom patterns. A valid config file **must** also include `version` and `hookBehavior`. Copy `assets/guardian.default.json` as your starting point and modify from there.`

Verification checklist:
- [x] Prominent warning: Uses blockquote with bold "Note" label -- visually distinct from surrounding prose
- [x] States example is partial: "a partial configuration showing only custom patterns"
- [x] Mentions `version` required: "**must** also include `version`"
- [x] Mentions `hookBehavior` required: "and `hookBehavior`"
- [x] Suggests copying default config: "Copy `assets/guardian.default.json` as your starting point and modify from there"

All five criteria met.

---

### Fix 3: PASS
**Spec**: README.md line ~153 and ~185 should clarify that the .env file does NOT need to exist. Guardian intercepts the command before execution, so no actual file is needed.

**Evidence**:

Line 153 (Important callout):
> `Verify hooks are loaded at the start of your session by running a blocked command -- for example, ask Claude to `cat .env` (even if the file doesn't exist, Guardian should block the attempt).`

- [x] Clarifies .env does not need to exist: "even if the file doesn't exist"
- [x] Explains Guardian blocks regardless: "Guardian should block the attempt"

Line 185 (Troubleshooting section):
> `At the start of your session, run a known-blocked command like `cat .env` (the file does not need to exist -- Guardian intercepts the command before it executes).`

- [x] Clarifies .env does not need to exist: "the file does not need to exist"
- [x] Explains Guardian intercepts before execution: "Guardian intercepts the command before it executes"

Both locations updated with consistent messaging.

---

### Fix 4: PASS
**Spec**: README.md should use "built-in defaults" consistently (not "sensible defaults"). Check lines ~84 and ~86 specifically.

**Evidence**:

Line 84:
> `This generates a `config.json` configuration file in your project with built-in defaults.`

Line 86:
> `If you skip setup, Guardian uses built-in defaults that protect common secret files (.env, *.pem, *.key) and block destructive commands.`

- [x] Line 84 uses "built-in defaults" (not "sensible defaults")
- [x] Line 86 uses "built-in defaults" (consistent with line 84)
- [x] Terminology is consistent across both occurrences

Searched remainder of README.md for any stray "sensible defaults" -- none found.

---

### Fix 5: PASS
**Spec**: SCOPE-02 should be listed under MEDIUM severity in Open Issues. Should document hookBehavior.timeoutSeconds as a by-design limitation. Should explain WHY it's not enforced (git state corruption, Windows threading, etc.). Should also appear in CHANGELOG.md under [Unreleased] Changed section.

**Evidence**:

KNOWN-ISSUES.md lines 86-90 (under "### MEDIUM Severity"):
```
#### SCOPE-02: hookBehavior.timeoutSeconds not enforced at hook level
- **File**: hooks/scripts/bash_guardian.py (line ~1235 TODO comment)
- **Issue**: `hookBehavior.timeoutSeconds` is defined in the config schema and returned by `get_hook_behavior()`, but is not enforced as a blanket timeout on hook execution.
- **Impact**: Users may configure `timeoutSeconds` expecting it to limit hook execution time, but it has no runtime effect.
- **Status**: By-design limitation. Wrapping hook execution with `with_timeout()` risks git state corruption (SIGALRM interrupting subprocess mid-write), partial archive file copies, and Windows threading race conditions.
```

Verification checklist for KNOWN-ISSUES:
- [x] Listed under MEDIUM Severity: Yes, under "### MEDIUM Severity" heading
- [x] Documents hookBehavior.timeoutSeconds: "hookBehavior.timeoutSeconds not enforced at hook level"
- [x] Labeled as by-design limitation: "By-design limitation"
- [x] Explains git state corruption risk: "risks git state corruption (SIGALRM interrupting subprocess mid-write)"
- [x] Explains partial file copies: "partial archive file copies"
- [x] Explains Windows threading: "Windows threading race conditions"
- [x] Follows same format as SCOPE-01: Yes -- File, Issue, Impact, Status fields

CHANGELOG.md line 30 (under [Unreleased] -> Changed):
> `- KNOWN-ISSUES: Added SCOPE-02 documenting hookBehavior.timeoutSeconds as a by-design limitation`

- [x] Present in CHANGELOG: Yes
- [x] Under [Unreleased] Changed section: Yes (line 30, within lines 16-30 Changed block)
- [x] Description matches the actual entry: Accurate summary

All criteria met.

---

### Summary: 5/5 PASS

All five fixes have been correctly applied as specified. Every verification criterion was met with specific evidence from the actual file contents. No discrepancies found between the team reports and the files on disk.
