# Phase 3 Edge Case Verification: `_is_interpreter_heredoc()`

## Summary

Traced 16 edge cases through `split_commands()` and `_is_interpreter_heredoc()`.
**15 of 16 cases produce correct results. 1 case is a confirmed gap.**

---

## Code Under Review

- `_is_interpreter_heredoc()`: lines 235-261
- `_extract_base_command()`: lines 118-186
- `_INTERPRETER_COMMANDS`: lines 95-101
- Integration point: lines 1971-1980

## Trace Table

| # | Input | split_commands output | `_is_interpreter_heredoc` | Final verdict | Correct? |
|---|-------|----------------------|---------------------------|---------------|----------|
| a | `bash << 'EOF'\nrm -rf /\nEOF` | `["bash << 'EOF'"]` (body consumed) | `cmd_before="bash "`, base=`bash`, in set -> **True** | ASK | YES |
| b | `bash <<-EOF\n\trm -rf /\nEOF` | `["bash <<-EOF"]` (body consumed, tabs stripped) | `cmd_before="bash "`, base=`bash`, in set -> **True** | ASK | YES |
| c | `bash <<EOF\nrm -rf /\nEOF` | `["bash <<EOF"]` (body consumed) | `cmd_before="bash "`, base=`bash`, in set -> **True** | ASK | YES |
| d | `echo "bash << EOF"` | `['echo "bash << EOF"']` (one sub_cmd, no split -- `<<` inside quotes) | `'<<' in sub_cmd` = True, but `cmd_before='echo "bash '`, shlex.split raises ValueError -> returns `''` -> **False** | No ASK from Phase 3 | YES (see note 1) |
| e | `command bash << EOF\ncode\nEOF` | `["command bash << EOF"]` (body consumed) | `cmd_before="command bash "`, `command` is skip_prefix, base=`bash` -> **True** | ASK | YES |
| f | `builtin exec << EOF\ncode\nEOF` | `["builtin exec << EOF"]` (body consumed) | `cmd_before="builtin exec "`, `builtin` is skip_prefix, base=`exec`, in set -> **True** | ASK | YES |
| g | `time bash << EOF\ncode\nEOF` | `["time bash << EOF"]` (body consumed) | `cmd_before="time bash "`, `time` is skip_prefix, base=`bash` -> **True** | ASK | YES |
| h | `strace bash << EOF\ncode\nEOF` | `["strace bash << EOF"]` (body consumed) | `cmd_before="strace bash "`, `strace` is skip_prefix, base=`bash` -> **True** | ASK | YES |
| i | `. /dev/stdin << EOF\ncode\nEOF` | `[". /dev/stdin << EOF"]` (body consumed) | `cmd_before=". /dev/stdin "`, shlex.split -> `['.', '/dev/stdin']`, `.` is NOT in skip_prefixes and NOT in `_INTERPRETER_COMMANDS` -> **False** | **No ASK from Phase 3** | **NO -- BUG** (see note 2) |
| j | `bash < file.sh` | `["bash < file.sh"]` | `'<<' in sub_cmd` = False -> **False** | No ASK from Phase 3 | YES |
| k | `cat << EOF \| bash` | `["cat << EOF", "bash"]` (pipe splits) | sub1: `cmd_before="cat "`, base=`cat`, not in set -> False. sub2: `'<<' not in "bash"` -> False. | No ASK from Phase 3 | YES (see note 3) |
| l | `bash << EOF; rm -rf /` | `["bash << EOF", "rm -rf /"]` (semicolon splits; no newline so heredoc body not consumed) | sub1: `cmd_before="bash "`, base=`bash` -> **True**. sub2: no `<<` -> False. | ASK (for sub1); sub2 evaluated by other rules | YES |
| m | `csh << EOF\ncode\nEOF` | `["csh << EOF"]` (body consumed) | `cmd_before="csh "`, base=`csh`, in set -> **True** | ASK | YES |
| n | `fish << EOF\ncode\nEOF` | `["fish << EOF"]` (body consumed) | `cmd_before="fish "`, base=`fish`, in set -> **True** | ASK | YES |
| o | `ksh << EOF\ncode\nEOF` | `["ksh << EOF"]` (body consumed) | `cmd_before="ksh "`, base=`ksh`, in set -> **True** | ASK | YES |
| p | `py << EOF\ncode\nEOF` | `["py << EOF"]` (body consumed) | `cmd_before="py "`, base=`py`, in set -> **True** | ASK | YES |

---

## Detailed Notes

### Note 1: Case (d) -- `echo "bash << EOF"` (operator inside quotes)

`split_commands` correctly does NOT split on `<<` inside double quotes. The entire
string becomes one sub_cmd: `echo "bash << EOF"`.

Inside `_is_interpreter_heredoc`, the naive `'<<' in sub_cmd` string check returns
True, so it proceeds to extract the base command. `sub_cmd.split('<<', 1)[0]` produces
`'echo "bash '` which has an unmatched double quote. `shlex.split()` raises `ValueError`,
causing `_extract_base_command` to return `''`. Since `''` is not in `_INTERPRETER_COMMANDS`,
the function returns False.

