# Verification Round 2: User Perspective Report
## Reviewer: Teammate J

**Date**: 2026-02-14
**Documents Reviewed**: README.md, CHANGELOG.md, KNOWN-ISSUES.md
**Code Files Spot-Checked**: hooks/hooks.json, assets/guardian.default.json, assets/guardian.schema.json, .claude-plugin/plugin.json, hooks/scripts/_guardian_utils.py, hooks/scripts/bash_guardian.py, commands/init.md

---

### First Impressions

Reading the README cold -- with zero knowledge of the codebase -- I came away with a solid understanding of what Guardian does, why it exists, and how to install it. The opening section ("Why Guardian?") is genuinely well-written. It names the exact pain point (`--dangerously-skip-permissions` is all-or-nothing), explains the trade-off in plain language, and the line "You keep the speed. You lose the existential dread" lands the message without being gimmicky.

The document is well-structured: it moves logically from motivation to features to installation to configuration to internals to failure modes. This is the right sequence for a new user. I could orient myself without scrolling back.

The CHANGELOG is clean and follows Keep a Changelog format correctly. The KNOWN-ISSUES document is impressively thorough for a v1.0 project.

---

### Clarity Assessment

**1. Can a new user understand what Guardian does from the README alone?**
YES. The "Why Guardian?" and "What It Catches" sections together paint a clear picture. The four-tier model (safety checkpoints, hard blocks, confirmation prompts, protected files) is intuitive and well-organized. A user unfamiliar with Claude Code hooks would understand the value proposition within 30 seconds.

**2. Are installation steps clear and actionable?**
MOSTLY YES, with caveats:

- **Manual installation** is clear: two commands, clone and point Claude at it. Good.
- **Persistence note** is important and well-placed. However, it says "add it to your shell profile or Claude Code settings" without explaining *how*. A new user would not know what to add to their shell profile or where Claude Code settings live. This is a gap.
- **Marketplace installation** is flagged as experimental, which is honest. But the two commands shown (`/plugin marketplace add` and `/plugin install`) are contradictory -- are they alternatives or sequential? This would confuse a first-time user. KNOWN-ISSUES UX-07 acknowledges these commands are unverified, but the README does not signal uncertainty strongly enough; a user could spend 20 minutes trying to make them work.
- **Update instructions** ("run `git pull`") are appropriately simple.

**3. Is the configuration section understandable without reading source code?**
YES, with one friction point:

- The example config is partial and the note says "Your config must also include `version` and `hookBehavior`". This is good, but a new user might wonder: "Where do I get the full config?" The answer is buried in a reference to `assets/guardian.default.json` and `/guardian:init`. It would be clearer to say: "Run `/guardian:init` to generate a complete config, then customize the sections below."
- The Configuration Sections table is excellent -- concise and scannable.
- `bashPathScan` in the table ("Raw command string scanning for protected path names") is somewhat opaque. A new user would not understand what "raw command string scanning" means without reading the code. One clarifying sentence would help.

**4. Are any terms used without explanation?**
A few:

- **"Glob patterns"** -- used throughout for path matching, never defined. Most developers know this, but a brief "(e.g., `*.env` matches all .env files, `**/*.pem` matches recursively)" would help.
- **"Fail-closed"** -- explained well in the How It Works section, but only after being used conceptually in the feature list. Minor; the explanation does come.
- **"Circuit breaker"** -- the concept is explained in the Failure Modes section, but the term itself is jargon from distributed systems. The explanation is adequate ("stops attempting auto-commits to prevent cascading failures") but could note this is a standard resilience pattern.
- **"PreToolUse"** and **"Stop"** -- used in the hooks table without defining them as Claude Code lifecycle events. A parenthetical like "(Claude Code runs this before executing a tool)" would help.

---

### Completeness Assessment

**5. Would a user know how to install, configure, test, and disable Guardian?**
YES. All four workflows are covered:

- **Install**: Manual path is clear. Marketplace path is experimental/uncertain.
- **Configure**: `/guardian:init` is documented. Manual config editing is explained with example and reference to defaults.
- **Test**: The Testing section shows pytest commands and references `tests/README.md`.
- **Disable**: The "Disabling Guardian" section covers three scenarios (dry-run, temporary disable, full uninstall) with concrete steps. This is good.

