# Phase 3 Security Audit: Interpreter+Heredoc ASK Backstop

**Auditor**: Claude Opus 4.6 (1M context)
**Date**: 2026-03-21
**Scope**: `_is_interpreter_heredoc()`, integration point at line 1975, `_INTERPRETER_COMMANDS`, `_extract_base_command()`, and test suite
**Verdict**: Implementation is sound for common cases. Several edge-case bypass vectors exist, most mitigated by fail-closed behavior in other layers.

---

## FINDINGS

### F1. `_extract_base_command()` fails to skip flags on non-sudo prefix commands [MEDIUM]

**Severity: MEDIUM**

`_extract_base_command()` has special flag-skipping logic only for `sudo`. All other prefix commands in `skip_prefixes` (`env`, `nice`, `time`, `strace`, `command`, `builtin`) cause the loop to advance by exactly 1 token and then treat the next token (often a flag like `-i`, `-n`, `-p`) as the command name.

**Bypass examples:**
```bash
env -i bash << EOF          # extracted: "-i"  (not "bash")
env -S bash << EOF          # extracted: "-s"  (not "bash")
env -- bash << EOF          # extracted: "--"  (not "bash")
nice -n 10 bash << EOF      # extracted: "-n"  (not "bash")
time -p bash << EOF         # extracted: "-p"  (not "bash")
strace -f bash << EOF       # extracted: "-f"  (not "bash")
command -v bash << EOF      # extracted: "-v"  (not "bash")
```

All of these return a string not in `_INTERPRETER_COMMANDS`, so `_is_interpreter_heredoc()` returns False -- missing the interpreter+heredoc pattern.

**Mitigations:**
- Phase 1 (`_classify_heredoc_safety()`) shares the same `_extract_base_command()` call. It fails to recognize the interpreter in Rule 1, BUT Rule 5 ("unknown commands fail-closed") returns False (UNSAFE), so the heredoc body is **retained** (not redacted). The body content remains visible to Layer 0 block patterns for single-line dangerous patterns.
- The bypass only evades the Phase 3 ASK escalation, not the entire security stack. Dangerous single-line patterns in the body (e.g., `rm --no-preserve-root`) would still be caught by Layer 0.
- Claude Code LLM is unlikely to generate `env -i bash << EOF` in normal operation, but an adversarial prompt injection could.

**Recommendation:** Add flag-skipping logic for `env` (at minimum: `-i`, `-u VAR`, `-S`, `--`, `-0`). Consider a generic "skip all flags until non-flag token" approach for simple prefix commands.

**Location:** `hooks/scripts/bash_guardian.py` lines 141-180

---

### F2. Missing interpreters in `_INTERPRETER_COMMANDS` [MEDIUM]

**Severity: MEDIUM**

The following interpreter-like commands accept stdin/heredoc input and execute code, but are absent from `_INTERPRETER_COMMANDS`:

| Command | Risk | Likelihood |
|---------|------|------------|
| `php` | Executes PHP code from stdin | Medium (common on web servers) |
| `lua`, `lua5.4`, `luajit` | Executes Lua code | Low |
| `tclsh`, `wish` | Tcl interpreters | Low |
| `gawk`, `mawk`, `nawk` | awk variants with `system()` capability | Medium |
| `python3.11`, `python3.12`, etc. | Versioned Python | Medium |
| `pypy`, `pypy3` | Alternative Python implementations | Low |
| `pwsh` | PowerShell Core (cross-platform) | Low-Medium |
| `Rscript`, `r` | R language (can call `system()`) | Low |
| `julia` | Julia language | Low |
| `elixir`, `iex` | Elixir/IEx | Low |
| `scala` | Scala REPL | Low |
| `groovy` | Groovy script runner | Low |

Additionally, `awk` is in `_PASSIVE_DATA_SINKS` but it has `system()` built-in. With a heredoc, `awk << EOF` could execute arbitrary commands via `system("rm -rf /")`. However, awk heredoc usage is very uncommon and `awk` is a well-known data processing tool, so the passive-sink classification is a reasonable trade-off.

**Most impactful gaps:** `php`, versioned Python (e.g., `python3.11`), and `gawk`/`mawk`/`nawk`.

**Mitigation:** Phase 1 fail-closed behavior means unknown commands retain heredoc bodies (not redacted). The missing ASK backstop means no user confirmation prompt, but single-line dangerous patterns in bodies are still caught by Layer 0.

