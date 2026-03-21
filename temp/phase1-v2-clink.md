# Phase 1 V2 Cross-Model Verification: V1 Fixes Review

**Date**: 2026-03-21
**Reviewers**: Codex 5.3 (codereviewer), Gemini 3.1 Pro (codereviewer)
**Coordinator**: Claude Opus 4.6
**Scope**: Verify V1 fixes for BUG-1 (post-`<<` redirect bypass) and BUG-2 (unquoted expansion bypass). Find remaining gaps.

---

## 1. V1 Fix Verdict

### BUG-1 (Post-`<<` redirect bypass): FIXED, CORRECT
Both models confirm the `full_segment` finalization approach correctly captures post-`<<` redirects like `cat << EOF > script.sh`. The finalization logic at every separator handler (`;`, `&&`, `||`, `|`, `&`, newline) is sound -- no path exists where `full_segment` remains None when it should be finalized.

### BUG-2 (Unquoted expansion bypass): FIXED, CORRECT
Both models confirm `is_quoted = raw_token != delim` correctly captures all bash quoting forms:
- `'EOF'` -> is_quoted=True (correct: bash suppresses expansion)
- `"EOF"` -> is_quoted=True (correct: bash suppresses expansion)
- `\EOF` -> is_quoted=True (correct: bash suppresses expansion)
- `$'EOF'` -> is_quoted=True (correct)
- `EOF` -> is_quoted=False (correct: bash expands)

The body scan for `$` and backtick in unquoted heredocs is robust and fail-closed.

### BUG-3 (sudo flag parsing): FIXED but INCOMPLETE (see below)

### BUG-4 (origins truthiness): FIXED, CORRECT

---

## 2. NEW Findings: Remaining Bypass Vectors

### CRITICAL-1: File Descriptor Duplication Bypass
**Agreement**: Both Codex and Gemini independently found this.
**Verified**: YES (reproduced locally)

`_OUTPUT_REDIR_PATTERN` exempts ALL `>&N` forms (intended for `>&1`, `>&2` fd duplication). But `>&3` through `>&9` (and beyond) can point to files opened by prior commands in the same compound statement.

**Exploit**:
```bash
exec 3>/tmp/exploit.sh; cat << EOF >&3
rm -rf /
EOF
```
- `cat << EOF >&3` -> `>&3` matches the fd-dup exemption -> classified SAFE -> body redacted
- bash writes the unredacted body to `/tmp/exploit.sh` via fd 3

**Result**: `split_commands()` redacts the body. `payload` invisible to Layer 0/0b.

**Fix**: Only exempt `>&0`, `>&1`, `>&2`, and `>&-` (close fd). Treat `>&3` through `>&9+` as output redirects. Concretely, change the negative lookahead from `(?!\s*(?:[0-9]+|-)...)` to `(?!\s*(?:[012]|-)...)`.

### CRITICAL-2: sudo `-p` Flag Argument Sync-Slip
**Agreement**: Gemini found this. Codex flagged sudo incompleteness at LOW severity.
**Verified**: YES (reproduced locally)

`_sudo_arg_flags` is missing several argument-taking flags. Most dangerous: `-p` (prompt string).

**Exploit**:
```bash
sudo -p cat python << EOF
import os; os.system("rm -rf /")
EOF
```
- Parser: skips `-p`, lands on `cat` (actually the `-p` argument), returns `cat`
- Classifier: `cat` in `_PASSIVE_DATA_SINKS` -> SAFE -> body redacted
- Runtime: sudo uses `cat` as prompt string, executes `python` with heredoc body

**Result**: `_extract_base_command("sudo -p cat python")` returns `'cat'` instead of `'python'`.

Other missing arg-taking flags: `-c` (class), `-a` (auth type), `-U` (other user).
Long options (`--user`, `--prompt`) not handled at all.

**Fix (recommended)**: Invert to allowlist approach. Maintain set of known no-arg flags. Any unknown flag -> fail-closed (return `''`).

```python
_sudo_noarg_flags = {'-A', '-b', '-E', '-e', '-H', '-h', '-K', '-k',
                     '-l', '-n', '-P', '-S', '-s', '-V', '-v'}
# In the loop: if flag not in _sudo_noarg_flags and not flag.startswith('--'):
#     return ''  # fail-closed: unknown flag
```

