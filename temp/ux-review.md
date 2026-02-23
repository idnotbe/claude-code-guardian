# UX/Beginner Review: guardian.recommended.json

**Reviewer:** ux-reviewer
**Date:** 2026-02-22
**File reviewed:** `assets/guardian.recommended.json` (324 lines)
**External input:** Gemini 3.1 Pro UX consultation

---

## First Impression (The "10-Second Open" Test)

A beginner opens this file in VS Code. What do they see?

- **324 lines of JSON** -- this is a long config file
- **Line 3:** A wall of text in `$comment` -- helpful but dense
- **Lines 12-101:** Immediately hit with ~90 lines of regex patterns containing things like `(?i)(?:^\\s*|[;|&`({]\\s*)` -- this is the most visually intimidating part of the entire config, and it is the FIRST thing they see after 8 lines of setup
- **Lines 102-211:** Another ~110 lines of regex in the `ask` section
- **Lines 213-244:** Finally, something readable -- simple file glob patterns
- **Lines 300-324:** Simple boolean settings at the very bottom

**Verdict:** The config front-loads its most complex and intimidating content. A beginner scanning top-to-bottom will encounter a wall of regex before they find anything they can easily understand or customize. The simple, approachable settings (git integration, path lists) are buried at the end.

---

## Findings

### P0: Blocks Usability

#### P0-1: Regex patterns are opaque to non-regex users

**What:** The `bashToolPatterns` block and ask arrays contain patterns like:
```json
"pattern": "(?i)(?:^\\s*|[;|&`({]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)`'\"]|$)"
```

A developer who does not know regex has zero ability to understand what this matches, modify it safely, or add similar patterns. The `reason` field helps explain *why* it exists, but not *what it catches*.

**Suggested improvement:** Add a `$comment` field at the top of the `block` and `ask` arrays explaining what the patterns do in human terms. Consider grouping patterns with sub-comments:

```json
"block": [
  {"$comment": "--- Filesystem destruction ---"},
  {"pattern": "rm\\s+-[rRf]+\\s+/(?:\\s*$|\\*)", "reason": "Blocks: rm -rf / (root filesystem deletion)"},
  ...
  {"$comment": "--- Git history destruction ---"},
  {"pattern": "git\\s+push\\s[^;|&\\n]*(?:--force(?!-with-lease)|-f\\b)", "reason": "Blocks: git push --force (rewrites remote history)"},
  ...
]
```

**Note on schema constraint:** The current schema defines `block` and `ask` as arrays of `patternRule` objects (with only `pattern` and `reason` fields, `additionalProperties: false`). Inline `$comment` objects as array items would fail validation. This limits documentation options to: (a) updating the schema to allow `$comment` items or a description field on patternRule, or (b) making the `reason` field do double duty as both "why" and "what it catches." Option (b) is immediately actionable without schema changes.

**Actionable without schema changes:** Improve `reason` fields to include example commands:

| Current reason | Suggested rewrite |
|---|---|
| `"Git repository deletion"` | `"Blocks 'rm .git' and similar -- git repository deletion"` |
| `"Force push to remote (destructive, rewrites history)"` | `"Blocks 'git push --force' -- rewrites remote history, can lose others' work"` |
| `"Fork bomb (shell function variant)"` | `"Blocks fork bomb syntax ':(){:|:&};:' -- crashes the system"` |
| `"Command substitution with deletion"` | `"Blocks deletion hidden inside $(...) -- e.g., $(rm -rf /)"` |

#### P0-2: Section ordering puts hardest content first

**What:** The file reads top-to-bottom as:
1. `hookBehavior` (3 simple settings -- good)
2. `bashToolPatterns` (200 lines of regex -- terrifying)
3. Path arrays (simple globs -- approachable)
4. `gitIntegration` (simple booleans -- easy)
5. `bashPathScan` (simple settings -- easy)

**Why it matters:** A beginner's natural behavior is to scroll from top to bottom. They hit the regex wall at line 12 and either (a) close the file, (b) feel they cannot understand/customize this tool, or (c) accidentally break a regex while trying to edit something below it.

**Suggested improvement:** JSON key ordering is technically irrelevant to parsers, so reorder for readability:
1. `version`, `$schema`, `$comment`
2. `hookBehavior` (simple -- "what happens on errors?")
3. `gitIntegration` (simple -- "how does auto-commit work?")
4. `zeroAccessPaths`, `readOnlyPaths`, `noDeletePaths` (medium -- globs are readable)
5. `allowedExternalReadPaths`, `allowedExternalWritePaths` (medium -- users customize these)
6. `bashPathScan` (simple settings)
7. `bashToolPatterns` (advanced -- regex, put last)

This lets beginners configure everything they need before encountering regex.

#### P0-3: No documentation link in the file itself

**What:** The root `$comment` says "See guardian.schema.json for all available options" but does not link to the human-readable config guide (`skills/config-guide/references/schema-reference.md`) or any getting-started documentation.

**Why it matters:** A beginner opening this file has no breadcrumb to find help. Pointing to the JSON schema is unhelpful -- schemas are for validators, not humans.

**Suggested improvement:**
```json
"$comment": "Claude Code Guardian - Recommended Configuration v1.0.0. For help customizing this file, run '/guardian:config-guide' in Claude Code or see the schema reference in the plugin's skills/config-guide/ directory."
```

---

### P1: Significant Friction

#### P1-1: Section names use internal jargon

**What:** Key names like `zeroAccessPaths`, `noDeletePaths`, `bashToolPatterns`, `bashPathScan`, and `hookBehavior` use Guardian-internal terminology. A first-time user must learn Guardian's vocabulary before they can navigate the file.

| Current name | What a beginner expects | Confusion level |
|---|---|---|
| `zeroAccessPaths` | "Zero access? What does that mean? No reading AND no writing?" | High |
| `noDeletePaths` | "I can still edit these but not delete them?" | Medium |
| `readOnlyPaths` | Self-explanatory | Low |
| `bashToolPatterns` | "What is a bash tool? Is this for bash scripts?" | Medium |
| `hookBehavior` | "What hook? What is a hook?" | High |
| `bashPathScan` | "Is this different from bashToolPatterns?" | High |

**Suggested improvement:** These are schema-defined names and cannot be renamed without breaking the schema. Instead, add a `$comment` to each section explaining what it does in plain English:

- Add to the `zeroAccessPaths` array (as a nearby key or in the root $comment): "Files that are completely off-limits -- Claude cannot read, write, or delete these. Put your secrets and credentials here."
- Add context for `hookBehavior`: "What should happen if Guardian itself crashes or takes too long? 'deny' = block the action (safe default)."

**Schema limitation:** Path arrays (`zeroAccessPaths`, etc.) are typed as `array of string`, so you cannot inject a `$comment` object into the array itself. The best option is to document these via the root `$comment` or in an adjacent document.

**Workaround:** Since the schema has `additionalProperties: false` at the root, you cannot add arbitrary comment keys alongside the arrays. The root `$comment` field is the only place for this documentation. Consider restructuring the root `$comment` to include a brief section-by-section guide:

```json
"$comment": "... Sections: hookBehavior = error handling defaults. bashToolPatterns = commands to block or ask about (regex). zeroAccessPaths = secrets/credentials (no access at all). readOnlyPaths = generated files (read OK, no edit). noDeletePaths = critical files (edit OK, no delete). gitIntegration = auto-commit settings. bashPathScan = extra scan layer for protected filenames in commands."
```

#### P1-2: `reason` fields are not consistently actionable

**What:** Some reason fields tell the user what the rule does, but not what to do instead. When a beginner gets blocked, the reason is their only guidance.

| reason | Tells you what's blocked | Tells you what to do instead |
|---|---|---|
| `"Recursive/force deletion"` | Yes | No |
| `"Python interpreter file deletion -- use rm/del for monitored deletion"` | Yes | Yes |
| `"Privilege escalation"` | Vaguely | No |
| `"Publishing package to npm registry"` | Yes | No (is this blocked or just ask?) |

**Suggested improvements for `ask` reasons** (where the user can still proceed):
- `"Recursive/force deletion"` -> `"Recursive/force deletion -- review target paths before confirming"`
- `"Privilege escalation"` -> `"Running with sudo -- confirm this needs root access"`
- `"Publishing package to npm registry"` -> `"npm publish -- confirm you want to publish to the public registry"`

For `block` reasons (user cannot override), the reason should explain *why* this is permanently blocked and what alternative to use:
- `"Secure file destruction (irrecoverable)"` -> `"shred permanently destroys files -- use rm instead (which Guardian can monitor)"`

#### P1-3: No distinction between "what we added" vs "inherited from default"

**What:** The recommended config is a superset of the default config. A user looking at this file has no way to know which entries are standard defaults and which are the recommended additions (like netcat detection, base64 obfuscation, mkfs, publish commands, sudo, docker prune, terraform, kubectl, chmod 777).

**Why it matters:** When a user wants to trim the config to their needs, they cannot tell which rules are "core safety" (keep these!) vs "nice-to-have recommended additions" (safe to remove if irrelevant).

**Suggested improvement:** Group patterns within block/ask arrays so core rules come first, then recommended additions. Use the `reason` prefix or the root `$comment` to indicate tiers:

In root `$comment`:
```
"Patterns are organized: core safety rules first (from default config), then recommended additions for broader coverage."
```

Or more directly, in the reason field:
```json
{"pattern": "(?i)mkfs\\.", "reason": "[Recommended] Filesystem formatting -- destroys all data on device"}
```

#### P1-4: `allowedExternalReadPaths` is empty with no guidance

**What:** The array is `[]` with no comment explaining what it is for, when to use it, or giving examples. The root `$comment` says "Customize allowedExternalReadPaths for your cross-project needs" but gives no examples.

**Why it matters:** The context doc (`temp/team1-context.md`) specifically notes Claude Code users "often read files from other projects (cross-repo reference)" and that Claude's auto-memory lives at `~/.claude/projects/*/memory/`. A recommended config should either pre-populate this or provide commented-out examples.

**Suggested improvement:** Since JSON does not support comments and you cannot put non-string items in the array, add guidance to the root `$comment`:

```
"allowedExternalReadPaths is empty by default. Add paths Claude should be able to read outside your project, e.g., '~/other-project/src/**' or '~/.claude/projects/*/memory/**' for Claude's memory files."
```

#### P1-5: `bashPathScan` section is confusing without context

**What:** The `bashPathScan` section has four settings (`enabled`, `scanTiers`, `exactMatchAction`, `patternMatchAction`) that are meaningless without understanding that this is a *separate* security layer from `bashToolPatterns`. Terms like "scanTiers", "exactMatchAction", and "patternMatchAction" are opaque.

**Why it matters:** A beginner will wonder: "I already have bash patterns that block commands. What is this extra scan thing? Do I need it? What does 'exactMatchAction: ask' mean?"

**Suggested improvement:** This is where a `$comment` in the `bashPathScan` object would help enormously. Since the schema allows `additionalProperties: false` on the `bashPathScan` object but does not define a `$comment` property... let me check.

Actually, looking at the schema, `bashPathScan` has `additionalProperties: false` and only defines `enabled`, `scanTiers`, `exactMatchAction`, and `patternMatchAction`. There is no `$comment` allowed. This is a schema limitation that should be addressed -- every object section should allow `$comment`.

**Workaround for now:** Add to root `$comment`:
```
"bashPathScan scans bash commands for references to protected filenames (e.g., if a command mentions '.env', even without using rm). It's an extra layer on top of bashToolPatterns."
```

---

### P2: Nice to Have

#### P2-1: Missing common developer workflow patterns

Patterns that common developers DO regularly that might cause unexpected friction or that they'd want covered:

**Potentially missing from `ask`:**
- `git rebase` (can rewrite history, lose commits if misused)
- `git push origin --delete` (deletes remote branches -- different from local `git branch -D`)
- `pip install` without `-r` (arbitrary package installation)
- `npx` (downloads and executes arbitrary packages)
- `docker run` with `--privileged` or `-v /:/host` (security-sensitive mounts)

**Potentially surprising blocks for beginners:**
- The `shred\s+` block pattern matches `shred ` with a trailing space -- this will also match `shred --help` or `shred --version`. A user trying to learn what shred does will be blocked.
- The Python/Node/Perl/Ruby interpreter deletion blocks are aggressive -- they block `python script.py` if the script happens to contain `os.remove` as a string argument. The reason says "use rm/del for monitored deletion" but that is not always practical (e.g., running a test suite that cleans up temp files).

#### P2-2: No "getting started" breadcrumbs for customization

**What:** A beginner who wants to add a custom rule (e.g., block `kubectl apply` in their k8s project) has to:
1. Understand JSON array syntax
2. Understand regex syntax
3. Figure out where in the block/ask arrays to add it
4. Hope they do not break the JSON

**Suggested improvement:** Add to root `$comment` or create a companion README:
```
"To add a custom rule: add {\"pattern\": \"your-regex\", \"reason\": \"why blocked\"} to the block or ask array. Test patterns at regex101.com. Run '/guardian:config-guide' for help."
```

#### P2-3: Inconsistent reason field formatting

**What:** Reason fields mix several styles:
- Short label: `"Recursive/force deletion"`
- Label with parenthetical: `"Force push to remote (destructive, rewrites history)"`
- Label with action: `"Python interpreter file deletion -- use rm/del for monitored deletion"`
- Question-style: none (but would be clearer for `ask` patterns)

**Suggested improvement:** Standardize to: `"[What it catches] -- [what to do / why it matters]"`

Examples:
- `"Recursive/force deletion -- review the target path before confirming"`
- `"Force push -- rewrites remote history, which can lose others' work"`
- `"sudo command -- confirm this needs root access"`

#### P2-4: The `allowedExternalWritePaths` entry needs explanation

**What:** `"~/.claude/plans"` and `"~/.claude/plans/**"` are included but with no explanation of why. A beginner will wonder: "What are Claude plans? Do I need this? Is this safe?"

**Suggested improvement:** Add to root `$comment`:
```
"allowedExternalWritePaths includes ~/.claude/plans/ because Claude Code saves plan-mode files there. Remove if you don't use plan mode."
```

#### P2-5: The `gitIntegration.identity` section may confuse git beginners

**What:** The `identity` section sets `email: "guardian@claude-code.local"` and `name: "Guardian Auto-Commit"`. A beginner unfamiliar with git author identity may wonder: "Will this override my git identity? Will my commits show as this email?"

**Suggested improvement:** Add explanation (in root `$comment` or as a separate documentation note): "gitIntegration.identity is ONLY used for Guardian's automatic checkpoint commits, not for your normal commits."

#### P2-6: `includeUntracked: false` is correct but unexplained

**What:** This is a critical safety setting (prevents committing untracked secrets), but a beginner does not know why `false` matters here. They might change it to `true` thinking "I want all my changes committed."

**Suggested improvement:** If the schema were updated to allow `$comment` in the `autoCommit` object, this would be ideal. In the meantime, add to root `$comment`:
```
"includeUntracked is false by default for safety -- setting it to true could auto-commit untracked files like .env that haven't been gitignored yet."
```

---

## Structural Recommendations (Beyond Single Findings)

### R1: Root `$comment` should be a section-by-section guide

The current root `$comment` is a paragraph of text. Rewrite it as a structured mini-guide since it is the *only* documentation mechanism available within the JSON file:

```json
"$comment": "Claude Code Guardian - Recommended Config v1.0.0 | SECTIONS: hookBehavior = what to do on errors/timeouts (safe defaults: deny). bashToolPatterns = regex rules for commands (block = always denied, ask = prompt user). zeroAccessPaths = secrets/keys (no access at all). readOnlyPaths = generated files (read OK, no write). noDeletePaths = critical project files (write OK, no delete). allowedExternalReadPaths = paths outside project Claude can read (empty = none, add your cross-project paths). allowedExternalWritePaths = paths outside project Claude can write (includes ~/.claude/plans for plan mode). gitIntegration = auto-commit checkpoints and git identity. bashPathScan = extra layer that scans commands for protected filenames. | CUSTOMIZE: Run '/guardian:config-guide' or see schema-reference.md. | SAFETY: includeUntracked is false to avoid committing secrets. hookBehavior uses 'deny' to fail-closed."
```

### R2: Consider an "extends" model for future versions

As Gemini suggested, an inheritance model (like ESLint's `extends`) would dramatically reduce the visible complexity. The user's file becomes:
```json
{"extends": "guardian:recommended", "allowedExternalReadPaths": ["~/other-project/**"]}
```
This is a schema/architecture change for a future version, not something to address in this config file.

### R3: Schema should allow `$comment` in all object types

Currently, `$comment` is only allowed on the root object and inside `bashToolPatterns`. Objects like `hookBehavior`, `gitIntegration`, `autoCommit`, `preCommitOnDangerous`, `identity`, and `bashPathScan` all have `additionalProperties: false` without a `$comment` property. This prevents inline documentation where it is needed most.

**Recommendation:** Add `"$comment": {"type": "string", "description": "..."}` to every object definition in `guardian.schema.json`. This is the single highest-impact schema change for UX.

---

## Summary Table

| ID | Priority | Category | Finding |
|---|---|---|---|
| P0-1 | P0 | Comprehensibility | Regex patterns opaque to non-regex users; reason fields need example commands |
| P0-2 | P0 | Organization | Config front-loads 200 lines of regex; simple settings buried at bottom |
| P0-3 | P0 | Documentation | No link to human-readable docs; only points to JSON schema |
| P1-1 | P1 | Naming | Section names use internal jargon (zeroAccessPaths, hookBehavior, bashPathScan) |
| P1-2 | P1 | Actionability | Reason fields inconsistently tell user what to do instead |
| P1-3 | P1 | Organization | No distinction between core defaults and recommended additions |
| P1-4 | P1 | Completeness | allowedExternalReadPaths empty with no guidance or examples |
| P1-5 | P1 | Comprehensibility | bashPathScan section confusing without context on what it does |
| P2-1 | P2 | Coverage | Missing patterns for git rebase, remote branch delete, npx, pip install |
| P2-2 | P2 | Onboarding | No breadcrumbs for how to add custom rules |
| P2-3 | P2 | Consistency | Reason field formatting is inconsistent across entries |
| P2-4 | P2 | Documentation | allowedExternalWritePaths Claude plans entry unexplained |
| P2-5 | P2 | Documentation | gitIntegration.identity may confuse git beginners |
| P2-6 | P2 | Safety | includeUntracked: false is critical but unexplained |
| R1 | -- | Structural | Root $comment should be a structured section-by-section guide |
| R2 | -- | Architecture | Future: "extends" model to hide complexity |
| R3 | -- | Schema | Allow $comment in all schema object definitions |
