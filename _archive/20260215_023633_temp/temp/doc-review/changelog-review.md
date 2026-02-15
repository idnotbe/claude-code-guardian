# CHANGELOG.md Review Report
## Date: 2026-02-14
## Reviewer: Teammate B

---

### 1. Document Overview

**File:** `/home/idnotbe/projects/claude-code-guardian/CHANGELOG.md`
**Length:** 30 lines (very short for a project of this complexity)
**Format:** Keep a Changelog 1.1.0 + Semantic Versioning
**Versions documented:** 2 (v1.0.0 and v1.0.1)

The CHANGELOG claims to follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html). It contains two version entries, both dated 2026-02-11.

**Overall assessment:** The changelog dramatically underrepresents the actual feature set. The v1.0.0 "Initial release" section uses 7 vague bullet points to describe a system with 6 Python scripts, 50+ functions, a JSON Schema, a default config with 80+ rules, and numerous sophisticated subsystems (circuit breaker, archive system, ReDoS defense, multi-layer command analysis, etc.). The v1.0.1 section is more precise but still selective.

---

### 2. Claims Inventory (Every Claim Listed)

#### Version 1.0.1 Claims

| # | Category | Claim |
|---|----------|-------|
| C1 | Changed | Renamed user config file from `guardian.json` to `config.json` (path `.claude/guardian/config.json` avoids stutter) |
| C2 | Changed | Renamed `evaluate_guardian()` to `evaluate_rules()` for clarity |
| C3 | Fixed | shlex.split quote handling on Windows (posix=False quote stripping) |
| C4 | Fixed | --force-with-lease moved from block to ask patterns |
| C5 | Fixed | errno 28 disk full check now handles Windows winerror 112 |

#### Version 1.0.0 Claims

| # | Category | Claim |
|---|----------|-------|
| C6 | Added | Initial release |
| C7 | Added | Bash command guarding (block dangerous patterns, ask for confirmation on risky ones) |
| C8 | Added | Edit/Write file guarding (zero-access paths, read-only paths, no-delete paths) |
| C9 | Added | Auto-commit on session stop with configurable git identity |
| C10 | Added | Pre-danger checkpoint commits before destructive operations |
| C11 | Added | JSON Schema for configuration validation |
| C12 | Added | Default configuration template with universal security defaults |
| C13 | Added | `/guardian:init` setup command |

**Total claims: 13**

---

### 3. Claims Verified Against Code (With Evidence)

#### C1: Renamed `guardian.json` to `config.json`
**STATUS: VERIFIED**
- `_guardian_utils.py` line 496: `config_path = Path(project_dir) / ".claude" / "guardian" / "config.json"`
- `_guardian_utils.py` line 358: `SELF_GUARDIAN_PATHS = (".claude/guardian/config.json",)`
- Grep for `guardian.json` across entire codebase returns only CHANGELOG.md itself -- no stale references remain.
- The path `.claude/guardian/config.json` is consistently used throughout.

#### C2: Renamed `evaluate_guardian()` to `evaluate_rules()`
**STATUS: VERIFIED**
- `_guardian_utils.py` line 1367: `def evaluate_rules(command: str) -> tuple[str, str]:`
- `_guardian_utils.py` line 27 (usage docstring): `evaluate_rules,  # Orchestration function`
- Grep for `evaluate_guardian` across entire codebase returns only CHANGELOG.md -- the old name is fully removed from code.

#### C3: shlex.split posix=False on Windows
**STATUS: VERIFIED**
- `bash_guardian.py` line 472: `parts = shlex.split(command, posix=(sys.platform != "win32"))`
- `bash_guardian.py` lines 477-479: COMPAT-03 FIX block strips quotes on Windows:
  ```python
  if sys.platform == "win32":
      parts = [p.strip("'\"") for p in parts]
      parts = [p for p in parts if p]
  ```

#### C4: --force-with-lease moved from block to ask
**STATUS: VERIFIED**
- In `guardian.default.json`, the block pattern for force push uses a negative lookahead to **exclude** `--force-with-lease`:
  ```
  "pattern": "git\\s+push\\s[^;|&\\n]*(?:--force(?!-with-lease)|-f\\b)"
  ```
  This is in the `block` array (line ~52 of guardian.default.json).
- A separate entry in the `ask` array (line ~116 of guardian.default.json):
  ```
  "pattern": "git\\s+push\\s[^;|&\\n]*--force-with-lease"
  ```
- The fallback config in `_guardian_utils.py` lines 382 and 388 mirrors this: block excludes `--force-with-lease`, ask includes it.