**Recommendation:** Add `php` at minimum. Consider prefix-matching for `python3.*` variants. Consider whether `awk` variants warrant reclassification (currently mitigated by being classified as "unknown" by `_classify_heredoc_safety` Rule 5 if not in `_PASSIVE_DATA_SINKS` -- but `awk` IS in `_PASSIVE_DATA_SINKS`, which is a separate concern for Phase 1, not Phase 3).

**Location:** `hooks/scripts/bash_guardian.py` lines 95-101

---

### F3. `busybox` prefix bypasses interpreter detection [LOW]

**Severity: LOW**

`busybox` is not in `skip_prefixes`, so `busybox sh << EOF` returns `"busybox"` as the base command. Since `"busybox"` is not in `_INTERPRETER_COMMANDS`, the heredoc backstop is not triggered.

```bash
busybox sh << EOF       # extracted: "busybox" -> miss
busybox ash << EOF      # extracted: "busybox" -> miss
```

**Mitigation:** Same as F1/F2 -- Phase 1 fails-closed on unknown commands, retaining the body. `busybox` is uncommon in Claude Code generated commands.

**Recommendation:** Either add `busybox` to `skip_prefixes` or add it to `_INTERPRETER_COMMANDS`.

---

### F4. No test for `_extract_base_command` flag-handling gaps in Phase 3 context [LOW]

**Severity: LOW**

The test suite (`tests/security/test_interpreter_heredoc.py`) covers:
- Basic interpreter detection (bash, python3, node, perl, ruby, sh, zsh, dash, deno, bun)
- Prefix handling (env, sudo, nohup, nice)
- Absolute paths, variable assignments
- Non-interpreters (cat, grep, echo, wc)
- Edge cases (empty string, `<<` only, tab-stripped heredoc, quoted delimiter)

**Not tested:**
1. `env -i bash << EOF` -- the F1 bypass (no test for prefix commands with flags)
2. `env -- bash << EOF` -- end-of-options separator
3. `busybox sh << EOF` -- the F3 bypass
4. `python3.11 << EOF` -- versioned interpreter (F2)
5. `php << EOF` -- missing interpreter (F2)
6. Commands where `<<` appears inside a variable assignment value before the actual heredoc: e.g., `FOO="<<" bash << EOF`
7. `bash <<-'EOF'` with both tab-stripping AND quoted delimiter simultaneously
8. Very long command before `<<` (stress test for shlex.split)
9. `exec bash << EOF` -- exec + interpreter (exec detected as the command, not bash)

**Recommendation:** Add negative tests demonstrating the known gaps (F1, F2, F3) so they serve as regression markers when fixes land.

---

### F5. Naive `str.split('<<', 1)` may incorrectly split on `<<` inside variable values [LOW]

**Severity: LOW**

`_is_interpreter_heredoc()` uses `sub_cmd.split('<<', 1)[0]` to isolate the command before the heredoc operator. If `<<` appears in a variable assignment value that precedes the actual heredoc, the split point is wrong:

```bash
FOO="<<" bash << EOF
```

- `sub_cmd.split('<<', 1)` splits at the first `<<` inside `"<<"`, producing `cmd_before = 'FOO="'`
- `shlex.split('FOO="')` raises `ValueError` -> returns `''` -> not in set -> False
- This is a **false negative**: `bash << EOF` with a variable containing `<<` is not detected.

**Mitigation:** This is an extremely unlikely real-world pattern. The broader system retains the heredoc body via Phase 1 fail-closed. Also, `split_commands()` would handle the heredoc correctly at the parser level, so the body content IS preserved and visible to block patterns.

**Recommendation:** A more robust approach would be to use `shlex`-aware splitting or regex with quote handling for the `<<` detection. Low priority given the unlikelihood.

---

### F6. `source` with heredoc is an unusual but valid detection [INFO]

**Severity: INFO**

`source /dev/stdin << EOF` is correctly detected because `source` is in `_INTERPRETER_COMMANDS` and `_extract_base_command("source /dev/stdin ")` returns `"source"`. The `/dev/stdin` argument is not a prefix command, so it's ignored by the loop after `source` is identified as the base command. Correct behavior.

However, `source << EOF` (without `/dev/stdin`) is invalid in bash -- `source` requires a filename argument. The detection still fires (returning ASK), which is harmless overapproximation.

