# Phase 1 V1 Fixes Applied

**Date**: 2026-03-21

## Bugs Fixed

### BUG-1 (CRITICAL): Post-`<<` redirection bypass
- **Root cause**: Origin only captured text BEFORE `<<`, missing redirects after it
- **Fix**: `heredoc_origins` now stores 4-tuples `(origin_cmd, was_piped, full_segment, is_quoted)`. `full_segment` is finalized at every separator handler with the full sub-command text. Classifier checks redirect pattern against `full_segment`.
- **Tests**: 7 new tests in TestV1FixPostRedirectBypass

### BUG-2 (CRITICAL): Unquoted heredoc expansion bypass
- **Root cause**: Bash expands `$()`, backticks in unquoted heredoc bodies. Redacting these bodies hides executable content.
- **Fix**: `is_quoted = raw_token != delim` propagated through origins. In `_consume_heredoc_bodies()`, if body contains `$` or backtick and delimiter was unquoted, force UNSAFE.
- **Tests**: 7 new tests in TestV1FixUnquotedExpansion

### BUG-3 (MEDIUM): sudo flag parsing
- **Root cause**: sudo loop assumed all `-X` flags take an argument, causing it to skip past the actual command
- **Fix**: Explicit set of arg-taking flags (`-u`, `-g`, `-C`, `-D`, `-r`, `-R`, `-T`). Handle `--` terminator.
- **Tests**: 5 new tests in TestV1FixSudoParsing

### BUG-4 (LOW): origins truthiness check
- **Fix**: `if classify and origins:` → `if classify and origins is not None:`

## Test Results
- **91 Phase 1 tests** pass (69 original + 22 V1 fix tests)
- **972 total tests** pass, 11 pre-existing failures, 1 pre-existing error
- No regressions
