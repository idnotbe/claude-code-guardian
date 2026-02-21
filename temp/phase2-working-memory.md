# Phase 2 Working Memory: Low-Severity Hardening + Ops Config Update

## Mission
1. Harden 3 low-severity gaps in claude-code-guardian regex patterns
2. Update ops custom config to match the fully hardened patterns

## Three Hardening Changes

### Fix 1: Leading whitespace (`  rm .claude/` not caught)
- **Change**: `(?:^|` → `(?:^\s*|`
- Adds optional whitespace after start-of-string anchor

### Fix 2: Brace group (`{ rm .claude/; }` not caught)
- **Change**: `[;|&` + backtick + `(]` → `[;|&` + backtick + `({]`
- Adds `{` to separator class

### Fix 3: Quoted paths (`rm ".claude"` not caught)
- **Change**: `[;&|)` + backtick + `]` → `[;&|)` + backtick + `'\"  ]`
- Adds `'` and `"` to terminator class

## Final Hardened Patterns

### JSON format (for .json files):

**.git pattern:**
```
"(?i)(?:^\\s*|[;|&`({]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)`'\"]|$)"
```

**.claude pattern:**
```
"(?i)(?:^\\s*|[;|&`({]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.claude(?:\\s|/|[;&|)`'\"]|$)"
```

**_archive pattern:**
```
"(?i)(?:^\\s*|[;|&`({]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*_archive(?:\\s|/|[;&|)`'\"]|$)"
```

### Python raw string format (for .py files):

**.git pattern:**
```
r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`'\"]|$)"
```

**.claude pattern:**
```
r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`'\"]|$)"
```

**_archive pattern:**
```
r"(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`'\"]|$)"
```

## Files to Change

### claude-code-guardian (10 patterns - hardening only)
| # | File | Lines | Format |
|---|------|-------|--------|
| 1-3 | `assets/guardian.default.json` | ~17,21,25 | JSON (`\\`) |
| 4-6 | `hooks/scripts/_guardian_utils.py` | ~374,378,382 | Python raw (`\`) |
| 7-8 | `tests/test_guardian_utils.py` | ~56,58 | Python raw (`\`) |
| 9-10 | `tests/test_guardian.py` | ~98,100 | Python raw (`\`) |

### ops (3 patterns - full update from OLD to fully hardened)
| # | File | Lines | Format |
|---|------|-------|--------|
| 11-13 | `/home/idnotbe/projects/ops/.claude/guardian/config.json` | ~18,22,26 | JSON (`\\`) |

## Current → New Pattern Diffs

### claude-code-guardian files (currently have anchored pattern from Phase 1):
**Current anchor**: `(?:^|[;|&` + backtick + `(]\s*)`
**New anchor**: `(?:^\s*|[;|&` + backtick + `({]\s*)`

**Current terminator**: `(?:\s|/|[;&|)` + backtick + `]|$)`
**New terminator**: `(?:\s|/|[;&|)` + backtick + `'\"  ]|$)`

### ops config (currently has OLD pattern with NO anchoring):
**Current**: `(?i)(?:rm|rmdir|del|remove-item).*\\.git(?:\\s|/|$)`
**New**: `(?i)(?:^\\s*|[;|&` + backtick + `({]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)` + backtick + `'\"]|$)`

## New Test Cases to Add

### Leading whitespace tests:
```python
("  rm .claude/config", True, "leading spaces before rm must be blocked"),
("\trm .claude/config", True, "leading tab before rm must be blocked"),
```

### Brace group tests:
```python
("{ rm .claude/x; }", True, "brace group rm must be blocked"),
```

### Quoted path tests:
```python
('rm ".claude/config"', True, "quoted path must be blocked"),
("rm '.claude/config'", True, "single-quoted path must be blocked"),
```

## DO NOT CHANGE
- `bash_guardian.py` `is_delete_command()` - already anchored differently
- SQL DELETE pattern - SQL-specific
- `del\s+` ask pattern - safe as-is

## Phase Tracking
- [x] Task 1: Apply 3 hardening fixes to 10 patterns (implementer-guardian) -- COMPLETE
- [x] Task 2: Update ops config.json (implementer-ops) -- COMPLETE
- [x] Task 3: Run test suite and validate (test-runner) -- 934 tests, 0 regressions
- [x] Task 4: Verification Round 1 (reviewer-regex, reviewer-security) -- PASS
- [x] Task 5: Verification Round 2 (verifier-final-a, verifier-final-b) -- PASS

## Final Status: ALL PHASES COMPLETE, ALL VERIFICATIONS PASSED

Reports:
- temp/phase2-implementation-report.md
- temp/phase2-ops-update-report.md
- temp/phase2-test-results.md
- temp/phase2-verification-round1-regex.md (106 tests, PASS)
- temp/phase2-verification-round1-security.md (20 targeted + red-team, PASS)
- temp/phase2-verification-round2-a.md (121 tests, PASS)
- temp/phase2-verification-round2-b.md (54 tests, PASS)

Minor finding (non-blocking):
- Python raw strings have `\"` in terminator which adds literal `\` to char class (fail-closed, slightly stricter than JSON version). Low-priority cleanup for future.

Pre-existing gaps noted for future work:
- Command prefix bypasses: `sudo rm`, `env rm`, `command rm` (MEDIUM)
- Shell concatenation: `rm .cl''aude` (MEDIUM)
- Redirection chars `>`, `<` not in terminator (LOW)
- All mitigated by defense-in-depth (scan_protected_paths, split_commands)
