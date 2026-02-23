# Task: Fix Heredoc False Positives in bash_guardian.py

You are working in `/home/idnotbe/projects/claude-code-guardian/`. This is a Claude Code plugin that acts as a PreToolUse:Bash hook, scanning bash commands for dangerous operations before they execute.

The main script is `hooks/scripts/bash_guardian.py`. It has a **heredoc blindness bug** that causes false `[CONFIRM]` popups when any plugin writes multi-line content (like JSON) via bash heredoc syntax (`cat > file << 'EOF'`). This has caused 7 false positive popups in 20 hours for a sibling plugin (claude-memory) and affects all guardian users who use heredoc syntax.

## Important

The implementation code below is the final verified design from a multi-reviewer research process (6 independent reviewers, 2 rounds). Implement it as written; do not redesign the approach.

## Out of Scope

DO NOT attempt to fix any of the following. These are explicitly out of scope:
- The `_is_inside_quotes()` backtick blindness (it does not track backtick substitution -- this is a pre-existing limitation, not a regression; practical impact is low because backtick substitution is rare in modern bash)
- The `<<\EOF` backslash-escaped delimiter edge case (treated as bare word `\EOF` -- body consumed to end of string, which is fail-closed behavior)
- Heredoc inside `$(...)` command substitution (the existing depth tracking already prevents splitting inside `$()`, so this is not a regression)
- Any changes to `_guardian_utils.py` or other files outside `bash_guardian.py` and the new test file

## Background: How the Guardian Works

The guardian processes bash commands through multiple layers:

1. **Layer 0**: Block patterns (catastrophic commands) -- short-circuits on deny
2. **Layer 1**: `scan_protected_paths()` -- scans the **raw command string** for protected path names like `.env`, `.pem`. Called in `main()` BEFORE command splitting.
3. **Layer 2**: `split_commands()` -- decomposes compound commands into sub-commands by splitting on `;`, `&&`, `||`, `|`, `&`, `\n`. Called in `main()` AFTER Layer 1.
4. **Layer 3**: `extract_paths()` / `extract_redirection_targets()` -- extracts file paths from each sub-command
5. **Layer 4**: `is_write_command()` / `is_delete_command()` -- classifies each sub-command
6. **F1 Safety Net**: If write/delete detected but no paths resolved, escalates to `ask`

Verdict aggregation: deny > ask > allow across all layers.

## Root Cause: Three-Layer Failure Chain

When a heredoc command like this is processed:

```bash
cat > .claude/memory/.staging/input-decision.json << 'EOFZ'
{"title": "Use B->A->C pattern", "tags": ["scoring"], "content": {"decision": ".env config"}}
EOFZ
```

**Three independent bugs** cause false positives:

### Failure Mode A: "Detected write but could not resolve target paths"

1. **Layer 2 bug**: `split_commands()` splits on `\n` without heredoc awareness. The above command becomes 3 sub-commands:
   - `cat > .claude/memory/.staging/input-decision.json << 'EOFZ'` (the real command)
   - `{"title": "Use B->A->C pattern", "tags": ["scoring"], ...}` (heredoc body -- NOT a command)
   - `EOFZ` (delimiter -- NOT a command)

2. **Layer 4 bug**: `is_write_command()` matches the `>` character inside `B->A->C` in the JSON body line via regex `r">\s*['\"]?[^|&;]+"`. It has no quote awareness.

3. **F1 escalation**: `extract_paths()` finds no real file paths in the JSON body line. Since `is_write=True` and `sub_paths=[]`, the F1 safety net escalates to `ask`: "Detected write but could not resolve target paths".

### Failure Mode B: "Protected path reference detected: .env"

1. **Layer 1 bug**: `scan_protected_paths()` scans the **entire raw command string** -- including heredoc body content. If the JSON mentions `.env`, it matches the protected path pattern.
2. Layer 1 runs BEFORE `split_commands()` in `main()`, so fixing the heredoc parser alone does NOT fix this failure mode.

## Execution Plan

Follow these steps in order. Each step ends with a test run.

### Step 1: Create the test file (TDD -- tests first)

Create a new test file at `tests/test_heredoc_fixes.py`. All test classes go in this one file.

