# Changelog

All notable changes to claude-code-guardian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Edit/Write file guarding (zero-access paths, read-only paths, no-delete paths)
- Auto-commit on session stop with configurable git identity
- Pre-danger checkpoint commits before destructive operations
- JSON Schema for configuration validation
- Default configuration template with universal security defaults
- `/guardian:init` setup command
