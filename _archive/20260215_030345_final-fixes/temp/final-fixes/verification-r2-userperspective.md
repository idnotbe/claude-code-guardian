# Verification Round 2: User Perspective
## Teammate V4

### 1. First Impressions: 9/10
Notes:

The opening line -- "Selective security guardrails for Claude Code's `--dangerously-skip-permissions` mode. Speed by default, intervention by exception." -- is excellent. It tells me exactly what this is and who it is for in a single sentence. The "Why Guardian?" section is one of the best problem-statement write-ups I have seen in an open-source README. It names the real pain point (`--dangerously-skip-permissions` is all-or-nothing), explains the gap (no distinction between safe and dangerous operations), and positions the solution without overselling. The line "You keep the speed. You lose the existential dread." is memorable and sets a confident, slightly informal tone that feels appropriate for a developer tool.

The "What It Catches" section immediately follows with concrete examples organized into four tiers (safety checkpoints, hard blocks, confirmation prompts, protected files). This is smart -- within 30 seconds of landing on the README, I know what this tool does, why I would want it, and roughly how it works. The tone is professional without being sterile.

Minor deduction: The safety checkpoints subsection (auto-commits, archive untracked files) is somewhat surprising as the first tier listed. A first-time reader might expect the "blocking dangerous commands" story first, since that is what the intro primes them for. The auto-commit and archiving features are valuable, but they feel like they belong after the blocking/prompting tiers in the narrative flow. This is a very minor ordering preference, not a real problem.

### 2. Installation Clarity: 8/10
Notes:

The manual installation path is clear and minimal: clone the repo, pass the flag. The persistence tip (alias in shell profile) is exactly the follow-up question I would have had. Prerequisites (Python 3.10+, Git) are stated upfront in a callout block, with verification commands. Good.

The marketplace section is handled well -- the "Unverified" callout is honest and prominent, and the text explicitly says "Manual installation (above) is the reliable path." This is the right call. The two alternative syntaxes (marketplace add vs. direct install) are presented without pretending either is tested, and the cross-reference to UX-07 in KNOWN-ISSUES.md is a nice touch for users who want the full story.

Deductions:

1. The `--plugin-dir /path/to/claude-code-guardian` placeholder appears multiple times but is never shown with an actual example path (e.g., `~/projects/claude-code-guardian`). For a first-time user, a concrete example alongside the placeholder would reduce friction. Minor, but the kind of thing that causes a 30-second head-scratch.

2. The Setup section introduces `/guardian:init` as a post-installation step, but it is not immediately clear whether this is a Claude Code slash command, a shell command, or something else. Users unfamiliar with Claude Code's plugin system might try to run it in their terminal. A one-line clarification like "Run this inside a Claude Code session" would help.

3. There is no mention of which operating systems are supported. The code handles Windows, macOS, and Linux (per the KNOWN-ISSUES.md cross-platform fixes), but the README never states this. A first-time user on Windows might wonder if this is Linux-only.

### 3. Configuration Guidance: 8/10
Notes:

The configuration resolution order (project-specific > plugin default > hardcoded fallback) is clearly stated and gives me confidence that there is always a working configuration. The three-tier fallback is well-designed.

The partial-config warning ("A valid config file **must** also include `version` and `hookBehavior`. Copy `assets/guardian.default.json` as your starting point") is present and bolded. Good -- this prevents the most common configuration mistake.

The Configuration Sections table is well-organized and gives me a quick overview of all the config keys without forcing me to read the schema. The `bashPathScan` entry is particularly well-explained for a table cell.

The pointer to `assets/guardian.schema.json` for the full schema is clear.

Deductions:

1. The example JSON block shows `zeroAccessPaths`, `readOnlyPaths`, and `noDeletePaths` as flat arrays of strings, but `bashToolPatterns` uses objects with `pattern` and `reason` keys. This inconsistency is not explained in context -- a user might wonder whether path patterns also support a `reason` field. A one-line note clarifying the difference would help.

2. The warning says to copy `assets/guardian.default.json` as a starting point, but the README never shows the path to that file relative to the cloned repo. A user who cloned to a non-standard location might not realize this is inside the Guardian repo itself. Something like "inside the cloned Guardian directory" would anchor the reference.

3. The `hookBehavior` table cell packs a lot into one line (timeout, error handling, allow/deny/ask, timeoutSeconds). Given that SCOPE-02 in KNOWN-ISSUES.md reveals that `timeoutSeconds` is not actually enforced at the hook level, documenting it here without a caveat could set false expectations. This is a transparency gap.

### 4. Verification & Troubleshooting: 9/10
Notes:

The `.env` test instruction is excellent. It appears twice -- once in the "How It Works" section and again in the Troubleshooting section under "Checking if hooks are loaded." Both instances explicitly state "the file does not need to exist" and explain that Guardian intercepts the command before execution. This is exactly the kind of detail that prevents a user from creating a dummy `.env` file and then panicking when they realize they added secrets to their repo.

The troubleshooting table covers the five most likely failure modes (hooks not firing, Python not found, config errors, circuit breaker, unexpected blocks) with clear cause/solution columns. The circuit breaker explanation (auto-reset after one hour, manual reset by deleting a file) is practical and actionable.

The dry-run mode (`CLAUDE_HOOK_DRY_RUN=1`) is well-documented with a concrete command example. The "Disabling Guardian" section covers three levels (dry-run, temporary disable, full uninstall) which is thorough.

The log file location (`.claude/guardian/guardian.log`) is stated clearly and early in the troubleshooting section. This is the first thing a user would look for when debugging.

