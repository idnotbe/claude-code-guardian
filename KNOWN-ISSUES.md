# Known Issues & Verification Checklist

## Version: 1.0.1
## Last Updated: 2026-02-14
## Review Status: 2 rounds complete (4 independent reviewers)

---

## Platform Verification Required (Pre-Release)

These 5 assumptions must be verified in a real Claude Code environment before public release.

### PV-01: CLAUDE_PLUGIN_ROOT Expansion
- **Assumption**: Claude Code expands CLAUDE_PLUGIN_ROOT in hooks.json command strings
- **Used in**: hooks/hooks.json (all 4 hook commands)
- **If wrong**: All hooks will fail to execute (scripts not found)
- **Test**: Install plugin, run any bash command, check if hook fires

### PV-02: Hook JSON Protocol
- **Assumption**: PreToolUse hooks communicate decisions via JSON on stdout with hookSpecificOutput containing permissionDecision (deny/ask/allow)
- **Used in**: All 4 hook scripts
- **If wrong**: Hooks will not block/ask as expected
- **Test**: Trigger a known-blocked command, verify it is denied

### PV-03: Skill and Agent Discovery
- **Assumption**: Claude Code discovers skills and agents from paths declared in plugin.json
- **Used in**: .claude-plugin/plugin.json (skills, agents arrays)
- **If wrong**: Config-guide skill and config-assistant agent will not be available
- **Test**: Install plugin, say "show guardian config" -- should trigger skill

### PV-04: Marketplace Resolution
- **Assumption**: .claude-plugin/marketplace.json enables self-hosted marketplace installation
- **Used in**: .claude-plugin/marketplace.json
- **If wrong**: Users must use manual installation (git clone + --plugin-dir)
- **Test**: Try marketplace add command with the repo

### PV-05: Command Registration
- **Assumption**: Commands listed in plugin.json are registered as slash commands
- **Used in**: .claude-plugin/plugin.json -> commands -> init.md
- **If wrong**: /guardian:init will not be available
- **Test**: Install plugin, type /guardian:init, verify wizard starts

---

## Open Issues

### MEDIUM Severity

#### UX-07: README marketplace install commands unverified
- **File**: README.md
- **Issue**: Marketplace installation commands are speculative -- actual CLI syntax may differ
- **Impact**: First thing users try may not work
- **Recommendation**: Verify against real Claude Code plugin CLI docs; lead with manual install

#### ~~COMPAT-03: shlex.split quote handling on Windows~~ FIXED
- **File**: hooks/scripts/bash_guardian.py
- **Issue**: shlex.split(posix=False) did not strip surrounding quotes from tokens on Windows
- **Fix**: Added quote stripping after shlex.split on Windows (v1.0.1)

#### COMPAT-04: LC_ALL=C on non-MSYS2 Windows git
- **File**: hooks/scripts/_guardian_utils.py, `_get_git_env()` function
- **Issue**: LC_ALL=C forces English git output; non-MSYS2 git may not respect it
- **Status**: Accepted risk. Git for Windows (dominant distribution) works correctly

#### COMPAT-05: Thread-based timeout non-killable on Windows
- **File**: hooks/scripts/_guardian_utils.py (lines 135-155)
- **Issue**: Windows with_timeout uses threading which cannot forcibly kill the target function
- **Status**: Accepted. Hook processes are short-lived; timeout still prevents blocking

#### ~~COMPAT-06: normalize_path resolves against CWD~~ FIXED
- **File**: hooks/scripts/_guardian_utils.py, `normalize_path()` function
- **Issue**: normalize_path() used os.path.abspath() resolving against CWD, not project dir
- **Fix**: Aligned with `normalize_path_for_matching()` to resolve relative paths against project dir

#### ~~COMPAT-07: fnmatch case sensitivity on macOS~~ FIXED
- **File**: hooks/scripts/_guardian_utils.py, `normalize_path_for_matching()` and `match_path_pattern()` functions
- **Issue**: Code lowercased paths only on Windows; macOS HFS+ is also case-insensitive
- **Fix**: Changed to `sys.platform != 'linux'` for lowercasing check (covers both Windows and macOS)

#### SCOPE-01: noDeletePaths only enforced for Bash delete commands
- **File**: hooks/scripts/bash_guardian.py, hooks/scripts/_guardian_utils.py `run_path_guardian_hook()`
- **Issue**: `noDeletePaths` is only checked by bash_guardian.py for delete-type commands. Edit/Write hooks do not enforce noDeletePaths -- an Edit tool call could replace file contents with empty content.
- **Impact**: Users may expect files in noDeletePaths are fully protected, but only bash `rm`-style deletion is blocked.
- **Status**: By-design limitation. Edit/Write hooks check zeroAccessPaths, readOnlyPaths, symlink escapes, and self-guarding.

#### SCOPE-02: hookBehavior.timeoutSeconds not enforced at hook level
- **File**: hooks/scripts/bash_guardian.py (line ~1235 TODO comment)
- **Issue**: `hookBehavior.timeoutSeconds` is defined in the config schema and returned by `get_hook_behavior()`, but is not enforced as a blanket timeout on hook execution. Individual subprocess calls have their own timeouts (5-30s), but the overall hook has no time limit.
- **Impact**: Users may configure `timeoutSeconds` expecting it to limit hook execution time, but it has no runtime effect.
- **Status**: By-design limitation. Wrapping hook execution with `with_timeout()` risks git state corruption (SIGALRM interrupting subprocess mid-write), partial archive file copies, and Windows threading race conditions. Individual subprocess timeouts provide sufficient protection.

### LOW Severity

