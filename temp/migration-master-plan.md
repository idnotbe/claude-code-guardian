# Test Vector Migration - Master Plan

## Goal
Create proper unittest test files covering the ~30+ unique test vectors identified by
code-reviewer and security-reviewer that had no equivalent in the organized test suite.

## Source Material
The original files were untracked and permanently deleted. We reconstruct from:
- `/home/idnotbe/projects/claude-code-guardian/temp/analysis-py-files.md` (py-analyst's detailed analysis)
- `/home/idnotbe/projects/claude-code-guardian/temp/analysis-sh-files.md` (sh-analyst's detailed analysis)
- `/home/idnotbe/projects/claude-code-guardian/temp/review-code-quality.md` (code-reviewer's gap analysis)
- `/home/idnotbe/projects/claude-code-guardian/temp/review-security.md` (security-reviewer's gap analysis)
- Subagent analysis results captured in conversation context

## Test Files to Create

### 1. tests/core/test_decoder_glob.py
Direct unit tests for internal functions:
- `_decode_ansi_c_strings()`: hex, octal (with/without leading 0), unicode 16/32-bit, control chars, mixed
- `_expand_glob_chars()`: single-char brackets, negated classes, ranges, escaped chars
- Piecewise ANSI-C concatenation: `$'\x2e'$'\x65'$'\x6e'$'\x76'`

### 2. tests/core/test_tokenizer_edge_cases.py
Tokenizer boundary conditions and depth tracking:
- Empty input, whitespace, lone operators (`;`, `&`, `|`)
- Very long input (10K chars)
- Nested construct depth: `${VAR:-$(echo;echo)}`, `${arr[$((i+1))]}`
- Depth tracking attacks: `${x:-$(echo })}; rm .env`
- Brace group detection: `{ rm -rf /; echo done; }`
- Feature interactions: extglob+conditional, arithmetic+param expansion

### 3. tests/security/test_bypass_vectors_extended.py
Extended bypass vectors:
- `bash -c "rm -rf .git"` wrapper pattern
- Heredoc + unclosed quotes + redirect interaction
- Obfuscation: ANSI-C unicode, hex single-char, escaped glob bracket
- Scan false positive prevention: all-? tokens, pattern matching
- Security bypass via new features

### 4. Add to tests/test_heredoc_fixes.py (or new file)
Heredoc edge cases from shell files:
- Quote concat delimiter: `E"O"F`, `'EOF'Z`
- Backslash-escaped delimiter: `\EOF`
- Empty string delimiter: `''`
- Backslash-space delimiter: `\ `
- Piped multiple heredocs: `<<EOF | <<EOF2`
- Pipeline+heredoc interleave
- Process substitution + heredoc nesting
- `)` in heredoc body inside `<()` (depth confusion)
- Depth corruption: `((((` in heredoc body
- `$()` with `)` in heredoc body
- `<<-` space vs tab indentation

## Team Structure

### Phase 1: Implementation (3 parallel implementers)
- **impl-decoder**: Creates tests/core/test_decoder_glob.py
- **impl-tokenizer**: Creates tests/core/test_tokenizer_edge_cases.py
- **impl-security**: Creates tests/security/test_bypass_vectors_extended.py + heredoc additions

### Phase 2: Review (2 parallel reviewers)
- **review-quality**: Code quality and test correctness review
- **review-security**: Security coverage completeness review

### Phase 3: Verification Round 1 (2 parallel verifiers)
- **verify-1a**: Run tests + check coverage from code perspective
- **verify-1b**: Run tests + check coverage from security perspective

### Phase 4: Verification Round 2 (2 parallel verifiers)
- **verify-2a**: Fresh perspective verification
- **verify-2b**: Safety/completeness verification

## Status: IN PROGRESS
- [ ] Phase 1: Implementation
- [ ] Phase 2: Review
- [ ] Phase 3: Verification Round 1
- [ ] Phase 4: Verification Round 2