Minor deduction: The troubleshooting section is nested under "Failure Modes" which is itself nested under "How It Works." From a navigation perspective, troubleshooting feels like it should be a top-level section. A user skimming the table of contents (or using GitHub's auto-generated TOC) might not realize troubleshooting is buried two levels deep. This is a structural concern, not a content concern.

### 5. Known Issues Transparency: 9/10
Notes:

KNOWN-ISSUES.md is one of the most honest and well-structured known-issues documents I have reviewed. Several things stand out:

1. **Platform Verification Required section**: Listing five explicit assumptions (PV-01 through PV-05) that have not been tested against a real Claude Code environment is remarkably transparent. Each entry names the assumption, where it is used, what happens if it is wrong, and how to test it. This is the kind of intellectual honesty that builds trust with power users.

2. **Fixed Issues table**: The fixed issues section serves double duty -- it shows project maturity (17 fixed issues across 2 review rounds) and demonstrates that the project takes quality seriously. The severity classifications (CRITICAL, HIGH, MEDIUM, LOW) are consistent, and each entry links back to a specific round or version.

3. **SCOPE-02 explanation**: The `timeoutSeconds` limitation is clearly explained with a rationale for why it was not implemented (risk of git state corruption, partial archives, Windows threading races). The "by-design limitation" framing is honest -- it is not a bug they plan to fix, it is a trade-off they made and documented. Users can decide for themselves whether this matters.

4. **Strikethrough formatting** for fixed issues within the open issues list makes it easy to see what has been resolved without losing the historical context.

Deductions:

1. The version number (1.0.1) and review status (2 rounds, 4 reviewers) at the top set good expectations, but there is no date per-issue to understand the timeline. Users cannot tell if an issue was opened last week or three months ago.

2. SCOPE-01 (noDeletePaths only enforced for Bash delete commands) is a significant semantic gap -- a user might assume "no delete" means "fully protected" when in fact Edit/Write can still empty the file. The explanation is clear, but its severity rating of MEDIUM feels low for something that contradicts user expectations at a conceptual level. This is a judgment call, not a documentation error.

### 6. Overall Flow: 8/10
Notes:

The README flows well from motivation (Why Guardian?) to capabilities (What It Catches) to installation to configuration to internals (How It Works) to failure modes to troubleshooting. This is a logical progression that mirrors how a developer would engage with the tool: "Why should I care?" -> "What does it do?" -> "How do I install it?" -> "How do I configure it?" -> "How does it work under the hood?" -> "What can go wrong?"

The cross-references between README and KNOWN-ISSUES.md are used appropriately (UX-07 marketplace reference, schema reference). Neither document tries to duplicate the other.

Specific flow concerns:

1. **Setup vs. Configuration**: The Setup section (run `/guardian:init`) and the Configuration section feel like they should be one continuous section. Currently, Setup appears, then Configuration appears separately, and the relationship between them is not fully explicit. Does `/guardian:init` create the config file that the Configuration section describes? The note under Setup says "This generates a `config.json` configuration file" but the Configuration section does not reference `/guardian:init` at all. A bridging sentence would help.

2. **Failure Modes placement**: The Failure Modes section appears after How It Works, which makes structural sense, but it contains Troubleshooting and Disabling Guardian as subsections. These are operationally different concerns -- understanding failure modes is conceptual, while troubleshooting and disabling are practical. Splitting them into separate top-level sections would improve scanability.

3. **Testing section**: The Testing section feels slightly out of place for a user-facing README. Most users of a security plugin do not need to run the test suite. It is fine to include for contributors, but it could be moved lower or into a CONTRIBUTING.md file to keep the user-facing narrative focused.

4. **Requirements section at the bottom**: Python 3.10+ and Git are already mentioned in the Installation section's callout. Having a separate Requirements section at the bottom feels redundant. Either consolidate into the Installation section or move Requirements above Installation so users see prerequisites before they start.

### Overall Score: 8.5/10

### Key Strengths:
- The "Why Guardian?" section is outstanding -- it names the real problem, explains the gap, and positions the solution without marketing fluff. This is the gold standard for open-source project motivation.
- The verification test (`cat .env` with "file does not need to exist") is a clever, low-friction way to confirm hooks are working. Documenting it twice (How It Works + Troubleshooting) is the right call since users skim.
- KNOWN-ISSUES.md is unusually honest and well-structured. The Platform Verification section (PV-01 through PV-05) builds real trust by admitting what has not been tested rather than silently hoping it works.
- The fail-closed design philosophy is stated clearly and the rationale ("A false denial is annoying; a false allow could be catastrophic") is memorable and defensible.
- The three-tier configuration fallback (project > plugin default > hardcoded) with clear resolution order means the tool always has a working config. Good defensive design.
- Fixed issues table in KNOWN-ISSUES.md demonstrates project maturity and review rigor.

### Remaining Improvements (if any):
1. **Add OS support statement**: Mention Windows, macOS, and Linux support explicitly in the README, since the code clearly handles all three.
2. **Bridge Setup and Configuration sections**: Add a sentence in Configuration that says something like "If you ran `/guardian:init`, this is the file it created."
3. **Caveat on `timeoutSeconds` in README**: Since SCOPE-02 confirms it is not enforced, the Configuration Sections table should note this limitation or link to SCOPE-02, rather than listing it without qualification.
4. **Promote Troubleshooting to top-level**: Move Troubleshooting out of the Failure Modes subsection to make it easier to find via table of contents.
5. **Concrete path example in Installation**: Show at least one example with an actual path (e.g., `~/projects/claude-code-guardian`) alongside the `/path/to/` placeholder.
6. **Clarify `/guardian:init` context**: Note that it is a Claude Code session command, not a shell command.