#### C5: errno 28 / winerror 112 disk full handling
**STATUS: VERIFIED**
- `bash_guardian.py` line 814:
  ```python
  is_disk_full = e.errno == 28 or getattr(e, "winerror", None) == 112
  ```
- This is within the `archive_files()` function's OSError handler (lines 813-819).

#### C6: Initial release
**STATUS: VERIFIED (trivially)**
- The git log shows the first commits. This is the initial release declaration.

#### C7: Bash command guarding (block dangerous patterns, ask for confirmation)
**STATUS: VERIFIED (under-specified)**
- `bash_guardian.py` is the main implementation (1232 lines).
- `_guardian_utils.py` lines 794-829: `match_block_patterns()` checks against block patterns.
- `_guardian_utils.py` lines 832-865: `match_ask_patterns()` checks against ask patterns.
- `guardian.default.json` contains 19 block patterns and 17 ask patterns.
- **Note:** The changelog bullet does not mention the multi-layer architecture (Layer 0 block patterns, Layer 0b ask patterns, Layer 1 protected path scan, Layer 2 command decomposition, Layer 3 enhanced path extraction, Layer 4 command type detection). This is a significant under-specification.

#### C8: Edit/Write file guarding (zero-access, read-only, no-delete paths)
**STATUS: VERIFIED (under-specified)**
- `edit_guardian.py` (76 lines): Calls `run_path_guardian_hook("Edit")`
- `write_guardian.py` (76 lines): Calls `run_path_guardian_hook("Write")`
- `_guardian_utils.py` lines 2166-2292: `run_path_guardian_hook()` implements all path checks:
  - Symlink escape check (line 2229)
  - Path-within-project check (line 2238)
  - Self-guardian path check (line 2255)
  - Zero-access check (line 2264)
  - Read-only check (line 2278, skipped for Read tool)
- `_guardian_utils.py` lines 1135-1174: `match_zero_access()`, `match_read_only()`, `match_no_delete()`
- **Note:** The changelog does not mention Read tool guarding (`read_guardian.py`) at all. It says "Edit/Write file guarding" but the system also guards Read operations against zero-access paths. This is a gap.

#### C9: Auto-commit on session stop with configurable git identity
**STATUS: VERIFIED**
- `auto_commit.py` (174 lines): Full implementation of auto-commit on Stop event.
- `hooks/hooks.json` lines 41-50: Stop hook registered pointing to `auto_commit.py`.
- `_guardian_utils.py` lines 1716-1845: `ensure_git_config()` reads identity from `gitIntegration.identity` in config.
- `guardian.default.json` `gitIntegration.identity` section:
  ```json
  "identity": {
      "email": "guardian@claude-code.local",
      "name": "Guardian Auto-Commit"
  }
  ```

#### C10: Pre-danger checkpoint commits before destructive operations
**STATUS: VERIFIED**
- `bash_guardian.py` lines 1137-1197: Pre-commit logic inside the `ask` verdict handler.
- Reads `preCommitOnDangerous.enabled` from config (line 1141).
- Checks for rebase/merge in progress (line 1142).
- Creates checkpoint commit with configurable prefix (lines 1149-1158).
- `guardian.default.json` `gitIntegration.preCommitOnDangerous` section:
  ```json
  "preCommitOnDangerous": {
      "enabled": true,
      "messagePrefix": "pre-danger-checkpoint"
  }
  ```

#### C11: JSON Schema for configuration validation
**STATUS: VERIFIED**
- `assets/guardian.schema.json` exists and is a valid JSON Schema (draft-07).
- Defines all configuration sections: `version`, `hookBehavior`, `bashToolPatterns`, `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths`, `allowedExternalPaths`, `gitIntegration`, `bashPathScan`.
- Schema uses `additionalProperties: false` for strict validation.
- `_guardian_utils.py` lines 616-698: `validate_guardian_config()` performs structural/semantic validation in code.

#### C12: Default configuration template with universal security defaults
**STATUS: VERIFIED**
- `assets/guardian.default.json` exists and contains comprehensive defaults:
  - 19 block patterns (root deletion, git repo deletion, force push, fork bomb, interpreter deletions, etc.)
  - 17 ask patterns (recursive deletion, hard reset, clean, branch deletion, SQL operations, etc.)
  - 27 zero-access path patterns (env files, keys, SSH, cloud credentials, terraform state, etc.)
  - 18 read-only path patterns (lock files, node_modules, dist, build, __pycache__, venv, etc.)
  - 28 no-delete path patterns (gitignore, LICENSE, README, CI configs, Dockerfile, build configs, etc.)

