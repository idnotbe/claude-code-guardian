# Known Issues & Verification Checklist

## Version: 1.0.0
## Last Updated: 2026-02-11
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
- **File**: hooks/scripts/_guardian_utils.py (lines 1452-1465)
- **Issue**: LC_ALL=C forces English git output; non-MSYS2 git may not respect it
- **Status**: Accepted risk. Git for Windows (dominant distribution) works correctly

#### COMPAT-05: Thread-based timeout non-killable on Windows
- **File**: hooks/scripts/_guardian_utils.py (lines 135-155)
- **Issue**: Windows with_timeout uses threading which cannot forcibly kill the target function
- **Status**: Accepted. Hook processes are short-lived; timeout still prevents blocking

#### COMPAT-06: normalize_path resolves against CWD
- **File**: hooks/scripts/_guardian_utils.py (lines 881-895)
- **Issue**: normalize_path() uses os.path.abspath() resolving against CWD, not project dir
- **Impact**: Latent bug -- not triggered since tool inputs arrive as absolute paths
- **Fix**: Align with normalize_path_for_matching() or document as absolute-path-only

#### COMPAT-07: fnmatch case sensitivity on macOS
- **File**: hooks/scripts/_guardian_utils.py (lines 1055, 1087)
- **Issue**: Code lowercases paths only on Windows; macOS HFS+ is also case-insensitive
- **Fix**: Consider sys.platform != 'linux' for lowercasing check

### LOW Severity

#### ~~UX-08: Default blocks --force-with-lease~~ FIXED
- **Issue**: --force-with-lease (safe force push) was blocked alongside --force
- **Fix**: Moved --force-with-lease from block to ask patterns (v1.0.1)

#### UX-09: Schema reference common patterns note
- **Issue**: Common patterns table lists defaults without noting they are pre-included

#### UX-10: Config-assistant agent lacks sample output
- **Issue**: Trigger examples show input/action but not expected output format

#### UX-11: No uninstall/disable documentation
- **Issue**: No docs on CLAUDE_HOOK_DRY_RUN=1 or uninstalling

#### UX-12: init.md quick tips depend on skill/agent
- **Status**: Resolved -- skill/agent now registered in plugin.json

#### COMPAT-08: Relative $schema in default config
- **Issue**: $schema uses relative path which breaks when copied to user project

#### ~~COMPAT-11: errno 28 disk full check is Linux-specific~~ FIXED
- **Issue**: e.errno == 28 was ENOSPC on Linux only; Windows uses winerror 112
- **Fix**: Added `getattr(e, 'winerror', None) == 112` check (v1.0.1)

#### COMPAT-12: Hypothetical marketplace schema URL
- **Status**: Cosmetic only -- no runtime impact

#### COMPAT-13: Recovery guidance uses Windows del on all platforms
- **Fix**: Use sys.platform to suggest del on Windows, rm on Unix

---

## Fixed Issues (for reference)

| ID | Severity | Description | Fixed In |
|----|----------|-------------|----------|
| F-01 | CRITICAL | bash_guardian.py fail-open on crash | Round 1 |
| F-02 | HIGH | Oversized command bypass (padding attack) | Round 1 |
| CRITICAL-01 | CRITICAL | README documented non-existent config step | Round 1 |
| HIGH-01 | HIGH | marketplace.json wrong $schema key | Round 1 |
| MEDIUM-02 | MEDIUM | Korean comments in committed code | Round 1 |
| MEDIUM-03 | MEDIUM | .gitignore wrong log filename | Round 1 |
| COMPAT-01 | HIGH | plugin.json missing skills/agents | Round 2 |
| COMPAT-02 | HIGH | python vs python3 in hooks.json | Round 2 |
| COMPAT-03 | MEDIUM | shlex.split Windows quote handling | v1.0.1 |
| COMPAT-11 | LOW | errno 28 disk full Linux-only | v1.0.1 |
| UX-08 | LOW | --force-with-lease blocked instead of ask | v1.0.1 |
| UX-01 | HIGH | SKILL.md vague config paths | Round 2 |
| UX-03 | MEDIUM | No skip-init guidance | Round 2 |
| UX-04 | MEDIUM | Inconsistent fail-closed terminology | Round 2 |
| UX-05 | MEDIUM | No fallback for unrecognized projects | Round 2 |
| UX-06 | MEDIUM | Legacy path check in init wizard | Round 2 |