```python
"""Tests for heredoc-related fixes in bash_guardian.py.

Covers:
- Fix 1: Heredoc-aware split_commands()
- Fix 2: Quote-aware is_write_command()
- Fix 3: Heredoc-aware scan_protected_paths() via layer reorder
"""
import sys
from pathlib import Path

import pytest

# Add hooks/scripts to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "scripts"))

from bash_guardian import (
    split_commands,
    is_write_command,
    scan_protected_paths,
)


# ============================================================
# Fix 1: Heredoc-aware split_commands()
# ============================================================


class TestHeredocSplitting:
    """Tests for heredoc-aware split_commands()."""

    def test_basic_heredoc_not_split(self):
        """Basic heredoc should produce 1 sub-command."""
        assert len(split_commands("cat <<EOF\nhello\nEOF")) == 1

    def test_quoted_heredoc_not_split(self):
        """Quoted heredoc should produce 1 sub-command."""
        assert len(split_commands("cat << 'EOFZ'\ncontent with > arrows\nEOFZ")) == 1

    def test_heredoc_with_redirection(self):
        """Heredoc with file redirection should be 1 command."""
        assert len(split_commands("cat > file << 'EOF'\n{\"a\": \"B->C\"}\nEOF")) == 1

    def test_heredoc_tab_stripping(self):
        """<<- should match tab-indented delimiter."""
        assert len(split_commands("cat <<-EOF\n\tcontent\n\tEOF")) == 1

    def test_here_string_not_heredoc(self):
        """<<< is a here-string, NOT a heredoc."""
        result = split_commands("cat <<< 'hello'")
        assert len(result) == 1

    def test_multiple_heredocs_one_line(self):
        """Multiple heredocs on one line should be 1 command."""
        assert len(split_commands("cmd <<A <<'B'\nbody A\nA\nbody B\nB")) == 1

    def test_heredoc_followed_by_command(self):
        """Heredoc followed by next command on new line should be 2 commands."""
        assert len(split_commands("cat <<EOF\nbody\nEOF\necho done")) == 2

    def test_heredoc_with_arrows_in_body(self):
        """Arrows in heredoc body should not trigger write detection on body."""
        subs = split_commands("cat > file << 'EOF'\n\"B->A->C\"\nEOF")
        assert len(subs) == 1
        assert is_write_command(subs[0])  # True for the > file part

    def test_heredoc_with_semicolon_in_body(self):
        """Semicolons in heredoc body should not cause splitting.

        This is the known limitation from test_bypass_v2.py:142-146
        that should now PASS.
        """
        assert len(split_commands('cat <<EOF\n;\nEOF')) == 1

    def test_heredoc_with_double_quoted_delimiter(self):
        """Double-quoted delimiter should work."""
        assert len(split_commands('cat <<"MARKER"\nbody\nMARKER')) == 1

    def test_unterminated_heredoc(self):
        """Unterminated heredoc should consume to end (fail-closed)."""
        result = split_commands("cat <<EOF\nbody line\nno terminator")
        # Body lines should NOT appear as separate sub-commands
        assert len(result) == 1

    def test_heredoc_inside_command_substitution(self):
        """Heredoc inside $() should not trigger (depth > 0)."""
        result = split_commands('echo $(cat <<EOF\nbody\nEOF\n)')
        # depth > 0 inside $(), so << is not detected
        # The existing behavior keeps $() as one chunk
        assert len(result) >= 1

    def test_real_memory_plugin_command(self):
        """The exact command that triggers false positives in production."""
        cmd = '''cat > .claude/memory/.staging/input-decision.json << 'EOFZ'
{"title": "Use B->A->C pattern", "tags": ["scoring"], "content": {"decision": "chose B->A"}}
EOFZ'''
        subs = split_commands(cmd)
        assert len(subs) == 1
        assert is_write_command(subs[0])


class TestArithmeticBypassPrevention:
    """Verify that (( x << 2 )) arithmetic shift is NOT mistaken for heredoc.

    CRITICAL SECURITY TEST: If these fail, the heredoc fix has introduced
    a security bypass where commands can be hidden from the guardian.
    """

    def test_arithmetic_shift_not_heredoc(self):
        """(( x << 2 )) followed by command -- command must remain visible."""
        subs = split_commands("(( x << 2 ))\nrm -rf /")
        # rm -rf / must NOT be consumed as heredoc body
        assert any("rm" in sub for sub in subs), \
            "rm -rf / was consumed as heredoc body -- arithmetic bypass!"

    def test_let_shift_is_heredoc(self):
        """let val<<1 IS a heredoc in bash (let does not create arithmetic context).

        Bash tokenizes << as heredoc before let can interpret it as arithmetic.
        So 'echo done' is consumed as heredoc body. This is correct behavior.
        """
        subs = split_commands("let val<<1\necho done")
        # echo done IS consumed as heredoc body (delimiter '1' != 'echo done')
        assert not any("echo" in sub for sub in subs), \
            "echo done should be consumed as heredoc body for let val<<1"


    def test_no_space_heredoc(self):
        """cat<<EOF (no space before <<) should be detected as heredoc."""
        assert len(split_commands("cat<<EOF\nbody\nEOF")) == 1

    def test_dollar_double_paren_not_affected(self):
        """$(( x << 2 )) should not be misdetected (existing depth tracking handles it)."""
        subs = split_commands("echo $(( x << 2 ))\necho done")
        assert any("echo done" in sub for sub in subs)


class TestParseHeredocDelimiter:
    """Tests for _parse_heredoc_delimiter helper."""

    def test_bare_word(self):
        from bash_guardian import _parse_heredoc_delimiter
        delim, raw, pos = _parse_heredoc_delimiter("EOF\nrest", 0)
        assert delim == "EOF"
        assert raw == "EOF"

    def test_single_quoted(self):
        from bash_guardian import _parse_heredoc_delimiter
        delim, raw, pos = _parse_heredoc_delimiter("'EOFZ'\nrest", 0)
        assert delim == "EOFZ"
        assert raw == "'EOFZ'"

    def test_double_quoted(self):
        from bash_guardian import _parse_heredoc_delimiter
        delim, raw, pos = _parse_heredoc_delimiter('"END"\nrest', 0)
        assert delim == "END"
        assert raw == '"END"'

    def test_empty_at_eof(self):
        from bash_guardian import _parse_heredoc_delimiter
        delim, raw, pos = _parse_heredoc_delimiter("", 0)
        assert delim == ""


# ============================================================
# Fix 2: Quote-aware is_write_command()
# ============================================================


class TestWriteCommandQuoteAwareness:
    """Tests for quote-aware is_write_command()."""

    def test_arrow_in_double_quotes_not_write(self):
        """'>' inside double quotes is not redirection."""
        assert not is_write_command('echo "B->A->C"')

    def test_score_comparison_in_quotes_not_write(self):
        """'score > 8' inside quotes is not redirection."""
        assert not is_write_command('echo "score > 8"')

    def test_git_commit_message_with_gt(self):
        """git commit -m with > in message is not a write."""
        assert not is_write_command('git commit -m "value > threshold"')

    def test_real_redirection_still_detected(self):
        """Actual file redirection must still be detected."""
        assert is_write_command("echo hello > output.txt")

    def test_tee_still_detected(self):
        """tee is always a write regardless of quotes."""
        assert is_write_command("echo hello | tee output.txt")

    def test_truncation_outside_quotes_detected(self):
        """: > file (truncation) outside quotes is a write."""
        assert is_write_command(": > file.txt")

    def test_quoted_gt_then_real_redirect(self):
        """First > in quotes, second > is real redirect -- must detect write."""
        assert is_write_command('echo "value > threshold" > output.txt')

    def test_multiple_quoted_gt_then_real_redirect(self):
        """Multiple quoted > chars, then real redirect."""
        assert is_write_command('echo "a > b" "c > d" > output.txt')


# ============================================================
# Fix 3: Heredoc-aware scan_protected_paths() via layer reorder
# ============================================================


class TestScanProtectedPathsHeredocAware:
    """Tests for heredoc-aware protected path scanning.

    After Fix 3, scan_protected_paths() runs on split sub-commands
    (which exclude heredoc bodies) instead of the raw command string.
    """

    def test_env_in_heredoc_body_not_flagged(self):
        """'.env' appearing in heredoc body should not be in sub-commands."""
        cmd = "cat > staging/file.json << 'EOF'\n{\"content\": \".env config\"}\nEOF"
        subs = split_commands(cmd)
        joined = ' '.join(subs)
        # .env should not appear in the joined sub-commands
        assert ".env" not in joined, \
            f".env found in sub-commands (should be in masked heredoc body): {subs}"

    def test_env_in_command_still_present(self):
        """'.env' in actual command part must still be in sub-commands."""
        cmd = "cat .env"
        subs = split_commands(cmd)
        joined = ' '.join(subs)
        assert ".env" in joined
```

