# Phase 3 V1 Combined Analysis

**Sources**: Opus 4.6 analysis + Codex 5.3 clink + Gemini 3.1 Pro clink

## Convergence Matrix

| Finding | Opus | Codex | Gemini | Severity | Action |
|---------|------|-------|--------|----------|--------|
| `.` (dot cmd) not in _INTERPRETER_COMMANDS | MEDIUM | HIGH 9/10 (grouped) | — | MEDIUM | **FIX** |
| Versioned interpreters (python3.10) | LOW | HIGH 9/10 | MEDIUM 5/10 | MEDIUM | **FIX** |
| Prefix flag parsing gap (nice -n 5 bash) | — | HIGH 8/10 | — | MEDIUM | **ACCEPT** |
| Subshell grouping bypass `(python <<EOF)` | — | — | CRITICAL 9/10 | LOW | **ACCEPT** |
| Preceding heredoc `<<EOF python` | — | — | HIGH 8/10 | LOW | **ACCEPT** |
| String masking `python -c "print('<<')" <<EOF` | — | — | HIGH 8/10 | LOW | **ACCEPT** |
| Missing uncommon interpreters (php, lua, awk) | LOW | HIGH 9/10 | — | LOW | **ACCEPT** |
| False positives (eval/exec heredocs) | — | LOW 4/10 | — | INFO | **ACCEPT** |
| False positive on `<<` in non-heredoc context | — | — | LOW 3/10 | INFO | **ACCEPT** |

## Findings Detail

### FIX: `.` (dot command) not in `_INTERPRETER_COMMANDS` (MEDIUM)
- `. /dev/stdin << EOF` is POSIX equivalent of `source /dev/stdin << EOF`
- `_extract_base_command(". /dev/stdin ")` returns `'.'`
- `'.'` is NOT in `_INTERPRETER_COMMANDS` (only `'source'` is)
- Phase 1 Rule 5 still retains body (unknown → UNSAFE), but Phase 3 backstop misses
- **Fix**: Add `'.'` to `_INTERPRETER_COMMANDS`

### FIX: Versioned interpreters (python3.10, etc.) (MEDIUM)
- `python3.10 << EOF`, `python3.12 << EOF` — exact match fails
- Codex verified: `python3.12 <<EOF` returns `_is_interpreter_heredoc=False`
- Common in AI agent workflows (pyenv, system Python versions)
- **Fix**: Add regex check for versioned variants in `_is_interpreter_heredoc`

### ACCEPT: Prefix flag parsing gap (MEDIUM)
- `nice -n 5 bash <<EOF`, `env -S bash <<EOF`, `time -p bash <<EOF` — only `sudo` gets flag parsing in `_extract_base_command()`
- `_extract_base_command("nice -n 5 bash")` returns `'-n'` not `'bash'`
- Phase 1 Rule 5 still catches it (unknown command → UNSAFE → body retained)
- Fix would require per-prefix flag semantics in shared `_extract_base_command()` — complex, risk of regressions
- **Decision**: Accept. Phase 1 provides primary defense. Document as known limitation.

### ACCEPT: Subshell grouping bypass (LOW)
- `(python << EOF)` — grouping preserved by `split_commands()`, `shlex` fails on `(python`
- Gemini rated 9/10 but this is defense-in-depth, not primary defense
- AI agents don't generate subshell-wrapped heredocs
- Phase 1 Rule 5 retains body, block patterns still scan
- **Decision**: Accept. Per threat model, AI agents generate straightforward code.

### ACCEPT: Preceding heredoc `<<EOF python` (LOW)
- Valid POSIX but unusual syntax
- Phase 1 retains body via Rule 5
- **Decision**: Accept. Non-idiomatic syntax.

### ACCEPT: String masking `python -c "print('<<')" <<EOF` (LOW)
- `.split('<<', 1)` hits the quoted `<<` first, breaks `shlex.split`
- Phase 1 correctly handles it (quote-aware parsing in `split_commands()`)
- **Decision**: Accept. Requires `<<` in argument before heredoc — artificial.

### ACCEPT: Missing uncommon interpreters (LOW)
- php, Rscript, make -f -, lua, awk, sed, tclsh — not in `_INTERPRETER_COMMANDS`
- Phase 1 Rule 5 retains body for all unknown commands
- Not typical in AI agent workflows
- **Decision**: Accept per threat model.

### ACCEPT: False positives (INFO)
- `eval << EOF`, `exec << EOF` — don't execute heredoc body in bash
- `source file << EOF` — ignores heredoc body
- Over-asking is safer than under-asking for defense-in-depth
- Verdict is ASK not DENY — user can approve quickly
- **Decision**: Accept. Consistent with conservative approach.

## V1 Fixes to Apply

1. Add `'.'` to `_INTERPRETER_COMMANDS` frozenset
2. Add versioned interpreter regex check in `_is_interpreter_heredoc()`
3. Add tests for both fixes
4. Document accepted limitations
