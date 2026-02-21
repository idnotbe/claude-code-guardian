# Team Plan: Guardian Regex Fix

## Task Summary
Fix false-positive regex patterns in claude-code-guardian where `del` matches as a substring inside `delete` in command arguments (e.g., `--action delete .claude/memory/X`).

## Files to Change (10 pattern updates across 4 files)

| File | Changes | Format |
|------|---------|--------|
| `assets/guardian.default.json` | 3 block patterns (lines 17, 21, 25) | JSON (`\\`) |
| `hooks/scripts/_guardian_utils.py` | 3 fallback patterns (lines 374, 378, 382) | Python raw (`\`) |
| `tests/test_guardian_utils.py` | 2 test patterns (lines 56, 58) | Python raw (`\`) |
| `tests/test_guardian.py` | 2 test patterns (lines 98, 100) | Python raw (`\`) |

## New Pattern (human-readable)
```
(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.TARGET(?:\s|/|[;&|)`]|$)
```

Key changes:
1. Command-position anchoring: `(?:^|[;|&`(]\s*)`
2. Added `delete`, `deletion`, `remove-item` to alternation
3. Added `\b` word boundary after alternation
4. Changed `.*` to `\s+.*` (require space after command)
5. Enhanced trailing anchor: `(?:\s|/|[;&|)`]|$)`

## Do NOT Change
- `bash_guardian.py` `is_delete_command()` - already properly anchored
- SQL DELETE pattern in guardian.default.json - SQL-specific, no collision
- `ask` pattern `del\s+` in guardian.default.json - already safe (requires whitespace after `del`)

## Team Structure

### Phase 1: Implementation
- **implementer**: Apply all 10 pattern changes + add new test cases
- **regex-reviewer**: Review regex correctness, escaping, edge cases

### Phase 2: Verification Round 1
- **correctness-verifier**: Verify all patterns match fix doc exactly, check escaping
- **edge-case-verifier**: Test false positive/negative edge cases

### Phase 3: Verification Round 2
- **functional-verifier**: Run pytest, functional verification
- **integration-verifier**: End-to-end integration, security perspective

## Verification Test Cases

### Must NOT be blocked (false positives):
- `python3 memory_write.py --action delete .claude/memory/MEMORY.md`
- `python3 memory_write.py --action delete --path .claude/memory/X`
- `python3 mem.py --action retire .claude/memory/sessions/foo.json`
- `echo "deletion" | grep .claude`
- `some-tool --model .claude/config`
- `cat .claude/memory/MEMORY.md`
- `ls .claude/memory/`

### MUST be blocked (true positives):
- `rm -rf .claude/`
- `rm .claude/memory/X`
- `del .claude/config`
- `delete .claude/config`
- `rmdir .claude/memory`
- `echo hello; rm .claude/x`
- `echo hello && del .claude/x`
- `(rm .claude/x)`