**This produces the correct result but via an accidental path.** The function relies on
shlex.split's ValueError for an unmatched quote to produce the correct answer. If the
quoted string happened to be well-formed (e.g., `echo "bash" << EOF`), the result
would still be correct because `echo` would be extracted as the base command and `echo`
is not in `_INTERPRETER_COMMANDS`. So the logic is sound overall, but the specific
mechanism for case (d) is fragile.

**Severity: Low.** The accidental path still produces the correct result, and the
well-formed variant also works correctly.

### Note 2: Case (i) -- `. /dev/stdin << EOF` (dot command = source) -- BUG

In bash, `.` is a builtin synonym for `source`. Both execute code from stdin/file
in the current shell context. However:

- `source` IS in `_INTERPRETER_COMMANDS` (line 100)
- `.` (dot) is NOT in `_INTERPRETER_COMMANDS`
- `.` is NOT in `skip_prefixes`

`_extract_base_command(". /dev/stdin ")` calls `shlex.split(". /dev/stdin ")` which
returns `['.', '/dev/stdin']`. The loop checks `.`: it's not a redirect token, not a
variable assignment, not a skip_prefix, so it's returned as the base command: `'.'`.
Since `'.'` is not in `_INTERPRETER_COMMANDS`, the function returns False.

**Impact:** `. /dev/stdin << EOF\nmalicious code\nEOF` would bypass the Phase 3
interpreter+heredoc backstop entirely.

**Fix:** Add `'.'` to `_INTERPRETER_COMMANDS`:
```python
_INTERPRETER_COMMANDS = frozenset({
    'bash', 'sh', 'zsh', 'dash', 'ksh', 'csh', 'tcsh', 'fish',
    'python', 'python2', 'python3', 'py',
    'node', 'deno', 'bun',
    'perl', 'ruby',
    'source', '.', 'eval', 'exec',
})
```

**Mitigation:** In practice, `. /dev/stdin << EOF` is an unusual attack vector.
The heredoc body content would still be scanned by other layers (Layer 1 pattern
scanning, Layer 3 path checks). But for defense-in-depth completeness, `.` should
be added.

### Note 3: Case (k) -- `cat << EOF | bash` (pipe heredoc to interpreter)

Phase 3 correctly does NOT flag this pattern. The heredoc is attached to `cat`
(not an interpreter), and `bash` receives piped input (no `<<` in its sub_cmd).

This is **correct behavior for Phase 3's scope**. Phase 3 targets the specific
pattern of interpreter+heredoc where block patterns can't match across newlines.
The cat-pipe-to-bash pattern is a different attack surface that should be addressed
by other layers (e.g., the Phase 2 heredoc body retention + pattern scanning for
piped interpreter patterns).

### Note 4: Case (l) -- `bash << EOF; rm -rf /` (no newline)

When the command has no newline after the heredoc operator, `split_commands` never
enters heredoc body consumption. The semicolon splits into `["bash << EOF", "rm -rf /"]`.
The first sub_cmd triggers Phase 3 ASK. The second sub_cmd (`rm -rf /`) is evaluated
by the existing deletion detection rules and would be denied.

In real shell execution, `bash << EOF; rm -rf /` would mean bash reads from an
unterminated heredoc (waiting for EOF on stdin), then runs `rm -rf /`. The guardian
correctly catches both: ASK for the heredoc and deny for the rm.

---

## Bugs Found

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| B1 | Medium | `.` (dot command) not in `_INTERPRETER_COMMANDS`. `. /dev/stdin << EOF` bypasses Phase 3. | Add `'.'` to `_INTERPRETER_COMMANDS` |

## Concerns (Non-Bugs)

| ID | Severity | Description |
|----|----------|-------------|
| C1 | Low | Case (d) correctness depends on shlex.split ValueError for unmatched quotes rather than explicit logic. Works correctly but fragile. |
| C2 | Informational | `cat << EOF \| bash` pipe-to-interpreter not caught by Phase 3. By design -- different attack surface for other layers. |

## Test Coverage Assessment

The existing `test_interpreter_heredoc.py` (34 tests: 27 unit + 7 integration) covers:
- All major interpreters (bash, sh, zsh, dash, python/2/3, node, deno, bun, perl, ruby)
- Prefixes (env, sudo, nohup, nice)
- Absolute paths, variable assignments
- Tab-stripped heredoc (`<<-`), quoted delimiters
- Non-interpreters (cat, grep, echo, wc)
- Here-strings (`<<<`)

**Missing test coverage:**
- `.` (dot) as source synonym (blocked by bug B1)
- `command` prefix
- `builtin` prefix
- `strace` prefix
- `time` prefix
- Pipe-to-interpreter pattern (by design -- out of scope)
- `<` vs `<<` distinction
- `csh`, `tcsh`, `fish`, `ksh` (in `_INTERPRETER_COMMANDS` but not tested)
- `py` alias (in `_INTERPRETER_COMMANDS` but not tested)
