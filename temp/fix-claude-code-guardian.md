# Fix Instructions: claude-code-guardian Regex Update

**Repo**: `claude-code-guardian` (at `/home/idnotbe/projects/claude-code-guardian/`)
**Purpose**: Paste this file into a Claude Code session opened in the claude-code-guardian repo.
**Context**: This fixes a false-positive issue where Guardian blocks legitimate memory management
commands because `del` matches as a substring inside the word `delete` in command arguments.

---

## Background

Guardian's block patterns currently match `del` as a substring of any word containing "del",
including `--action delete` in Python script arguments. The regex:

```
(?i)(?:rm|rmdir|del|remove-item).*\.claude(?:\s|/|$)
```

Matches `python3 memory_write.py --action delete --path .claude/memory/X` because:
- `del` appears inside `delete` (no word boundary)
- `.*` matches `ete --path `
- `.claude` matches the path argument

This is a false positive. The fix has two parts:
1. Add command-position anchoring so `del` only matches when it appears as a standalone command
2. Add `delete` to the alternation explicitly (so `delete .claude/...` as a real shell command IS blocked)
3. Add `\b` after the alternation as belt-and-suspenders

**Dependency note**: This fix works best AFTER claude-memory renames `--action delete` to
`--action retire`. After that rename, no legitimate command will contain `--action delete`,
eliminating the collision entirely. But this regex fix is still needed for general correctness
and future-proofing (command-position anchoring is more precise regardless).

---

## Escaping Reference

**CRITICAL**: JSON and Python raw strings use different escaping for backslashes.

| Context | Backslash in regex | Example |
|---|---|---|
| JSON (`.json` files) | `\\` (doubled) | `\s` in regex becomes `\\s` in JSON |
| Python raw string (`r"..."`) | `\` (single) | `\s` in regex is literally `\s` |

Reference:
- JSON string `"\\s"` represents the regex character `\s` (whitespace)
- JSON string `"\\."` represents the regex `.` (literal dot)
- Python `r"\s"` represents the same `\s` (whitespace)
- Python `r"\."` represents the same `\.` (literal dot)

When reading diffs below: JSON patterns have doubled backslashes; Python patterns have single backslashes.

---

## The Correct Final Patterns

These are the regex patterns in their native format for each file type.

### Regex logic (human-readable):

```
(?i)                           -- case-insensitive
(?:^|[;|&`(]\s*)               -- start of string OR command separator + optional whitespace
(?:rm|rmdir|del|delete|deletion|remove-item)  -- one of the blocked commands
\b                             -- word boundary (prevents matching "deleting", "deleted", etc.)
\s+                            -- one or more spaces (command must have an argument)
.*                             -- any characters
\.claude                       -- literal ".claude"
(?:\s|/|[;&|)`]|$)             -- followed by space, slash, separator, or end of string
```

Why `[;|&`(]\s*` and NOT `[\s;|&`(]`:
- `[\s;|&`(]` includes `\s` (whitespace), so a space before `delete` (as in `--action delete`)
  satisfies the anchor. This is STILL a false positive.
- `[;|&`(]\s*` only matches command separators (`;`, `|`, `&`, `` ` ``, `(`), with optional
  trailing whitespace. A plain argument space does NOT satisfy this anchor.

**Note on `deletion`**: The founder explicitly requested `deletion` be included in the alternation
group. While `deletion` is not a real OS command, the founder's decision stands. Add `deletion`
after `delete` in all alternation groups: `(?:rm|rmdir|del|delete|deletion|remove-item)`.
All patterns below should include `deletion` in the alternation.

### JSON format (for `.json` files):

**.git pattern:**
```
"(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)`]|$)"
```

**.claude pattern:**
```
"(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.claude(?:\\s|/|[;&|)`]|$)"
```

**_archive pattern:**
```
"(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*_archive(?:\\s|/|[;&|)`]|$)"
```

### Python raw string format (for `.py` files):

**.git pattern:**
```
r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`]|$)"
```

**.claude pattern:**
```
r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)"
```