#### C13: `/guardian:init` setup command
**STATUS: VERIFIED**
- `commands/init.md` (171 lines): Full setup wizard specification.
- Defines a 6-step process: check existing config, detect project type, build config, present and confirm, write config, confirm success.
- Supports Node.js, Python, Rust, Go, Java/Kotlin, Docker, and IaC project types.

---

### 4. Claims NOT Found in Code (Potential Gaps)

**No unverified claims.** All 13 claims in the changelog have corresponding implementations in the codebase. Every claim was verified.

However, several claims are **under-specified** (marked above) where the changelog bullet covers only the surface of a much deeper implementation.

---

### 5. Missing Items (Things in Code but NOT in Changelog)

This is the most significant finding. The changelog omits a large number of implemented features and capabilities. These are categorized into two tiers per the vibe-check recommendation.

#### Tier 1: User-Facing Features Not in Changelog

These are features that users interact with directly or that affect observable behavior. They should almost certainly have changelog entries.

| # | Feature | Evidence |
|---|---------|----------|
| M1 | **Read tool guarding** (`read_guardian.py`) | `hooks/hooks.json` lines 13-20 register a PreToolUse hook for "Read". `read_guardian.py` blocks zero-access paths, symlink escapes, and paths outside the project for Read operations. The changelog only mentions "Edit/Write file guarding." |
| M2 | **Dry-run mode** (CLAUDE_HOOK_DRY_RUN env var) | `_guardian_utils.py` lines 706-719: `is_dry_run()` checks the `CLAUDE_HOOK_DRY_RUN` environment variable. `bash_guardian.py` uses it at lines 962, 1049, 1071, 1119, 1160, 1200. This is a user-configurable simulation mode. |
| M3 | **Archive system for untracked file deletion** | `bash_guardian.py` lines 690-849: Full archive system with `archive_files()`, `create_deletion_log()`, `generate_archive_title()`. Archives untracked files to `_archive/` directory before allowing deletion. Includes safety limits (100MB per file, 500MB total, 50 files max). |
| M4 | **`allowedExternalPaths` configuration option** | `guardian.schema.json` defines it. `_guardian_utils.py` lines 1177-1191: `match_allowed_external_path()`. `_guardian_utils.py` line 2240: Used in `run_path_guardian_hook()`. Allows users to whitelist paths outside the project for write operations. |
| M5 | **`bashPathScan` configuration section** (Layer 1 raw string scanning) | `guardian.schema.json` defines it with `enabled`, `scanTiers`, `exactMatchAction`, `patternMatchAction` options. `bash_guardian.py` lines 303-374: `scan_protected_paths()`. This is a configurable defense-in-depth layer. |
| M6 | **Self-guarding of config file** | `_guardian_utils.py` lines 357-362: `SELF_GUARDIAN_PATHS` constant. Lines 2094-2139: `is_self_guardian_path()`. The guardian protects its own configuration from modification. |
| M7 | **Symlink escape detection** | `_guardian_utils.py` lines 927-971: `is_symlink_escape()`. Used in both bash_guardian.py (line 1013) and run_path_guardian_hook() (line 2229). Prevents symlink attacks pointing outside the project. |
| M8 | **`hookBehavior` configuration** (onTimeout, onError, timeoutSeconds) | `guardian.schema.json` defines it as required. `_guardian_utils.py` lines 600-613: `get_hook_behavior()`. Allows users to configure fail-close/fail-open behavior. |
| M9 | **Fail-close on unhandled exceptions** | `bash_guardian.py` lines 1215-1231: Top-level exception handler denies on crash. Same pattern in `edit_guardian.py`, `write_guardian.py`, `read_guardian.py`. This is a security posture decision. |
| M10 | **Interpreter-mediated deletion detection** (Python, Node, Perl, Ruby) | `bash_guardian.py` lines 599-604: Detects `os.remove`, `shutil.rmtree`, `unlinkSync`, `rmSync`, `File.delete`, etc. `guardian.default.json` has 4 block patterns for interpreter deletions. Not mentioned at all in changelog. |

#### Tier 2: Internal Implementation Details Not in Changelog

These are internal mechanisms that affect robustness and reliability. They are judgment calls for changelog inclusion but represent significant engineering effort.

