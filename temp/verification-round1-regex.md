# Verification Round 1: Regex Correctness Review

**Reviewer**: reviewer-regex
**Date**: 2026-02-18
**Verdict**: PASS -- All 10 pattern changes are correct.

---

## Methodology

1. Read all 4 changed source files and extracted the exact 10 patterns
2. Verified escaping correctness (JSON doubled backslashes vs Python raw string single backslashes)
3. Verified regex structural components against the spec
4. Ran 80 programmatic test cases via `temp/verify_regex.py`
5. Verified DO NOT CHANGE items were not modified
6. Obtained external review from Gemini CLI (Codex CLI unavailable due to usage limit)
7. Investigated Gemini's quoted-path finding to determine if it is a regression

---

## 1. Pattern Extraction and Compilation (10/10 PASS)

All 10 patterns were extracted and compile without errors:

| # | File | Target | Compiles |
|---|------|--------|----------|
| 1 | `assets/guardian.default.json:17` | .git | PASS |
| 2 | `assets/guardian.default.json:21` | .claude | PASS |
| 3 | `assets/guardian.default.json:25` | _archive | PASS |
| 4 | `hooks/scripts/_guardian_utils.py:374` | .git | PASS |
| 5 | `hooks/scripts/_guardian_utils.py:378` | .claude | PASS |
| 6 | `hooks/scripts/_guardian_utils.py:382` | _archive | PASS |
| 7 | `tests/test_guardian_utils.py:56` | .git | PASS |
| 8 | `tests/test_guardian_utils.py:58` | .claude | PASS |
| 9 | `tests/test_guardian.py:98` | .git | PASS |
| 10 | `tests/test_guardian.py:100` | _archive | PASS |

---

## 2. Escaping Verification

### JSON file (`guardian.default.json`)
All backslashes are properly doubled in the JSON source:
- Line 17 (.git): 5 escaped sequences `\\s`, `\\b`, `\\s`, `\\.`, `\\s` -- CORRECT
- Line 21 (.claude): 5 escaped sequences `\\s`, `\\b`, `\\s`, `\\.`, `\\s` -- CORRECT
- Line 25 (_archive): 4 escaped sequences `\\s`, `\\b`, `\\s`, `\\s` -- CORRECT (no `\\.` needed for `_archive`)
- JSON file validates with `json.load()` -- CORRECT

### Python files (`_guardian_utils.py`, `test_guardian_utils.py`, `test_guardian.py`)
All use raw strings (`r"..."`) with single backslashes -- CORRECT

---

## 3. Cross-File Pattern Consistency (3/3 PASS)

After JSON decoding, all patterns targeting the same path are byte-identical across files:
- All 4 `.git` patterns (json, utils, test_utils, test_guard): IDENTICAL
- All 3 `.claude` patterns (json, utils, test_utils): IDENTICAL
- All 3 `_archive` patterns (json, utils, test_guard): IDENTICAL

---

## 4. Regex Structure Verification (9/9 PASS)

Using the `.claude` pattern as reference:
```
(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)
```

| Component | Expected | Found | Status |
|-----------|----------|-------|--------|
| `(?i)` case-insensitive flag | Yes | Yes | PASS |
| `(?:^\|[;\|&\`(]\\s*)` command-position anchor | Yes | Yes | PASS |
| `(?:rm\|rmdir\|del\|delete\|deletion\|remove-item)` full alternation | Yes | Yes | PASS |
| `\\b` word boundary after alternation | Yes | Yes | PASS |
| `\\s+` required whitespace | Yes | Yes | PASS |
| `.*` any-chars bridge | Yes | Yes | PASS |
| `\\.claude` literal dot target | Yes | Yes | PASS |
| `(?:\\s\|/\|[;&\|)\`]\|$)` enriched terminator | Yes | Yes | PASS |
| Anchor class does NOT include `\\s` | Yes | Confirmed: `[;\|&\`(]` | PASS |

