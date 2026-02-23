# Guardian Fixes - Team Master Plan

## Objective
Fix all identified issues from the heredoc verification:
1. Polish the 3 deviations (already improvements, need to be first-class)
2. Fix 3 pre-existing `ln` pattern test failures
3. Fix 15 pre-existing `test_bypass_v2.py` failures

## Work Streams

### Stream A: Deviations Polish
Formalize the 3 deviations as proper, documented, tested features.
- Deviation 1: Regex `[^|&;>]+` in `is_write_command()` — add test proving it's needed
- Deviation 2: Comment tracking in `split_commands()` — review for edge cases
- Deviation 3: Extra tests — ensure comprehensive coverage
- Also address Codex finding: comment text still in `sub_commands` for Layer 1 scan (false positive risk with `# .env`)

### Stream B: ln Pattern Test Fixes
Fix 3 test assertions that look for `\bln\s+` but code uses `(?<![A-Za-z-])ln\s+`:
- `tests/core/test_v2fixes.py::TestF2_LnWritePattern::test_ln_pattern_in_source`
- `tests/security/test_v2_adversarial.py::TestP1_4_MetadataBypass::test_ln_symlink_not_detected`
- `tests/security/test_v2_adversarial.py::TestKnownGaps::test_ln_symlink_gap`

### Stream C: Tokenizer Improvements (7 failures)
Fix `split_commands()` to handle:
1. `${VAR:-;}` — parameter expansion with `;`
2. `${VAR//a|b/c}` — parameter expansion with `|`
3. `(cd /tmp; ls)` — bare subshell (NOT `$()`)
4. `{echo a; echo b;}` — brace group
5. `!(*.txt|*.md)` — extglob
6. `[[ regex | ]]` — conditional expression
7. `(( x & y ))` — arithmetic `&` (already partially handled)

### Stream D: Scan/Detection Improvements (8 failures)
Fix scan bypasses:
1. `cat .en[v]` — character class glob bypass
2. `cat .en?` — question mark glob bypass
3. `cat $'\x2e\x65\x6e\x76'` — hex-encoded .env bypass

Fix write/delete detection:
4. `chmod 777 poetry.lock` — read-only enforcement
5. `chown user poetry.lock` — read-only enforcement
6. `touch poetry.lock` — read-only enforcement
7. `> CLAUDE.md` — truncation as delete
8. `git rm CLAUDE.md` — git rm detection

## Files

| File | Purpose |
|------|---------|
| `temp/task-a-deviations.md` | Detailed spec for Stream A |
| `temp/task-b-ln-tests.md` | Detailed spec for Stream B |
| `temp/task-c-tokenizer.md` | Detailed spec for Stream C |
| `temp/task-d-detection.md` | Detailed spec for Stream D |
| `temp/verification-round1.md` | Round 1 verification results |
| `temp/verification-round2.md` | Round 2 verification results |

## Key Source Files
- `hooks/scripts/bash_guardian.py` — Main implementation (1421 lines)
- `hooks/scripts/_guardian_utils.py` — Shared utilities
- `tests/test_heredoc_fixes.py` — Heredoc fix tests
- `tests/core/test_v2fixes.py` — V2 fix tests
- `tests/security/test_v2_adversarial.py` — Adversarial security tests
- `tests/security/test_bypass_v2.py` — Standalone bypass tests

## Rules
- Every code change must have corresponding test
- All existing tests must continue to pass
- Security changes must fail-closed
- Use vibe-check at important decision points
- Use pal clink (codex + gemini) for second opinions
- File-based communication between teammates
