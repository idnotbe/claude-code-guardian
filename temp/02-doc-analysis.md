# Documentation Catalog & Gap Analysis

## 1. Inventory of All Documentation Sources

### 1.1 Root-Level Markdown Files

| File | Lines | Purpose | Audience |
|------|-------|---------|----------|
| `README.md` | 232 | Primary user-facing documentation: overview, installation, setup, configuration, how it works, failure modes, troubleshooting, testing | End users and developers |
| `CLAUDE.md` | 72 | Developer instructions for AI agents and contributors: repo layout, dev rules, testing requirements, security invariants, known gaps | Contributors / Claude Code AI |
| `CHANGELOG.md` | 63 | Version history following Keep a Changelog format | Users and contributors |
| `KNOWN-ISSUES.md` | 161 | Detailed issue tracker: platform verification items, open issues by severity, fixed issues | Contributors and advanced users |
| `TEST-PLAN.md` | 89 | Prioritized test action plan (P0/P1/P2) from audit | Contributors |
| `tests/README.md` | 68 | Test suite documentation: directory structure, category boundaries, how to add tests | Contributors |

### 1.2 Plugin UX Files

| File | Purpose | Audience |
|------|---------|----------|
| `commands/init.md` | `/guardian:init` setup wizard prompt. Detects project type, builds tailored config, presents summary, writes config. | End users (via Claude Code) |
| `skills/config-guide/SKILL.md` | Natural language config modification skill. Covers: block/unblock commands, protect/unprotect paths, git integration, review config, troubleshoot. | End users (via Claude Code) |
| `skills/config-guide/references/schema-reference.md` | Complete field-by-field documentation of config.json. Includes glob syntax, regex cookbook, pattern writing tips. | End users (via skill reference) |
| `agents/config-assistant.md` | Reactive config assistant agent. Triggers on guardian-related conversations. Includes safety assessment workflow. | End users (via Claude Code) |

### 1.3 Plugin Infrastructure Files

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin manifest: name, version, description, commands, skills, agents, keywords |
| `.claude-plugin/marketplace.json` | Marketplace discovery metadata |
| `hooks/hooks.json` | Hook registration: 4 PreToolUse hooks (Bash, Read, Edit, Write) + 1 Stop hook |
| `assets/guardian.schema.json` | JSON Schema (draft-07) for config.json validation |
| `assets/guardian.default.json` | Default configuration template with all sections populated |

### 1.4 Supplementary Files

| File | Purpose |
|------|---------|
| `.claude/ccyolo.md` | User's personal launcher docs (not part of plugin, but relevant context) |
| `.pytest_cache/README.md` | Auto-generated pytest cache docs (not project documentation) |
| `_archive/` | Archived temp files from prior review rounds (not active documentation) |

---

## 2. Per-Document Detailed Analysis

### 2.1 README.md