---

### F7. Phase 3 does not interact negatively with Phase 1 or Phase 2 [INFO]

**Severity: INFO**

- **Phase 1 (heredoc redaction):** Phase 3 runs on sub_commands produced by `split_commands()`. The sub_command text includes the `<< DELIM` operator but not the body (body lines are consumed separately). Phase 3 checks `'<<' in sub_cmd` which works on the command line, not the body. No conflict.
- **Phase 2 (interpreter path resolution for `-c`/`-e` payloads):** Phase 2 handles `-c` and `-e` payloads. Phase 3 handles `<<` heredocs. These are independent code paths triggered by different syntax. A command like `bash -c "code" << EOF` would trigger BOTH Phase 2 (for `-c`) and Phase 3 (for `<<`), resulting in the stronger of the two verdicts. This is correct behavior.
- **Layer 0 (block patterns):** Phase 3 runs AFTER Layer 0. If a block pattern matches the redacted command, Layer 0 DENYs before Phase 3 runs. Phase 3 provides defense-in-depth for cases where block patterns can't match (multiline bodies). No conflict.

---

### F8. Here-string (`<<<`) caught intentionally -- design review [INFO]

**Severity: INFO**

`_is_interpreter_heredoc()` catches here-strings (`<<<`) because `'<<' in sub_cmd` is true for `<<<`. The spec explicitly notes this is intentional. Here-strings feed input to interpreters and can execute arbitrary code:

```bash
bash <<< 'rm -rf /'    # Executes rm -rf / in subshell
```

However, here-strings are single-line, so block patterns CAN match them within the same line of the retained command text. The ASK backstop for here-strings is therefore redundant but harmless. No action needed.

---

### F9. `split_commands` does not check `depth > 0` when detecting `<<` [INFO]

**Severity: INFO** (pre-existing, not Phase 3 specific)

At line 629, `split_commands` checks `arithmetic_depth == 0` but does NOT check `depth == 0` (the `$()` / `<()` / `>()` depth tracker). This means `<<` inside command substitution `$(...)` would be parsed as a heredoc operator, potentially causing incorrect command splitting.

Example: `echo $(bash << EOF\ncode\nEOF)` might be parsed incorrectly.

This is a pre-existing issue in `split_commands`, not introduced by Phase 3. Phase 3 operates on the resulting sub_commands, so it inherits any incorrect splitting but does not make it worse.

---

## SUMMARY TABLE

| ID | Severity | Category | Description |
|----|----------|----------|-------------|
| F1 | MEDIUM | Bypass | `_extract_base_command()` skips prefix commands by 1 token, not accounting for flags |
| F2 | MEDIUM | False Negative | Missing interpreters: `php`, `python3.11+`, `gawk`/`mawk`/`nawk` |
| F3 | LOW | Bypass | `busybox` prefix not in `skip_prefixes` |
| F4 | LOW | Coverage Gap | No tests for F1/F2/F3 bypass vectors |
| F5 | LOW | False Negative | Naive `str.split('<<')` fails when `<<` in variable value |
| F6 | INFO | Observation | `source << EOF` (invalid bash) correctly causes ASK (harmless) |
| F7 | INFO | Observation | No negative interaction with Phase 1 or Phase 2 |
| F8 | INFO | Observation | Here-string detection is intentional and harmless |
| F9 | INFO | Pre-existing | `split_commands` missing `depth` check for `<<` inside `$()` |

## OVERALL ASSESSMENT

Phase 3 is a well-designed defense-in-depth measure. The core logic (`_is_interpreter_heredoc`) is simple and correct for the common case. The main weakness is inherited from `_extract_base_command()`, which lacks flag-handling for non-sudo prefix commands (F1). This is the same function used by Phase 1, so the impact is limited by Phase 1's fail-closed behavior.

**No CRITICAL findings.** The two MEDIUM findings (F1, F2) represent partial bypasses in uncommon scenarios where the broader fail-closed security stack still provides protection. The Phase 3 backstop is additive security -- its failure degrades to the pre-Phase-3 security posture rather than creating a new vulnerability.

**Recommended priority:**
1. Fix F1 (env/nice/time flag handling in `_extract_base_command`) -- benefits both Phase 1 and Phase 3
2. Add `php` and versioned Python to `_INTERPRETER_COMMANDS` (F2)
3. Add regression tests for known gaps (F4)