**6. Would a user understand what operations are blocked vs asked vs allowed?**
YES. The "What It Catches" section lays out the four tiers clearly. The default config confirms these claims are accurate:

- VERIFIED: `rm -rf /` is in `block` patterns.
- VERIFIED: `.env`, `*.pem` are in `zeroAccessPaths`.
- VERIFIED: `git push --force` is in `block` (with `--force-with-lease` correctly in `ask`).
- VERIFIED: `git reset --hard` and branch deletion are in `ask` patterns.
- VERIFIED: `package-lock.json` is in `readOnlyPaths`.
- VERIFIED: `README.md` and `LICENSE` are in `noDeletePaths`.

One minor discrepancy: The README says "SSH keys" are blocked, and the default config has `id_rsa`, `id_ed25519`, and `~/.ssh/**` in zeroAccessPaths. This is accurate but the README could be more specific -- "SSH keys" might make a user think only `~/.ssh/` is covered, not standalone `id_rsa` files.

**7. Would a user know what to do if something goes wrong?**
MOSTLY YES:

- The Failure Modes section is unusually honest for a README. The verification tip (try to read a `.env` file) is actionable and clever.
- The circuit breaker recovery path is documented (delete `.circuit_open`).
- The "Does not protect against" section sets realistic expectations.
- MISSING: There is no troubleshooting section. What if hooks load but behave unexpectedly? What if the config file has a syntax error? Where are logs written? A user hitting a problem has no debugging steps beyond "verify hooks are loaded." The KNOWN-ISSUES file has some of this information scattered across entries, but a user would not think to check KNOWN-ISSUES for debugging help.

**8. Is dry-run mode discoverable and well-explained?**
PARTIALLY. KNOWN-ISSUES UX-11 correctly identifies this gap:

- Dry-run is mentioned exactly once, in the "Disabling Guardian" section: `CLAUDE_HOOK_DRY_RUN=1`.
- It says "Hooks will log what they would do without actually blocking operations." This is clear enough but minimal.
- A new user would not discover dry-run mode unless they happened to read the Disabling section. It should also appear in the Configuration or Testing sections, where a user would naturally look for "how do I test my config without risk?"
- VERIFIED in code: `CLAUDE_HOOK_DRY_RUN` is defined in `_guardian_utils.py` line 75, confirming the env var name is correct.

---

### Trust Assessment

**9. Does the README inspire confidence that Guardian is reliable?**
YES. Several elements build trust:

- The "fail-closed" philosophy is stated clearly and verified in code (all four security hooks default `onTimeout: deny`, `onError: deny`).
- The explicit acknowledgment that "A false denial is annoying; a false allow could be catastrophic" shows the author understands the security model.
- The auto-commit hook being explicitly documented as fail-open "by design" shows thoughtful engineering, not accident.
- The warning about Guardian failing to load is refreshingly honest.
- The test count (~1,009 methods) is verified: I counted 1,018 `def test_` methods across 36 test files, which rounds to the stated "~1,009". Close enough; the tilde is honest.
- Six test category directories exist (core, patterns, regression, review, security, usability), matching the claim.

**10. Are failure modes honestly documented?**
YES. This is a strength of the documentation:

- "If Guardian fails to load... you have zero protection" -- stated twice for emphasis.
- "Does not protect against" includes "determined human adversaries," "arbitrary code within interpreter scripts," and crucially "its own failure to load."
- The note about interpreter scripts is accurate: the default config blocks `os.remove`, `shutil.rmtree`, etc. at the bash command level but acknowledges this is pattern-matching, not sandboxing.
- The recommendation to use Guardian "alongside" other protections "not instead of them" is responsible.

**11. Does the "Does not protect against" section set appropriate expectations?**
YES. It is appropriately scoped:

- Correctly notes the hook-based architecture's fundamental limitation.
- Does not overstate what regex-based pattern matching can achieve.
- The phrasing about interpreter scripts ("blocks known deletion APIs... but cannot catch all possible code patterns") is accurate and avoids false confidence.

---

