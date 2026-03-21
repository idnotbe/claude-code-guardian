# Phase 1: Heredoc Body Redaction — Draft Summary

**Date**: 2026-03-21
**Status**: Draft complete, pending verification

## Changes Made

### 1. `_consume_heredoc_bodies()` (bash_guardian.py:688-740)
- Added `classify` and `origins` parameters
- When `classify=True`, returns `(position, body_ranges)` where body_ranges is `list[tuple[int, int, bool]]`
- Each body range is `(start, end, is_safe)` — excludes delimiter line
- Unterminated heredocs: fail-closed, marked UNSAFE

### 2. `split_commands()` (bash_guardian.py:216-635)
- New tracking: `all_body_ranges`, `heredoc_origins`
- F1-1: Origin command captured at `<<` parse time (line 558), BEFORE appending `<<` to current
- Pipe handler (line 508): marks all pending heredoc origins as piped (was_piped=True)
- Newline handler (line 586): passes origins to `_consume_heredoc_bodies(classify=True)`
- End of function (line 610): builds redacted string by replacing safe body content with empty lines
- Newline count preserved: `body.count('\n')` newlines replace body content
- Fail-closed: try/except returns original command on error
- Backward compatible: `redact_safe_heredocs=False` returns list (unchanged)

### 3. `main()` (bash_guardian.py:1697-1722)
- `split_commands(command, redact_safe_heredocs=True)` called FIRST
- Layer 0 (`match_block_patterns`) scans `redacted_command`
- Layer 0b (`match_ask_patterns`) scans `redacted_command`
- Layer 1+ uses original `sub_commands` (unchanged)

### Pre-existing Data Structures (from partial Phase 1 work)
- `_PASSIVE_DATA_SINKS`: cat, grep, egrep, fgrep, head, tail, wc, uniq, cut, tr, fold, fmt, column, paste, join, comm, echo, printf, jq, yq, diff, cmp, md5sum, sha256sum, sha1sum
- `_INTERPRETER_COMMANDS`: bash, sh, zsh, dash, ksh, csh, tcsh, fish, python, python2, python3, py, node, deno, bun, perl, ruby, source, eval, exec
- `_OUTPUT_REDIR_PATTERN`: regex for >, >>, >|, &>, >&file
- `_extract_base_command()`: strips env/sudo/nohup/time/command/builtin/strace prefixes, variable assignments, I/O redirects, absolute paths
- `_classify_heredoc_safety()`: 5-rule classifier (interpreter→UNSAFE, redirect→UNSAFE, piped→UNSAFE, passive sink→SAFE, unknown→UNSAFE)

## Test Results
- **69 Phase 1 tests** pass (test_heredoc_redaction.py)
- **950 total tests** pass, 11 pre-existing failures, 1 pre-existing error
- No regressions from Phase 1 changes

## Key Design Decisions
1. **Single-parser**: Redaction integrated into `split_commands()`, no separate parser
2. **F1-1 origin tracking**: Origin captured at `<<` parse time, survives all separator splits
3. **Piped flag**: Only `|` marks heredocs as piped (not `;`, `&&`, `||`, `&`)
4. **Newline preservation**: Prevents token merging and line alignment changes
5. **Fail-closed everywhere**: Unknown commands → UNSAFE, errors → original command, unterminated → UNSAFE
6. **Minimal blast radius**: Only Layer 0/0b see redacted string; all other layers use originals
