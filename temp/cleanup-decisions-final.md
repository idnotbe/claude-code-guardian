# Root Test File Cleanup - FINAL DECISIONS

## Decision: DELETE ALL 60+ root test files

### Validation Sources
1. **Internal Analysis**: Read all 60+ files. All are scratch scripts (4-55 lines, no assertions, no unittest/pytest classes)
2. **Vibe Check**: Approved "delete all", flagged uniformity bias but confirmed after review
3. **Gemini CLI Review**: Strong agreement. Additionally found that tests/_archive/ already breaks pytest (sys.exit in test_p1_fixes.py, def test() in test_bypass_v2.py). Recommends NOT moving any files to _archive.

### Key Rationale
- All 60+ files are development exploration artifacts, not test infrastructure
- Organized tests/ has 17,148 lines, ~1,045 test methods covering all scenarios
- Unasserted scratch scripts provide zero regression protection
- Git history preserves all content if ever needed
- Moving to _archive would risk breaking pytest (confirmed by Gemini)

---

## Files to Delete

### Python (37 files):
test_parser.py test_parser2.py test_parser3.py test_heredoc_bypass.py
test_heredoc_bypass_review.py test_heredoc_bypass_top.py test_del.py
test_scan.py test_scan2.py test_eval_regex.py test_sub.py test_bg.py
test_bypass.py test_bypass_old.py test_bypass2.py test_bypass3.py
test_bypass4.py test_comment.py test_regex.py test_regex2.py
test_regex_rm.py test_rm_regex.py test_rm.py test_clobber.py
test_extract.py test_arithmetic.py test_ansi.py test_bracket.py
test_brace.py test_empty_quotes.py test_piecewise.py test_crontab_regex.py
test_git_regex.py test_git.py test_git_clean.py test_chmod.py test_chmod_2.py

### Shell (23 files):
test_script.sh test_heredoc_quote.sh test_heredoc_bs.sh test_empty_delim.sh
test_bs_space.sh test_multiple_heredocs.sh test_pipeline_heredoc.sh
test_pipeline_heredoc2.sh test_pipeline_heredoc3.sh test_pipeline_cat.sh
test_pipeline_cat2.sh test_proc_sub.sh test_unmatched_paren.sh
test_depth_bypass.sh test_comment_bash.sh test_depth_heredoc.sh
test_bash_heredoc.sh test_bash_heredoc2.sh test_bash_syntax.sh
test_bash_sync.sh test_quote_concat.sh test_quote_concat_bg.sh test_bypass.sh

### Other:
- temp/test_edge_cases_v1.py
- test_project/ (recursive delete)
- test_redirect.txt

## NOT in scope (separate concern):
- Files inside tests/ directory (tests/test_guardian*.py, tests/test_heredoc_fixes.py etc.) — internal organization is a separate task
