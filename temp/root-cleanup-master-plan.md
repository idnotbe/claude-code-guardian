# Root Test File Cleanup - Master Plan

## Scope
60+ test files (37 .py, 23+ .sh) scattered in project root that need to be either:
- **Deleted**: if they are scratch/one-off files superseded by organized tests
- **Moved to tests/**: if they contain valuable test cases not covered elsewhere
- **Archived**: if they have historical value but shouldn't be in root

## Root Files to Process

### Python files (37):
test_parser.py, test_heredoc_bypass.py, test_parser2.py, test_parser3.py,
test_heredoc_bypass_review.py, test_del.py, test_heredoc_bypass_top.py,
test_scan.py, test_eval_regex.py, test_sub.py, test_scan2.py, test_bg.py,
test_bypass_old.py, test_bypass2.py, test_bypass3.py, test_comment.py,
test_regex2.py, test_bypass4.py, test_arithmetic.py, test_regex_rm.py,
test_regex.py, test_clobber.py, test_bypass.py, test_extract.py,
test_ansi.py, test_bracket.py, test_empty_quotes.py, test_brace.py,
test_piecewise.py, test_crontab_regex.py, test_git_regex.py, test_rm_regex.py,
test_chmod.py, test_git.py, test_git_clean.py, test_chmod_2.py, test_rm.py

### Shell files (23+):
test_script.sh, test_heredoc_quote.sh, test_heredoc_bs.sh, test_empty_delim.sh,
test_bs_space.sh, test_multiple_heredocs.sh, test_pipeline_heredoc.sh,
test_pipeline_heredoc2.sh, test_pipeline_heredoc3.sh, test_pipeline_cat.sh,
test_pipeline_cat2.sh, test_proc_sub.sh, test_unmatched_paren.sh,
test_depth_bypass.sh, test_comment_bash.sh, test_depth_heredoc.sh,
test_bash_heredoc.sh, test_bash_heredoc2.sh, test_bash_syntax.sh,
test_bash_sync.sh, test_quote_concat.sh, test_quote_concat_bg.sh, test_bypass.sh

### Other:
- temp/test_edge_cases_v1.py
- test_project/ (directory)
- test_redirect.txt

## Team Structure

### Phase 1: Analysis (parallel)
- **py-analyst**: Read all Python test files, categorize, check overlap with tests/
- **sh-analyst**: Read all Shell test files, categorize, check overlap with tests/
- **structure-analyst**: Map existing tests/ structure, identify gaps and overlaps

### Phase 2: Decision & Review (parallel reviewers)
- **Team Lead**: Synthesize analysis into draft decisions
- **code-reviewer**: Review from code quality/testing perspective
- **security-reviewer**: Review from security/coverage perspective

### Phase 3: Execution
- **executor**: Execute approved file operations

### Phase 4: Verification Round 1 (parallel)
- **verifier-1a**: Verify from code completeness perspective
- **verifier-1b**: Verify from structural correctness perspective

### Phase 5: Verification Round 2 (parallel)
- **verifier-2a**: Verify from different angle
- **verifier-2b**: Verify from safety/no-data-loss perspective

## Status: IN PROGRESS
- [x] Plan created
- [ ] Phase 1: Analysis
- [ ] Phase 2: Decision & Review
- [ ] Phase 3: Execution
- [ ] Phase 4: Verification Round 1
- [ ] Phase 5: Verification Round 2
