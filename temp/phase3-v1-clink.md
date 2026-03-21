# Phase 3 Cross-Model Security Review: `_is_interpreter_heredoc()` Backstop

**Date**: 2026-03-21
**Reviewers**: Claude Opus 4.6 (primary), Codex 5.3 (via clink), Gemini 3.1 Pro (via clink)
**Scope**: `_is_interpreter_heredoc()`, `_extract_base_command()`, integration at L1971-1980
**Validation**: All bypass vectors empirically confirmed against live implementation

---

## 1. Individual Model Reviews (Summarized)

### Claude Opus 4.6 (Primary Reviewer)

Performed empirical validation of 12 bypass vectors against the live codebase. Confirmed every false negative raised by the other models. Key independent observations:

- The `sub_cmd.split('<<', 1)[0]` pre-split is **quote-unaware** and fundamentally unsound when the sub_cmd contains `<<` inside quoted strings.
- `_extract_base_command()` only has flag-skipping logic for `sudo`; all other prefixes in `skip_prefixes` blindly `i += 1` past the name, so any flags (e.g., `env -i`, `time -p`, `command -p`) are misidentified as the base command.
- Numeric FD redirects (`2>`, `0<`) are not recognized as redirects, causing tokens like `'2>'` or `'null'` (from `0</dev/null`) to be returned as the base command.
- The here-string (`<<<`) and arithmetic shift (`$((1<<2))`) false positives are confirmed and the here-string case is even enshrined in the test suite as intentional (test_here_string_also_caught).

### Codex 5.3

Three main findings, with evidence-backed reproduction:

1. **Prefix-option parsing gaps (9/10)**: `env -i`, `time -p`, `command -p`, `sudo --user=root`, and `0</dev/null` all bypass. Only `sudo` has partial flag parsing; all other prefixes skip zero flags. Numeric redirections are not handled.
2. **Lexical command-name check is brittle (8/10)**: Dynamic names (`$(command -v bash)`, `${SHELL}`), alias/function wrappers, renamed binaries, and unlisted interpreters (`python3.12`) all bypass. Recommended failing closed for unresolved/dynamic command words.
3. **Raw `<<` substring causes false positives (4/10)**: Here-strings, arithmetic shifts, and `<<` in comments all trigger false ASK. Recommended reusing parser metadata from `split_commands()` instead of raw text scanning.

### Gemini 3.1 Pro

Six findings in severity order:

1. **Unmatched quote ValueError bypass (10/10)**: `env X="<<" bash <<EOF` causes `split('<<',1)` to slice mid-quote, producing `env X="` which `shlex.split()` rejects with ValueError, returning `''`. Complete silent bypass.
2. **Un-skipped prefix arguments (10/10)**: Same as Codex finding. `env -i`, etc. Only `sudo` has flag handling.
3. **Numeric FD redirect masking (9/10)**: `2>`, `{fd}>` not in the static redirect tuple. Recommended regex-based redirect detection.
4. **Sudo inline `=` argument flaw (8/10)**: `sudo --user=root` skips the `bash` token because `--user=root` is treated as an arg-taking flag consuming the next token.
5. **Incomplete wrapper allowlist (6/10)**: `timeout`, `stdbuf`, `xargs`, `unshare`, `nsenter`, `chroot`, `doas`, `su` etc. not in `skip_prefixes`.
6. **Variable expansion limits (5/10)**: `$BASH`, `$(command -v bash)` are inherent static analysis limitations.

---

## 2. Convergence Analysis

### All Three Models Agree (High Confidence)

| Finding | Claude | Codex | Gemini | Confirmed |
|---------|--------|-------|--------|-----------|
| Prefix flag-skipping gap (`env -i`, `time -p`, `command -p`) | Yes | Yes (9/10) | Yes (10/10) | Empirically verified |
| Numeric FD redirects not handled (`2>`, `0<`) | Yes | Yes (9/10) | Yes (9/10) | Empirically verified |
| `sudo --user=root` inline arg skips command | Yes | Yes (9/10) | Yes (8/10) | Empirically verified |
| Dynamic/variable command names (`$BASH`, `$(...)`) | Yes | Yes (8/10) | Yes (5/10) | Empirically verified |
| Unlisted interpreter versions (`python3.12`) | Yes | Yes (8/10) | Implicit | Empirically verified |
| Here-string/arithmetic false positives | Yes | Yes (4/10) | Not raised | Empirically verified |