### LOW-1: Pipe Handler Over-Applies `was_piped` to All Origins
**Source**: Codex
**Verified**: YES (but fail-closed -- causes over-retention, not bypass)

The pipe separator handler at line 546-549 rewrites ALL `heredoc_origins` entries with `was_piped=True`, not just the current segment's origins. For `cat << A ; cat << B | grep x`, heredoc A also gets `was_piped=True`.

This is conservative (retains more bodies than necessary) and not a bypass. Low priority.

### LOW-2: `sudo -s` / `sudo -i` Shell/Login Modes
**Source**: Gemini
**Verified**: YES

`sudo -s cat << EOF` returns `cat` as base command. But `-s` means sudo invokes a shell; `-i` means login shell. The post-flag token is passed as a command *string* to the shell, not executed directly. Should probably force UNSAFE when these modes are detected.

Currently fails closed because the heredoc body feeds an interpreter (shell), but only by accident -- the guardian classifies based on the post-flag token (`cat`), not the execution mode.

### LOW-3: `<>` (read-write) Redirect Not Detected
**Source**: Gemini investigation
**Not verified yet**: `<>` (bash read-write open) is not caught by `_OUTPUT_REDIR_PATTERN`. `cat << EOF <> file` would allow read-write access to a file. Very edge-case but technically a gap.

---

## 3. Agreement Matrix

| Finding | Codex | Gemini | Verified |
|---------|-------|--------|----------|
| V1 BUG-1 fix correct | YES | YES | YES |
| V1 BUG-2 fix correct | YES | YES | YES |
| `full_segment` logic sound | YES | YES | YES |
| `is_quoted` check sufficient | YES | YES | YES |
| **fd dup bypass (>&3)** | **CRITICAL** | **CRITICAL** | **YES** |
| **sudo -p sync-slip** | LOW (incomplete) | **CRITICAL** | **YES** |
| Pipe over-application | LOW | -- | YES (fail-closed) |
| sudo -s/-i shell mode | -- | LOW | YES (fail-closed) |
| `<>` redirect gap | -- | investigated | Not verified |

---

## 4. Actionable Items

### Must Fix (Security Bypasses)

1. **`_OUTPUT_REDIR_PATTERN` fd dup narrowing**
   - Change exemption from "any digit" to "only 0, 1, 2" in the `>&N` negative lookahead
   - Consider also catching `<&` for non-standard fd duplication

2. **sudo flag parsing: invert to no-arg allowlist**
   - Known no-arg flags: `-A`, `-b`, `-E`, `-e`, `-H`, `-h`, `-K`, `-k`, `-l`, `-n`, `-P`, `-S`, `-s`, `-V`, `-v`
   - Unknown flag -> fail-closed (return empty string)
   - Long options -> fail-closed (return empty string) unless explicitly handled

### Should Fix (Correctness)

3. **sudo `-s`/`-i` detection**: When shell/login mode detected, force UNSAFE classification regardless of post-flag token.

4. **Pipe over-application**: Only mark origins whose `full_segment` is still None as piped, or track origins per-segment.

### Tests to Add

- `exec 3>/tmp/out; cat << EOF >&3` -> body RETAINED
- `cat << EOF >&3` (standalone) -> body RETAINED
- `cat << EOF >&2` -> body SAFE (stderr dup, no file write)
- `cat << EOF >&1` -> body SAFE
- `sudo -p cat python << EOF` -> body RETAINED (python is interpreter)
- `sudo -c class cat << EOF` -> body RETAINED (fail-closed on unknown)
- `sudo --user root cat << EOF` -> body RETAINED (fail-closed on long option)

---

## 5. Summary

The V1 fixes for the two original CRITICAL bypasses are **correct and complete**. The `full_segment` approach properly captures post-`<<` redirects, and the `is_quoted` check correctly matches bash expansion semantics for all delimiter quoting forms.

However, both review models independently identified a **new CRITICAL bypass via file descriptor duplication** (`>&3` through `>&9+`), and Gemini found a **CRITICAL sudo flag sync-slip** where missing arg-taking flags (especially `-p`) cause the parser to misidentify the base command, enabling an attacker to disguise an interpreter as a passive data sink.

Both bypasses are straightforward to fix:
1. Narrow the `>&N` exemption to only `>&0`, `>&1`, `>&2`, `>&-`
2. Invert sudo flag parsing to a no-arg allowlist with fail-closed default
