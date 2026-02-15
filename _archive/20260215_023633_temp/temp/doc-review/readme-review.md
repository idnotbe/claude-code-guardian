# README.md Review Report
## Date: 2026-02-14
## Reviewer: Teammate D

---

### 1. Document Overview

The README.md is 168 lines and covers: project motivation ("Why Guardian?"), feature summary ("What It Catches"), installation (manual + marketplace), setup (/guardian:init), configuration, architecture ("How It Works"), failure modes, requirements, and license.

Overall, the README is well-written, clearly structured, and appropriately scoped for a user-facing document. The tone is practical and the security philosophy (fail-closed, intervention-by-exception) is consistently communicated.

However, several concrete gaps exist between what the README describes and what the implementation actually provides. These range from a missing hook in the architecture table to entire feature subsystems (circuit breaker, archive-before-delete, dry-run mode) that are undocumented.

---

### 2. Section-by-Section Verification

#### Section: Title and Tagline (Lines 1-3)
- **Claim**: "Selective security guardrails for Claude Code's `--dangerously-skip-permissions` mode."
- **Verdict**: ACCURATE. This correctly describes the project's purpose.

#### Section: "Why Guardian?" (Lines 5-13)
- **Claim**: Guardian "hooks into Claude Code's plugin system to intercept operations before they execute."
- **Verdict**: ACCURATE. The `.claude-plugin/plugin.json` declares hooks via `hooks/hooks.json`, which registers PreToolUse hooks for Bash, Read, Edit, Write and a Stop hook for auto-commit.
- **Claim**: "The 99% of safe operations run silently. The 1% that could ruin your day ... get caught."
- **Verdict**: ACCURATE in spirit. The hook scripts exit silently (sys.exit(0) with no output) for allowed operations, per Claude Code's hook protocol.

#### Section: "What It Catches" -- Safety Checkpoints (Lines 17-20)
- **Claim**: "Auto-commits pending changes when a Claude Code session ends."
- **Verdict**: ACCURATE. `auto_commit.py` runs on the Stop event and commits changes when `gitIntegration.autoCommit.enabled` and `onStop` are both true.
- **Claim**: "Creates a commit before any destructive operation."
- **Verdict**: PARTIALLY ACCURATE. The pre-danger checkpoint commit (`preCommitOnDangerous`) only fires for operations that reach an "ask" verdict in `bash_guardian.py` (lines 1137-1197). Operations that are outright blocked (deny) do NOT get a pre-commit because they never execute. The README implies pre-commit happens for all destructive operations, but it only happens for the "ask" tier. This is arguably correct behavior (no need to checkpoint before a blocked operation) but the README wording is slightly misleading.
- **Claim**: "Your work is never more than one `git reset` away from recovery."
- **Verdict**: ASPIRATIONAL / PARTIALLY ACCURATE. The auto-commit only stages tracked files by default (`includeUntracked: false` in guardian.default.json). Untracked files are NOT committed and thus NOT recoverable via `git reset`. The archive-before-delete feature provides a separate safety net for untracked files being deleted, but this is not mentioned in the README at all.

#### Section: "What It Catches" -- Hard Blocks (Lines 22-26)
- **Claim**: "`rm -rf /`, fork bombs, and other catastrophic shell commands."
- **Verdict**: ACCURATE. The default config blocks root deletion (`rm\s+-[rRf]+\s+/(?:\s*$|\*)`), fork bombs (`:\s*\(\s*\)\s*\{[^}]{0,200}\}\s*;\s*:`), and many other catastrophic patterns.
- **Claim**: "Reading `.env`, `.pem`, SSH keys, and other secret files."
- **Verdict**: ACCURATE. These are in `zeroAccessPaths` in the default config. The Read Guardian hook enforces zero-access checks via `run_path_guardian_hook("Read")`.
- **Claim**: "Writing to protected paths outside your project."
- **Verdict**: ACCURATE. The `run_path_guardian_hook()` function in `_guardian_utils.py` (line 2238) checks `is_path_within_project()` and blocks external writes unless the path is in `allowedExternalPaths`.
- **Claim**: "`git push --force` and `--force-with-lease` (configure to allow if needed)."
- **Verdict**: PARTIALLY INACCURATE. In the current default config, `--force` (without `--force-with-lease`) is in the **block** list, but `--force-with-lease` is in the **ask** list, not the block list. The README says both are "hard blocks (always denied)" but `--force-with-lease` is actually a confirmation prompt, not a hard block. The parenthetical "(configure to allow if needed)" partially covers this, but placing both under "Hard blocks" is misleading. KNOWN-ISSUES.md UX-08 confirms this was intentionally changed in v1.0.1.