**Topics Covered:**
- Why Guardian exists (value proposition)
- What it catches (safety checkpoints, hard blocks, confirmation prompts, protected files)
- Installation (manual + marketplace, both with caveats)
- Setup (`/guardian:init` wizard)
- Configuration (config resolution order, example, section table)
- How it works (hook table, fail-closed principle, ask in permissionless mode)
- Failure modes (what it does/doesn't protect against)
- Circuit breaker behavior
- Troubleshooting (log location, hook verification, common issues table)
- Disabling Guardian (dry-run mode, temporary disable, uninstall)
- Testing (running tests, known gaps)
- Requirements (Python 3.10+, Git)

**Accuracy Assessment:**
- ACCURATE: Installation instructions (manual path is correct, marketplace marked unverified)
- ACCURATE: Config resolution order matches implementation (`load_guardian_config()`)
- ACCURATE: Hook registration matches `hooks.json`
- ACCURATE: Fail-closed behavior described correctly
- ACCURATE: Circuit breaker description matches implementation
- ACCURATE: Dry-run mode description matches `is_dry_run()` implementation
- MINOR GAP: Configuration table lists `bashPathScan` description as "Scans bash commands for references to protected path names" but doesn't mention it's a separate layer (Layer 1) from regex pattern matching
- MINOR GAP: Does not mention `bashPathScan` sub-options (`exactMatchAction`, `patternMatchAction`)

**What's Missing:**
1. No mention of archive-before-delete behavior (files archived to `_archive/` with size limits: 100MB per file, 500MB total, 50 files max)
2. No mention of self-guarding (Guardian protects its own config.json from AI modification) - partially mentioned in "How It Works" but details are thin
3. No mention of pre-danger checkpoint commits (mentioned in "What It Catches" briefly but not in Configuration section with details)
4. No mention of command size limit (100KB MAX_COMMAND_LENGTH) and that oversized commands are denied
5. No mention of log rotation behavior (1MB max, automatic rotation)
6. No mention of config validation at load time (`validate_guardian_config()`)
7. No detailed explanation of how path matching works across different tools (Bash vs Read/Edit/Write)
8. No mention of the fallback config behavior when CLAUDE_PROJECT_DIR is not set
9. No mention of environment variables beyond CLAUDE_HOOK_DRY_RUN (CLAUDE_PROJECT_DIR, CLAUDE_PLUGIN_ROOT are infrastructure but users might need to know)

### 2.2 CLAUDE.md

**Topics Covered:**
- Repository layout overview
- Testing requirements and commands
- Security invariants (fail-closed, hook output contract, thin wrappers, auto-commit fail-open)
- Known security gaps (prioritized)
- Coverage gaps by script (LOC and test coverage table)
- Quick reference (commands and key files)

**Accuracy Assessment:**
- ACCURATE: Repository layout
- ACCURATE: Security invariants
- SLIGHTLY OUTDATED: Coverage gaps table says edit/read/write_guardian.py have "None" test coverage, but CLAUDE.md itself notes they're "now tested via subprocess integration in tests/security/test_p0p1_failclosed.py" (contradiction within same file)
- ACCURATE: LOC counts (approximately)

**What's Missing:**
- No mention of the plugin UX layer (commands, skills, agents)
- No architectural overview (how hooks, config, and utils interact)

### 2.3 CHANGELOG.md

**Topics Covered:**
- Unreleased changes (added, changed, fixed)
- v1.0.1 changes
- v1.0.0 initial release features

**Accuracy Assessment:**
- ACCURATE: All entries match code changes observed
- WELL-FORMATTED: Follows Keep a Changelog standard

**What's Missing:**
- Nothing significant - this is a good changelog

### 2.4 KNOWN-ISSUES.md

**Topics Covered:**
- Platform verification items (PV-01 through PV-05)
- Open issues (medium and low severity)
- Fixed issues reference table

**Accuracy Assessment:**
- ACCURATE: All issues described match implementation observations
- WELL-ORGANIZED: By severity, with file references and impact assessments

**What's Missing:**
- The auto-commit `--no-verify` security gap (documented in CLAUDE.md but not cross-referenced here with its own issue ID)
- The normalization helpers fail-open gap (documented in CLAUDE.md but not here)

### 2.5 TEST-PLAN.md

**Topics Covered:**
- P0 (must test immediately): fail-open exception paths, guardian smoke tests, auto-commit security
- P1 (should test soon): hook JSON protocol E2E, auto-commit functional, TOCTOU, CI/CD
- P2 (should test): test migration, parametrize, coverage tooling, pytest config, import hardening
- Test style guide

**Accuracy Assessment:**
- ACCURATE: All targets reference correct file paths and line numbers
- ACCURATE: Priority ordering is appropriate

**What's Missing:**
- No timeline or ownership assignments
- No progress tracking (which items are done vs pending)

### 2.6 tests/README.md

**Topics Covered:**
- Directory structure
- Category boundaries (review vs usability)
- Running tests
- Adding new tests (bootstrap pattern)
- Category table

**Accuracy Assessment:**
- ACCURATE: Directory structure matches actual filesystem
- ACCURATE: Bootstrap pattern matches actual test files

**What's Missing:**
- No test counts per directory
- No description of what specific test files cover

### 2.7 commands/init.md

**Topics Covered:**
- Setup wizard philosophy (opinionated on safety, flexible on workflow)
- 6-step process: check existing, detect project, build config, present, write, confirm
- Project type detection matrix (9 project types)
- Per-project-type customization rules
- Safety rules for always-applies items

**Accuracy Assessment:**
- ACCURATE: References correct config paths
- ACCURATE: References correct schema and default config paths
- WELL-DESIGNED: Covers many project types

**What's Missing:**
- No mention of `bashPathScan` configuration in the generated config
- No mention of `allowedExternalReadPaths` / `allowedExternalWritePaths` in the wizard
- The wizard doesn't mention dry-run mode (UX-11 in KNOWN-ISSUES.md)

### 2.8 skills/config-guide/SKILL.md + references/schema-reference.md

**Topics Covered:**
- When skill activates
- Config location resolution
- 6 core operations (block, protect, unblock, configure git, review, troubleshoot)
- Safety rules
- Regex writing tips
- FULL schema reference with all fields, types, defaults, examples
- Glob pattern syntax guide
- Regex pattern cookbook (package management, infrastructure, database, git, system/network)

**Accuracy Assessment:**
- ACCURATE: Schema reference matches `guardian.schema.json`
- ACCURATE: All config sections documented
- ACCURATE: Examples are correct and useful
- MINOR: UX-09 notes that the cookbook doesn't mention patterns are already in defaults (documented as known issue)

**What's Missing:**
- `bashPathScan` is NOT documented in the schema reference (it's in the JSON schema but omitted from the human-readable reference)
- No mention of config validation behavior
- No mention of the fallback config mechanism

### 2.9 agents/config-assistant.md

**Topics Covered:**
- When to activate (with positive and negative examples)
- Workflow: read config, understand request, assess safety, apply changes, confirm
- Safety assessment categories (safe, warning, refuse)
- Config structure overview
- Regex and path pattern tips

**Accuracy Assessment:**
- ACCURATE: Trigger examples are well-chosen
- ACCURATE: Safety assessment categories are appropriate
- UX-10 notes it lacks sample output (documented as known issue)

**What's Missing:**
- No sample output for common interactions
- No mention of config validation after changes

### 2.10 assets/guardian.schema.json

**Topics Covered:**
- Full JSON Schema for all config sections
- Descriptions for every field
- Type constraints, enums, defaults, min/max values
- Pattern rule definition ($defs/patternRule)

**Accuracy Assessment:**
- ACCURATE: Matches implementation's config loading and validation
- COMPLETE: All config sections present

**What's Missing:**
- This is a schema, so "missing" isn't quite right, but some descriptions could be more detailed (e.g., explaining that `allowedExternalReadPaths` only bypasses the "outside project" check is good, but could mention it's checked by the Read tool specifically)

### 2.11 assets/guardian.default.json

**Topics Covered:**
- Complete default configuration with all sections populated
- 17 block patterns, 16 ask patterns
- 26 zeroAccessPaths, 16 readOnlyPaths, 36 noDeletePaths
- Git integration defaults
- bashPathScan defaults

**Accuracy Assessment:**
- ACCURATE: This is the actual runtime default config

**What's Missing:**
- No inline comments explaining why specific patterns exist (JSON doesn't support comments; the `$comment` field is used at the top level but not per-pattern)

---

## 3. Cross-Document Gap Analysis

### 3.1 Features Documented Nowhere or Insufficiently

| Feature | Where it exists in code | Documentation status |
|---------|------------------------|---------------------|
| **Archive-before-delete** (untracked files archived to `_archive/` before rm is allowed) | `bash_guardian.py:748-863` | README mentions it in "What It Catches" as one line. No details on limits (100MB/file, 500MB total, 50 files), archive naming, or deletion log creation |
| **bashPathScan** (Layer 1 raw string scanning for protected path names in bash commands) | `bash_guardian.py:306-400`, config schema, default config | README configuration table has one-line mention. NOT in schema-reference.md. Sub-options `exactMatchAction`, `patternMatchAction` undocumented in human-readable docs |
| **Command size limit** (commands >100KB are denied as fail-closed protection) | `_guardian_utils.py:79,853-858` | Not documented anywhere |
| **Self-guarding** (Guardian protects its own config from AI modification) | `_guardian_utils.py:2162-2218` | README has one sentence. No details on what paths are protected or why |
| **Config validation at load time** | `_guardian_utils.py:653-749` | Not documented in user-facing docs |
| **Log rotation** (1MB max, automatic rotation to .old) | `_guardian_utils.py:1267-1300` | Not documented (log location is documented in README troubleshooting) |
| **Fallback config** (hardcoded minimal config when no config.json found) | `_guardian_utils.py:367-425` | README mentions "hardcoded minimal guardian ruleset" but doesn't list what's in it |
| **Pre-danger checkpoint commits** | `bash_guardian.py:main()`, `_guardian_utils.py:git_commit()` | README "What It Catches" mentions it. Config reference documents it. But no explanation of when exactly it triggers |
| **Redirection target extraction** (bash commands writing to files via `>`, `>>` are checked) | `bash_guardian.py:431-476` | Not documented |
| **Path extraction from bash commands** (bash commands referencing paths are checked against protection rules) | `bash_guardian.py:478-569` | Not documented as a distinct feature |
| **Multi-command splitting** (piped/chained commands are split and each checked independently) | `bash_guardian.py:82-251` | Not documented |
| **Write command detection** (commands that write files are identified for path checking) | `bash_guardian.py:635-668` | Not documented |
| **Delete command detection** (commands that delete files are identified for noDelete checking) | `bash_guardian.py:599-633` | Not documented |
| **Interpreter file deletion blocking** (Python/Node/Perl/Ruby file deletion APIs blocked) | Default config block patterns | Listed in default config but not explained in docs |
| **hookBehavior.timeoutSeconds not enforced** | SCOPE-02 in KNOWN-ISSUES.md | Only in KNOWN-ISSUES.md, not in main docs where users configure it |
| **noDeletePaths only enforced for bash delete commands** | SCOPE-01 in KNOWN-ISSUES.md | Only in KNOWN-ISSUES.md, not in main docs |

### 3.2 Configuration Options Documentation Matrix

| Config Option | JSON Schema | Default Config | README | Schema Reference | Skill SKILL.md |
|---------------|:-----------:|:--------------:|:------:|:----------------:|:--------------:|
| version | Y | Y | Y | Y | N |
| hookBehavior.onTimeout | Y | Y | Y | Y | Y |
| hookBehavior.onError | Y | Y | Y | Y | Y |
| hookBehavior.timeoutSeconds | Y | Y | Y | Y | N |
| bashToolPatterns.block | Y | Y | Y | Y | Y |
| bashToolPatterns.ask | Y | Y | Y | Y | Y |
| zeroAccessPaths | Y | Y | Y | Y | Y |
| readOnlyPaths | Y | Y | Y | Y | Y |
| noDeletePaths | Y | Y | Y | Y | Y |
| allowedExternalReadPaths | Y | Y | Y | Y | N |
| allowedExternalWritePaths | Y | Y | Y | Y | N |
| gitIntegration.autoCommit.enabled | Y | Y | N | Y | Y |
| gitIntegration.autoCommit.onStop | Y | Y | N | Y | N |
| gitIntegration.autoCommit.messagePrefix | Y | Y | N | Y | Y |
| gitIntegration.autoCommit.includeUntracked | Y | Y | N | Y | Y |
| gitIntegration.preCommitOnDangerous.enabled | Y | Y | N | Y | N |
| gitIntegration.preCommitOnDangerous.messagePrefix | Y | Y | N | Y | N |
| gitIntegration.identity.email | Y | Y | N | Y | Y |
| gitIntegration.identity.name | Y | Y | N | Y | Y |
| bashPathScan.enabled | Y | Y | Y (brief) | **N** | N |
| bashPathScan.scanTiers | Y | Y | Y (brief) | **N** | N |
| bashPathScan.exactMatchAction | Y | Y | N | **N** | N |
| bashPathScan.patternMatchAction | Y | Y | N | **N** | N |

**Key finding:** `bashPathScan` sub-options are missing from the schema-reference.md and the skill documentation entirely.

### 3.3 User Journey Gaps

| User Journey | Documented? | Gap |
|-------------|-------------|-----|
| First-time install (manual) | Yes (README) | Good |
| First-time install (marketplace) | Partial (marked unverified) | Acceptable given unverified status |
| Initial setup | Yes (README + init wizard) | Good |
| Customizing config manually | Partial (README + schema ref) | README example is partial; no full config walkthrough |
| Using the config skill | Yes (SKILL.md) | Good |
| Understanding a block | Partial | No example of what the user sees when a command is blocked (no sample hook output) |
| Debugging unexpected blocks | Yes (README troubleshooting) | Good |
| Understanding archive behavior | Minimal | One line in README; no details on limits, location, cleanup |
| Upgrading Guardian | Minimal | README says "git pull" but no migration guidance for config changes between versions |
| Uninstalling | Yes (README) | Good |
| Understanding what's in the default config | Partial | Have to read the JSON file; no human-readable summary of defaults |
| Contributing tests | Yes (tests/README + CLAUDE.md) | Good |
| Understanding security model | Partial (README "Failure Modes") | Good overview, but no security architecture document |

### 3.4 Cross-Reference Gaps

1. **CLAUDE.md vs KNOWN-ISSUES.md**: The auto-commit `--no-verify` security gap (CLAUDE.md known gap #1) has no corresponding issue ID in KNOWN-ISSUES.md
2. **CLAUDE.md vs KNOWN-ISSUES.md**: The normalization helpers fail-open gap (CLAUDE.md known gap #3) has no corresponding issue ID in KNOWN-ISSUES.md
3. **CLAUDE.md coverage table**: States edit/read/write guardians have "None" test coverage, but also says they're "now tested via subprocess integration" (internal contradiction)
4. **README vs Schema Reference**: README configuration table doesn't link to schema-reference.md
5. **README vs KNOWN-ISSUES.md**: README doesn't link to KNOWN-ISSUES.md for detailed issue tracking

---

## 4. Documentation Quality Assessment

### 4.1 Strengths

1. **README.md is well-structured** with clear sections, a compelling value proposition, and practical troubleshooting
2. **Schema reference is thorough** for the fields it covers, with examples and a regex cookbook
3. **Init wizard is well-designed** with project-type detection and smart defaults
4. **KNOWN-ISSUES.md is exemplary** - detailed, severity-tagged, with file references and status tracking
5. **CHANGELOG follows standards** (Keep a Changelog format)
6. **Config assistant agent has good trigger examples** including negative examples

### 4.2 Weaknesses

1. **bashPathScan is the biggest documentation gap** - a significant feature with 4 sub-options that's barely mentioned
2. **Archive-before-delete is undersold** - a major safety feature that gets one line
3. **No sample output** - users don't know what a blocked command looks like in practice
4. **No architecture overview** - how the 6 scripts interact, the layered checking approach in bash_guardian (Layer 1: path scan, Layer 2: pattern matching, Layer 3: path extraction), the distinction between bash_guardian's comprehensive checks vs the thin path guardian wrappers
5. **Implementation details not surfaced** - command size limits, log rotation, config validation, multi-command splitting are invisible to users
6. **By-design limitations are buried** - SCOPE-01 (noDeletePaths only for bash) and SCOPE-02 (timeoutSeconds not enforced) are only in KNOWN-ISSUES.md, not in the main docs where users configure these features

### 4.3 Priority Recommendations

| Priority | Gap | Impact | Effort |
|----------|-----|--------|--------|
| P0 | Document bashPathScan fully in schema-reference.md | Users cannot configure a significant feature | Low |
| P0 | Add SCOPE-01 caveat to noDeletePaths docs | Users have false expectations about protection | Low |
| P1 | Document archive-before-delete behavior in README | Users miss a key safety feature | Medium |
| P1 | Add sample blocked/asked output to README | Users don't know what to expect | Medium |
| P1 | Document self-guarding behavior | Users don't understand why config edits are blocked | Low |
| P2 | Add architecture overview (layered checking, script interactions) | Contributors lack mental model | Medium |
| P2 | Document implementation limits (command size, log rotation) | Advanced users may hit limits without understanding | Low |
| P2 | Add human-readable summary of default config patterns | Users shouldn't have to read JSON | Medium |
| P2 | Fix CLAUDE.md internal contradiction (coverage table vs text) | Contributors get confused | Low |
| P3 | Cross-reference CLAUDE.md security gaps as KNOWN-ISSUES IDs | Consistency | Low |
| P3 | Add config upgrade/migration guidance | Future version users | Low |

---

## 5. Summary Statistics

| Metric | Count |
|--------|-------|
| Total documentation files | 14 (excluding _archive and .pytest_cache) |
| Total documentation lines | ~1,100 |
| User-facing doc files | 6 (README, CHANGELOG, KNOWN-ISSUES, init.md, SKILL.md, schema-reference.md) |
| Developer-facing doc files | 4 (CLAUDE.md, TEST-PLAN.md, tests/README.md, config-assistant.md) |
| Infrastructure files (self-documenting) | 4 (plugin.json, marketplace.json, hooks.json, guardian.schema.json) |
| Config options fully documented | 18 of 22 (82%) |
| Config options partially documented | 4 of 22 (18%) - all bashPathScan sub-options |
| Implementation features documented | ~60% (major features covered, implementation details and edge behaviors not) |
| Known issues with documentation gaps | 3 (UX-09, UX-10, UX-11) |