### Gemini-Only Finding (Validated)

| Finding | Gemini | Confirmed |
|---------|--------|-----------|
| Quoted `<<` decoy causes ValueError bypass (`env X="<<" bash <<EOF`) | 10/10 | Empirically verified: `_extract_base_command` returns `''` |

This is the **most critical finding** from the review. It was uniquely identified by Gemini. The root cause is that `sub_cmd.split('<<', 1)[0]` is a raw string split that does not respect shell quoting. When a quoted `<<` appears before the real heredoc operator, the split point is wrong, the resulting fragment has an unmatched quote, and `shlex.split()` raises ValueError which maps to `return ''`.

### Codex-Only Emphasis

Codex uniquely emphasized the **architectural recommendation**: stop re-parsing raw text in `_is_interpreter_heredoc()` and instead propagate structured metadata (command head, heredoc presence) from `split_commands()`, which already has full syntax-aware parsing. This is the most impactful long-term fix.

### Divergence

- **Severity calibration**: Gemini rated prefix flag-skipping at 10/10 while Codex rated it 9/10. Both are appropriate given the trivial exploitability; the difference is cosmetic.
- **False positive concern**: Codex and Claude flagged here-string/arithmetic false positives; Gemini did not raise this. This is a usability issue (confirmation fatigue) rather than a safety issue.
- **Wrapper allowlist**: Gemini provided the most comprehensive list of missing wrappers (`timeout`, `stdbuf`, `xargs`, `unshare`, `nsenter`, `chroot`, `doas`, `su`). Codex mentioned this implicitly. Claude confirmed `timeout` empirically.

---

## 3. Actionable Findings with Severity Ratings

### CRITICAL (Must Fix Before Ship)

#### C1: Quoted `<<` Decoy Causes Silent Complete Bypass
- **Severity**: 10/10
- **Vector**: `env X="<<" bash <<EOF\nrm -rf /\nEOF`
- **Root cause**: `sub_cmd.split('<<', 1)[0]` is quote-unaware
- **Impact**: Complete bypass -- attacker adds any `VAR="<<"` before the real heredoc
- **Confirmed by**: Gemini (identified), Claude (empirically verified)
- **Fix**: Parse the full sub_cmd with `shlex.split()` first, then locate the `<<` token positionally; or propagate parsed token data from `split_commands()`

#### C2: Prefix Command Flags Misidentified as Base Command
- **Severity**: 9/10
- **Vectors**: `env -i bash <<EOF`, `time -p bash <<EOF`, `command -p bash <<EOF`
- **Root cause**: `skip_prefixes` handler only does `i += 1` for the prefix name; no flag skipping except for `sudo`
- **Impact**: Any flagged prefix wrapper silently bypasses detection
- **Confirmed by**: All three models; empirically verified
- **Fix**: Add generic flag-skipping (`while parts[i].startswith('-'): i += 1`) for all prefix commands, with per-command refinement where needed

#### C3: `sudo --user=root` Inline Argument Skips Command Token
- **Severity**: 8/10
- **Vector**: `sudo --user=root bash <<EOF`
- **Root cause**: `--user=root` is not in `_sudo_noarg_flags`, so the handler consumes the *next* token (`bash`) as the flag's argument
- **Impact**: The actual command is skipped; returns `''`
- **Confirmed by**: Gemini (identified), Codex (identified), Claude (empirically verified)
- **Fix**: Check for `=` in the flag before consuming the next token: `if flag not in _sudo_noarg_flags and '=' not in flag and i < len(parts): i += 1`

### HIGH (Should Fix)