| # | Feature | Evidence |
|---|---------|----------|
| M11 | **Circuit breaker pattern** | `_guardian_utils.py` lines 225-351: `set_circuit_open()`, `is_circuit_open()`, `clear_circuit()`. Auto-expires after 1 hour. Used by `auto_commit.py` and `bash_guardian.py` to prevent cascading failures. |
| M12 | **ReDoS defense with regex timeout** | `_guardian_utils.py` lines 59-65: Optional `regex` module import. Lines 727-786: `safe_regex_search()` with configurable timeout (default 0.5s). All pattern matching uses this. |
| M13 | **3-step config resolution chain** | `_guardian_utils.py` lines 467-568: (1) User config `.claude/guardian/config.json`, (2) Plugin default `assets/guardian.default.json`, (3) Hardcoded `_FALLBACK_CONFIG`. Ensures critical paths are always protected. |
| M14 | **Hardcoded fallback config** | `_guardian_utils.py` lines 366-413: `_FALLBACK_CONFIG` dict with essential protections. Used when config file is missing or corrupted. |
| M15 | **Log rotation** | `_guardian_utils.py` lines 1199-1231: `_rotate_log_if_needed()`. Rotates at 1MB, keeps one backup (.log.1). |
| M16 | **Hook timeout mechanism** | `_guardian_utils.py` lines 110-169: `HookTimeoutError`, `with_timeout()`. Platform-specific: signal-based on Unix, threading-based on Windows. |
| M17 | **Detached HEAD detection** | `_guardian_utils.py` lines 1981-2020: `is_detached_head()`. `auto_commit.py` line 78: Skips auto-commit in detached HEAD to avoid orphaned commits. |
| M18 | **Rebase/merge in-progress detection** | `_guardian_utils.py` lines 2023-2050: `is_rebase_or_merge_in_progress()`. Checks for `.git/rebase-merge`, `.git/MERGE_HEAD`, `.git/CHERRY_PICK_HEAD`, `.git/BISECT_LOG`. Used in both `auto_commit.py` and `bash_guardian.py`. |
| M19 | **Multi-layer command analysis architecture** (Layers 0-4) | `bash_guardian.py` docstring lines 7-14 and main() lines 921-930 describe the full pipeline: Layer 0 (block), Layer 0b (ask), Layer 1 (path scan), Layer 2 (command decomposition), Layer 3 (path extraction), Layer 4 (type detection). |
| M20 | **Command decomposition** (Layer 2) | `bash_guardian.py` lines 79-242: `split_commands()` handles `;`, `&&`, `||`, `|`, `&`, newline. Quote-aware, nesting-aware, backslash-escape-aware. |
| M21 | **Verdict aggregation** (deny > ask > allow) | `bash_guardian.py` lines 888-911: `_VERDICT_PRIORITY`, `_stronger_verdict()`. All layers complete before final decision is emitted (C-1 fix). |
| M22 | **Git lock file retry with backoff** | `_guardian_utils.py` `git_add_all()` (line 1608), `git_add_tracked()` (line 1671), `git_commit()` (line 1874): All have `max_retries=3` with exponential backoff on lock errors and timeouts. |
| M23 | **Commit message sanitization** | `_guardian_utils.py` lines 1488-1512: `sanitize_commit_message()`. Removes control characters, preserves UTF-8, enforces 72-char limit. |
| M24 | **Oversized command fail-close** (F-02 FIX) | `_guardian_utils.py` lines 807-816: Commands exceeding 100,000 bytes are blocked to prevent padding attacks that bypass pattern matching. |
| M25 | **Fail-closed safety net for unresolved paths** (F1) | `bash_guardian.py` lines 1002-1007: If write/delete detected but no paths could be resolved, escalates to "ask" instead of silently allowing. |
| M26 | **Process substitution handling** (F6) | `bash_guardian.py` lines 436-437: `extract_redirection_targets()` skips `>(cmd)` and `<(cmd)` which are not file paths. |
| M27 | **Path traversal prevention** (F7) | `bash_guardian.py` lines 544-564: `_is_within_project_or_would_be()` uses `Path.resolve(strict=False)` to prevent `../` traversal attacks. |
| M28 | **Symlink-preserving archive** (F5) | `bash_guardian.py` lines 793-801: `archive_files()` preserves symlinks as symlinks instead of dereferencing them during archive. |

---

### 6. Formatting and Consistency Issues

