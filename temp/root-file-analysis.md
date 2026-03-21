# Root Directory Stray File Analysis

**Date**: 2026-03-21
**Analyzed by**: Automated code audit
**Total stray files**: 76

## Summary Statistics

| Category | Count | Total Size |
|----------|-------|------------|
| scratch (ad-hoc debug/exploration scripts) | 63 | ~118 KB |
| copy (outdated copy of canonical source) | 2 | ~96 KB |
| empty | 3 | 0 B |
| output (captured output) | 1 | 13 B |
| scratch-analysis (design review document) | 1 | ~5.6 KB |

**Recommendation**: All 76 files are safe to delete. None contain unique test logic not already covered by the proper test suite in `tests/`. None use unittest/pytest framework. All Python "test" files are standalone print-and-check scripts.

---

## Detailed File Table

### Python Files -- Source Copies (2 files)

| File | Size | Category | Recommendation | Reason |
|------|------|----------|---------------|--------|
| `bash_guardian.py` | 80,418 B (2,076 lines) | copy | DELETE | Outdated copy of `hooks/scripts/bash_guardian.py` (2,303 lines). Missing ~227 lines of fixes: versioned interpreter regex, V2 sudo flag parsing, `>&3+` redirect hardening, heredoc origin `full_segment`/`is_quoted` fields. 270 diff lines. |
| `split_cmds.py` | 15,993 B (424 lines) | copy | DELETE | Extracted copy of `split_commands()` from an older version of `bash_guardian.py`. Missing V1 heredoc origin `full_segment` finalization and `is_quoted` field. Diverges from canonical. |

### Python Files -- Scratch Scripts (44 files)

All are standalone scripts (no unittest, no TestCase classes, no assertions). They import from `hooks/scripts/` via `sys.path` manipulation, call a single function, and print results. Every scenario they test is covered by the proper test suite.