#### H1: Numeric File Descriptor Redirects Not Recognized
- **Severity**: 7/10
- **Vectors**: `2> error.log bash <<EOF`, `0</dev/null bash <<EOF`
- **Root cause**: Static tuple only matches bare operators (`<`, `>`, etc.), not `2>`, `0<`, `{fd}>`
- **Confirmed by**: All three models; empirically verified
- **Fix**: Use regex: `re.match(r'^(?:\d+|\{[_a-zA-Z0-9]+\})?(?:[<>]|>>|<<|>&|&>|>\|)', part)`

#### H2: Incomplete Wrapper Allowlist
- **Severity**: 6/10
- **Vectors**: `timeout 10 bash <<EOF`, also `stdbuf`, `xargs -0`, `unshare`, `nsenter`, `chroot`, `doas`, `su`
- **Confirmed by**: Gemini (comprehensive list), Codex (implicit), Claude (timeout verified)
- **Fix**: Add `timeout`, `stdbuf`, `doas`, `su`, `chroot`, `unshare`, `nsenter` to `skip_prefixes`

#### H3: Unlisted Interpreter Versions
- **Severity**: 5/10
- **Vectors**: `python3.12 <<EOF`, `python3.11 <<EOF`, `ruby3.2 <<EOF`
- **Root cause**: `_INTERPRETER_COMMANDS` uses exact name matching
- **Confirmed by**: Codex (identified), Claude (empirically verified)
- **Fix**: Use prefix matching for versioned interpreters (e.g., `base_cmd.startswith(('python', 'ruby', 'node'))`)

### MEDIUM (Should Fix or Accept with Documentation)

#### M1: Dynamic/Variable Command Names
- **Severity**: 5/10
- **Vectors**: `$BASH <<EOF`, `${SHELL} <<EOF`, `$(command -v bash) <<EOF`
- **Root cause**: Inherent limitation of static lexical analysis
- **Confirmed by**: All three models
- **Fix**: Trigger ASK when base command starts with `$` or contains backticks and `<<` is present. Or accept as documented limitation since this is defense-in-depth.

#### M2: Here-String and Arithmetic Shift False Positives
- **Severity**: 3/10
- **Vectors**: `bash <<< "hello"`, `bash $((1<<2))`
- **Root cause**: Raw `'<<' in sub_cmd` substring check
- **Confirmed by**: Codex (identified), Claude (empirically verified)
- **Impact**: Unnecessary ASK prompts causing confirmation fatigue
- **Fix**: Reuse heredoc metadata from `split_commands()` parser, which already distinguishes `<<` (heredoc), `<<<` (here-string), and `<<` in arithmetic contexts

---

## 4. Recommended Fix Priority

**Immediate (before Phase 3 ships)**:
1. C1 (quoted `<<` decoy) -- complete bypass, trivially exploitable
2. C2 (prefix flag skipping) -- complete bypass, trivially exploitable
3. C3 (sudo `--user=` inline) -- complete bypass, trivially exploitable

**Fast follow**:
4. H1 (numeric FD redirects) -- bypass requires slightly more obscure syntax
5. H2 (wrapper allowlist) -- bypass requires wrapping in `timeout` etc.
6. H3 (versioned interpreter names) -- moderate risk

**Architectural (recommended for Phase 4)**:
7. Propagate parsed metadata from `split_commands()` instead of re-parsing raw text. This eliminates C1, M2, and reduces future maintenance burden. All three reviewers converge on this as the long-term right answer.

---

## 5. Positive Observations

All reviewers noted these strengths:
- **Integration point is correct**: Placing the check at the top of the per-sub-command loop, after `split_commands()`, is architecturally sound
- **`_extract_base_command()` baseline is solid**: Handles the common cases (bare commands, absolute paths, variable assignments, simple prefixes) well
- **Verdict escalation via `_stronger_verdict()`**: Ensures the ASK cannot be downgraded by later checks
- **Defense-in-depth framing**: ASK (not deny) is the right verdict for a backstop that may have false positives
- **Fail-closed on shlex.split ValueError**: Good security default (though C1 shows the pre-split undermines this)