| # | Issue | Details |
|---|-------|---------|
| F1 | **Both versions have the same date** | v1.0.0 and v1.0.1 are both dated `2026-02-11`. If both shipped the same day, this is valid but unusual for a major + patch release. |
| F2 | **No `[Unreleased]` section** | Keep a Changelog convention recommends maintaining an `[Unreleased]` section at the top for tracking in-progress changes. The file lacks this. |
| F3 | **No version comparison links** | Keep a Changelog convention expects footer links like `[1.0.1]: https://github.com/.../compare/v1.0.0...v1.0.1`. These are absent. |
| F4 | **Inconsistent detail level** | v1.0.1 entries are specific and verifiable ("shlex.split quote handling on Windows"). v1.0.0 entries are extremely vague ("Bash command guarding"). The gap in specificity is large. |
| F5 | **Missing `Added` sub-items under v1.0.0** | Each v1.0.0 bullet point covers a complex subsystem. Keep a Changelog allows nested bullets or multiple entries to provide adequate detail. |
| F6 | **"Changed" section in v1.0.1 documents a rename** | The rename from `guardian.json` to `config.json` is more accurately a breaking change if any users existed on v1.0.0. Since both versions share a date, this is likely fine, but worth noting. |
| F7 | **No `Security` category used** | Keep a Changelog defines a `Security` category. Several features (symlink escape detection, fail-close behavior, ReDoS defense, oversized command blocking, self-guarding) are security features that would benefit from this category. |

---

### 7. Recommendations

#### Priority 1: Address Major Documentation Gaps

1. **Add Read tool guarding to the changelog** (M1). The system guards Read, Edit, and Write tools, but the changelog only mentions Edit/Write. This could mislead users into thinking Read operations are unguarded.

2. **Add dry-run mode to the changelog** (M2). This is a user-configurable feature via an environment variable. Users need to know it exists.

3. **Add archive system to the changelog** (M3). The automatic archiving of untracked files before deletion is a major safety feature that users should know about.

4. **Add `allowedExternalPaths` to the changelog** (M4). This is a user-configurable schema option that allows writes outside the project boundary. It is documented in the schema but invisible in the changelog.

5. **Add interpreter-mediated deletion detection** (M10). The system blocks deletions via Python, Node.js, Perl, and Ruby interpreters -- a notable security feature.

#### Priority 2: Expand v1.0.0 Detail

6. **Break down the v1.0.0 "Bash command guarding" bullet** into sub-bullets covering:
   - Block patterns (19 rules: force push, root deletion, git repo deletion, fork bomb, etc.)
   - Ask patterns (17 rules: recursive deletion, hard reset, SQL operations, etc.)
   - Multi-layer analysis (command decomposition, path extraction, verdict aggregation)
   - Protected path scanning (Layer 1 raw string defense)

7. **Break down "Edit/Write file guarding" bullet** to include:
   - Read tool guarding
   - Symlink escape detection
   - Self-guarding of config file
   - Outside-project path blocking

8. **Break down "Auto-commit on session stop" bullet** to mention:
   - Circuit breaker integration (prevents cascading failures)
   - Detached HEAD and rebase/merge safety checks
   - Configurable `includeUntracked` option

#### Priority 3: Formatting Fixes

9. **Add an `[Unreleased]` section** at the top per Keep a Changelog convention.

10. **Add version comparison links** in the footer.

11. **Use the `Security` category** for security-focused features.

12. **Add a `bashPathScan` mention** under either v1.0.0 Added or as a separate configurable feature, since it has its own schema section and is user-configurable.

#### Priority 4: Consider Whether to Backfill or Go Forward

Given that v1.0.0 and v1.0.1 share a date and the project appears to be in early release, the team should decide:

- **Option A (Backfill):** Expand v1.0.0 with comprehensive sub-bullets and move security features to a `Security` category. This produces the most accurate historical record.
- **Option B (Go Forward):** Leave v1.0.0 and v1.0.1 as-is and start detailed entries from the next version. Add a note to v1.0.0 like "See README.md for full feature documentation."

**Recommendation: Option A.** The changelog is the canonical record of what shipped. With only 2 versions, backfilling is low-effort and high-value.

---

### Summary Statistics

| Metric | Count |
|--------|-------|
| Total changelog claims | 13 |
| Claims verified against code | 13 (100%) |
| Claims NOT found in code | 0 |
| Claims under-specified | 4 (C7, C8, C9, C10) |
| Tier 1 missing items (user-facing) | 10 |
| Tier 2 missing items (internal) | 18 |
| Formatting issues | 7 |
| Total recommendations | 12 |

**Bottom line:** The changelog is *accurate* -- nothing it claims is false. But it is *severely incomplete*, documenting roughly 30% of the user-facing feature surface and virtually none of the internal architecture. For a security-focused tool where users need to understand what protections exist, this gap is significant.
