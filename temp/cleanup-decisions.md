# Root Test File Cleanup - Decision Document

## Executive Summary

All 60+ root test files are **scratch/exploration scripts** created during development.
None are proper unittest/pytest classes. The organized `tests/` directory already contains
comprehensive coverage (17,148 lines, ~1,045 test methods across 45 files).

**Recommendation: DELETE ALL root test files.**

No files need to be moved to `tests/` — the coverage is already there.

---

## Detailed Decisions

### Python Files (37 files) — ALL DELETE

| File | Lines | What It Tests | Why Delete |
|------|-------|---------------|------------|
| test_parser.py | 49 | Heredoc parser prototype | Scratch prototype; parsing covered by core/security suites |
| test_parser2.py | 48 | Enhanced parser prototype | Scratch prototype; superseded |
| test_parser3.py | 49 | Parser with quote handling | Scratch prototype; superseded |
| test_heredoc_bypass.py | 18 | split_commands() heredoc bypass | Covered by tests/security/test_v2_adversarial.py, test_bypass_v2.py |
| test_heredoc_bypass_review.py | 30 | eval/source/bash-c heredoc | Covered by security suite |
| test_heredoc_bypass_top.py | 35 | Top-level heredoc detection | Covered by security suite |
| test_del.py | 6 | is_delete_command() | Covered by core/test_p0p1_comprehensive.py |
| test_scan.py | 7 | scan_protected_paths() | Covered by core suite |
| test_scan2.py | 7 | AWS credentials scanning | Covered by core suite |
| test_eval_regex.py | 5 | eval+rm regex | Covered by core/security suites |
| test_sub.py | 6 | extract_paths() with $() | Covered by core suite |
| test_bg.py | 6 | split_commands() file reader | Scratch script |
| test_bypass.py | 10 | Redirect >& detection | Covered by security suite |
| test_bypass_old.py | 44 | Old split logic comparison | Historical; superseded by v2 tests |
| test_bypass2.py | 5 | Quote in cmd substitution | Covered by security suite |
| test_bypass3.py | 13 | Heredoc + unclosed quotes | Covered by security suite |
| test_bypass4.py | 9 | Heredoc delimiter confusion | Covered by security suite |
| test_comment.py | 6 | Comment handling | Covered by core suite |
| test_regex.py | 17 | Redirection regex patterns | Covered by patterns/ verify scripts |
| test_regex2.py | 14 | Heredoc .env delimiter | Covered by core suite |
| test_regex_rm.py | 12 | Redirect regex with lookbehind | Covered by patterns/ |
| test_rm_regex.py | 9 | rm -rf / regex | Covered by core/security suites |
| test_rm.py | 11 | rm with various flags regex | Covered by core suite |
| test_clobber.py | 7 | >| clobber operator | Covered by core suite |
| test_extract.py | 7 | extract_redirection_targets() | Covered by core suite |
| test_arithmetic.py | 4 | $(( )) vs << parsing | Covered by core suite |
| test_ansi.py | 55 | ANSI-C string decoding | Covered by usability/test_edge_cases.py |
| test_bracket.py | 10 | Glob [x] expansion | Covered by core suite |
| test_brace.py | 9 | Brace expansion scanning | Covered by core suite |
| test_empty_quotes.py | 22 | 8 obfuscation techniques | Covered by security/adversarial suites |
| test_piecewise.py | 9 | Piecewise ANSI-C decoding | Covered by core suite |
| test_crontab_regex.py | 23 | crontab command regex | Covered by patterns/ |
| test_git_regex.py | 11 | git push --force regex | Covered by patterns/ |
| test_git.py | 11 | git push force variants | Covered by patterns/ |
| test_git_clean.py | 9 | git clean flags regex | Covered by patterns/ |
| test_chmod.py | 11 | chmod 777 regex | Covered by patterns/ |
| test_chmod_2.py | 11 | chmod 0777 regex | Covered by patterns/ |

### Shell Files (23 files) — ALL DELETE

| File | Lines | What It Tests | Why Delete |
|------|-------|---------------|------------|
| test_script.sh | 7 | Nested arithmetic + heredoc | No assertions; scratch exploration |
| test_heredoc_quote.sh | 5 | Quoted heredoc delimiter | No assertions; edge case covered by Python tests |
| test_heredoc_bs.sh | 5 | Backslash-escaped delimiter | No assertions; covered |
| test_empty_delim.sh | 7 | Empty string delimiter | No assertions; edge case |
| test_bs_space.sh | 5 | Backslash-space delimiter | No assertions; edge case |
| test_multiple_heredocs.sh | 7 | Chained heredocs in pipe | No assertions; covered |
| test_pipeline_heredoc.sh | 6 | Heredoc in pipeline | No assertions; covered |
| test_pipeline_heredoc2.sh | 6 | Duplicate of above | Exact duplicate |
| test_pipeline_heredoc3.sh | 6 | Pipeline heredoc variant | No assertions; covered |
| test_pipeline_cat.sh | 6 | Heredoc piped to cat | No assertions; covered |
| test_pipeline_cat2.sh | 6 | Heredoc pipe variant | No assertions; covered |
| test_proc_sub.sh | 9 | Process substitution heredoc | No assertions; covered |
| test_unmatched_paren.sh | 6 | Unmatched paren delimiter | No assertions; edge case |
| test_depth_bypass.sh | 6 | Nested parens bypass | No assertions; covered by security tests |
| test_comment_bash.sh | 5 | Heredoc in comments | No assertions; covered |
| test_depth_heredoc.sh | 8 | Nested cmd sub + heredoc | No assertions; covered |
| test_bash_heredoc.sh | 4 | Basic heredoc | No assertions; trivial |
| test_bash_heredoc2.sh | 5 | Backslash in delimiter | No assertions; edge case |
| test_bash_syntax.sh | 3 | Arithmetic expansion | No assertions; trivial |
| test_bash_sync.sh | 4 | <<- tab-trim operator | No assertions; covered |
| test_quote_concat.sh | 5 | Quote concat delimiter | No assertions; edge case |
| test_quote_concat_bg.sh | 5 | Duplicate of above | Exact duplicate |
| test_bypass.sh | 5 | Heredoc in comment bypass | No assertions; covered |

### Other Files — ALL DELETE

| File | Why Delete |
|------|------------|
| temp/test_edge_cases_v1.py (301 lines) | Verification script; edge cases fully covered by core/security/usability suites |
| test_project/ (directory) | Scratch sandbox with own .git; testing artifact |
| test_redirect.txt | Trivial artifact ("hello") |

---

## Important Notes

### Files NOT being deleted (in tests/ root, not project root):
These are inside tests/ and are a separate concern:
- tests/test_guardian.py (502 lines) — Phase 5 integration tests, unique
- tests/test_guardian_utils.py (822 lines) — Unit tests for utils, unique
- tests/test_guardian_p0p1_comprehensive.py — Possible duplicate of core/ version
- tests/test_guardian_v2fixes.py — Possible duplicate of core/ version
- tests/test_guardian_v2fixes_adversarial.py — Possible duplicate of security/ version
- tests/test_heredoc_fixes.py — Unique heredoc-specific tests

### Risk Assessment
- **Risk of losing test coverage: NONE** — All scenarios are covered by organized tests
- **Risk of losing scratch code insights: MINIMAL** — Patterns are already incorporated
- **Reversibility: FULL** — All files are in git history