After creating the file, run `pytest tests/test_heredoc_fixes.py -v` to verify the tests fail (establishing a baseline). Most tests should fail because the fixes are not yet implemented.

### Step 2: Implement Fix 2 -- Make `is_write_command()` quote-aware

This is the simplest fix. Do it first because it does not affect line numbers for the other fixes.

**Where**: In `hooks/scripts/bash_guardian.py`, find the function `is_write_command`. It is in the "Layer 4: Command Type Detection" section, right after `is_delete_command()`. It currently uses `any(re.search(...))` with a flat list of regex patterns.

**What to change**: Replace the flat pattern list with a list of `(pattern, needs_quote_check)` tuples, and use `_is_inside_quotes()` (which already exists in the "Layer 3: Enhanced Path Extraction" section) to filter matches on `>` patterns.

**Current code:**

```python
def is_write_command(command: str) -> bool:
    write_patterns = [
        r">\s*['\"]?[^|&;]+",  # Redirection (existing)
        r"\btee\s+",  # tee (with word boundary)
        r"\bmv\s+",  # mv (with word boundary)
        r"(?<![A-Za-z-])ln\s+",  # ...
        r"\bsed\s+.*-[^-]*i",
        r"\bcp\s+",
        r"\bdd\s+",
        r"\bpatch\b",
        r"\brsync\s+",
        r":\s*>",  # Truncation via : > file
        r"\bchmod\s+",
        r"\btouch\s+",
        r"\bchown\s+",
        r"\bchgrp\s+",
    ]
    return any(re.search(p, command, re.IGNORECASE) for p in write_patterns)
```