#### Section: "What It Catches" -- Confirmation Prompts (Lines 28-30)
- **Claim**: "`git reset --hard`, branch deletion."
- **Verdict**: ACCURATE. Both are in the `bashToolPatterns.ask` list in the default config.
- **Claim**: "Other risky-but-sometimes-intentional operations."
- **Verdict**: ACCURATE but vague. The default config has 17 ask patterns including `rm -rf` (non-root), `git clean`, `git stash drop`, SQL DROP/TRUNCATE/DELETE, `find -exec rm`, `xargs rm`, etc. The README could be more specific.

#### Section: "What It Catches" -- Protected Files (Lines 32-35)
- **Claim**: "Zero-access paths for secrets."
- **Verdict**: ACCURATE. Implemented via `match_zero_access()` in `_guardian_utils.py`.
- **Claim**: "Read-only paths for lock files and generated configs."
- **Verdict**: ACCURATE. Implemented via `match_read_only()`.
- **Claim**: "No-delete paths for critical project files."
- **Verdict**: ACCURATE. Implemented via `match_no_delete()`.
- **Claim**: "Default patterns cover both Unix and Windows commands."
- **Verdict**: ACCURATE. The default config includes `Remove-Item`, `del`, and `ri` (PowerShell alias) alongside Unix equivalents.

#### Section: Installation -- Manual (Lines 39-50)
- **Claim**: `git clone https://github.com/idnotbe/claude-code-guardian` then `claude --plugin-dir /path/to/claude-code-guardian`.
- **Verdict**: PLAUSIBLE BUT UNVERIFIED. The project has a valid `.claude-plugin/plugin.json` structure. Whether `--plugin-dir` is the correct Claude Code CLI flag depends on the Claude Code plugin system, which is noted as unverified in KNOWN-ISSUES.md (PV-01 through PV-05).
- **Claim**: "The `--plugin-dir` flag applies to a single session."
- **Verdict**: UNVERIFIED. This is a claim about Claude Code's behavior, not Guardian's. Cannot be verified from source code alone.

#### Section: Installation -- Marketplace (Lines 52-59)
- **Claim**: `/plugin marketplace add idnotbe/claude-code-guardian` and `/plugin install claude-code-guardian@idnotbe-security`.
- **Verdict**: UNVERIFIED / LIKELY SPECULATIVE. KNOWN-ISSUES.md UX-07 explicitly flags this: "Marketplace installation commands are speculative -- actual CLI syntax may differ." The README does include a warning that marketplace is "currently experimental."

#### Section: Setup (Lines 61-71)
- **Claim**: "Run `/guardian:init` -- this generates a `config.json` configuration file."
- **Verdict**: ACCURATE in intent. The `commands/init.md` file defines the `/guardian:init` slash command which guides the user through config generation. Whether it registers correctly depends on Claude Code's command discovery (KNOWN-ISSUES.md PV-05).
- **Claim**: "If you skip setup, Guardian uses built-in defaults."
- **Verdict**: ACCURATE. The 3-step config resolution chain in `_guardian_utils.py` (lines 467-568) falls back to plugin default config, then hardcoded `_FALLBACK_CONFIG`.

