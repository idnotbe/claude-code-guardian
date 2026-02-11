# Changelog

All notable changes to claude-code-guardian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-11

### Added
- Initial release
- Bash command protection (block dangerous patterns, ask for confirmation on risky ones)
- Edit/Write file protection (zero-access paths, read-only paths, no-delete paths)
- Auto-commit on session stop with configurable git identity
- Pre-danger checkpoint commits before destructive operations
- JSON Schema for configuration validation
- Default configuration template with universal security defaults
- `/guardian:init` setup command
