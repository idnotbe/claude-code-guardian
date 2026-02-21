# Team Working Memory: Regex Update Fix

## Mission
Fix false-positive issue where Guardian blocks legitimate `--action delete` arguments
by adding command-position anchoring to 10 regex patterns across 4 files.

## Plan File
See: `temp/fix-claude-code-guardian.md` for full specification.

## Files to Change (10 patterns total)
| # | File | Lines | Format | Changes |
|---|------|-------|--------|---------|
| 1 | `assets/guardian.default.json` | ~17,21,25 | JSON (`\\`) | 3 block patterns |
| 2 | `hooks/scripts/_guardian_utils.py` | ~374,378,382 | Python raw (`\`) | 3 fallback patterns |
| 3 | `tests/test_guardian_utils.py` | ~56,58 | Python raw (`\`) | 2 test patterns |
| 4 | `tests/test_guardian.py` | ~98,100 | Python raw (`\`) | 2 test patterns |

## Correct Final Patterns

### JSON format (files 1):
```
"(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)`]|$)"
"(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.claude(?:\\s|/|[;&|)`]|$)"
"(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*_archive(?:\\s|/|[;&|)`]|$)"
```

### Python raw string format (files 2,3,4):
```
r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`]|$)"
r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)"
r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`]|$)"
```

## DO NOT Change
- `bash_guardian.py` `is_delete_command()` (~lines 612-616) - already anchored
- SQL DELETE pattern in `guardian.default.json` (~line 147) - SQL-specific
- `ask` pattern `del\s+` in `guardian.default.json` (~line 91) - safe as-is

## New Test Cases to Add (in test_guardian_utils.py)
```python
# False positive regression: memory_write.py --action delete must NOT be blocked
("python3 memory_write.py --action delete .claude/memory/MEMORY.md", False,
 "delete as argument flag should not trigger block"),
# True positive: standalone delete command MUST be blocked
("delete .claude/config", True,
 "delete as standalone command must be blocked"),
```

## Phase Tracking
- [x] Phase 1: Implementation (implementer) -- COMPLETE
- [x] Phase 2: Test execution (test-runner) -- 627 passed, 0 new failures
- [x] Phase 3: Verification Round 1 (reviewer-regex, reviewer-security) -- PASS
- [x] Phase 4: Verification Round 2 (verifier-final-a, verifier-final-b) -- PASS

## Final Status: ALL PHASES COMPLETE, ALL VERIFICATIONS PASSED

Reports:
- temp/implementation-report.md
- temp/test-results.md
- temp/verification-round1-regex.md (80/80 tests, PASS)
- temp/verification-round1-security.md (66/66 tests, PASS with 2 low-severity future items)
- temp/verification-round2-a.md (54/54 tests, PASS)
- temp/verification-round2-b.md (32/32 tests, PASS)

Low-severity future hardening items noted:
1. Leading whitespace: `  rm .claude/` not caught (add `^\s*` to anchor)
2. Brace groups: `{ rm .claude/; }` not caught (add `{` to separator class)
3. Quoted paths: `rm ".claude"` not caught (add quotes to terminator)
All 3 are pre-existing gaps mitigated by defense-in-depth (scan_protected_paths)