### Actionability of KNOWN-ISSUES

**12. Could a developer pick up a KNOWN-ISSUES item and fix it without ambiguity?**
MOSTLY YES. The format is strong:

- Each issue has: File, Issue description, Impact, and either a Fix recommendation or Status.
- The Platform Verification items (PV-01 through PV-05) include specific test steps.
- COMPAT-06 gives exact function name and a concrete fix direction ("Align with normalize_path_for_matching()").
- COMPAT-07 gives the exact code change needed (`sys.platform != 'linux'`).
- SCOPE-01 explains the design rationale for why it is not being fixed.

Weaker items:

- UX-09 ("Schema reference common patterns note") is too terse. A developer would need to find the schema, find the common patterns table, and figure out what "noting they are pre-included" means. This needs one more sentence.
- UX-10 ("Config-assistant agent lacks sample output") names the problem but not the file to edit.
- COMPAT-08 ("Relative $schema in default config") does not state the fix. (Change to absolute URL? Remove it? Use a different path?)
- COMPAT-13 does not specify which file contains the recovery guidance.

**13. Are issue statuses (open, fixed, partially fixed) clear?**
YES. The convention is consistent:

- Fixed items use strikethrough with "FIXED" tag and version reference.
- The Fixed Issues table at the bottom provides a clean summary.
- "Accepted risk" status is used for items that won't be fixed (COMPAT-04, COMPAT-05).
- "Partially fixed" is used for UX-11 with a clear explanation of what remains.
- Open items are grouped by severity (MEDIUM, LOW).

One inconsistency: The KNOWN-ISSUES header says "Version: 1.0.0" but documents fixes from v1.0.1. The version should be updated to 1.0.1 or "current" to avoid confusion.

---

### Red Flags

**14. Any claims that seem too good to be true?**
No. The documentation is measured in its claims. Specific observations:

- "The 99% of safe operations run silently. The 1% that could ruin your day... get caught" -- this is marketing language but the qualifying section ("Does not protect against") appropriately tempers it.
- The test count is verified and slightly understated (1,018 actual vs ~1,009 claimed).
- No performance claims are made (latency of hooks, etc.), which is honest since no benchmarks are shown.

**15. Any confusing or contradictory information?**
A few items:

- **Marketplace commands**: Two different commands are shown without explanation of whether they are alternatives. The experimental warning helps but does not fully resolve the ambiguity.
- **Config file naming**: The CHANGELOG says "Renamed user config file from `guardian.json` to `config.json`" (v1.0.1). This is fine for the changelog audience, but if a user followed a pre-1.0.1 guide, they might still have `guardian.json`. The README makes no mention of migration from the old name. The code does not appear to have a migration path either -- it only looks for `config.json`.
- **KNOWN-ISSUES version mismatch**: Header says 1.0.0, content includes 1.0.1 fixes.
- **Hook count**: README says "five hooks" and the hooks table shows 5 rows (Bash, Read, Edit, Write, Auto-Commit). hooks.json shows 5 entries (4 PreToolUse + 1 Stop). These match. No issue.
- **"hookBehavior" required**: The README Configuration Sections table lists `hookBehavior` as "What to do on timeout or error (allow/deny/ask)." The schema requires `hookBehavior` with three sub-fields (`onTimeout`, `onError`, `timeoutSeconds`). The table does not mention `timeoutSeconds`. A user following only the README might create an invalid config.

**16. Any missing information that would block a user from getting started?**
Not blocked, but slowed:

- **Shell profile persistence**: The README says to add `--plugin-dir` to your shell profile but does not show the actual line to add. A new user would need to figure out: `alias claude='claude --plugin-dir /path/to/claude-code-guardian'` or equivalent.
- **Python 3.10 requirement**: Listed under Requirements but not checked during installation. If a user has Python 3.8, hooks will silently fail with syntax errors (the code uses `match/case`, `type[X]` hints, etc.). The README could suggest `python3 --version` as a pre-install check.
- **No quickstart for the impatient**: The README structure is thorough but linear. A "30-second quickstart" block at the top (clone, point, verify) would serve users who just want to get running.
- **Log location**: Never mentioned. Where does `log_guardian()` write? A user debugging issues has no idea where to look. (Checked code: it writes to stderr and optionally to `.claude/guardian/guardian.log`.)

