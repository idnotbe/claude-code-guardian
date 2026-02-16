# V2 Developer Perspective Review

## Reviewer Context
Simulating a developer who has **never seen this plugin before**, evaluating whether the documentation alone is sufficient to understand, install, configure, use, and troubleshoot claude-code-guardian.

---

## Evaluation Criteria Results

### 1. First Impression
**PASS**

The opening line -- "Selective security guardrails for Claude Code's `--dangerously-skip-permissions` mode. Speed by default, intervention by exception." -- is immediately clear. Within 30 seconds I understand:
- What it does (security guardrails for permissionless mode)
- Why I want it (keep speed, lose the risk)
- How it works conceptually (hooks that intercept dangerous operations)

The "Why Guardian?" section is well-written and relatable. The "What It Catches" section with its three tiers (hard blocks, confirmation prompts, protected files) gives a concrete picture immediately.

**Minor suggestion:** The phrase "existential dread" in the intro is memorable but might not land for all audiences. Consider a slightly more professional alternative, or keep it -- it works for the target audience of power users.

---

### 2. Installation
**PASS**

Installation instructions are clear and actionable:
- Prerequisites stated upfront (Python 3.10+, Git)
- Manual installation is two commands (git clone + claude --plugin-dir)
- Persistence via shell alias is documented
- Marketplace install is clearly marked as "Unverified" with a cross-reference to KNOWN-ISSUES.md
- Optional `regex` dependency is explained with rationale

**One potential confusion point:** The README says `--plugin-dir /path/to/claude-code-guardian` but the plugin.json lives at `.claude-plugin/plugin.json`. A brand-new developer might wonder whether `--plugin-dir` should point to the repo root or the `.claude-plugin/` subdirectory. The docs imply repo root (correct based on hooks.json location), but this could be made more explicit.

**Suggestion:** Add a one-line note: "Point `--plugin-dir` to the repository root (the directory containing `hooks/`), not to any subdirectory."

---

### 3. Quick Start
**PASS**

The Quick Start is four numbered steps and can be completed in under 5 minutes:
1. Install (already covered)
2. Launch with `--plugin-dir`
3. Run `/guardian:init` (optional but recommended)
4. Verify with `cat .env`

The "Skipping setup" note clarifies that defaults work without `/guardian:init`. The dry-run testing note is helpful.

**Strength:** The verification step ("ask Claude to `cat .env`") is a brilliant touch -- it gives immediate confidence that hooks are active.

---

### 4. Configuration
**PASS**

The Configuration Reference is thorough and well-organized:
- Config resolution order is clear (project > plugin default > emergency fallback)
- Every config field has a table with type, default, and description
- Code examples show real JSON for each section
- Glob pattern syntax table with examples
- Regex writing guidance with JSON escaping, word boundaries, and ReDoS warnings
- IDE validation via `$schema` is mentioned

**Strengths:**
- The glob pattern syntax table is excellent
- The regex section with JSON double-escaping and negative lookahead examples is valuable
- The `bashPathScan` config is well-documented with clear defaults

**Minor issues:**
- The `hookBehavior.timeoutSeconds` documentation says "Configured timeout value" but the Note below says it's not enforced as a blanket timeout. This is adequately documented but slightly confusing at first glance. The reader has to read the note to understand the field is partially aspirational.
- `noDeletePaths` limitation is documented inline with a SCOPE-01 cross-reference -- good.

---

### 5. Troubleshooting
**PASS**

The Troubleshooting section is practical and covers real issues:
- Log file location and log levels are documented
- Common issues table with Problem/Cause/Solution format
- "Checking if hooks are loaded" tip is repeated from Quick Start
- Circuit breaker recovery is documented

**Strength:** The log level table (`[ALLOW]`, `[BLOCK]`, `[ASK]`, etc.) makes log reading intuitive.

**One missing scenario:** There is no guidance for "Guardian is active but everything is being denied (too aggressive config)." The Troubleshooting table mentions "Unexpected blocks" with "check guardian.log for which pattern matched", but a more detailed workflow (e.g., "enable dry-run mode, check logs, narrow the pattern") would help frustrated users.

---

### 6. Completeness
**PASS** (with minor gaps noted below)

