# Fix All Issues - Master Plan

## Scope: Fix ALL discovered issues from doc review, even minor ones

### Team A: Code Bug Fixes (_guardian_utils.py, bash_guardian.py)
- COMPAT-13: Recovery guidance uses `del` on all platforms -> use sys.platform
- COMPAT-08: Relative $schema in default config -> fix path
- COMPAT-06: normalize_path resolves against CWD -> align with normalize_path_for_matching
- COMPAT-07: fnmatch case sensitivity on macOS -> sys.platform != 'linux'
- evaluate_rules() fails-open -> change to fail-closed (return "deny")
- MAX_COMMAND_LENGTH comment says "fail-open" but code is fail-closed -> fix comment

### Team B: Code Feature Wiring (connect unused functions)
- Wire up validate_guardian_config() in config loading
- Wire up with_timeout() in hook scripts OR remove if unnecessary
- Wire up hookBehavior.onTimeout/onError to actual runtime behavior
- Implement scanTiers support in bash_guardian.py Layer 1

### Team C: Documentation Polish (README, KNOWN-ISSUES, CHANGELOG)
- README: Add shell profile persistence example
- README: Clarify marketplace commands
- README: Add troubleshooting section with log file location
- README: Add hookBehavior.timeoutSeconds to config table
- README: Surface Python 3.10+ requirement prominently
- KNOWN-ISSUES: Update UX-11 title (no longer "undocumented")
- KNOWN-ISSUES: Flesh out UX-09, UX-10, COMPAT-08 descriptions
- KNOWN-ISSUES: Mark items as FIXED as they get resolved
- CHANGELOG: Add entries for all fixes under [Unreleased]

### Phase 2: Verification Round 1 (Teammates G, H)
### Phase 3: Verification Round 2 (Teammates I, J)
### Phase 4: Temp cleanup + Commit

## Output Files
- fix-all-issues/team-a-fixes.md
- fix-all-issues/team-b-fixes.md
- fix-all-issues/team-c-fixes.md
- fix-all-issues/verification-r1.md
- fix-all-issues/verification-r2.md