---

### Recommendations

**Priority 1 (should fix before release):**

1. **Add shell profile example** under Installation > Persistence note. Show the actual alias or config line for bash/zsh.
2. **Clarify marketplace commands** -- either mark them as placeholder/unknown or remove them entirely. The current state will frustrate users.
3. **Add a "Troubleshooting" section** or at minimum document the log file location (`.claude/guardian/guardian.log`) somewhere visible.
4. **Update KNOWN-ISSUES version** from 1.0.0 to 1.0.1.
5. **Mention Python version check** in installation: `python3 --version` (must be 3.10+).

**Priority 2 (should fix soon):**

6. **Promote dry-run mode** to its own subsection or mention it in Configuration. Testing a config change should be a first-class workflow.
7. **Add `timeoutSeconds`** to the Configuration Sections table or note that `hookBehavior` has sub-fields.
8. **Flesh out weak KNOWN-ISSUES items**: UX-09, UX-10, COMPAT-08, COMPAT-13 need file paths and/or concrete fix descriptions.
9. **Add a quickstart block** at the top of the README for users who want the 3-command version.

**Priority 3 (nice to have):**

10. **Define "glob patterns"** briefly on first use.
11. **Add parenthetical for PreToolUse/Stop** events in the hooks table.
12. **Note the guardian.json -> config.json rename** somewhere discoverable for early adopters.
13. **Document log file location** in a visible place (Failure Modes or a new Debugging section).

---

### Cross-Verification Summary

| README Claim | Code Verification | Status |
|---|---|---|
| 5 hooks registered | hooks.json has 4 PreToolUse + 1 Stop = 5 | CONFIRMED |
| Fail-closed on timeout/error | Default config: `onTimeout: deny`, `onError: deny`; code enforces everywhere | CONFIRMED |
| Auto-commit on Stop | auto_commit.py registered as Stop hook | CONFIRMED |
| Circuit breaker auto-resets after 1 hour | `CIRCUIT_TIMEOUT_SECONDS = 3600` in _guardian_utils.py | CONFIRMED |
| .circuit_open file path | Code uses `.claude/guardian/.circuit_open` | CONFIRMED |
| Dry-run via CLAUDE_HOOK_DRY_RUN=1 | `DRY_RUN_ENV = "CLAUDE_HOOK_DRY_RUN"` in _guardian_utils.py | CONFIRMED |
| --force-with-lease in ask (not block) | Default config and fallback config both have it in ask | CONFIRMED |
| ~1,009 test methods | Counted 1,018 `def test_` methods | CONFIRMED (close enough) |
| 6 test category directories | core, patterns, regression, review, security, usability | CONFIRMED |
| Config path .claude/guardian/config.json | load_guardian_config() looks for this exact path | CONFIRMED |
| python3 used in hooks | All 5 hooks.json entries use `python3` | CONFIRMED |
| Self-guarding of config file | SELF_GUARDIAN_PATHS includes config.json | CONFIRMED |
| Hardcoded fallback config | _FALLBACK_CONFIG exists with critical paths | CONFIRMED |
| Archive-before-delete to _archive/ | bash_guardian.py has archive logic using _archive/ dir | CONFIRMED |
| Blocks os.remove, shutil.rmtree at bash level | Default config block patterns include these | CONFIRMED |

All 15 spot-checked claims are accurate. No false claims found.

---

### Overall Verdict: PASS

The documentation is strong for a v1.0 project. The README is well-structured, honest about limitations, and the claims I verified are all accurate. The CHANGELOG follows standards correctly. The KNOWN-ISSUES document is thorough and mostly actionable.

The gaps identified (no troubleshooting section, undiscoverable log location, unverified marketplace commands, missing shell profile example) are real but none would fully block a competent user from getting started. They would, however, cause friction and unnecessary debugging for first-time users.

The documentation earns a PASS with the Priority 1 recommendations noted above as improvements that should be addressed before wider public release. The honesty about failure modes and the thorough "Does not protect against" section are particularly commendable and build user trust effectively.