#### ~~UX-08: Default blocks --force-with-lease~~ FIXED
- **Issue**: --force-with-lease (safe force push) was blocked alongside --force
- **Fix**: Moved --force-with-lease from block to ask patterns (v1.0.1)

#### UX-09: Schema reference common patterns note
- **File**: assets/guardian.schema.json
- **Issue**: The common patterns table in the schema reference lists example patterns (e.g., `rm -rf`, `.env` blocking) without noting that these patterns are already pre-included in the default configuration. Users may add duplicate patterns thinking they need to be explicitly configured.
- **Fix**: Add a note to the common patterns table stating "These patterns are already included in the default configuration (`assets/guardian.default.json`). You only need to add them to your custom config if you have removed or overridden the defaults."

#### UX-10: Config-assistant agent lacks sample output
- **File**: .claude-plugin/agents/config-assistant.md
- **Issue**: The config-assistant agent definition includes trigger examples (e.g., "help me configure guardian", "what patterns should I block?") showing when the agent activates, but does not include sample output demonstrating what the agent's response looks like. Users cannot preview expected behavior before triggering the agent.
- **Fix**: Add a "Sample Output" section to config-assistant.md showing an example response for a common query like "help me configure guardian for a Node.js project."

#### UX-11: Dry-run mode not mentioned in setup wizard
- **Issue**: `CLAUDE_HOOK_DRY_RUN=1` dry-run mode is now documented in the README (Disabling Guardian and Setup sections), but the `/guardian:init` setup wizard does not mention it as a way to test configuration changes safely.
- **Status**: Partially fixed -- README documents dry-run mode. Remaining gap: setup wizard does not surface dry-run as a testing option.

#### ~~UX-12: init.md quick tips depend on skill/agent~~ FIXED
- **Status**: Resolved -- skill/agent now registered in plugin.json (Round 2)

#### ~~COMPAT-08: Relative $schema in default config~~ FIXED
- **File**: assets/guardian.default.json
- **Issue**: The `$schema` field used a relative path (`./guardian.schema.json`) which broke when users copied config to their project
- **Fix**: Removed `$schema` field from default config entirely

#### ~~COMPAT-11: errno 28 disk full check is Linux-specific~~ FIXED
- **Issue**: e.errno == 28 was ENOSPC on Linux only; Windows uses winerror 112
- **Fix**: Added `getattr(e, 'winerror', None) == 112` check (v1.0.1)

#### COMPAT-12: Hypothetical marketplace schema URL
- **File**: .claude-plugin/marketplace.json
- **Issue**: The `$schema` field in marketplace.json references a hypothetical URL (`https://claude.ai/schemas/marketplace.json`) that does not resolve to an actual schema endpoint. This prevents IDE-based schema validation from working.
- **Status**: Cosmetic only -- no runtime impact. The marketplace.json file is only used during plugin discovery and installation, not at runtime.

#### ~~COMPAT-13: Recovery guidance uses Windows del on all platforms~~ FIXED
- **File**: hooks/scripts/_guardian_utils.py, circuit breaker recovery messages
- **Issue**: Recovery messages suggested `del` regardless of OS; Linux/macOS users should see `rm`
- **Fix**: Added `sys.platform` check to suggest `del` on Windows and `rm` on Unix/macOS

---

## Fixed Issues (for reference)

| ID | Severity | Description | Fixed In |
|----|----------|-------------|----------|
| F-01 | CRITICAL | bash_guardian.py failed open on unhandled crash, allowing commands through without checks | Round 1 |
| F-02 | HIGH | Oversized command could bypass pattern matching via padding attack | Round 1 |
| CRITICAL-01 | CRITICAL | README documented a configuration step that did not exist in the codebase | Round 1 |
| HIGH-01 | HIGH | marketplace.json used wrong `$schema` key format | Round 1 |
| MEDIUM-02 | MEDIUM | Korean-language comments left in committed production code | Round 1 |
| MEDIUM-03 | MEDIUM | .gitignore referenced wrong log filename, leaving actual logs unignored | Round 1 |
| COMPAT-01 | HIGH | plugin.json missing skills and agents declarations, preventing discovery | Round 2 |
| COMPAT-02 | HIGH | hooks.json used `python` instead of `python3`, failing on Linux/WSL systems | Round 2 |
| COMPAT-03 | MEDIUM | shlex.split(posix=False) did not strip surrounding quotes on Windows | v1.0.1 |
| COMPAT-11 | LOW | errno 28 disk-full check was Linux-specific; Windows uses winerror 112 | v1.0.1 |
| UX-08 | LOW | --force-with-lease (safe force push) was blocked instead of prompting ask | v1.0.1 |
| UX-01 | HIGH | SKILL.md referenced vague config paths that did not match actual file locations | Round 2 |
| UX-03 | MEDIUM | No guidance for skipping /guardian:init wizard when manually configuring | Round 2 |
| UX-04 | MEDIUM | Inconsistent fail-closed terminology across documentation and code comments | Round 2 |
| UX-05 | MEDIUM | No fallback behavior defined for unrecognized project types in init wizard | Round 2 |
| UX-06 | MEDIUM | Init wizard checked for legacy config path that no longer existed | Round 2 |
| UX-12 | LOW | init.md quick tips referenced skill/agent before they were registered in plugin.json | Round 2 |
| COMPAT-06 | MEDIUM | normalize_path() resolved relative paths against CWD instead of project directory | Unreleased |
| COMPAT-07 | MEDIUM | fnmatch case sensitivity incorrect on macOS HFS+ (case-insensitive filesystem) | Unreleased |
| COMPAT-08 | LOW | Relative `$schema` path in default config broke when config copied to project | Unreleased |
| COMPAT-13 | LOW | Circuit breaker recovery guidance suggested Windows `del` command on all platforms | Unreleased |