**Replace with:**

```python
def is_write_command(command: str) -> bool:
    write_patterns = [
        (r">\s*['\"]?[^|&;]+", True),    # Redirection -- needs quote check
        (r"\btee\s+", False),
        (r"\bmv\s+", False),
        (r"(?<![A-Za-z-])ln\s+", False),
        (r"\bsed\s+.*-[^-]*i", False),
        (r"\bcp\s+", False),
        (r"\bdd\s+", False),
        (r"\bpatch\b", False),
        (r"\brsync\s+", False),
        (r":\s*>", True),                  # Truncation -- needs quote check
        (r"\bchmod\s+", False),
        (r"\btouch\s+", False),
        (r"\bchown\s+", False),
        (r"\bchgrp\s+", False),
    ]
    for pattern, needs_quote_check in write_patterns:
        for match in re.finditer(pattern, command, re.IGNORECASE):
            if needs_quote_check and _is_inside_quotes(command, match.start()):
                continue  # Skip this occurrence: > is inside a quoted string
            return True
    return False
```

After implementing, run `pytest tests/test_heredoc_fixes.py::TestWriteCommandQuoteAwareness -v`. All 8 tests should pass.

### Step 3: Implement Fix 1 -- Add heredoc awareness to `split_commands()`

This is the most important fix.

**Where**: In `hooks/scripts/bash_guardian.py`, find the function `split_commands()`. It is in the "Layer 2: Command Decomposition" section at the top of the file.

**What to add -- 3 changes inside `split_commands()`:**

**(3a)** Add two new variables after the existing state variables (`in_backtick`, `i = 0`):

```python
pending_heredocs: list[tuple[str, bool]] = []  # (delimiter, strip_tabs)
arithmetic_depth = 0  # tracks (( ... )) nesting for arithmetic context
```

**(3b)** Inside the `if depth == 0:` block, **immediately before** the block starting with `if c == "\n":` (the newline handler), add arithmetic context tracking AND heredoc detection:

```python
            # Track arithmetic context: (( ... ))
            # This prevents << inside (( )) from being misdetected as heredoc.
            # Note: $(( is already handled by the existing depth tracking
            # (the $( part increments depth), so we only need to catch bare ((.
            if (command[i:i+2] == '(('
                    and (i == 0 or command[i-1] not in ('$', '<', '>'))):
                arithmetic_depth += 1
                current.append('((')
                i += 2
                continue

            if command[i:i+2] == '))' and arithmetic_depth > 0:
                arithmetic_depth -= 1
                current.append('))')
                i += 2
                continue

            # Detect heredoc operator: << or <<- (but NOT <<< here-string)
            # Only detect when outside arithmetic context (arithmetic_depth == 0)
            if (command[i:i+2] == '<<'
                    and command[i:i+3] != '<<<'
                    and arithmetic_depth == 0):

                strip_tabs = command[i:i+3] == '<<-'
                op_len = 3 if strip_tabs else 2
                current.append(command[i:i+op_len])
                i += op_len

                # Skip optional whitespace between << and delimiter
                while i < len(command) and command[i] in ' \t':
                    current.append(command[i])
                    i += 1

                # Parse delimiter word: bare, 'quoted', or "quoted"
                delim, raw_token, i = _parse_heredoc_delimiter(command, i)
                current.append(raw_token)
                pending_heredocs.append((delim, strip_tabs))
                continue
```