**Key design point**: The anchor `[;|&`(]` intentionally excludes `\s`. A plain space (as in `--action delete`) does NOT satisfy the command-position requirement. Only shell separators (`;`, `|`, `&`, backtick, `(`) qualify. This is the core fix.

---

## 5. Programmatic Regex Testing (80/80 PASS)

### Must-PASS (ALLOWED) -- 13/13 PASS
Commands that must NOT be blocked by the new patterns:

| Command | Target | Result |
|---------|--------|--------|
| `python3 memory_write.py --action delete .claude/memory/MEMORY.md` | .claude | ALLOWED |
| `python3 memory_write.py --action delete --path .claude/memory/X` | .claude | ALLOWED |
| `python3 mem.py --action retire .claude/memory/sessions/foo.json` | .claude | ALLOWED |
| `echo "deletion" \| grep .claude` | .claude | ALLOWED |
| `some-tool --model .claude/config` | .claude | ALLOWED |
| `cat .claude/memory/MEMORY.md` | .claude | ALLOWED |
| `ls .claude/memory/` | .claude | ALLOWED |
| `python3 script.py --action delete .git/config` | .git | ALLOWED |
| `git status` | .git | ALLOWED |
| `echo deleting .git is bad` | .git | ALLOWED |
| `ls _archive/` | _archive | ALLOWED |
| `python3 script.py --action delete _archive/x` | _archive | ALLOWED |
| `cat _archive/readme.md` | _archive | ALLOWED |

### Must-BLOCK -- 19/19 PASS
Destructive commands that MUST be blocked:

| Command | Target | Result |
|---------|--------|--------|
| `rm -rf .claude/` | .claude | BLOCKED |
| `rm .claude/memory/X` | .claude | BLOCKED |
| `del .claude/config` | .claude | BLOCKED |
| `delete .claude/config` | .claude | BLOCKED |
| `rmdir .claude/memory` | .claude | BLOCKED |
| `echo hello; rm .claude/x` | .claude | BLOCKED |
| `echo hello && del .claude/x` | .claude | BLOCKED |
| `(rm .claude/x)` | .claude | BLOCKED |
| `Remove-Item .claude/config` | .claude | BLOCKED |
| `DELETION .claude/stuff` | .claude | BLOCKED |
| `rm -rf .git` | .git | BLOCKED |
| `rm -rf .git/` | .git | BLOCKED |
| `delete .git/` | .git | BLOCKED |
| `rmdir .git` | .git | BLOCKED |
| `echo x; del .git/config` | .git | BLOCKED |
| `rm -rf _archive` | _archive | BLOCKED |
| `delete _archive/old` | _archive | BLOCKED |
| `rmdir _archive` | _archive | BLOCKED |
| `echo x \| rm _archive/y` | _archive | BLOCKED |

### Edge Cases -- 17/17 PASS

| Test Case | Expected | Actual | Notes |
|-----------|----------|--------|-------|
| `deleting .claude/x` | ALLOWED | ALLOWED | `\b` blocks "deleting" |
| `deleted .claude/x` | ALLOWED | ALLOWED | `\b` blocks "deleted" |
| `deletion .claude/x` | BLOCKED | BLOCKED | "deletion" is in alternation |
| `RM -rf .claude/` | BLOCKED | BLOCKED | Case insensitive |
| `DEL .claude/config` | BLOCKED | BLOCKED | Case insensitive |
| `Delete .claude/config` | BLOCKED | BLOCKED | Case insensitive |
| `` `rm .claude/x` `` | BLOCKED | BLOCKED | Backtick separator |
| `echo x;  rm .claude/x` | BLOCKED | BLOCKED | Semicolon + spaces |
| `echo x \| rm .claude/x` | BLOCKED | BLOCKED | Pipe separator |
| `echo x && rm .claude/x` | BLOCKED | BLOCKED | && separator |
| `rm .claude; echo done` | BLOCKED | BLOCKED | Followed by ; |
| `rm .claude \| true` | BLOCKED | BLOCKED | Followed by pipe |
| `rm .claude` | BLOCKED | BLOCKED | At end of string |
| `(rm .claude)` | BLOCKED | BLOCKED | Followed by ) |
| `rm.claude` | ALLOWED | ALLOWED | No space after rm |
| `git delete .claude/x` | ALLOWED | ALLOWED | git is the command |
| `npm run delete .claude/test` | ALLOWED | ALLOWED | npm is the command |

---

## 6. DO NOT CHANGE Items (5/5 PASS)

| Item | Status | Verification |
|------|--------|-------------|
| `bash_guardian.py` `is_delete_command()` | NOT MODIFIED | All 5 original patterns confirmed intact at lines 612-616 |
| SQL DELETE pattern (`guardian.default.json:147`) | NOT MODIFIED | `(?i)delete\\s+from\\s+\\w+(?:\\s*;\|\\s*$\|\\s+--)` preserved exactly |
| `del\\s+` ask pattern (`guardian.default.json:91`) | NOT MODIFIED | `(?i)del\\s+(?:/[sq]\\s+)*` preserved exactly |

---

## 7. External Review: Gemini CLI

Gemini CLI (gemini-3-pro-preview) confirmed:
- All 5 core test cases pass correctly
- Command-position anchoring logic is sound
- `\b` word boundary correctly blocks "deleting"/"deleted"
- ReDoS risk is LOW
- No bugs in the core pattern logic

### Gemini Finding: Quoted-Path Bypass

Gemini identified that `rm ".claude"` and `rm '.claude'` are NOT blocked because `"` and `'` are not in the terminator group.

**Assessment**: This is a **pre-existing gap**, NOT a regression from this change. I verified:
- OLD pattern: `rm ".claude"` -- ALLOWED (same behavior)
- NEW pattern: `rm ".claude"` -- ALLOWED (same behavior)

The old terminator `(?:\s|/|$)` also lacked quote characters. The new terminator `(?:\s|/|[;&|)`]|$)` expands coverage (adding separator chars) but does not introduce or worsen the quote gap.

**Recommendation for future work**: Consider adding `'"` to the terminator group across all patterns in a separate, dedicated change with its own test cases.

---

## 8. New Test Cases Verification

Two new test cases were added to `tests/test_guardian_utils.py`:

| Test Case | Expected | Location | Status |
|-----------|----------|----------|--------|
| `delete .claude/config` (true positive) | BLOCKED | Line 212 | PASS |
| `python3 memory_write.py --action delete .claude/memory/MEMORY.md` (false positive regression) | ALLOWED | Line 225 | PASS |

Both are correctly placed and test the exact scenarios from the spec.

---

## Summary

| Check Category | Result |
|----------------|--------|
| Pattern extraction & compilation | 10/10 PASS |
| Escaping correctness (JSON vs Python) | CORRECT |
| Cross-file consistency | 3/3 PASS |
| Regex structure vs spec | 9/9 PASS |
| Must-PASS (false positive prevention) | 13/13 PASS |
| Must-BLOCK (true positive preservation) | 19/19 PASS |
| Edge cases | 17/17 PASS |
| DO NOT CHANGE items | 5/5 PASS |
| External review (Gemini) | CONFIRMED CORRECT |
| New test cases | 2/2 PASS |
| **Total programmatic checks** | **80/80 PASS** |

**Verdict: PASS** -- All 10 regex pattern changes are correct, properly escaped, consistent across files, and match the specification exactly. No regressions introduced. One pre-existing gap (quoted-path bypass) noted as recommendation for future work.
