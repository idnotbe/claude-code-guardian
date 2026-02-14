# Changelog

All notable changes to claude-code-guardian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `validate_guardian_config()` now called during config loading with warnings logged for invalid fields
- `hookBehavior.onTimeout` and `hookBehavior.onError` now used at runtime in all 4 security hook scripts
- `make_hook_behavior_response()` helper for converting hookBehavior actions to hook protocol responses
- `bashPathScan.scanTiers` now implemented in bash_guardian.py Layer 1 (supports `zeroAccess`, `readOnly`, `noDelete`)

### Changed
- COMPAT-06: `normalize_path()` aligned with `normalize_path_for_matching()` for consistent path resolution
- COMPAT-07: Case sensitivity check now uses `sys.platform != 'linux'` to cover macOS HFS+ volumes
- COMPAT-08: Default config `$schema` field removed for portability (broke when config copied to project)
- COMPAT-13: Circuit breaker recovery guidance now uses platform-aware commands (`rm` on Unix, `del` on Windows)
- README: Added shell profile persistence example for automatic Guardian loading
- README: Clarified marketplace commands as unverified alternatives
- README: Added Troubleshooting section with log location, hook verification, and common issues
- README: Surfaced Python 3.10+ requirement in Installation section
- README: Improved dry-run mode discoverability with cross-references in Setup section
- README: Added `timeoutSeconds` to `hookBehavior` description in Configuration table
- KNOWN-ISSUES: Updated UX-11 title to reflect current state (dry-run documented in README)
- KNOWN-ISSUES: Fleshed out terse entries (UX-09, UX-10, COMPAT-12) with file paths and actionable detail
- KNOWN-ISSUES: Marked UX-12 as fixed with consistent strikethrough formatting

### Fixed
- `evaluate_rules()` now returns deny on internal error instead of fail-open allow
- `MAX_COMMAND_LENGTH` docstring corrected from "fail-open" to "fail-closed"

## [1.0.1] - 2026-02-11

### Changed
- Renamed user config file from `guardian.json` to `config.json` (path `.claude/guardian/config.json` avoids stutter)
- Renamed `evaluate_guardian()` to `evaluate_rules()` for clarity (function evaluates rules, not "the guardian")

### Fixed
- shlex.split quote handling on Windows (posix=False quote stripping)
- --force-with-lease moved from block to ask patterns (safe force push should not be silently blocked)
- errno 28 disk full check now handles Windows winerror 112

## [1.0.0] - 2026-02-11

### Added
- Initial release
- Bash command guarding (block dangerous patterns, ask for confirmation on risky ones)
- Read/Edit/Write file guarding (zero-access paths, read-only paths, no-delete paths)
- Auto-commit on session stop with configurable git identity
- Pre-danger checkpoint commits before destructive operations
- Dry-run mode via `CLAUDE_HOOK_DRY_RUN=1` environment variable for testing configurations
- Archive-before-delete: untracked files are archived to `_archive/` before deletion is permitted
- JSON Schema for configuration validation
- Default configuration template with universal security defaults
- `/guardian:init` setup command

[Unreleased]: https://github.com/idnotbe/claude-code-guardian/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/idnotbe/claude-code-guardian/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/idnotbe/claude-code-guardian/releases/tag/v1.0.0