**_archive pattern:**
```
r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`]|$)"
```

---

## Files to Change

### File 1: `assets/guardian.default.json`

**Lines to change**: 17, 21, 25 (use content search to locate exactly -- line numbers may shift)

**Important**: This is a JSON file. Use `\\` for every backslash.

#### Change 1 of 3 -- Git pattern (around line 17)

Before:
```json
"pattern": "(?i)(?:rm|rmdir|del|remove-item).*\\.git(?:\\s|/|$)"
```

After:
```json
"pattern": "(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.git(?:\\s|/|[;&|)`]|$)"
```

#### Change 2 of 3 -- Claude pattern (around line 21)

Before:
```json
"pattern": "(?i)(?:rm|rmdir|del|remove-item).*\\.claude(?:\\s|/|$)"
```

After:
```json
"pattern": "(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*\\.claude(?:\\s|/|[;&|)`]|$)"
```

#### Change 3 of 3 -- Archive pattern (around line 25)

Before:
```json
"pattern": "(?i)(?:rm|rmdir|del|remove-item).*_archive(?:\\s|/|$)"
```

After:
```json
"pattern": "(?i)(?:^|[;|&`(]\\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\\b\\s+.*_archive(?:\\s|/|[;&|)`]|$)"
```

---

### File 2: `hooks/scripts/_guardian_utils.py`

**Lines to change**: Around lines 374, 378, 382 (use content search -- line numbers may shift)

**Important**: These are Python raw strings (`r"..."`). Use single `\` for backslashes.

Note: The fallback config was previously missing `remove-item` compared to the JSON config.
The "after" patterns below add it to close that pre-existing gap. This is a safe, contained
improvement included in this fix.

#### Change 1 of 3 -- Git fallback pattern (around line 374)

Before:
```python
"pattern": r"(?i)(?:rm|rmdir|del).*\.git(?:\s|/|$)",
```

After:
```python
"pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`]|$)",
```

#### Change 2 of 3 -- Claude fallback pattern (around line 378)

Before:
```python
"pattern": r"(?i)(?:rm|rmdir|del).*\.claude(?:\s|/|$)",
```

After:
```python
"pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)",
```

#### Change 3 of 3 -- Archive fallback pattern (around line 382)

Before:
```python
"pattern": r"(?i)(?:rm|rmdir|del).*_archive(?:\s|/|$)",
```

After:
```python
"pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`]|$)",
```

---

### File 3: `tests/test_guardian_utils.py`

**Lines to change**: Around lines 56 and 58 (use content search -- line numbers may shift)

These test patterns must mirror the production fallback patterns. Update them in sync.

#### Change 1 of 2 -- Git test pattern (around line 56)

Before:
```python
{"pattern": r"(?i)(?:rm|rmdir|del).*\.git(?:\s|/|$)", "reason": "Git deletion"},
```

After:
```python
{"pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`]|$)", "reason": "Git deletion"},
```

#### Change 2 of 2 -- Claude test pattern (around line 58)

Before (may be multi-line):
```python
{
    "pattern": r"(?i)(?:rm|rmdir|del).*\.claude(?:\s|/|$)",
    "reason": "Claude deletion",
},
```

After:
```python
{
    "pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`]|$)",
    "reason": "Claude deletion",
},
```

---

### File 4: `tests/test_guardian.py`

**Lines to change**: Around lines 98 and 100 (use content search -- line numbers may shift)

#### Change 1 of 2 -- Git test pattern (around line 98)

Before:
```python
{"pattern": r"(?i)(?:rm|rmdir|del).*\.git(?:\s|/|$)", "reason": "Git deletion"},
```

After:
```python
{"pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.git(?:\s|/|[;&|)`]|$)", "reason": "Git deletion"},
```

#### Change 2 of 2 -- Archive test pattern (around line 100)

Before (may be multi-line):
```python
{
    "pattern": r"(?i)(?:rm|rmdir|del).*_archive(?:\s|/|$)",
    "reason": "Archive deletion",
},
```

After:
```python
{
    "pattern": r"(?i)(?:^|[;|&`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*_archive(?:\s|/|[;&|)`]|$)",
    "reason": "Archive deletion",
},
```

---

## What NOT to Change

### `bash_guardian.py` -- `is_delete_command()` (around lines 612-616)

This function uses its own patterns for detecting delete operations (for the archive-before-delete
feature). It already uses proper command-position anchoring. Leave it alone.

Current patterns look like:
```python
r"(?:^|[;&|]\s*)rm\s+",
r"(?:^|[;&|]\s*)del\s+",
r"(?:^|[;&|]\s*)rmdir\s+",
r"(?:^|[;&|]\s*)Remove-Item\s+",
r"(?:^|[;&|]\s*)ri\s+",
```

These are correct. `del\s+` requires `del` followed immediately by whitespace, so it will NOT
match inside `delete` (which has `e` after `del`, not whitespace). No change needed.

### SQL DELETE pattern in `assets/guardian.default.json` (around line 147)

The pattern:
```json
"(?i)delete\\s+from\\s+\\w+(?:\\s*;|\\s*$|\\s+--)"
```

This is SQL-specific (`DELETE FROM tablename`). It is not a shell command pattern and does not
collide with any case we are fixing. Leave it alone.

### `ask` pattern `del\s+` in `assets/guardian.default.json` (around line 91)

The pattern:
```json
"(?i)del\\s+(?:/[sq]\\s+)*"
```

This is a Windows `del` command with `/S` and `/Q` flags. It requires `del` followed immediately
by whitespace, so `delete /path` does NOT match (the `e` in `delete` prevents `del\s+` from
matching). This pattern is safe as-is. Leave it alone.

---

## Testing

After applying all changes, run the test suite:

```bash
pytest tests/ -v
```

### Test cases that MUST pass (these are legitimate commands -- Guardian must NOT block them)

| Command | Reason |
|---|---|
| `python3 memory_write.py --action delete .claude/memory/MEMORY.md` | `delete` is an arg, not a command |
| `python3 memory_write.py --action delete --path .claude/memory/X` | Same: arg position |
| `python3 mem.py --action retire .claude/memory/sessions/foo.json` | Renamed action, safe |
| `echo "deletion" \| grep .claude` | `deletion` in string, not a command |
| `some-tool --model .claude/config` | No delete command at all |
| `cat .claude/memory/MEMORY.md` | Read-only operation |
| `ls .claude/memory/` | Read-only operation |

### Test cases that MUST be blocked (actual destructive commands)

| Command | Reason |
|---|---|
| `rm -rf .claude/` | `rm` at start of string |
| `rm .claude/memory/X` | `rm` as standalone command |
| `del .claude/config` | `del` as standalone Windows command |
| `delete .claude/config` | `delete` as standalone command (now in alternation) |
| `rmdir .claude/memory` | `rmdir` as standalone command |
| `echo hello; rm .claude/x` | `rm` after `;` separator |
| `echo hello && del .claude/x` | `del` after `&&` -- the second `&` in `&&` satisfies `[;|&`(]` |
| `(rm .claude/x)` | `rm` after `(` separator |

### New test case to add to test_guardian_utils.py

Add this test to the false-positive verification section:

```python
# False positive regression: memory_write.py --action delete must NOT be blocked
("python3 memory_write.py --action delete .claude/memory/MEMORY.md", False,
 "delete as argument flag should not trigger block"),
# True positive: standalone delete command MUST be blocked
("delete .claude/config", True,
 "delete as standalone command must be blocked"),
```

---

## Verification Checklist

After applying all changes:

- [ ] `pytest tests/ -v` passes with no failures
- [ ] Grep for old pattern to confirm no remaining instances:
  ```bash
  grep -r "(?:rm|rmdir|del).*\\\\." assets/ hooks/ tests/
  ```
- [ ] Grep confirms new pattern is present in all 4 files:
  ```bash
  grep -r "remove-item.*\\\\b" assets/ hooks/ tests/
  ```
- [ ] Manually test the false-positive case (should NOT be blocked):
  ```bash
  echo 'python3 memory_write.py --action delete --path .claude/memory/X' | python3 -c "
  import re, sys
  pattern = r'(?i)(?:^|[;|&\`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)\`]|\$)'
  cmd = sys.stdin.read().strip()
  print('BLOCKED' if re.search(pattern, cmd) else 'ALLOWED')
  "
  ```
  Expected output: `ALLOWED`
- [ ] Manually test the true-positive case (MUST be blocked):
  ```bash
  echo 'delete .claude/config' | python3 -c "
  import re, sys
  pattern = r'(?i)(?:^|[;|&\`(]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)\`]|\$)'
  cmd = sys.stdin.read().strip()
  print('BLOCKED' if re.search(pattern, cmd) else 'ALLOWED')
  "
  ```
  Expected output: `BLOCKED`

---

## Implementation Order

Apply changes in this order to keep the test suite green throughout:

1. `assets/guardian.default.json` (3 changes) -- production config
2. `hooks/scripts/_guardian_utils.py` (3 changes) -- fallback config
3. `tests/test_guardian_utils.py` (2 changes) -- test mirrors of production
4. `tests/test_guardian.py` (2 changes) -- test mirrors of production
5. Run `pytest tests/ -v` and confirm passing

---

## Summary

| File | Changes | Backslash style |
|---|---|---|
| `assets/guardian.default.json` | 3 block patterns (lines ~17, ~21, ~25) | `\\` (JSON) |
| `hooks/scripts/_guardian_utils.py` | 3 fallback patterns (lines ~374, ~378, ~382) | `\` (Python raw) |
| `tests/test_guardian_utils.py` | 2 test patterns (lines ~56, ~58) | `\` (Python raw) |
| `tests/test_guardian.py` | 2 test patterns (lines ~98, ~100) | `\` (Python raw) |
| `hooks/scripts/bash_guardian.py` | NO CHANGE (already anchored) | -- |
| `assets/guardian.default.json` ask `del\s+` | NO CHANGE (safe as-is) | -- |
| `assets/guardian.default.json` SQL DELETE | NO CHANGE (SQL-specific) | -- |

Total: 10 pattern updates across 4 files.