#### Section: Configuration (Lines 73-116)
- **Claim**: Config resolved in order: (1) `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json`, (2) plugin default as fallback.
- **Verdict**: PARTIALLY ACCURATE. The actual resolution chain is 3-step, not 2-step:
  1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` (user custom)
  2. `$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json` (plugin default)
  3. Hardcoded `_FALLBACK_CONFIG` (emergency fallback)
  The README mentions the hardcoded fallback on line 80 ("a hardcoded minimal guardian ruleset activates as an emergency fallback") but does not mention the plugin default step as a distinct middle step. This is a minor gap.
- **Claim**: Example config JSON on lines 86-101.
- **Verdict**: PARTIALLY INACCURATE. The example config omits `version` (required by schema), `hookBehavior` (required by schema), and `bashPathScan` (present in default config). While the README says "partial custom configuration," a user copying this example would get a schema validation failure because `version` and `hookBehavior` are required fields per `guardian.schema.json`.

##### Configuration Sections Table (Lines 103-115)
- **`hookBehavior`**: ACCURATE. Exists in schema and default config.
- **`bashToolPatterns.block`**: ACCURATE.
- **`bashToolPatterns.ask`**: ACCURATE.
- **`zeroAccessPaths`**: ACCURATE.
- **`readOnlyPaths`**: ACCURATE.
- **`noDeletePaths`**: ACCURATE.
- **`allowedExternalPaths`**: ACCURATE.
- **`gitIntegration`**: ACCURATE.
- **MISSING from table**: `bashPathScan` -- This section exists in both the default config and the schema but is completely absent from the README. It controls Layer 1 raw command string scanning behavior (enabled/disabled, scan tiers, match actions).
- **MISSING from table**: `version` -- Required by schema but not mentioned in the configuration sections table.

#### Section: "How It Works" -- Hook Table (Lines 118-128)
- **Claim**: Four hooks: Bash Guardian, Edit Guardian, Write Guardian, Auto-Commit.
- **Verdict**: INACCURATE. There are actually FIVE hooks registered in `hooks/hooks.json`:
  1. PreToolUse: Bash -> `bash_guardian.py`
  2. PreToolUse: Read -> `read_guardian.py`
  3. PreToolUse: Edit -> `edit_guardian.py`
  4. PreToolUse: Write -> `write_guardian.py`
  5. Stop -> `auto_commit.py`
  The **Read Guardian** hook is completely missing from the README table. This is a significant documentation gap since users would not know their file read operations are being intercepted and guarded. The Read Guardian blocks reading of zeroAccess files, symlink escapes, and paths outside the project.

#### Section: Fail-Closed Behavior (Lines 129)
- **Claim**: "All security hooks (Bash, Edit, Write) are fail-closed."
- **Verdict**: ACCURATE but incomplete. Read Guardian is also fail-closed (its ImportError handler emits a deny response, and its unhandled exception handler also denies). The claim should include Read Guardian.
- **Claim**: "Auto-Commit hook is fail-open by design."
- **Verdict**: ACCURATE. The auto_commit.py ImportError handler prints a warning to stderr and exits 0, and the main exception handler also exits 0.

#### Section: "How 'ask' works in permissionless mode" (Lines 133-135)
- **Claim**: "Hooks operate at a layer above the permission bypass."
- **Verdict**: ACCURATE per Claude Code's documented hook architecture. Hooks can return "ask" decisions that prompt users even in permissionless mode.

#### Section: Failure Modes (Lines 137-155)
- **Claim**: "Does not protect against: Shell commands inside Python scripts (e.g., `subprocess.run()`)."
- **Verdict**: PARTIALLY ACCURATE. Guardian DOES block some interpreter-mediated operations. The default config blocks `python ... os.remove`, `python ... shutil.rmtree`, `node ... unlinkSync`, etc. However, arbitrary `subprocess.run()` calls within a Python script that Claude runs would indeed not be intercepted. The claim is technically correct but could mislead users into thinking Guardian has zero interpreter coverage.
- **Claim**: "Does not protect against: Determined human adversaries crafting bypass commands."
- **Verdict**: ACCURATE. This is an honest and important caveat.
- **Claim**: "Does protect against: Loss of work (via auto-commit checkpoints)."
- **Verdict**: PARTIALLY ACCURATE. Only protects tracked files by default. Untracked file loss is mitigated by the archive-before-delete feature, which is undocumented in the README.

#### Section: Disabling Guardian (Lines 157-159)
- **Claim**: "Remove the `--plugin-dir` flag... delete the cloned repository... remove `.claude/guardian/` directory."
- **Verdict**: ACCURATE. These are correct uninstall steps.
- **MISSING**: No mention of `CLAUDE_HOOK_DRY_RUN=1` environment variable for temporary disable/testing mode. This is noted in KNOWN-ISSUES.md as UX-11.

#### Section: Requirements (Lines 161-163)
- **Claim**: "Python 3.10 or later."
- **Verdict**: PLAUSIBLE. The code uses `list[str]` type hints (PEP 585, Python 3.9+), `Path.unlink(missing_ok=True)` (Python 3.8+), and `bool | None` union syntax (PEP 604, Python 3.10+). So Python 3.10+ is the correct minimum. ACCURATE.
- **Claim**: "Git (for auto-commit features)."
- **Verdict**: ACCURATE. Git is required for auto-commit and is checked via `is_git_available()` in `_guardian_utils.py`.
- **MISSING**: No mention of the optional `regex` package for ReDoS defense. The code has explicit support for it (`_guardian_utils.py` lines 59-65) with a fallback to standard `re`. While optional, this is a security-relevant dependency worth mentioning.

#### Section: License (Line 168)
- **Verdict**: ACCURATE. The LICENSE file exists and contains an MIT license.

---

### 3. Accurate Claims (Confirmed)

1. **Core architecture**: Guardian hooks into Claude Code's plugin system via PreToolUse and Stop events.
2. **Fail-closed semantics**: Security hooks deny on error/crash. Auto-commit is fail-open.
3. **Configuration resolution**: User config -> plugin default -> hardcoded fallback chain works as described.
4. **Block patterns**: `rm -rf /`, fork bombs, git repo deletion, force push are all blocked in default config.
5. **Ask patterns**: `git reset --hard`, branch deletion, recursive rm require confirmation.
6. **Protected file tiers**: zeroAccessPaths, readOnlyPaths, noDeletePaths all implemented correctly.
7. **Configuration sections table**: 7 of 7 listed sections are accurate (hookBehavior, bashToolPatterns.block/ask, zeroAccessPaths, readOnlyPaths, noDeletePaths, allowedExternalPaths, gitIntegration).
8. **Auto-commit on session stop**: Implemented in auto_commit.py, configurable via gitIntegration.autoCommit.
9. **Pre-danger checkpoints**: Implemented in bash_guardian.py for "ask" tier operations.
10. **`/guardian:init` setup wizard**: Exists as `commands/init.md` with project-type detection.
11. **Python 3.10+ requirement**: Matches code's use of PEP 604 union types.
12. **Git requirement**: Correctly identified as needed for auto-commit features.
13. **MIT License**: Matches LICENSE file.
14. **Unix + Windows coverage**: Default patterns include PowerShell and Windows commands.
15. **"ask" works in permissionless mode**: Correctly explained.
16. **Honest failure mode documentation**: Accurately describes what Guardian cannot protect against.

---

### 4. Inaccurate Claims (Gaps Found)

| # | Severity | Location | Claim | Reality |
|---|----------|----------|-------|---------|
| 1 | **HIGH** | Lines 122-127 | Hook table lists 4 hooks (Bash, Edit, Write, Auto-Commit) | There are 5 hooks. **Read Guardian** is missing from the table. `hooks/hooks.json` registers `read_guardian.py` for PreToolUse:Read. |
| 2 | **MEDIUM** | Lines 22-26 | `--force-with-lease` listed under "Hard blocks (always denied)" | `--force-with-lease` is in the **ask** list (confirmation prompt), not the block list. Only bare `--force` is hard-blocked. Changed in v1.0.1 per CHANGELOG.md. |
| 3 | **MEDIUM** | Lines 86-101 | Example config is presented as a "partial custom configuration" | The example omits `version` and `hookBehavior`, both of which are **required** by `guardian.schema.json`. A user copying this example and adding only their own patterns would fail schema validation. |
| 4 | **LOW** | Lines 17-20 | "Creates a commit before any destructive operation" | Pre-commit only fires for "ask" tier operations, not for "block" tier (which are denied outright) or for operations that pass all checks. The wording implies universal pre-commit. |
| 5 | **LOW** | Lines 17-20 | "Your work is never more than one `git reset` away" | Only tracked files are auto-committed by default (`includeUntracked: false`). Untracked files require the archive-before-delete feature (undocumented in README) for recovery. |
| 6 | **LOW** | Line 129 | "All security hooks (Bash, Edit, Write) are fail-closed" | Should also list Read Guardian as fail-closed. |

---

### 5. Missing Documentation (In Code but Not in README)

| # | Severity | Feature | Implementation Location | Description |
|---|----------|---------|------------------------|-------------|
| 1 | **HIGH** | Read Guardian hook | `hooks/scripts/read_guardian.py`, `hooks/hooks.json` | A full Read file guardian that blocks reading zeroAccess files, symlink escapes, and paths outside the project. Completely absent from README. |
| 2 | **HIGH** | `bashPathScan` config section | `guardian.default.json`, `guardian.schema.json`, `bash_guardian.py` lines 303-374 | Layer 1 raw command string scanning for protected path names. Configurable via `enabled`, `scanTiers`, `exactMatchAction`, `patternMatchAction`. Not mentioned anywhere in README. |
| 3 | **MEDIUM** | Archive-before-delete | `bash_guardian.py` lines 690-849 | When deleting untracked files, Guardian archives them to `_archive/` with timestamped folders and deletion logs before prompting for confirmation. This is a significant safety feature with no README coverage. |
| 4 | **MEDIUM** | Circuit breaker pattern | `_guardian_utils.py` lines 222-351 | If auto-commit fails, a circuit breaker opens to prevent repeated failures. Auto-expires after 1 hour. Recoverable by deleting `.claude/guardian/.circuit_open`. No README documentation. |
| 5 | **MEDIUM** | Dry-run mode | `_guardian_utils.py` lines 706-719, used throughout all hooks | Setting `CLAUDE_HOOK_DRY_RUN=1` enables simulation mode where hooks log what they WOULD do without actually blocking. Useful for testing. Not mentioned in README. Already flagged as UX-11 in KNOWN-ISSUES.md. |
| 6 | **MEDIUM** | Self-guarding | `_guardian_utils.py` lines 2094-2139, `SELF_GUARDIAN_PATHS` | Guardian protects its own config file (`.claude/guardian/config.json`) from being modified by the AI agent. This is an important security property not documented in README. |
| 7 | **LOW** | Symlink escape detection | `_guardian_utils.py` lines 927-971, `bash_guardian.py` lines 1012-1018 | Guardian detects and blocks symlinks that point outside the project directory. Mentioned indirectly in "Writing to protected paths outside your project" but the symlink-specific protection is not called out. |
| 8 | **LOW** | ReDoS defense | `_guardian_utils.py` lines 55-69, 727-786 | Optional `regex` package integration for timeout-protected regex matching. Falls back to standard `re` without timeout. Not mentioned in README or Requirements. |
| 9 | **LOW** | Multi-layer analysis architecture | `bash_guardian.py` (4 layers) | The Bash Guardian uses a sophisticated 4-layer analysis: Layer 0 (pattern matching), Layer 1 (raw string scan), Layer 2 (command decomposition), Layer 3+4 (path extraction + type detection). The README describes it simply as "checks commands against block/ask patterns." |
| 10 | **LOW** | Interpreter-mediated deletion blocking | Default config block patterns | Guardian blocks `python os.remove`, `node unlinkSync`, `perl unlink`, `ruby File.delete` etc. The README "Does not protect against" section says "Shell commands inside Python scripts" which is partially contradicted by these blocks. |
| 11 | **LOW** | `version` config field | `guardian.schema.json` (required) | The `version` field is required by schema but never mentioned in the Configuration section of the README. |
| 12 | **LOW** | Skills and Agents | `skills/config-guide/`, `agents/config-assistant.md` | The plugin ships with a config-guide skill and config-assistant agent registered in `plugin.json`. These are not mentioned in the README. |
| 13 | **LOW** | Log rotation | `_guardian_utils.py` lines 1199-1231 | Guardian logs to `.claude/guardian/guardian.log` with automatic rotation at 1MB. No documentation on log location or rotation. |

---

### 6. Outdated Information

| # | Item | Status |
|---|------|--------|
| 1 | `--force-with-lease` listed as "hard block" | Outdated since v1.0.1 -- it was moved to the "ask" tier. README was not updated to reflect this change. |
| 2 | Hook table missing Read Guardian | The Read Guardian hook was added (based on hooks.json and the existence of read_guardian.py) but the README table was never updated. |

No other outdated information was found. The README does not reference any removed features or deprecated APIs.

---

### 7. Recommendations

#### Priority 1: Fix Inaccuracies (HIGH)

**R-01: Add Read Guardian to the "How It Works" table.**
The table at lines 122-127 should include a fifth row:
```
| Read Guardian | PreToolUse: Read | Validates file paths against access rules |
```
The fail-closed statement on line 129 should also be updated to: "All security hooks (Bash, Read, Edit, Write) are fail-closed."

**R-02: Move `--force-with-lease` from "Hard blocks" to "Confirmation prompts" in the "What It Catches" section.**
It was moved to the ask tier in v1.0.1 but the README still lists it under hard blocks. Suggested rewrite for line 26:
```
- `git push --force` (configure to allow if needed; `--force-with-lease` prompts for confirmation)
```

#### Priority 2: Add Missing Critical Documentation (MEDIUM)

**R-03: Document `bashPathScan` in the Configuration Sections table.**
Add a row:
```
| `bashPathScan` | Raw command string scanning for protected path names (Layer 1) |
```

**R-04: Document the archive-before-delete feature.**
Add a brief mention under "Safety checkpoints" or as a new subsection. Example:
```
- Archives untracked files to `_archive/` before deletion, with timestamped folders
```

**R-05: Document dry-run mode.**
Add a subsection or mention under "Disabling Guardian":
```
To test Guardian without blocking, set `CLAUDE_HOOK_DRY_RUN=1` in your environment.
```

**R-06: Fix the example config to include required fields.**
At minimum, add `"version": "1.0.0"` and a `"hookBehavior"` object to the example, or add a note that the example is incomplete and must include these fields.

**R-07: Document the circuit breaker.**
Mention in the Failure Modes section that if auto-commit fails, Guardian stops attempting auto-commits until `.claude/guardian/.circuit_open` is removed or 1 hour passes.

#### Priority 3: Improve Completeness (LOW)

**R-08: Add `regex` package as optional dependency in Requirements.**
```
- `regex` package (optional, for ReDoS defense): `pip install regex`
```

**R-09: Clarify the "Does not protect against" section.**
The claim about Python subprocess is technically correct but misleading since Guardian does block interpreter-mediated deletions at the Bash command level. Consider rewording to:
```
- Arbitrary code execution within interpreter scripts (Guardian blocks known deletion APIs
  like os.remove and shutil.rmtree, but cannot catch all possible code patterns)