**(3c)** Replace the existing newline handler (`if c == "\n":` block inside `if depth == 0:`) with:

```python
            # Newline
            if c == "\n":
                sub_commands.append("".join(current).strip())
                current = []
                i += 1
                # Consume heredoc bodies after newline
                if pending_heredocs:
                    i = _consume_heredoc_bodies(command, i, pending_heredocs)
                    pending_heredocs = []
                continue
```

**What to add -- 2 new top-level helper functions:**

Add these as **module-level functions** in the file, right after the end of `split_commands()` and before the "Layer 1: Protected Path Scan" section comment. Do NOT nest them inside `split_commands()`.

```python
def _parse_heredoc_delimiter(command: str, i: int) -> tuple[str, str, int]:
    """Parse heredoc delimiter word from position i.

    Handles:
      - Bare word: EOF, EOFZ, END_MARKER
      - Single-quoted: 'EOF' (literal heredoc, no expansion)
      - Double-quoted: "EOF" (expansion-active heredoc)

    Returns: (delimiter_text, raw_token, new_position)
    """
    if i >= len(command):
        return ('', '', i)

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


def _consume_heredoc_bodies(command: str, i: int,
                             pending: list[tuple[str, bool]]) -> int:
    """Consume heredoc body lines until each delimiter is matched.

    For each pending heredoc, reads lines until a line matches the
    delimiter exactly (after optional tab-stripping for <<-).

    Returns: new position after all heredoc bodies consumed.
    """
    for delim, strip_tabs in pending:
        while i < len(command):
            # Find end of current line
            line_start = i
            while i < len(command) and command[i] != '\n':
                i += 1
            line = command[line_start:i]

            # Advance past newline
            if i < len(command):
                i += 1

            # Check if this line matches the delimiter
            cmp_line = line.rstrip('\r')
            if strip_tabs:
                cmp_line = cmp_line.lstrip('\t')
            if cmp_line == delim:
                break
        # If we exhaust the input without finding the delimiter,
        # we've consumed an unterminated heredoc -- body lines
        # won't leak to sub-commands (fail-closed behavior)
    return i
```

**About the arithmetic bypass guard**: The heredoc detection is gated on `arithmetic_depth == 0`, which prevents `<<` inside `(( ... ))` from being misdetected as a heredoc. The `arithmetic_depth` counter increments when `((` is found at depth 0 (excluding `$((` which is already tracked by the existing `depth` counter), and decrements on `))`. This correctly distinguishes `(( x << 2 ))` (arithmetic shift, NOT heredoc) from `cat << EOF` (heredoc). Note that `cat<<EOF` (no space) IS correctly detected as heredoc because there is no lookbehind requirement. This is the mandatory mitigation.

After implementing, run:
```bash
pytest tests/test_heredoc_fixes.py::TestHeredocSplitting tests/test_heredoc_fixes.py::TestArithmeticBypassPrevention tests/test_heredoc_fixes.py::TestParseHeredocDelimiter -v
```

All heredoc and arithmetic bypass tests should pass.

### Step 4: Implement Fix 3 -- Reorder Layer 1 after Layer 2 in `main()`

This is the simplest approach to make `scan_protected_paths()` heredoc-aware: move `split_commands()` to run BEFORE `scan_protected_paths()`, then scan the joined sub-commands (which no longer contain heredoc body content) instead of the raw command string.

**Where**: In `hooks/scripts/bash_guardian.py`, find the `main()` function. Look for the section with the comments `# ========== Layer 1: Protected Path Scan ==========` and `# ========== Layer 2+3+4: Command Decomposition + Path Analysis ==========`.

**Current order in `main()`:**
```python
    # ========== Layer 1: Protected Path Scan ==========
    scan_verdict, scan_reason = scan_protected_paths(command, config)
    ...

    # ========== Layer 2+3+4: Command Decomposition + Path Analysis ==========
    sub_commands = split_commands(command)
    ...
```