| File | Size | Category | Recommendation | Reason |
|------|------|----------|---------------|--------|
| `consume.py` | 0 B | empty | DELETE | Empty file. |
| `run_guardian.py` | 969 B | scratch | DELETE | Manual invocation of `bash_guardian.main()` with mocked stdin for a python3 -c path-traversal command. |
| `run_test.py` | 646 B | scratch | DELETE | Tests `_is_interpreter_heredoc()` with various heredoc patterns. Covered by `tests/security/test_interpreter_heredoc.py`. |
| `run_test2.py` | 690 B | scratch | DELETE | Tests `bash_guardian.main()` with mocked stdin for python3 -c file write. Same pattern as `run_guardian.py`. |
| `run_test_no_env.py` | 802 B | scratch | DELETE | Same as `run_test2.py` but tests without `CLAUDE_CODE_DANGEROUSLY_SKIP_PERMISSIONS` env var. |
| `test_ampersand.py` | 628 B | scratch | DELETE | Standalone function testing `&` character classification in shell parsing. Not a real test. |
| `test_braces.py` | 399 B | scratch | DELETE | Tests `_is_interpreter_heredoc()` with brace-group and subshell heredocs. Covered by `tests/security/test_interpreter_heredoc.py`. |
| `test_bracket.py` | 153 B | scratch | DELETE | Tests `split_commands()` with `[[ ]]` inside command substitution. Covered by `tests/core/test_tokenizer_edge_cases.py`. |
| `test_bypass.py` | 897 B | scratch | DELETE | Tests `_is_interpreter_heredoc()` with 12 bypass variants. All covered by `tests/security/test_interpreter_heredoc.py`. |
| `test_bypass1.py` | 378 B | scratch | DELETE | Tests `extract_paths_from_interpreter_payload()` with edge-case paths like `./././`. |
| `test_check_destructive.py` | 650 B | scratch | DELETE | Tests `bash_guardian.main()` with mocked stdin for os.remove. |
| `test_concat.py` | 228 B | scratch | DELETE | Tests `split_commands()` with heredoc delimiter bypass using concat (`\E"O"F`). Covered by heredoc delimiter tests. |
| `test_delimiter.py` | 168 B | scratch | DELETE | Tests `_parse_heredoc_delimiter()` with ANSI-C `$'EOF'` quoting. |
| `test_exploit_bs2.py` | 251 B | scratch | DELETE | Tests `split_commands()` with backslash-appended heredoc delimiter (`EOF\`). |
| `test_extract.py` | 1,033 B | scratch | DELETE | Standalone reimplementation of `_extract_base_command()` with print tests. Covered by `tests/regression/test_heredoc_redaction.py`. |
| `test_extract2.py` | 231 B | scratch | DELETE | Tests `_extract_base_command()` with `<<EOF python` order. Covered by proper suite. |
| `test_f1.py` | 157 B | scratch | DELETE | Tests `check_interpreter_payload()` with a single python3 command. |
| `test_fd_bypass.py` | 528 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against `>&3` and `>&9` fd redirects. |
| `test_fp2.py` | 181 B | scratch | DELETE | Tests `_is_interpreter_heredoc()` with false positive `python script_<<.py`. |
| `test_fstring_bypass.py` | 95 B | scratch | DELETE | Tests `Path("{target_path}").resolve()` -- standalone, not a test of guardian code. |
| `test_guardian_bypass.py` | 339 B | scratch | DELETE | Tests `BashGuardian.analyze()` with ANSI-C heredoc delimiter (`$'\x45OF'`). |
| `test_guardian_bypass2.py` | 267 B | scratch | DELETE | Tests `split_commands()` with ANSI-C heredoc delimiter. Same scenario as above. |
| `test_guardian_bypass3.py` | 267 B | scratch | DELETE | Tests `split_commands()` with `\$'EOF'` delimiter variant. |
| `test_is_write.py` | 206 B | scratch | DELETE | Tests `is_write_command()` with a single python3 command. |
| `test_match.py` | 201 B | scratch | DELETE | Tests `match_block_patterns()` with `cat > script.sh << EOF` + `bash script.sh`. |
| `test_match2.py` | 172 B | scratch | DELETE | Tests `match_block_patterns()` with `bash << EOF` heredoc containing `rm -rf /`. |
| `test_mix.py` | 232 B | scratch | DELETE | Tests `split_commands()` with mixed quoted delimiter (`\E"O"F`). |
| `test_parens.py` | 342 B | scratch | DELETE | Tests `_is_interpreter_heredoc()` inside subshell `(python << EOF)`. |
| `test_parse.py` | 2,337 B | scratch | DELETE | Standalone reimplementation of `_extract_base_command()` with 14 test cases including sudo, env, redirects. All covered by `tests/regression/test_heredoc_redaction.py`. |
| `test_pattern.py` | 516 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against 8 basic redirect cases. |
| `test_pattern2.py` | 439 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against process substitution `> >(bash)` and `>&` to `/dev/tcp`. |
| `test_pattern3.py` | 500 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against `&>>` append redirect. |
| `test_pattern4.py` | 598 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against `{fd}>` brace-fd redirect. |
| `test_pattern5.py` | 488 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against `>&2.sh` (fd vs filename ambiguity). |
| `test_pattern6.py` | 496 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against `>&3` fd dup. |
| `test_redir.py` | 858 B | scratch | DELETE | Tests `_OUTPUT_REDIR_PATTERN` regex against `1<>` read-write redirect. |
| `test_regex.py` | 348 B | scratch | DELETE | Tests a standalone `is_redirect()` function with various redirect tokens. |
| `test_shlex.py` | 361 B | scratch | DELETE | Tests `shlex.split()` behavior with heredoc-style strings. Pure stdlib exploration. |
| `test_shlex2.py` | 138 B | scratch | DELETE | Tests `shlex.split()` with unterminated quotes in heredoc. Pure stdlib exploration. |
| `test_split.py` | 310 B | scratch | DELETE | Tests `split_commands()` with process substitution heredoc and file-writing heredoc. |
| `test_split2.py` | 158 B | scratch | DELETE | Tests `split_commands()` with `bash << EOF` containing `rm -rf /`. |
| `test_stop.py` | 198 B | scratch | DELETE | Tests `_extract_base_command()` with `env FOO=bar python << EOF`. |
| `test_sudo.py` | 1,346 B | scratch | DELETE | Standalone reimplementation of `_extract_base_command()` with sudo flag parsing (V1, pre-noarg-allowlist). Covered by `tests/regression/test_heredoc_redaction.py`. |
| `test_sudo2.py` | 1,401 B | scratch | DELETE | Iteration on sudo parsing with `_sudo_arg_flags` dict. Outdated compared to V2 noarg-allowlist approach. |
| `test_sudo_bypass.py` | 1,305 B | scratch | DELETE | Tests sudo `-p` flag bypass in `_extract_base_command()`. Covered by proper suite's sudo tests. |
| `test_syntax_err.py` | 243 B | scratch | DELETE | Tests `split_commands()` with syntax error (`if [; then ;;`). |
| `test_trailing_bs2.py` | 240 B | scratch | DELETE | Tests `split_commands()` with trailing backslash on heredoc delimiter. Same as `test_exploit_bs2.py`. |
| `test_unterminated.py` | 216 B | scratch | DELETE | Tests `split_commands()` with unterminated heredoc (no closing `EOF`). |
| `test_vars.py` | 235 B | scratch | DELETE | Tests `_is_interpreter_heredoc()` with variable-based commands (`$CMD << EOF`). |

### Shell Files -- Scratch Scripts (22 files)

All are standalone bash snippets used to manually verify how bash handles heredoc edge cases. None are executable test harnesses. They were used during development of heredoc delimiter parsing.

| File | Size | Category | Recommendation | Reason |
|------|------|----------|---------------|--------|
| `test_backslash_space.sh` | 42 B | scratch | DELETE | Tests heredoc with backslash-space in delimiter (`E\ OF`). |
| `test_bash_behavior2.sh` | 318 B | scratch | DELETE | Tests 7 heredoc delimiter quoting variants (`\EOF`, `\\EOF`, `E\OF`, `$'EOF'`, `$'E\nOF'`, `$'E\x4fF'`). |
| `test_bash_bypass3.sh` | 55 B | scratch | DELETE | Tests `\$'EOF'` bypass variant. |
| `test_bash_bypass_4.sh` | 61 B | scratch | DELETE | Same as `test_bash_bypass3.sh` with different body text. |
| `test_bash_heredoc.sh` | 32 B | scratch | DELETE | Tests `$'EOF'` ANSI-C heredoc delimiter (incomplete, no closing). |
| `test_bash_heredoc2.sh` | 86 B | scratch | DELETE | Tests `$'EOF'` and `$"EOF"` heredoc delimiter variants. |
| `test_bash_heredoc3.sh` | 57 B | scratch | DELETE | Tests `$'E\tOF'` heredoc delimiter with tab escape. |
| `test_bash_heredoc4.sh` | 53 B | scratch | DELETE | Tests `\$'EOF'` delimiter (literal dollar sign). |
| `test_bash_mix.sh` | 68 B | scratch | DELETE | Tests mixed quoting in heredoc delimiter (`\E"O"F`). |
| `test_bs.sh` | 71 B | scratch | DELETE | Tests `E\x4fF` (non-ANSI-C context) heredoc delimiter. |
| `test_bypass.sh` | 67 B | scratch | DELETE | Tests heredoc with command substitution in body (`$(echo ...)`). |
| `test_escaped_quotes.sh` | 44 B | scratch | DELETE | Tests heredoc with escaped quote in delimiter (`EO\"F`). |
| `test_exploit.sh` | 53 B | scratch | DELETE | Tests `$'E\x4fF'` ANSI-C bypass (body says "DANGEROUS_COMMAND"). |
| `test_exploit_bs.sh` | 52 B | scratch | DELETE | Tests trailing backslash on heredoc delimiter (`EOF\`). |
| `test_exploit_bypass.sh` | 44 B | scratch | DELETE | Tests `$'E\x4fF'` bypass to inject `touch /tmp/pwned`. |
| `test_inline_quotes.sh` | 41 B | scratch | DELETE | Tests inline single-quote in heredoc delimiter (`E'O'F`). |
| `test_leak.sh` | 45 B | scratch | DELETE | Tests backslash-space delimiter with potential data leak. |
| `test_newline_delim.sh` | 65 B | scratch | DELETE | Tests `$'E\nOF'` (newline in delimiter) heredoc. |
| `test_param_exp.sh` | 68 B | scratch | DELETE | Tests parameter expansion in heredoc delimiter (`$EOF` vs `$'EOF'`). |
| `test_sort.sh` | 9 B | scratch | DELETE | Contains only `rm -rf /` -- obviously a test payload, not real. |
| `test_subshell_heredoc.sh` | 32 B | scratch | DELETE | Tests heredoc inside command substitution `$(cat << DONE ... DONE)`. |
| `test_trailing_bs.sh` | 83 B | scratch | DELETE | Tests trailing backslash behavior on heredoc delimiters. |
| `test_user_scenario.sh` | 52 B | scratch | DELETE | Tests `$'\x45OF'` (hex 45 = 'E') ANSI-C heredoc bypass. |

### Other Files (4 files)

| File | Size | Category | Recommendation | Reason |
|------|------|----------|---------------|--------|
| `output2.txt` | 0 B | empty | DELETE | Empty file. |
| `output3.txt` | 0 B | empty | DELETE | Empty file. |
| `test_out_1.txt` | 13 B | output | DELETE | Contains only "test_content". Captured output from a debug run. |
| `adversarial_review.md` | 5,639 B | scratch-analysis | DELETE | Adversarial review of Round 1 security analysis for heredoc false-positive plans. Historical design discussion. The decisions it influenced have already been implemented. Not referenced by any code or documentation. |

---

## Verdict

### Safe to Delete (76 files -- ALL)

Every file in this list is safe to delete. Rationale:

1. **No unique test coverage**: All test scenarios exercised by these scratch files are already covered by the proper test suite in `tests/security/test_interpreter_heredoc.py`, `tests/regression/test_heredoc_redaction.py`, `tests/core/test_tokenizer_edge_cases.py`, and `tests/core/test_v2fixes.py`.

2. **No unittest framework**: None of the 44 Python test files use `unittest.TestCase`, assertions, or any test framework. They are all print-and-manually-inspect scripts.

3. **Outdated copies**: `bash_guardian.py` and `split_cmds.py` are stale copies missing critical security fixes (V2 sudo parsing, versioned interpreter regex, `>&3+` redirect hardening).

4. **Design doc superseded**: `adversarial_review.md` discusses plans that have already been implemented. The decisions are captured in commit history and the proper action plans.

### Needs Review (0 files)

None. All files are clearly disposable development artifacts.

### Suggested Cleanup Command

```bash
cd /home/idnotbe/projects/claude-code-guardian
rm -f \
  bash_guardian.py consume.py split_cmds.py \
  run_guardian.py run_test.py run_test2.py run_test_no_env.py \
  test_ampersand.py test_braces.py test_bracket.py test_bypass.py test_bypass1.py \
  test_check_destructive.py test_concat.py test_delimiter.py test_exploit_bs2.py \
  test_extract.py test_extract2.py test_f1.py test_fd_bypass.py test_fp2.py \
  test_fstring_bypass.py test_guardian_bypass.py test_guardian_bypass2.py test_guardian_bypass3.py \
  test_is_write.py test_match.py test_match2.py test_mix.py test_parse.py \
  test_pattern.py test_pattern2.py test_pattern3.py test_pattern4.py test_pattern5.py test_pattern6.py \
  test_redir.py test_regex.py test_shlex.py test_shlex2.py test_split.py test_split2.py \
  test_stop.py test_parens.py test_sudo.py test_sudo2.py test_sudo_bypass.py \
  test_syntax_err.py test_trailing_bs2.py test_unterminated.py test_vars.py \
  test_backslash_space.sh test_bash_behavior2.sh test_bash_bypass3.sh test_bash_bypass_4.sh \
  test_bash_heredoc.sh test_bash_heredoc2.sh test_bash_heredoc3.sh test_bash_heredoc4.sh \
  test_bash_mix.sh test_bs.sh test_bypass.sh test_escaped_quotes.sh test_exploit.sh \
  test_exploit_bs.sh test_exploit_bypass.sh test_inline_quotes.sh test_leak.sh \
  test_newline_delim.sh test_param_exp.sh test_sort.sh test_subshell_heredoc.sh \
  test_trailing_bs.sh test_user_scenario.sh \
  output2.txt output3.txt test_out_1.txt \
  adversarial_review.md
```