```

**R-10: Mention self-guarding.**
Add a brief note that Guardian protects its own config file from AI modification.

**R-11: Document log file location.**
Mention that Guardian logs to `.claude/guardian/guardian.log` for debugging.

---

### Cross-Reference with KNOWN-ISSUES.md

| KNOWN-ISSUES ID | This Review Finding | Status |
|-----------------|-------------------|--------|
| UX-07 | Marketplace install commands unverified | Confirmed -- README includes "experimental" warning |
| UX-08 | --force-with-lease block vs ask | Confirmed -- README still shows old behavior (Inaccuracy #2) |
| UX-11 | No dry-run documentation | Confirmed -- Missing Documentation #5 |
| PV-01 through PV-05 | Plugin system assumptions | Confirmed -- Installation section claims cannot be verified from source |
| COMPAT-08 | Relative $schema in default config | Not a README issue, but the example config inherits this problem |

**Newly discovered issues not in KNOWN-ISSUES.md:**
- Read Guardian missing from README hook table (HIGH)
- bashPathScan config section undocumented (HIGH)
- Archive-before-delete undocumented (MEDIUM)
- Circuit breaker undocumented (MEDIUM)
- Self-guarding undocumented (LOW)
- Example config missing required schema fields (MEDIUM)

---

### Summary Statistics

| Category | Count |
|----------|-------|
| Sections verified | 15 |
| Claims confirmed accurate | 16 |
| Inaccurate claims found | 6 (1 HIGH, 2 MEDIUM, 3 LOW) |
| Missing documentation items | 13 (2 HIGH, 5 MEDIUM, 6 LOW) |
| Outdated information items | 2 |
| Recommendations | 11 (2 Priority 1, 5 Priority 2, 4 Priority 3) |