**Change to:**
```python
    # ========== Layer 2: Command Decomposition (moved before Layer 1) ==========
    sub_commands = split_commands(command)

    # ========== Layer 1: Protected Path Scan ==========
    # Scan joined sub-commands instead of raw command string.
    # After heredoc-aware split_commands(), heredoc body content is excluded,
    # so .env/.pem in heredoc bodies no longer trigger false positives.
    scan_text = ' '.join(sub_commands)
    scan_verdict, scan_reason = scan_protected_paths(scan_text, config)
    if scan_verdict != "allow":
        final_verdict = _stronger_verdict(final_verdict, (scan_verdict, scan_reason))
        log_guardian("SCAN", f"Layer 1 {scan_verdict}: {scan_reason}")

    # ========== Layer 3+4: Per-Sub-Command Analysis ==========
    # sub_commands already computed above, remove the duplicate assignment
    all_paths: list[Path] = []
    ...
```

Remove the duplicate `sub_commands = split_commands(command)` line that was previously in the Layer 2+3+4 section -- it is now computed above.

After implementing, run the full test suite:
```bash
pytest tests/test_heredoc_fixes.py -v
pytest tests/ -v
```

All tests should pass, including the new heredoc tests and all existing tests.

### Step 5: Final verification

1. **Compile check**: `python3 -m py_compile hooks/scripts/bash_guardian.py`
2. **Full test suite**: `pytest tests/ -v`
3. **Check the known limitation test**: `tests/security/test_bypass_v2.py` is a standalone script (NOT a pytest file). It contains a heredoc test at lines 142-146 that documents the heredoc splitting limitation. After your fix, running `python3 tests/security/test_bypass_v2.py` should show this test passing (it previously failed because `split_commands('cat <<EOF\n;\nEOF')` produced 3 sub-commands instead of 1).
4. **Version bump**: If a plugin manifest or version file exists, bump to 1.1.0.

## Edge Cases Reference

| Edge Case | Expected Handling |
|-----------|----------|
| `<<<` (here-string) | Excluded by checking `command[i:i+3] != '<<<'` |
| Multiple heredocs on one line: `cmd <<A <<'B'` | Queue processes all pending in order |
| `<<-` tab stripping | Only strips tabs (not spaces) from delimiter comparison |
| Quoted delimiters (`'EOF'`, `"EOF"`) | Quotes stripped for delimiter matching |
| Unterminated heredoc at EOF | Body consumed to end of string; no lines leak to sub-commands |
| `<<` inside quotes/backticks/subshells | Already skipped by existing quote/backtick/depth tracking |
| Commands after heredoc body | Resume normal parsing at position after delimiter line |
| CRLF line endings | `rstrip('\r')` on delimiter comparison lines |
| `(( x << 2 ))` arithmetic shift | NOT detected as heredoc -- `arithmetic_depth > 0` gates it out |
| `$(( x << 2 ))` dollar arithmetic | NOT detected as heredoc -- existing `depth > 0` handles it |
| `let val<<1` | IS detected as heredoc (bash tokenizer sees `<<` before `let` can evaluate arithmetic) |
| `cat<<EOF` (no space) | IS detected as heredoc (no lookbehind requirement) |
| `<<\EOF` (backslash-escaped) | Out of scope. Treated as bare word `\EOF` -- body consumed to end of string (fail-closed) |
| `arr[x<<1]=5` (array subscript) | Known limitation: `<<` may be misdetected as heredoc (fails closed, not a security bypass) |

## Key Landmarks in bash_guardian.py

Use these semantic landmarks to find the right locations (line numbers may shift as you edit):

| Landmark | How to Find |
|----------|------------|
| `split_commands()` function | Search for `def split_commands(command: str)` -- it's in the "Layer 2: Command Decomposition" section |
| State variables | Inside `split_commands()`, look for `depth = 0` / `in_single_quote = False` / `in_backtick = False` / `i = 0` |
| The `depth == 0` block | Inside the `while i < len(command):` loop, look for `if depth == 0:` |
| Newline handler | Inside the `depth == 0` block, look for `if c == "\n":` |
| `_is_inside_quotes()` helper | Search for `def _is_inside_quotes` -- it's in the "Layer 3: Enhanced Path Extraction" section |
| `is_write_command()` function | Search for `def is_write_command` -- it's in the "Layer 4: Command Type Detection" section |
| `scan_protected_paths()` call in main | Search for `scan_protected_paths(command, config)` inside `def main()` |
| `split_commands()` call in main | Search for `sub_commands = split_commands(command)` inside `def main()` |
| F1 safety net | Search for `if (is_write or is_delete) and not sub_paths:` inside `main()` |
