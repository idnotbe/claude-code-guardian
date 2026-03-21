# Round 1 Synthesis

## Unanimous Findings Across All 3 Analysts + 2 External Models (Codex, Gemini)

### Plan A: Heredoc False Positives — FAIL (NOT SHIPPABLE)

**CRITICAL Issues:**
1. **Per-sub-command Layer 0/0b breaks curl|bash** — `split_commands()` splits on `|`, so pipeline-spanning block patterns never match. Regression from DENY to ALLOW for remote script execution.
2. **Pipe-to-interpreter mitigation broken** — `split_commands()` splits `cat << EOF | bash` on `|` BEFORE the newline handler, so `cmd_so_far` is `"bash"` not `"cat << EOF | bash"`. The pipe check never fires.
3. **Generated executable bypass** (Gemini unique): `cat << 'EOF' > run.sh\nrm -rf /\nEOF\nbash run.sh` — body stripped because cat is data, then script executed blindly.

**HIGH Issues:**
4. `_is_data_heredoc_command()` returns `True` (fail-OPEN) when no `<<` found
5. Subsumption claim fails: `[^|&\n]*` in block patterns stops at newlines, `re.MULTILINE` flag missing
6. ANSI-C quoting (`$'EOF'`, `$"EOF"`) not handled in `_parse_heredoc_delimiter()`
7. Stale tests (mysql/psql still tested as allowlisted but were removed)

**CONSENSUS ALTERNATIVE:** Keep Layer 0/0b scanning the raw command. Build a "heredoc-redacted" version that replaces ONLY safe heredoc bodies with empty strings, preserving all operators. Run redacted string through Layer 0/0b.

### Plan B: Interpreter Path Resolution — FAIL (NOT SHIPPABLE)

**HIGH Issues:**
1. **Decoy literal suppresses F1** — ANY string containing `/` (URLs, MIME types, format strings) can populate `interpreter_paths`, suppressing the fail-closed safety net. Not just a "decoy attack" — ordinary code routinely contains such strings.
2. **Regex insufficient** — f-strings, triple-quotes, pathlib patterns all fail. AI agents commonly generate these.
3. **glob.glob() DoS/oracle** — unbounded filesystem probing on attacker-controlled input.

**CONSENSUS ALTERNATIVE:** Don't implement Plan B as written. Instead:
1. Improve F1 ASK message quality (show detected API + payload excerpt)
2. System prompt guidance for agents to use CLI tools
3. If still needed, narrow Python-only AST recognizer (Phase 2) that proves source-to-sink binding

### Paradigm Insights (Cross-Model)
- **Alert fatigue is a security failure** — excessive ASKs condition auto-allow behavior
- **Heredoc classification**: Hybrid model — small allowlist of proven passive data sinks + blocklist of known interpreters + fail-closed for unknown
- **write-to-file case** (cat > script.sh) needs special handling in ANY paradigm — both models identify this as the most dangerous edge case
- **Codex unique**: Sink capability taxonomy (passive_data_sink, write_sink, exec_sink, unknown_sink)
- **Gemini unique**: Host OS vs. Domain Execution framing

### Pre-existing Bugs Discovered
1. Missing `re.MULTILINE` in `match_block_patterns()` — `$` anchor only matches end-of-string, not end-of-line
2. `_parse_heredoc_delimiter()` doesn't handle ANSI-C quoting (`$'EOF'`, `$"EOF"`)
3. Backslash-escaped delimiter parsing (already in Plan A as P0, valid)