The documentation covers:
- All 5 hooks (Bash, Read, Edit, Write, Stop)
- All config fields with types and defaults
- All three path protection tiers
- External path allowlisting (read and write)
- Auto-commit behavior and skip conditions
- Archive-before-delete with limits
- Self-guarding mechanism
- Circuit breaker behavior
- Security model (what it does/doesn't protect)
- Dry-run mode
- Environment variables
- Upgrading path
- FAQ with 10 common questions

**Minor gaps:**

1. **No example of `guardian.log` output**: A sample log entry showing a real block/allow decision would help new users understand what to look for. Currently the log levels are listed but no example output is shown.

2. **No mention of log rotation details in main README**: The README mentions "auto-rotates at 1MB, keeps one backup as `.log.1`" in the Configuration File Location section. This is adequate but could benefit from a brief mention in Troubleshooting for users whose logs are growing.

3. **`allowedExternalReadPaths` / `allowedExternalWritePaths` interaction**: The docs say these "Only bypass the 'outside project' check" and that "zeroAccess, readOnly, and symlink checks still apply." This is correct and documented, but a concrete example scenario would help. E.g., "If you add `~/.config/myapp/**` to `allowedExternalReadPaths`, you can read files there, but `~/.config/myapp/secrets.key` would still be blocked by zeroAccessPaths because `*.key` is zero-access."

---

### 7. Accuracy
**PASS** (with one minor inconsistency noted)

Cross-referencing documentation claims against implementation:

| Claim | Verified | Notes |
|-------|----------|-------|
| 5 hooks registered (Bash, Read, Edit, Write, Stop) | Yes | hooks.json confirms exactly these |
| Fail-closed on error for security hooks | Yes | All 4 security scripts have exception handlers that deny |
| Fail-open for auto-commit | Yes | auto_commit.py catches all exceptions and exits 0 |
| 100KB command size limit | Yes | `MAX_COMMAND_LENGTH = 100_000` (100,000 bytes) in code |
| Self-guarding blocks Read, Edit, Write | Yes | `is_self_guardian_path()` called in `run_path_guardian_hook()` for all tools |
| noDeletePaths enforced for Write tool overwrite | Yes | Check at line 2388 of _guardian_utils.py |
| noDeletePaths NOT enforced for Edit tool | Yes | Edit tool skips noDelete check (only Write checks it) |
| Circuit breaker auto-expires after 1 hour | Need to verify | Code uses `is_circuit_open()` which checks file age |
| Config resolution: project > plugin default > fallback | Yes | `load_guardian_config()` follows this exact chain |
| Emergency fallback protects .git, .claude, _archive, .env, *.pem, *.key, ~/.ssh/**, ~/.gnupg/**, ~/.aws/**, secrets.json, secrets.yaml | Yes | `_FALLBACK_CONFIG` in _guardian_utils.py matches |
| 18 block + 18 ask patterns in default config | Yes | Counted in guardian.default.json |
| Auto-commit uses --no-verify | Yes | `auto_commit.py:146` calls `git_commit(message, no_verify=True)` |
| Dry-run env var values: 1, true, yes | Need to verify | |
| Log rotation at 1MB | Yes | `MAX_LOG_SIZE_BYTES = 1_000_000` |
| Archive limits: 100MB/file, 500MB total, 50 files | Yes | Constants match in bash_guardian.py |
| Pre-danger checkpoint creates commit before ask-verdict commands | Yes | bash_guardian.py lines 1178-1238 |

**Minor inconsistency found:**
- README section "What It Catches" says "Commands exceeding 100KB (padding attack prevention)" -- the actual limit is 100,000 bytes (approximately 97.6 KB, not exactly 100KB). This is close enough to not be misleading, but technically "~100KB" or "100,000 bytes" would be more precise.

---

### 8. Flow / Organization
**PASS**

The document follows a logical progression:
1. What it does (What It Catches)
2. How to install it (Installation)
3. How to use it immediately (Quick Start)
4. How to customize it (Configuration)
5. How it works internally (How It Works)
6. Security boundaries (Security Model)
7. Practical usage guide (User Guide)
8. When things break (Troubleshooting)
9. Turning it off (Disabling Guardian)
10. Keeping it current (Upgrading)
11. Common questions (FAQ)

The Table of Contents is well-structured with deep links.

**Strengths:**
- The Architecture table (Hook/Event/Script/Fail Mode) is an excellent reference
- The Path Guardian check-order table makes the security model transparent
- The User Guide section bridges the gap between "what it does" and "how to change it"
- Understanding Block Messages table is very practical

**Minor suggestion:** The "How It Works" section is quite detailed (architecture, multi-layer defense, etc.) and could overwhelm a user who just wants to get going. Consider adding a brief note at the top: "This section explains Guardian internals. Skip to [User Guide](#user-guide) if you just want to customize protection."

---

## Happy Path Walkthrough

Simulating: "I heard about this plugin and want to use it."

1. **Read README intro** -- Immediately understand value proposition. Clear.
2. **Check requirements** -- Python 3.10+, Git. I have both. Clear.
3. **Install** -- `git clone`, then `claude --plugin-dir /path --dangerously-skip-permissions`. Two commands. Clear.
4. **Verify** -- Ask Claude to `cat .env`. It gets blocked. Hooks are working. Great.
5. **Run /guardian:init** -- Wizard auto-detects my project type. Generates config. Clear.
6. **Customize** -- I want to block `npm publish`. The User Guide section shows exactly how to add it. Clear.
7. **Something gets blocked unexpectedly** -- Check `guardian.log`, find the pattern, narrow it. Clear.

**Verdict: Happy path is smooth and well-documented.**

---

## Confused User Walkthrough

Simulating: "Something is wrong and I don't know what."

### Scenario A: "My legitimate command keeps getting blocked"
1. README says check `guardian.log` -- **found it** in `.claude/guardian/guardian.log`
2. Log levels documented -- I look for `[BLOCK]` entries
3. Understanding Block Messages table -- **found it**, matches my error message
4. Resolution: "narrow the regex" or "move from block to ask"
5. Dry-run mode to test changes -- documented in Quick Start and Disabling sections

**Verdict: Adequate. Could use a sample log entry for clarity.**

### Scenario B: "Hooks aren't firing at all"
1. Quick Start says "ask Claude to cat .env" to verify
2. If it succeeds silently, "hooks are not active -- check your --plugin-dir path"
3. Troubleshooting table: "Hooks not firing" -> "Verify path"
4. Also checks: `python3: command not found` (Python not installed)

**Verdict: Well-covered.**

### Scenario C: "Auto-commits stopped happening"
1. Troubleshooting table lists three causes: circuit breaker, detached HEAD, rebase in progress
2. Circuit breaker fix: delete `.circuit_open` or wait 1 hour
3. FAQ has "How do I reset the circuit breaker?" entry

**Verdict: Well-covered.**

### Scenario D: "I want to read an external config file but it's blocked"
1. Block message: "Path is outside project directory"
2. Understanding Block Messages table: "Add to `allowedExternalReadPaths`"
3. Configuration Reference: `allowedExternalReadPaths` with example
4. User Guide section: "Allow reading external files"

**Verdict: Well-covered with a clear resolution path.**

### Scenario E: "I edited config.json but my changes aren't taking effect"
1. Config resolution docs say "first found wins" with project config first
2. If JSON syntax error, falls back to plugin default with `[FALLBACK]` log
3. FAQ: "What happens if my config has a JSON syntax error?"
4. Troubleshooting: "Config not loading" -> "Validate JSON syntax"

**Verdict: Well-covered.**

### Scenario F: "I want to understand what the default config protects"
1. "What It Catches" section gives high-level overview
2. "Understanding Default Protection" in User Guide gives detailed breakdown (18+18 patterns, 27+18+27 paths)
3. `assets/guardian.default.json` is referenced as the source of truth

**Verdict: Excellent. Multiple levels of detail available.**

---

## Issues Found (Prioritized)

### MEDIUM Priority

**M1: No sample log output in documentation**
- **Location**: Troubleshooting section (README.md)
- **Issue**: Log levels are listed but no sample log entry is shown. A confused user would benefit from seeing what a real `[BLOCK]` or `[ALLOW]` entry looks like.
- **Suggestion**: Add a brief example:
  ```
  2026-02-16 14:30:22 [BLOCK] Zero access path: .env
  2026-02-16 14:30:23 [ALLOW] cat README.md
  ```

**M2: hookBehavior.timeoutSeconds is partially misleading**
- **Location**: Configuration Reference, `hookBehavior` section
- **Issue**: The field is documented as "Configured timeout value" with a default of 10 and range 1-60, but the Note says it's not enforced. A new user would naturally assume configuring it would change behavior.
- **Suggestion**: Change the description from "Configured timeout value" to "Configured timeout value (see note below)" or add "(not currently enforced at hook level)" inline.
- **Cross-ref**: SCOPE-02 in KNOWN-ISSUES.md

### LOW Priority

**L1: 100KB vs 100,000 bytes**
- **Location**: README.md "What It Catches" section
- **Issue**: Says "100KB" but actual limit is 100,000 bytes (97.6 KB). Not misleading in practice.
- **Suggestion**: Change to "~100KB" or leave as-is (negligible difference).

**L2: No concrete example of allowedExternalPaths interaction with zeroAccess**
- **Location**: Configuration Reference, `allowedExternalReadPaths` section
- **Issue**: The docs say these "Only bypass the 'outside project' check" but a concrete example showing that a `.key` file in an external allowed path would STILL be blocked would reinforce the defense-in-depth message.
- **Suggestion**: Add one sentence: "For example, `~/.config/myapp/service.key` would still be blocked by zeroAccessPaths (`*.key`) even if `~/.config/myapp/**` is in allowedExternalReadPaths."

**L3: Could benefit from "skip to User Guide" note in How It Works**
- **Location**: README.md "How It Works" section
- **Issue**: This section is dense and technically detailed. Users who just want to customize may get lost.
- **Suggestion**: Add a brief note at the top: "Skip to [User Guide](#user-guide) for practical customization guidance."

---

## Summary Scorecard

| Criterion | Grade | Notes |
|-----------|-------|-------|
| First Impression | **PASS** | Clear value prop in 30 seconds |
| Installation | **PASS** | Two commands, prereqs stated, persistence documented |
| Quick Start | **PASS** | Under 5 minutes, includes verification step |
| Configuration | **PASS** | Complete reference with types, defaults, examples |
| Troubleshooting | **PASS** | Common issues table, log levels, resolution paths |
| Completeness | **PASS** | All features documented, minor gaps noted |
| Accuracy | **PASS** | All verified claims match implementation |
| Flow | **PASS** | Logical progression, good ToC, well-organized |

**Overall: PASS (8/8 criteria met)**

The documentation is comprehensive, accurate, and well-organized for a V1 release. A new developer can go from "never heard of it" to "protecting my project" in under 5 minutes using only the README. The security model is transparent, the troubleshooting is practical, and the configuration reference is thorough. The issues found (M1, M2, L1-L3) are minor polish items that do not block usability.
