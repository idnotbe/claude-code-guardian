#!/usr/bin/env python3
# PLUGIN MIGRATION: Migrated from ops/.claude/hooks/ to plugin structure
# Import paths unchanged - scripts are colocated in hooks/scripts/

"""Bash Guardian Hook - Full Implementation.

Protects against dangerous bash commands by:
1. Blocking catastrophic patterns (force push, etc.)
2. Scanning raw command for protected path references (Layer 1)
3. Decomposing compound commands for per-sub-command analysis (Layer 2)
4. Enhanced path extraction with redirection and non-existent file support (Layer 3)
5. Expanded write/delete type detection (Layer 4)
6. Archiving untracked files before deletion
7. Verdict aggregation: deny > ask > allow across all layers

Phase: 3 (Bash Bypass Protection)
"""

import glob
import json
import os
import re
import secrets
import shlex
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from _guardian_utils import (
        COMMIT_MESSAGE_MAX_LENGTH,  # Import constant for message length
        ask_response,
        deny_response,
        get_hook_behavior,  # hookBehavior config support
        get_project_dir,
        git_add_tracked,
        git_commit,
        git_has_changes,
        git_has_staged_changes,  # FIX: Check staged changes before commit
        git_is_tracked,
        is_dry_run,
        is_rebase_or_merge_in_progress,  # Phase 5: Fragile state check
        is_symlink_escape,
        load_guardian_config,
        log_guardian,
        make_hook_behavior_response,  # hookBehavior response helper
        match_allowed_external_path,
        match_ask_patterns,
        match_block_patterns,
        match_no_delete,
        match_read_only,
        match_zero_access,
        set_circuit_open,  # Phase 4 Fix: Circuit Breaker
        truncate_command,
        validate_commit_prefix,  # m3 FIX: centralized prefix validation
    )
except ImportError as e:
    # Fail-close: guardian system unavailable = block all
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Guardian system unavailable: {e}",
                }
            }
        )
    )
    sys.exit(0)


# ============================================================
# Layer 2: Command Decomposition + Heredoc Redaction
# ============================================================

# Passive data sinks: commands that process data, never execute it.
# Heredoc bodies feeding these commands are safe to redact.
# V1 fix (F1-2): tee REMOVED — writes to files without > operator.
# sort excluded — has -o output flag.
_PASSIVE_DATA_SINKS = frozenset({
    'cat',
    'grep', 'egrep', 'fgrep', 'head', 'tail', 'wc', 'uniq',
    'cut', 'tr', 'fold', 'fmt', 'column', 'paste', 'join', 'comm',
    'echo', 'printf',
    'jq', 'yq',
    'diff', 'cmp', 'md5sum', 'sha256sum', 'sha1sum',
})

# Interpreter commands: ALWAYS unsafe for heredoc redaction.
_INTERPRETER_COMMANDS = frozenset({
    'bash', 'sh', 'zsh', 'dash', 'ksh', 'csh', 'tcsh', 'fish',
    'python', 'python2', 'python3', 'py',
    'node', 'deno', 'bun',
    'perl', 'ruby',
    'source', '.', 'eval', 'exec',
})

# V1 fix: Versioned interpreter regex for commands like python3.10, python3.12.
# Exact frozenset match misses these; AI agents commonly use pyenv/system versions.
# V2 fix: Allow hyphenated versions (bash-5.0), letter suffixes (python3.8m),
# and broader version patterns. Requires digit or hyphen after base name to avoid
# matching unrelated tools (e.g., 'shred', 'perldoc').
_VERSIONED_INTERPRETER_RE = re.compile(
    r'^(?:python[23]?|ruby|perl|bash|sh|zsh|dash|ksh)(?:[-\d][\w.-]*)$'
)

# Output redirection operators that make a heredoc UNSAFE (body written to file).
# V1 fix (F1-3): >&file added with negative lookahead for fd duplication (>&2).
# V2 fix: Only exempt >&0, >&1, >&2, >&- (standard fds + close). Treat >&3+
# as output redirect since those fds may point to files opened by prior commands.
_OUTPUT_REDIR_PATTERN = re.compile(
    r'(?:'
    r'[0-9]*>{1,2}'        # >, >>, 2>, 2>>, n>, n>>
    r'|[0-9]*>\|'          # >| (clobber), n>|
    r'|&>'                  # &> (redirect both stdout+stderr)
    r'|[0-9]*>&(?!\s*(?:[012]|-)(?:[\s;&|)]|$))'  # >&file (only exempt >&0/1/2/-)
    r')'
    r'\s*[^\s&|;)>]'       # followed by a target (not another operator)
)


def _extract_base_command(cmd_text: str) -> str:
    """Extract the base command name from a command string.

    Handles env prefixes, variable assignments, sudo, absolute paths,
    and I/O redirect tokens before the command.

    V2 fix: skips I/O redirect tokens (< file, > file) before the command.

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
        return ''

    skip_prefixes = {'env', 'command', 'builtin', 'sudo', 'nice',
                     'nohup', 'time', 'strace'}
    i = 0
    while i < len(parts):
        part = parts[i]

        # Skip I/O redirect tokens: <, >, >>, <<, and their targets
        if part in ('<', '>', '>>', '<<', '>&', '&>', '>|'):
            i += 2  # skip operator + target
            continue
        # Handle combined redirect+target (e.g., <file, >file)
        if len(part) >= 2 and part[0] in '<>' and part[1] not in '<>':
            i += 1
            continue

        # Variable assignment: contains = before any /
        if '=' in part and '/' not in part.split('=')[0]:
            i += 1
            continue

        # Known prefix commands (skip, move to next)
        base = Path(part).name if '/' in part else part
        if base.lower() in skip_prefixes:
            i += 1
            if base.lower() == 'sudo':
                # V2 fix: no-arg allowlist (fail-closed for unknown flags).
                # Unknown flags assumed to take an argument → fail-closed
                # (returns '' → Rule 5 UNSAFE).
                _sudo_noarg_flags = {
                    '-A', '-b', '-E', '-e', '-H', '-h', '-i',
                    '-K', '-k', '-l', '-n', '-P', '-S', '-s', '-V', '-v',
                }
                while i < len(parts) and parts[i].startswith('-'):
                    flag = parts[i]
                    i += 1
                    if flag == '--':
                        break  # -- terminates sudo flags
                    if flag not in _sudo_noarg_flags and '=' not in flag and i < len(parts):
                        i += 1  # arg-taking or unknown flag: skip argument
                    # V2 Phase 3 fix: --flag=value (GNU-style inline argument)
                    # already contains its argument, so do NOT skip next token
            continue

        # This is the actual command
        base = Path(part).name if '/' in part else part
        return base.lower()

    return ''


def _classify_heredoc_safety(
    cmd_before_heredoc: str, was_piped: bool, full_segment: str = ''
) -> bool:
    """Classify whether a heredoc body is safe to redact.

    Uses a 5-rule hybrid classifier:
      1. Interpreter command -> UNSAFE (retain body)
      2. Output redirection present -> UNSAFE (retain body)
      3. Pipeline member (heredoc crossed a pipe) -> UNSAFE (retain body)
      4. Passive data sink -> SAFE (redact body)
      5. Unknown command -> UNSAFE (fail-closed, retain body)

    Args:
        cmd_before_heredoc: The command text preceding the << operator.
        was_piped: Whether the heredoc crossed a pipe boundary.
        full_segment: The full sub-command text containing the <<, including
            text after << (e.g., redirects). V1 fix: redirect check uses this
            to catch post-<< redirects like `cat << EOF > script.sh`.

    Returns:
        True if the heredoc body is safe to redact, False otherwise.
    """
    # Rule 3: Pipeline membership (checked first because it's a flag, not text)
    if was_piped:
        return False

    base_cmd = _extract_base_command(cmd_before_heredoc)

    # Rule 1: Interpreter commands are always unsafe
    if base_cmd in _INTERPRETER_COMMANDS:
        return False

    # Rule 2: Output redirection makes the heredoc unsafe
    # V1 fix: check full segment (includes post-<< redirects like > file)
    check_text = full_segment or cmd_before_heredoc
    if _OUTPUT_REDIR_PATTERN.search(check_text):
        return False

    # Rule 4: Passive data sinks are safe
    if base_cmd in _PASSIVE_DATA_SINKS:
        return True

    # Rule 5: Unknown commands fail-closed
    return False


def _is_interpreter_heredoc(sub_cmd: str) -> bool:
    """Check if a sub-command is an interpreter with a heredoc operator.

    Defense-in-depth backstop: even with Phase 1 heredoc body retention,
    block patterns using [^|&\\n]* cannot match across newline boundaries
    in retained bodies. This detects the pattern and escalates to ASK.

    Uses _extract_base_command() for robust interpreter detection, handling:
    - env/sudo/nohup/nice prefixes
    - Absolute paths (/usr/bin/bash)
    - Variable assignments (FOO=bar bash << EOF)
    - I/O redirect tokens before the command

    Args:
        sub_cmd: A single sub-command string from split_commands().

    Returns:
        True if the sub-command is an interpreter with heredoc.
    """
    if '<<' not in sub_cmd:
        return False

    # Extract command portion before the heredoc operator
    cmd_before = sub_cmd.split('<<', 1)[0]
    base_cmd = _extract_base_command(cmd_before)
    if base_cmd in _INTERPRETER_COMMANDS:
        return True
    # V1 fix: Handle versioned interpreters (e.g., python3.10, python3.12)
    if base_cmd and _VERSIONED_INTERPRETER_RE.match(base_cmd):
        return True
    return False


def split_commands(command: str, redact_safe_heredocs: bool = False
                   ) -> 'list[str] | tuple[list[str], str]':
    """Split compound command into sub-commands.

    Handles delimiters: ;  &&  ||  |  &  newline

    Does NOT split inside:
    - Single-quoted strings ('...')
    - Double-quoted strings ("...")
    - Command substitution ($(...))
    - Process substitution (<(...) or >(...))
    - Backtick substitution (backtick...backtick)
    - Backslash-escaped characters
    - Parameter expansion (${...})
    - Bare subshells ((...))
    - Brace groups ({ ...; })
    - Conditional expressions ([[ ... ]])
    - Extglob patterns (?(...), *(...), +(...), @(...), !(...))
    - Arithmetic expressions ((( ... )))

    When redact_safe_heredocs=True, also produces a redacted version of
    the command with safe heredoc bodies replaced by empty lines. Safe
    means the heredoc feeds a passive data sink (cat, grep, etc.) with
    no output redirection and no pipeline. Unsafe bodies (interpreters,
    write-to-file, piped, unknown) are retained.

    Critical fixes incorporated:
    - C-2: Backslash escapes and backtick substitution handling
    - M-4: Single & as command separator
    - F1-1: Heredoc origin tracking at << parse time

    Args:
        command: The compound bash command to split.
        redact_safe_heredocs: If True, return (sub_commands, redacted_command).

    Returns:
        If redact_safe_heredocs is False: list of sub-command strings.
        If redact_safe_heredocs is True: tuple of (sub_commands, redacted_command).
    """
    sub_commands: list[str] = []
    current: list[str] = []
    depth = 0  # Track nesting: $(), <(), >()
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    i = 0
    pending_heredocs: list[tuple[str, bool]] = []  # (delimiter, strip_tabs)
    # Redaction support (F1-1): track heredoc origins and body ranges
    all_body_ranges: list[tuple[int, int, bool]] = []  # (start, end, is_safe)
    # (origin_cmd, was_piped, full_segment, is_quoted)
    # full_segment: full sub-command text (filled at separator/newline time)
    # is_quoted: delimiter was quoted (suppresses expansion in bash)
    heredoc_origins: list[tuple[str, bool, 'str | None', bool]] = []
    arithmetic_depth = 0  # tracks (( ... )) nesting for arithmetic context
    param_expansion_depth = 0  # tracks ${ ... } nesting
    bracket_depth = 0  # tracks [[ ... ]] nesting
    brace_group_depth = 0  # tracks { ...; } brace groups
    extglob_depth = 0  # tracks extglob ?() *() +() @() !() nesting

    while i < len(command):
        c = command[i]

        # Backslash escape handling (outside single quotes)
        # C-2 fix: \; should NOT be treated as a delimiter
        if c == "\\" and not in_single_quote:
            # Consume backslash + next character as literal
            current.append(c)
            if i + 1 < len(command):
                i += 1
                current.append(command[i])
            i += 1
            continue

        # Single quote tracking (not inside double quotes or backticks)
        if c == "'" and not in_double_quote and not in_backtick and depth == 0:
            in_single_quote = not in_single_quote
            current.append(c)
            i += 1
            continue

        # Double quote tracking (not inside single quotes or backticks)
        if c == '"' and not in_single_quote and not in_backtick and depth == 0:
            in_double_quote = not in_double_quote
            current.append(c)
            i += 1
            continue

        # Skip everything inside quotes
        if in_single_quote or in_double_quote:
            current.append(c)
            i += 1
            continue

        # C-2 fix: Backtick substitution tracking
        if c == "`" and depth == 0:
            in_backtick = not in_backtick
            current.append(c)
            i += 1
            continue

        # Skip everything inside backticks
        if in_backtick:
            current.append(c)
            i += 1
            continue

        # Track nesting depth for $(), <(), >()
        if c == "(" and i > 0 and command[i - 1] in ("$", "<", ">"):
            depth += 1
            current.append(c)
            i += 1
            continue
        if c == "(" and depth > 0:
            depth += 1
            current.append(c)
            i += 1
            continue
        if c == ")" and depth > 0:
            depth -= 1
            current.append(c)
            i += 1
            continue

        # --- Context tracking (BEFORE separator checks) ---
        # All context entry/exit must happen before separators so that
        # delimiters inside these constructs are suppressed correctly.

        # Track ${...} parameter expansion
        if c == "$" and i + 1 < len(command) and command[i + 1] == "{":
            param_expansion_depth += 1
            current.append("${")
            i += 2
            continue

        # Track } for parameter expansion (only when inside ${} and not
        # inside a nested command substitution where } is literal)
        if c == "}" and param_expansion_depth > 0 and depth == 0:
            param_expansion_depth -= 1
            current.append(c)
            i += 1
            continue

        # Skip everything inside ${...} (but still track nested ${} and $())
        if param_expansion_depth > 0 and depth == 0:
            # Track nested ${ inside parameter expansion
            if c == "$" and i + 1 < len(command) and command[i + 1] == "{":
                param_expansion_depth += 1
                current.append("${")
                i += 2
                continue
            current.append(c)
            i += 1
            continue

        # Track [[ ... ]] conditional expressions
        if (command[i:i+2] == "[["
                and (i == 0 or command[i-1] in " \t\n;|&(")
                and i + 2 < len(command) and command[i+2] in " \t"):
            bracket_depth += 1
            current.append("[[")
            i += 2
            continue

        # V2-fix: depth == 0 guard prevents ]] inside $() from decrementing
        if (command[i:i+2] == "]]" and bracket_depth > 0 and depth == 0):
            bracket_depth -= 1
            current.append("]]")
            i += 2
            continue

        # Skip separators inside [[ ... ]]
        if bracket_depth > 0:
            current.append(c)
            i += 1
            continue

        # Track arithmetic context: (( ... ))
        # Must come BEFORE bare-paren and separator checks.
        # Note: $(( is already handled by the $() depth tracking.
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

        # Skip separators inside (( ... ))
        if arithmetic_depth > 0:
            current.append(c)
            i += 1
            continue

        # Track extglob patterns: ?() *() +() @() !()
        if (c in "?*+@!" and i + 1 < len(command) and command[i + 1] == "("
                and depth == 0):
            extglob_depth += 1
            current.append(c)
            current.append("(")
            i += 2
            continue

        if c == ")" and extglob_depth > 0:
            extglob_depth -= 1
            current.append(c)
            i += 1
            continue

        # Skip separators inside extglob
        if extglob_depth > 0:
            # Track nested extglob
            if (c in "?*+@!" and i + 1 < len(command)
                    and command[i + 1] == "("):
                extglob_depth += 1
                current.append(c)
                current.append("(")
                i += 2
                continue
            current.append(c)
            i += 1
            continue

        # Track bare (...) subshells (not $(), <(), >(), or (())
        if c == "(" and depth == 0:
            # Not preceded by $, <, > (those are handled above)
            if i == 0 or command[i - 1] not in ("$", "<", ">"):
                depth += 1
                current.append(c)
                i += 1
                continue

        # Track { ... } brace groups
        # { is a reserved word only when it's a standalone token:
        # preceded by whitespace/SOL and followed by whitespace
        if (c == "{" and brace_group_depth == 0
                and (i == 0 or command[i-1] in " \t\n;|&(")
                and i + 1 < len(command) and command[i+1] in " \t\n"):
            # Make sure this is not ${ (already handled above)
            if i == 0 or command[i-1] != "$":
                brace_group_depth += 1
                current.append(c)
                i += 1
                continue

        # Track nested { inside brace groups
        if (c == "{" and brace_group_depth > 0
                and (command[i-1] in " \t\n;|&(" if i > 0 else True)
                and i + 1 < len(command) and command[i+1] in " \t\n"):
            brace_group_depth += 1
            current.append(c)
            i += 1
            continue

        # } closes brace group when it's a standalone token
        # V2-fix: depth == 0 guard prevents } inside $() from decrementing
        if (c == "}" and brace_group_depth > 0 and depth == 0):
            brace_group_depth -= 1
            current.append(c)
            i += 1
            continue

        # Skip separators inside brace groups
        if brace_group_depth > 0:
            current.append(c)
            i += 1
            continue

        # --- Separator checks (only at top level, depth == 0) ---
        if depth == 0:
            # Semicolon
            if c == ";":
                sub_commands.append("".join(current).strip())
                # V1 fix: finalize full_segment for pending heredoc origins
                if redact_safe_heredocs and heredoc_origins:
                    _seg = sub_commands[-1]
                    heredoc_origins = [
                        (c_, p, _seg if s is None else s, q)
                        for c_, p, s, q in heredoc_origins
                    ]
                current = []
                i += 1
                continue
            # && (two ampersands)
            if c == "&" and i + 1 < len(command) and command[i + 1] == "&":
                sub_commands.append("".join(current).strip())
                if redact_safe_heredocs and heredoc_origins:
                    _seg = sub_commands[-1]
                    heredoc_origins = [
                        (c_, p, _seg if s is None else s, q)
                        for c_, p, s, q in heredoc_origins
                    ]
                current = []
                i += 2
                continue
            # || (two pipes)
            if c == "|" and i + 1 < len(command) and command[i + 1] == "|":
                sub_commands.append("".join(current).strip())
                if redact_safe_heredocs and heredoc_origins:
                    _seg = sub_commands[-1]
                    heredoc_origins = [
                        (c_, p, _seg if s is None else s, q)
                        for c_, p, s, q in heredoc_origins
                    ]
                current = []
                i += 2
                continue
            # | (single pipe, not ||)
            if c == "|":
                sub_commands.append("".join(current).strip())
                # F1-1: Mark pending heredocs as piped + finalize full_segment
                if pending_heredocs and redact_safe_heredocs:
                    _seg = sub_commands[-1]
                    heredoc_origins = [
                        (c_, True, _seg if s is None else s, q)
                        for c_, p, s, q in heredoc_origins
                    ]
                current = []
                i += 1
                continue
            # M-4 fix: & (single ampersand = background, also a separator)
            # Codex review fix: skip & when part of redirection (&>, >&, <&, |&)
            if c == "&":
                next_c = command[i + 1] if i + 1 < len(command) else ""
                prev_c = command[i - 1] if i > 0 else ""
                # &> is "redirect both stdout+stderr" -- not a separator
                if next_c == ">":
                    current.append(c)
                    i += 1
                    continue
                # >& and <& are fd duplication -- not a separator
                if prev_c in (">", "<"):
                    current.append(c)
                    i += 1
                    continue
                # n>& where n is a digit (e.g., 2>&1)
                if prev_c.isdigit() and len(current) >= 2 and current[-1] == ">":
                    current.append(c)
                    i += 1
                    continue
                sub_commands.append("".join(current).strip())
                if redact_safe_heredocs and heredoc_origins:
                    _seg = sub_commands[-1]
                    heredoc_origins = [
                        (c_, p, _seg if s is None else s, q)
                        for c_, p, s, q in heredoc_origins
                    ]
                current = []
                i += 1
                continue
            # Comment tracking: # starts a comment to end-of-line in bash.
            # Consume the rest of the line to prevent << inside comments
            # from being misdetected as heredoc (security: fail-closed).
            # Only triggers when # follows whitespace/separator (bash semantics).
            if c == '#' and (i == 0 or command[i-1] in ' \t\n;|&()'):
                while i < len(command) and command[i] != '\n':
                    current.append(command[i])
                    i += 1
                continue

            # Detect heredoc operator: << or <<- (but NOT <<< here-string)
            # Only detect when outside arithmetic context (arithmetic_depth == 0)
            if (command[i:i+2] == '<<'
                    and command[i:i+3] != '<<<'
                    and arithmetic_depth == 0):

                # F1-1: Capture origin command BEFORE appending <<
                # This origin persists across all separator splits
                if redact_safe_heredocs:
                    origin_cmd = "".join(current).strip()

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
                if redact_safe_heredocs:
                    # V1 fix: track is_quoted (any quoting suppresses expansion)
                    # and full_segment (filled in at separator/newline time)
                    is_quoted = raw_token != delim
                    heredoc_origins.append((origin_cmd, False, None, is_quoted))
                continue

            # Newline
            if c == "\n":
                sub_commands.append("".join(current).strip())
                current = []
                i += 1
                # Consume heredoc bodies after newline
                if pending_heredocs:
                    if redact_safe_heredocs:
                        # V1 fix: finalize full_segment for remaining origins
                        if heredoc_origins:
                            _seg = sub_commands[-1] if sub_commands else ""
                            heredoc_origins = [
                                (c_, p, _seg if s is None else s, q)
                                for c_, p, s, q in heredoc_origins
                            ]
                        i, ranges = _consume_heredoc_bodies(
                            command, i, pending_heredocs,
                            classify=True,
                            origins=heredoc_origins,
                        )
                        all_body_ranges.extend(ranges)
                        heredoc_origins = []
                    else:
                        i = _consume_heredoc_bodies(command, i, pending_heredocs)
                    pending_heredocs = []
                continue

        current.append(c)
        i += 1

    # Don't forget the last segment
    remaining = "".join(current).strip()
    if remaining:
        sub_commands.append(remaining)

    # Filter empty strings
    result = [cmd for cmd in sub_commands if cmd]

    if redact_safe_heredocs:
        try:
            if all_body_ranges:
                # Build redacted command: replace safe body content with
                # empty lines (preserving newline count to prevent token
                # merging and line alignment changes)
                parts: list[str] = []
                prev_end = 0
                for start, end, is_safe in sorted(all_body_ranges):
                    parts.append(command[prev_end:start])
                    if is_safe:
                        body_text = command[start:end]
                        newline_count = body_text.count('\n')
                        parts.append('\n' * newline_count)
                    else:
                        parts.append(command[start:end])
                    prev_end = end
                parts.append(command[prev_end:])
                redacted = ''.join(parts)
            else:
                redacted = command
        except Exception:
            # Fail-closed: use original command (more content = more checks)
            redacted = command
        return result, redacted

    return result


def _parse_heredoc_delimiter(command: str, i: int) -> tuple[str, str, int]:
    """Parse heredoc delimiter word from position i.

    Handles:
      - Bare word: EOF, EOFZ, END_MARKER
      - Single-quoted: 'EOF' (literal heredoc, no expansion)
      - Double-quoted: "EOF" (expansion-active heredoc)
      - ANSI-C quoted: $'EOF' (strip $ prefix, then strip quotes)
      - Locale translation: $"EOF" (strip $ prefix, then strip quotes)
      - Backslash-escaped: \\EOF (strip backslashes from bare word)

    Returns: (delimiter_text, raw_token, new_position)
    """
    if i >= len(command):
        return ('', '', i)

    # ANSI-C quoting ($'...') or locale translation ($"...")
    # Must be checked BEFORE the single/double quote branch
    if (command[i] == '$' and i + 1 < len(command)
            and command[i + 1] in ("'", '"')):
        quote_char = command[i + 1]
        start = i
        i += 2  # skip $' or $"
        while i < len(command) and command[i] != quote_char:
            if command[i] == '\\' and i + 1 < len(command):
                i += 2  # skip escaped chars inside $'...'
            else:
                i += 1
        if i < len(command):
            i += 1  # consume closing quote
        raw_token = command[start:i]
        if quote_char == "'" and len(raw_token) >= 3:
            # Decode ANSI-C escape sequences (\x45 → E, \n → newline, etc.)
            # using the existing decoder to match bash behavior
            delim = _decode_ansi_c_strings(raw_token)
        elif len(raw_token) >= 3:
            # $"..." locale translation: strip prefix/quotes
            delim = raw_token[2:-1]
        else:
            delim = ''
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

    # Bare word: consume until whitespace, newline, or shell metachar
    # Handle backslash-newline (line continuation) within the token
    start = i
    while i < len(command) and command[i] not in ' \t\n;|&<>()':
        if (command[i] == '\\' and i + 1 < len(command)
                and command[i + 1] == '\n'):
            # Backslash-newline: line continuation, skip both and continue
            i += 2
            continue
        i += 1
    raw_token = command[start:i]
    # Process backslash escapes in bare-word delimiters (bash behavior:
    # \E -> E, \\ -> \, so \EOF -> EOF, \\EOF -> \EOF)
    delim_chars = []
    j = 0
    while j < len(raw_token):
        if raw_token[j] == '\\' and j + 1 < len(raw_token):
            delim_chars.append(raw_token[j + 1])
            j += 2
        else:
            delim_chars.append(raw_token[j])
            j += 1
    delim = ''.join(delim_chars)
    return (delim, raw_token, i)


def _consume_heredoc_bodies(
    command: str, i: int,
    pending: 'list[tuple[str, bool]]',
    classify: bool = False,
    origins: 'list[tuple[str, bool, str | None, bool]] | None' = None,
) -> 'int | tuple[int, list[tuple[int, int, bool]]]':
    """Consume heredoc body lines until each delimiter is matched.

    For each pending heredoc, reads lines until a line matches the
    delimiter exactly (after optional tab-stripping for <<-).

    Args:
        command: Full command string.
        i: Current position (start of first body line).
        pending: List of (delimiter, strip_tabs) tuples.
        classify: If True, also return body ranges with safety classification.
        origins: Parallel list of (origin_cmd, was_piped, full_segment, is_quoted)
            for each pending heredoc. Required when classify=True.
            F1-1: origin_cmd captured at << parse time.
            V1 fix: full_segment includes post-<< text for redirect detection.
            V1 fix: is_quoted flags whether bash expansion is suppressed.

    Returns:
        If classify is False: new position after all bodies consumed.
        If classify is True: tuple of (new_position, body_ranges) where
            body_ranges is list of (start, end, is_safe) tuples.
    """
    body_ranges: list[tuple[int, int, bool]] = []
    for idx, (delim, strip_tabs) in enumerate(pending):
        body_start = i
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
                # Body is [body_start, line_start) — excludes delimiter line
                if classify and origins is not None:
                    origin_cmd, was_piped, full_seg, is_quoted = (
                        origins[idx] if idx < len(origins)
                        else ('', False, '', True)
                    )
                    is_safe = _classify_heredoc_safety(
                        origin_cmd, was_piped, full_seg or ''
                    )
                    # V1 fix: unquoted heredocs with expansion syntax → UNSAFE
                    # Bash expands $(), ${}, backticks in unquoted heredoc bodies
                    if is_safe and not is_quoted:
                        body_text = command[body_start:line_start]
                        if '$' in body_text or '`' in body_text:
                            is_safe = False
                    body_ranges.append((body_start, line_start, is_safe))
                break
        else:
            # Unterminated heredoc: fail-closed, mark as UNSAFE
            if classify:
                body_ranges.append((body_start, i, False))
        # If we exhaust the input without finding the delimiter,
        # we've consumed an unterminated heredoc -- body lines
        # won't leak to sub-commands (fail-closed behavior)

    if classify:
        return i, body_ranges
    return i


# ============================================================
# Layer 1: Protected Path Scan
# ============================================================


def glob_to_literals(pattern: str) -> list[str]:
    """Convert a glob pattern to literal search strings for raw command scanning.

    Only converts patterns where the literal is distinctive enough to be
    meaningful as a substring search. Returns empty list for patterns that
    are too generic.

    Critical fix C-3: Returns [] for generic patterns like *.env to avoid
    false positives. Only exact matches, prefix patterns, and specific
    suffix patterns are converted.

    Examples:
        ".env"       -> [".env"]       (exact match)
        ".env.*"     -> [".env."]      (prefix match)
        "id_rsa"     -> ["id_rsa"]     (exact match)
        "id_rsa.*"   -> ["id_rsa."]    (prefix match)
        "*.pem"      -> [".pem"]       (suffix match)
        "*.tfstate"  -> [".tfstate"]   (suffix match)
        "*.env"      -> []             (too generic)
        "*credentials*.json" -> []     (too generic)

    Args:
        pattern: A glob pattern from zeroAccessPaths config.

    Returns:
        List of literal strings to search for, or [] if too generic.
    """
    # Exact match (no wildcards)
    if "*" not in pattern and "?" not in pattern:
        return [pattern]

    # Prefix match: "name.*" -> search for "name."
    if pattern.endswith(".*"):
        prefix = pattern[:-1]  # "name."
        # Only if the prefix itself has no wildcards
        if "*" not in prefix and "?" not in prefix:
            return [prefix]

    # Suffix match: "*.ext" -> search for ".ext"
    # C-3 fix: Only if the extension is distinctive enough
    if pattern.startswith("*.") and "*" not in pattern[1:] and "?" not in pattern[1:]:
        suffix = pattern[1:]  # ".ext"
        # Skip short/generic suffixes that cause excessive false positives
        if len(suffix) >= 4:
            bare = suffix[1:]  # strip leading dot
            generic_words = {"env", "key", "log"}
            if bare.lower() not in generic_words:
                return [suffix]

    # Wildcard patterns like "*credentials*" -- too generic, skip
    return []


def _decode_ansi_c_strings(command: str) -> str:
    """Decode ANSI-C quoted strings ($'...') in a command.

    Bash ANSI-C quoting allows hex (\\xHH), octal (\\0NNN or \\NNN),
    and standard escapes (\\n, \\t, etc.) inside $'...' sequences.
    Attackers can use this to hide protected filenames from literal scans.

    Args:
        command: Raw command string.

    Returns:
        Command with $'...' sequences replaced by their decoded content.
    """
    def _decode_escape(m: re.Match) -> str:
        content = m.group(1)
        result: list[str] = []
        i = 0
        while i < len(content):
            if content[i] == '\\' and i + 1 < len(content):
                nc = content[i + 1]
                if nc == 'x' and i + 3 < len(content):
                    hex_str = content[i + 2:i + 4]
                    try:
                        val = int(hex_str, 16)
                        # V2-fix: \x00 (null byte) terminates C strings in bash;
                        # replace with space (boundary char) for scan matching
                        result.append(' ' if val == 0 else chr(val))
                        i += 4
                        continue
                    except ValueError:
                        pass
                elif nc == 'u' and i + 5 < len(content):
                    # \uHHHH — 16-bit Unicode
                    hex_str = content[i + 2:i + 6]
                    if len(hex_str) == 4:
                        try:
                            result.append(chr(int(hex_str, 16)))
                            i += 6
                            continue
                        except ValueError:
                            pass
                elif nc == 'U' and i + 9 < len(content):
                    # \UHHHHHHHH — 32-bit Unicode
                    hex_str = content[i + 2:i + 10]
                    if len(hex_str) == 8:
                        try:
                            cp = int(hex_str, 16)
                            if cp <= 0x10FFFF:
                                result.append(chr(cp))
                                i += 10
                                continue
                        except ValueError:
                            pass
                elif nc in '01234567':
                    # Octal: \NNN (1-3 octal digits, with or without leading 0)
                    j = i + 1
                    oct_str = ''
                    while j < len(content) and content[j] in '01234567' and len(oct_str) < 3:
                        oct_str += content[j]
                        j += 1
                    if oct_str:
                        try:
                            result.append(chr(int(oct_str, 8)))
                            i = j
                            continue
                        except ValueError:
                            pass
                elif nc == 'c':
                    # V2-fix: \c terminates ANSI-C string (bash discards rest)
                    break
                elif nc in ('n', 't', 'r', 'a', 'b', 'f', 'v', 'e', 'E', '\\', "'"):
                    escape_map = {
                        'n': '\n', 't': '\t', 'r': '\r', 'a': '\a',
                        'b': '\b', 'f': '\f', 'v': '\v', 'e': '\x1b',
                        'E': '\x1b',  # V2-fix: uppercase \E is ESC, same as \e
                        '\\': '\\', "'": "'",
                    }
                    result.append(escape_map[nc])
                    i += 2
                    continue
                result.append(content[i])
                i += 1
            else:
                result.append(content[i])
                i += 1
        return ''.join(result)

    return re.sub(r"""\$'((?:[^'\\]|\\.)*)'""", _decode_escape, command)


def _expand_glob_chars(command: str) -> str:
    """Expand single-character glob bracket classes in command text.

    Converts evasion patterns so literal scanning can catch them:
    - [x] (single char in brackets) -> x
    - [\\x] (escaped char in brackets) -> x

    Only expands single-character classes to avoid false positives
    from multi-char classes like [abc] or ranges like [a-z].

    Args:
        command: Raw command string.

    Returns:
        Command with single-char bracket classes expanded.
    """
    # Match [x] or [\x] (single char, optionally backslash-escaped)
    return re.sub(r'\[\\?([^\]\[\\])\]', r'\1', command)


def scan_protected_paths(command: str, config: dict) -> tuple[str, str]:
    """Scan raw command string for protected path references (Layer 1).

    Defense-in-depth layer that catches bypasses which defeat structured
    parsing by scanning for literal occurrences of protected filenames.

    Scans path tiers configured in bashPathScan.scanTiers (default: ["zeroAccess"]).
    Supported tiers: "zeroAccess" -> zeroAccessPaths,
                     "readOnly" -> readOnlyPaths,
                     "noDelete" -> noDeletePaths.
    Uses word-boundary regex to reduce false matches.

    I-4 fix: Includes / in word-boundary regex so ./.env is caught.

    Also scans a normalized copy of the command where:
    - ANSI-C quoted strings ($'\\x2e\\x65\\x6e\\x76') are decoded
    - Single-char glob classes ([v]) are expanded
    This catches evasion attempts that hide protected paths via encoding.

    Args:
        command: The raw bash command string.
        config: Guardian configuration dict.

    Returns:
        Tuple of (verdict, reason) where verdict is "deny", "ask", or "allow".
    """
    scan_config = config.get("bashPathScan", {})
    if not scan_config.get("enabled", True):
        return "allow", ""

    exact_action = scan_config.get("exactMatchAction", "ask")
    pattern_action = scan_config.get("patternMatchAction", "ask")

    # Read scanTiers from config; default to ["zeroAccess"] (preserves current behavior)
    scan_tiers = scan_config.get("scanTiers", ["zeroAccess"])

    # Map tier names to config keys
    tier_to_config_key = {
        "zeroAccess": "zeroAccessPaths",
        "readOnly": "readOnlyPaths",
        "noDelete": "noDeletePaths",
    }

    # Collect all path patterns from configured tiers
    all_scan_paths: list[str] = []
    for tier in scan_tiers:
        config_key = tier_to_config_key.get(tier)
        if config_key:
            all_scan_paths.extend(config.get(config_key, []))

    # Build normalized variants of the command to catch evasion attempts.
    normalized = _decode_ansi_c_strings(command)
    normalized = _expand_glob_chars(normalized)
    expanded_orig = _expand_glob_chars(command)

    # Collect all text variants to scan (deduplicated)
    scan_texts = [command]
    if expanded_orig != command:
        scan_texts.append(expanded_orig)
    if normalized not in scan_texts:
        scan_texts.append(normalized)

    strongest_verdict = "allow"
    strongest_reason = ""

    for pattern in all_scan_paths:
        # Skip directory patterns -- too noisy for raw string scan
        if "**" in pattern or pattern.endswith("/"):
            continue

        is_exact = "*" not in pattern and "?" not in pattern
        literals = glob_to_literals(pattern)

        for literal in literals:
            # I-4 fix: Include / in word-boundary character set
            # Gemini review fix: Include {, }, , for brace expansion
            # For exact matches: strict word boundaries on both sides
            # For prefix patterns (e.g. ".env." from ".env.*"): strict before, relaxed after
            # For suffix patterns (e.g. ".pem" from "*.pem"): relaxed before, strict after
            boundary_before = r"(?:^|[\s;|&<>(\"`'=/,{\[:\]])"
            boundary_after = r"(?:$|[\s;|&<>)\"`'/,}\[:\]])"

            is_prefix_pattern = pattern.endswith(".*")
            is_suffix_pattern = pattern.startswith("*.")

            if is_suffix_pattern:
                # ".pem" can be preceded by any word char (server.pem)
                regex = re.escape(literal) + boundary_after
            elif is_prefix_pattern:
                # ".env." can be followed by any word char (.env.local)
                regex = boundary_before + re.escape(literal)
            else:
                # Exact match: strict boundaries both sides
                regex = boundary_before + re.escape(literal) + boundary_after

            # Build a glob-?-aware regex: for each char in the literal,
            # also allow ? as a substitute (catches .en? -> .env evasion).
            # Uses a capturing group per position to verify post-match that
            # at least one position matched a concrete character (not all ?).
            glob_q_parts = []
            for ch in literal:
                glob_q_parts.append(f'({re.escape(ch)}|\\?)')
            glob_q_literal = ''.join(glob_q_parts)
            if is_suffix_pattern:
                glob_q_regex = glob_q_literal + boundary_after
            elif is_prefix_pattern:
                glob_q_regex = boundary_before + glob_q_literal
            else:
                glob_q_regex = boundary_before + glob_q_literal + boundary_after

            # Check all text variants (original + normalized)
            found = False
            for scan_text in scan_texts:
                if re.search(regex, scan_text):
                    found = True
                    break
                # Only try glob-? regex if command contains ? chars
                # V2-fix: Use finditer (not search) to check ALL matches,
                # so a leading ???? doesn't shadow a later .en? match
                if '?' in scan_text:
                    for gm in re.finditer(glob_q_regex, scan_text):
                        # Require at least one non-? character match
                        # to prevent all-? tokens like ???? from matching
                        if any(g != '?' for g in gm.groups() if g):
                            found = True
                            break

            if found:
                action = exact_action if is_exact else pattern_action
                reason = f"Protected path reference detected: {literal}"

                if action == "deny":
                    strongest_verdict = "deny"
                    strongest_reason = reason
                elif action == "ask" and strongest_verdict != "deny":
                    strongest_verdict = "ask"
                    strongest_reason = reason

    return strongest_verdict, strongest_reason


# ============================================================
# Layer 3: Enhanced Path Extraction
# ============================================================


def _is_inside_quotes(command: str, pos: int) -> bool:
    """Check if a position in a command string is inside a quoted region.

    I-5 fix: Used to make redirection extraction quote-aware.

    Args:
        command: The command string.
        pos: The character position to check.

    Returns:
        True if the position is inside single or double quotes.
    """
    in_single = False
    in_double = False
    i = 0
    while i < pos:
        c = command[i]
        if c == "\\" and not in_single:
            i += 2  # Skip escaped character
            continue
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        i += 1
    return in_single or in_double


def extract_redirection_targets(command: str, project_dir: Path) -> list[Path]:
    """Extract file paths from shell redirections (>, >>, <).

    Handles: echo x > file.txt, echo x >> file.txt, cat < input.txt,
    cmd 2> errors.log, cmd &> all.log

    I-5 fix: Quote-aware -- skips > inside quoted regions.

    Args:
        command: The bash sub-command to parse.
        project_dir: Project directory for resolving relative paths.

    Returns:
        List of Path objects found as redirection targets.
    """
    targets: list[Path] = []
    redir_pattern = r'(?:(?:\d|&)?(?:>\|?|>{2})|<(?!<))\s*([^\s;|&<>]+)'

    for match in re.finditer(redir_pattern, command):
        # I-5 fix: Skip redirections inside quoted regions
        if _is_inside_quotes(command, match.start()):
            continue

        target = match.group(1).strip("'\"")

        # F6: Skip process substitutions — >(cmd) and <(cmd) are not file paths
        if target.startswith("("):
            continue

        # Skip variable targets like $FILE
        if target.startswith("$"):
            continue

        if not _is_path_candidate(target):
            continue

        try:
            path = Path(target)
            if not path.is_absolute():
                path = project_dir / path
            targets.append(path)
        except OSError:
            continue

    return targets


# Regex to extract single/double-quoted string literals from interpreter payloads.
# Handles escaped characters within quotes.
_QUOTED_LITERAL_RE = re.compile(
    r"""(?:'([^'\\]*(?:\\.[^'\\]*)*)'|"([^"\\]*(?:\\.[^"\\]*)*)")"""
)


def extract_paths_from_interpreter_payload(
    command: str, project_dir: Path
) -> list[Path]:
    """Extract file paths from interpreter -c/-e payload string literals.

    Used by the F1 fail-closed block to attempt path resolution before
    falling back to ASK. Only returns paths that are within the project
    boundary (checked via Path.relative_to, NOT str.startswith).

    Security invariants:
    - F2-1: Uses is_within_project() (relative_to-based) for boundary check
    - F2-2: Rejects literals containing {} or $ (interpolation markers)
    - Fail-closed: returns [] on any error (F1 ASK fires)

    Args:
        command: The bash command string (e.g., 'python3 -c "os.remove(...)"').
        project_dir: Project directory for resolving relative paths and
            boundary checking.

    Returns:
        List of resolved Path objects within the project, or [] if none.
    """
    try:
        from _guardian_utils import extract_interpreter_payload

        payload = extract_interpreter_payload(command)
        if payload is None:
            return []

        paths: list[Path] = []
        saw_out_of_project = False  # V2 fix: fail-closed on mixed paths
        for match in _QUOTED_LITERAL_RE.finditer(payload):
            # Group 1 = single-quoted content, Group 2 = double-quoted content
            literal = match.group(1) if match.group(1) is not None else match.group(2)
            if literal is None:
                continue

            # F2-2: Reject interpolation markers — unresolvable templates
            # V1 fix: Added % for C-style format strings (e.g., "%s/passwd" % var)
            if '{' in literal or '}' in literal or '$' in literal or '%' in literal:
                continue

            # V1 fix: Reject literals containing backslash-escaped path chars.
            # JS escape sequences (e.g., \/ → / at runtime) make the literal
            # path diverge from the runtime path. Applies to all quote types
            # because extract_interpreter_payload() strips outer shell quotes,
            # so inner JS/Perl/Ruby single-quotes still have escape semantics.
            if '\\' in literal:
                continue

            # Must look like a path: contains / or starts with .
            if '/' not in literal and not literal.startswith('.'):
                continue

            # V1+V2 fix: Reject trivial literals that resolve to project root.
            # ".", "./", "./.", etc. are too generic to be meaningful targets
            # and can serve as decoys to suppress F1 ASK.
            # Use resolved path comparison instead of string matching to catch
            # all variants (V2 fix: "./.` bypassed the string check).
            try:
                _check = Path(literal)
                if not _check.is_absolute():
                    _check = project_dir / _check
                if _check.resolve() == project_dir.resolve():
                    continue
            except (OSError, ValueError):
                pass

            # Skip URLs
            if '://' in literal:
                continue

            # Skip MIME types: known type prefixes with single /
            # V1 fix: Use prefix allowlist instead of fragile heuristic to
            # avoid false negatives on extensionless paths like "src/utils"
            _MIME_PREFIXES = (
                'application/', 'text/', 'image/', 'audio/', 'video/',
                'multipart/', 'font/', 'model/', 'message/',
            )
            if (literal.count('/') == 1
                    and not literal.startswith('.')
                    and not literal.startswith('/')
                    and any(literal.lower().startswith(p) for p in _MIME_PREFIXES)):
                continue

            try:
                path = Path(literal)
                if not path.is_absolute():
                    path = project_dir / path

                # Check for glob patterns
                if '*' in literal or '?' in literal or '[' in literal:
                    # Expand glob, filter each result through project boundary.
                    # Note: recursive=True is intentionally omitted — ** patterns
                    # should NOT recursively expand to prevent DoS via massive expansion.
                    expanded = glob.glob(str(path))
                    for exp_str in expanded:
                        exp_path = Path(exp_str)
                        if is_within_project(exp_path, project_dir):
                            paths.append(exp_path)
                        else:
                            saw_out_of_project = True
                else:
                    # F2-1 CRITICAL: Use is_within_project (relative_to-based)
                    if is_within_project(path, project_dir):
                        paths.append(path)
                    else:
                        # V2 fix: Track out-of-project paths for mixed-path
                        # fail-closed behavior
                        saw_out_of_project = True
            except (OSError, ValueError):
                continue

        # V2 fix: If ANY path-like literal resolved outside the project,
        # return empty to trigger F1 ASK. This prevents the "mixed paths"
        # bypass where a benign in-project path alongside an out-of-project
        # target silently drops the dangerous path and suppresses F1 ASK.
        if saw_out_of_project:
            return []
        return paths
    except Exception:
        # Fail-closed: any error → return empty → F1 ASK fires
        return []


def extract_paths(
    command: str, project_dir: Path, allow_nonexistent: bool = False
) -> list[Path]:
    """Extract file paths from command arguments.

    Args:
        command: The bash command to parse.
        project_dir: Project directory for resolving relative paths.
        allow_nonexistent: If True, include paths that don't exist on disk
            (for write/delete context where the target may not exist yet).

    Returns:
        List of Path objects found in the command.
    """
    try:
        parts = shlex.split(command, posix=(sys.platform != "win32"))
    except ValueError as e:
        log_guardian("DEBUG", f"shlex.split failed ({e}), falling back to simple split")
        parts = command.split()

    # COMPAT-03 FIX: shlex.split(posix=False) keeps surrounding quotes on Windows.
    if sys.platform == "win32":
        parts = [p.strip("'\"") for p in parts]
        parts = [p for p in parts if p]

    if not parts:
        return []

    paths: list[Path] = []
    for part in parts[1:]:  # Skip command name
        if part.startswith("-"):
            # P1-6: Flag-concatenated paths like -f.env
            # Short flags (-x) are skipped, but -f.env has a path suffix
            if len(part) > 2 and not part.startswith("--"):
                flag_suffix = part[2:]  # After -X, the rest is the argument
                if _is_path_candidate(flag_suffix):
                    try:
                        suffix_path = Path(flag_suffix)
                        if not suffix_path.is_absolute():
                            suffix_path = project_dir / suffix_path
                        if suffix_path.exists() and is_within_project(suffix_path, project_dir):
                            paths.append(suffix_path)
                        elif allow_nonexistent and _is_within_project_or_would_be(suffix_path, project_dir):
                            paths.append(suffix_path)
                        elif match_allowed_external_path(str(suffix_path)):
                            paths.append(suffix_path)
                    except OSError:
                        pass
            continue

        # M-3: Handle dd of= syntax
        if part.startswith("of="):
            part = part[3:]
            if not part:
                continue

        if not _is_path_candidate(part):
            continue

        try:
            # P1-5: Expand environment variables and tilde before path creation
            expanded_part = os.path.expandvars(part)
            path = Path(expanded_part)
            if str(path).startswith("~"):
                try:
                    path = path.expanduser()
                except (RuntimeError, KeyError):
                    pass  # Unknown user -- leave as-is, will be rebased
            if not path.is_absolute():
                path = project_dir / path

            # Expand wildcards (including character classes like [v])
            if "*" in str(path) or "?" in str(path) or "[" in str(path):
                expanded = glob.glob(str(path))
                for exp in expanded:
                    p = Path(exp)
                    if p.exists() and is_within_project(p, project_dir):
                        paths.append(p)
                    elif match_allowed_external_path(str(p)):
                        paths.append(p)
            else:
                if path.exists() and is_within_project(path, project_dir):
                    paths.append(path)
                elif allow_nonexistent and _is_within_project_or_would_be(path, project_dir):
                    paths.append(path)
                elif match_allowed_external_path(str(path)):
                    paths.append(path)
        except OSError:
            continue

    return paths


def _is_within_project_or_would_be(path: Path, project_dir: Path) -> bool:
    """Check if a path is or would be within the project directory.

    F7: Uses Path.resolve(strict=False) to canonicalize paths before checking,
    preventing traversal attacks like /project/../etc/passwd.

    Args:
        path: Path to check (may not exist).
        project_dir: Project directory boundary.

    Returns:
        True if path is or would be within project_dir.
    """
    try:
        # F7: Use resolve() to canonicalize, preventing ../traversal attacks
        resolved = path.resolve(strict=False)
        resolved_project = project_dir.resolve(strict=False)
        resolved.relative_to(resolved_project)
        return True
    except (OSError, ValueError):
        return False


# ============================================================
# Layer 4: Command Type Detection (Enhanced)
# ============================================================


def is_delete_command(command: str) -> bool:
    """Check if command is a delete operation.

    Detects shell delete commands and interpreter-mediated deletions.

    Args:
        command: The bash command (or sub-command) to check.

    Returns:
        True if command appears to be a delete operation.
    """
    delete_patterns = [
        # Shell delete commands
        # V1-fix: Added ({ to alternation so commands inside { } and ( ) are detected
        r"(?:^|[;&|({]\s*)rm\s+",
        r"(?:^|[;&|({]\s*)del\s+",
        r"(?:^|[;&|({]\s*)rmdir\s+",
        r"(?:^|[;&|({]\s*)Remove-Item\s+",
        r"(?:^|[;&|({]\s*)ri\s+",
        # P1-1: git rm (deletes files from working tree and index)
        # F8: Allow optional git global flags before subcommand (e.g., git -C dir rm)
        r"(?:^|[;&|({]\s*)git\s+(?:-[A-Za-z]\s+\S+\s+|--[a-z][-a-z]*(?:=\S+|\s+(?!rm\b)\S+)?\s+)*rm\s+",
        # mv to /dev/null (effective deletion)
        r"\bmv\s+\S+\s+/dev/null\b",
        # P1-2: Standalone redirect truncation (> file, : > file, >| file)
        # Destroys content by truncating to zero bytes
        r"^\s*(?::)?\s*>(?!>)\|?\s*\S+",
        # Interpreter-mediated deletions (python/node/perl/ruby)
        # F4: Split pathlib.Path pattern to avoid ReDoS (O(N^2) backtracking)
        r"(?:py|python[23]?|python\d[\d.]*)\s[^|&\n]*(?:os\.remove|os\.unlink|shutil\.rmtree|shutil\.move|os\.rmdir)",
        r"(?:py|python[23]?|python\d[\d.]*)\s[^|&\n]*pathlib\.Path\([^)]*\)\.unlink",
        r"(?:node|deno|bun)\s[^|&\n]*(?:unlinkSync|rmSync|rmdirSync|fs\.unlink|fs\.rm\b|promises\.unlink)",
        r"(?:perl|ruby)\s[^|&\n]*(?:\bunlink\b|File\.delete|FileUtils\.rm)",
    ]
    if any(re.search(p, command, re.IGNORECASE) for p in delete_patterns):
        return True

    # NEW: Fallback — extract interpreter payload and check for destructive APIs
    # This catches multiline -c/-e payloads in sub-commands (compound commands)
    # where the regex patterns fail due to [^|&\n]* stopping at newlines.
    from _guardian_utils import check_interpreter_payload
    is_destructive, _ = check_interpreter_payload(command)
    return is_destructive


def is_write_command(command: str) -> bool:
    """Check if command is a write/modify operation.

    Enhanced with additional write vectors: sed -i, cp, dd, rsync,
    patch, and colon truncation (: >).

    Critical fix I-2: Does NOT include 'install' to avoid breaking
    npm/pip/cargo/brew/apt commands.

    Args:
        command: The bash command (or sub-command) to check.

    Returns:
        True if command appears to write or modify files.
    """
    write_patterns = [
        (r">\s*['\"]?[^|&;>]+", True),   # Redirection -- needs quote check
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


def is_within_project(path: Path, project_dir: Path) -> bool:
    """Check if path is within project directory.

    Args:
        path: Path to check.
        project_dir: Project directory boundary.

    Returns:
        True if path is within project_dir.
    """
    try:
        path.resolve().relative_to(project_dir.resolve())
        return True
    except ValueError:
        return False


def _is_path_candidate(s: str) -> bool:
    """Check if a string is a plausible filesystem path.

    Rejects strings that cannot be valid paths before they reach os.path calls.

    Args:
        s: String to check.

    Returns:
        True if the string could be a valid filesystem path.
    """
    if not s:
        return False
    if "\n" in s or "\r" in s:
        return False
    if "\0" in s:
        return False
    if len(s) > 4096:
        return False
    for component in s.split("/"):
        if len(component) > 255:
            return False
    return True


# ============================================================
# Archive Functions
# ============================================================


def generate_archive_title(files: list[Path]) -> str:
    """Generate descriptive title for archive folder.

    Args:
        files: List of files being archived.

    Returns:
        Sanitized title string for the archive folder name.
    """
    if not files:
        return "empty"

    first_name = files[0].name
    sanitized = re.sub(r'[<>:"/\\|?*\s]', "_", first_name)
    sanitized = re.sub(r"_+", "_", sanitized)
    if len(sanitized) > 50:
        sanitized = sanitized[:47] + "..."
    sanitized = sanitized.strip("_") or "unnamed"

    if len(files) == 1:
        return sanitized
    else:
        return f"{sanitized}_and_{len(files) - 1}_more"


# Archive constraints
ARCHIVE_MAX_FILE_SIZE_MB = 100  # Skip files larger than this
ARCHIVE_MAX_TOTAL_SIZE_MB = 500  # Stop archiving if total exceeds this
ARCHIVE_MAX_FILES = 50  # Maximum number of files to archive


def archive_files(
    files: list[Path], project_dir: Path
) -> tuple[Path | None, list[tuple[Path, Path]]]:
    """Archive files before deletion.

    Applies safety limits:
    - Max file size: 100MB per file
    - Max total size: 500MB total
    - Max files: 50 files

    Files exceeding limits are logged and skipped.
    """
    if not files:
        return None, []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = generate_archive_title(files)
    archive_dir = project_dir / "_archive" / f"{timestamp}_{title}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived = []
    total_size = 0
    skipped_count = 0
    start_time = datetime.now()

    for file_path in files:
        if len(archived) >= ARCHIVE_MAX_FILES:
            log_guardian(
                "WARN", f"Archive file limit reached ({ARCHIVE_MAX_FILES}), skipping rest"
            )
            skipped_count += len(files) - len(archived)
            break

        try:
            file_size = 0
            if file_path.is_file():
                file_size = file_path.stat().st_size
            elif file_path.is_dir():
                file_size = sum(f.stat().st_size for f in file_path.rglob("*") if f.is_file())

            file_size_mb = file_size / (1024 * 1024)

            if file_size_mb > ARCHIVE_MAX_FILE_SIZE_MB:
                max_mb = ARCHIVE_MAX_FILE_SIZE_MB
                log_guardian(
                    "WARN",
                    f"Skipping large file {file_path.name} ({file_size_mb:.1f}MB > {max_mb}MB)",
                )
                skipped_count += 1
                continue

            if (total_size + file_size) / (1024 * 1024) > ARCHIVE_MAX_TOTAL_SIZE_MB:
                limit_mb = ARCHIVE_MAX_TOTAL_SIZE_MB
                log_guardian(
                    "WARN",
                    f"Archive total size limit reached ({limit_mb}MB), skipping rest",
                )
                skipped_count += len(files) - len(archived)
                break

            rel_path = file_path.relative_to(project_dir)
            target_dir = archive_dir / rel_path.parent
            target_dir.mkdir(parents=True, exist_ok=True)

            target_path = target_dir / file_path.name
            if target_path.exists():
                suffix = secrets.token_hex(3)
                stem = file_path.stem
                ext = file_path.suffix
                target_path = target_dir / f"{stem}_{suffix}{ext}"

            if file_path.is_file():
                # F5: Symlink safety — preserve symlinks instead of dereferencing
                if os.path.islink(file_path):
                    link_target = os.readlink(file_path)
                    os.symlink(link_target, target_path)
                else:
                    shutil.copy2(file_path, target_path)
            elif file_path.is_dir():
                # F5: Symlink safety — preserve symlinks as symlinks
                shutil.copytree(file_path, target_path, symlinks=True, dirs_exist_ok=True)

            archived.append((file_path, target_path))
            total_size += file_size

        except PermissionError as e:
            log_guardian(
                "WARN",
                f"Archive PERMISSION DENIED for {file_path.name}: {e}\n"
                "  Check file permissions or run with elevated privileges.",
            )
            skipped_count += 1
        except OSError as e:
            is_disk_full = e.errno == 28 or getattr(e, "winerror", None) == 112
            error_type = "DISK FULL" if is_disk_full else "FILESYSTEM ERROR"
            log_guardian(
                "WARN",
                f"Archive {error_type} for {file_path.name}: {e}\n  errno={e.errno}",
            )
            skipped_count += 1
        except Exception as e:
            log_guardian(
                "WARN",
                f"Archive UNEXPECTED ERROR for {file_path.name}: {type(e).__name__}: {e}",
            )
            skipped_count += 1

    elapsed = (datetime.now() - start_time).total_seconds()
    if elapsed > 5:
        log_guardian("INFO", f"Archive completed in {elapsed:.1f}s ({len(archived)} files)")

    if skipped_count > 0:
        log_guardian("WARN", f"Skipped {skipped_count} file(s) during archive")

    return archive_dir, archived


def create_deletion_log(archive_dir: Path, archived: list[tuple[Path, Path]], command: str):
    """Create metadata JSON in archive directory."""
    truncated_command = command[:200] + "..." if len(command) > 200 else command
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": truncated_command,
        "files": [{"original": str(orig), "archived": str(arch)} for orig, arch in archived],
    }
    log_file = archive_dir / "_deletion_log.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# ============================================================
# Pre-commit Message Helper
# ============================================================


def create_precommit_message(prefix: str, command: str, timestamp: str) -> str:
    """Create a pre-commit message with length limit.

    Args:
        prefix: Message prefix (e.g., "pre-danger-checkpoint")
        command: The command being executed (will be truncated)
        timestamp: Timestamp string

    Returns:
        Commit message limited to COMMIT_MESSAGE_MAX_LENGTH (72 chars)
    """
    cmd_short = command[:20].replace("\n", " ").strip()
    fixed_len = len(prefix) + len(": ") + len("... @ ") + len(timestamp)
    available = COMMIT_MESSAGE_MAX_LENGTH - fixed_len

    if available > 10:
        cmd_short = command[:available].replace("\n", " ").strip()
    else:
        cmd_short = command[:10].replace("\n", " ").strip()

    message = f"{prefix}: {cmd_short}... @ {timestamp}"

    if len(message) > COMMIT_MESSAGE_MAX_LENGTH:
        message = message[: COMMIT_MESSAGE_MAX_LENGTH - 3] + "..."

    return message


# ============================================================
# Verdict Aggregation
# ============================================================

# Verdict precedence: deny > ask > allow
_VERDICT_PRIORITY = {"deny": 2, "ask": 1, "allow": 0}
_FAIL_CLOSE_PRIORITY = max(_VERDICT_PRIORITY.values())  # Unknown verdicts fail closed


def _stronger_verdict(
    current: tuple[str, str], candidate: tuple[str, str]
) -> tuple[str, str]:
    """Return the stronger of two verdicts based on precedence.

    C-1 fix: All layers must complete before any decision is emitted.
    This helper enables verdict aggregation with deny > ask > allow.
    Unknown verdict strings default to deny priority (fail-close).

    Args:
        current: Current (verdict, reason) tuple.
        candidate: New (verdict, reason) tuple to compare.

    Returns:
        The stronger (verdict, reason) tuple.
    """
    if _VERDICT_PRIORITY.get(candidate[0], _FAIL_CLOSE_PRIORITY) > _VERDICT_PRIORITY.get(current[0], _FAIL_CLOSE_PRIORITY):
        return candidate
    return current


# ============================================================
# Main Hook Logic
# ============================================================


def main() -> None:
    """Main hook entry point.

    Execution flow (Phase 1: heredoc redaction integrated):
    1. Layer 2: split_commands() with redaction — produces sub-commands + redacted string
    2. Layer 0: Block patterns scan redacted command (safe heredoc bodies removed)
    3. Layer 0b: Ask patterns scan redacted command
    4. Layer 1: Protected path scan (joined sub-commands)
    5. Layer 3+4: Per-sub-command path analysis (original sub-commands)
    6. Aggregate verdicts: deny > ask > allow
    7. Handle deletions with archive
    8. Pre-commit for dangerous operations
    9. Emit final verdict
    """
    # Get project directory
    project_dir_str = get_project_dir()
    if not project_dir_str:
        # SECURITY: No project dir = can't verify safety, deny by default
        print("GUARDIAN WARN: No project dir set, failing closed for bash guardian", file=sys.stderr)
        reason = "Guardian cannot verify command safety: project directory not set"
        print(json.dumps(deny_response(reason)))
        sys.exit(0)
    project_dir = Path(project_dir_str)

    # Parse input - FAIL-CLOSE on invalid JSON for security
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log_guardian("ERROR", f"Malformed JSON input: {e}")
        print(json.dumps(deny_response("Invalid hook input (malformed JSON)")))
        sys.exit(0)

    # Only process Bash commands
    if input_data.get("tool_name") != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")

    # Truncate for logging
    cmd_preview = truncate_command(command)

    # Load config once for all layers
    config = load_guardian_config()

    # ========== Layer 2: Command Decomposition + Heredoc Redaction ==========
    # Split FIRST to produce redacted command for Layer 0/0b.
    # Single-pass: same parser produces both sub-commands and redacted string.
    sub_commands, redacted_command = split_commands(
        command, redact_safe_heredocs=True
    )

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
    # C-1 fix: ALL layers complete before any decision
    final_verdict: tuple[str, str] = ("allow", "")

    # Layer 0b: Ask patterns (uses redacted command — safe heredoc bodies removed)
    needs_ask, ask_reason = match_ask_patterns(redacted_command)
    if needs_ask:
        final_verdict = _stronger_verdict(final_verdict, ("ask", ask_reason))

    # ========== Layer 1: Protected Path Scan ==========
    # Scan joined sub-commands instead of raw command string.
    # After heredoc-aware split_commands(), heredoc body content is excluded,
    # so .env/.pem in heredoc bodies no longer trigger false positives.
    # Also filter out comment-only sub-commands to prevent false positives
    # from e.g. "# .env" appearing in scan text.
    scan_text = ' '.join(
        sub for sub in sub_commands if not sub.lstrip().startswith('#')
    )
    scan_verdict, scan_reason = scan_protected_paths(scan_text, config)
    if scan_verdict != "allow":
        final_verdict = _stronger_verdict(final_verdict, (scan_verdict, scan_reason))
        log_guardian("SCAN", f"Layer 1 {scan_verdict}: {scan_reason}")

    # ========== Layer 3+4: Per-Sub-Command Analysis ==========
    all_paths: list[Path] = []  # Collect all paths for archive step

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

        # Layer 3: Extract paths from arguments (enhanced with allow_nonexistent)
        paths = extract_paths(sub_cmd, project_dir, allow_nonexistent=(is_write or is_delete))

        # Layer 3: Extract paths from redirections
        redir_paths = extract_redirection_targets(sub_cmd, project_dir)

        sub_paths = paths + redir_paths
        all_paths.extend(sub_paths)

        # F1: Fail-closed safety net — if write/delete detected but no paths
        # resolved from shell-level arguments, attempt interpreter payload
        # path extraction before falling back to ASK.
        if (is_write or is_delete) and not sub_paths:
            op_type = "delete" if is_delete else "write"

            # Check if this is an interpreter command with extractable paths
            from _guardian_utils import check_interpreter_payload
            is_interp, interp_detail = check_interpreter_payload(sub_cmd)
            if is_interp:
                # Attempt to resolve paths from interpreter payload
                interp_paths = extract_paths_from_interpreter_payload(
                    sub_cmd, project_dir
                )
                if interp_paths:
                    # Paths resolved: route through normal path validation
                    sub_paths = interp_paths
                    all_paths.extend(sub_paths)
                    log_guardian(
                        "DEBUG",
                        f"F1: Resolved {len(interp_paths)} path(s) from "
                        f"interpreter payload"
                    )
                    # Fall through to path validation loop below
                else:
                    # Paths not resolved: F1 ASK with enriched message
                    api_name = (
                        interp_detail.rsplit(": ", 1)[-1]
                        if ": " in interp_detail
                        else ""
                    )
                    api_info = f" via {api_name}" if api_name else ""
                    final_verdict = _stronger_verdict(
                        final_verdict,
                        ("ask", f"Detected {op_type}{api_info} but could not "
                         f"resolve target paths"),
                    )
            else:
                # Not an interpreter command: standard F1 ASK
                final_verdict = _stronger_verdict(
                    final_verdict,
                    ("ask", f"Detected {op_type} but could not resolve target paths"),
                )

        for path in sub_paths:
            path_str = str(path)

            # Symlink escape check
            if is_symlink_escape(path_str):
                log_guardian("BLOCK", f"Symlink escape detected: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Symlink points outside project: {path.name}")
                )
                continue

            # Zero access check (applies to ALL operations)
            if match_zero_access(path_str):
                log_guardian("BLOCK", f"Zero access path: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Protected path: {path.name}")
                )
                continue

            # Read-only check (for write commands in this sub-command)
            if is_write and match_read_only(path_str):
                log_guardian("BLOCK", f"Read-only path: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Read-only path: {path.name}")
                )
                continue

            # External read-only check (for write commands targeting allowedExternalReadPaths)
            if is_write or is_delete:
                ext_mode = match_allowed_external_path(path_str)
                if ext_mode == "read":
                    log_guardian("BLOCK", f"Read-only external path (bash write): {path.name}")
                    final_verdict = _stronger_verdict(
                        final_verdict, ("deny", f"External path is read-only: {path.name}")
                    )
                    continue

            # No-delete check (for delete commands in this sub-command)
            if is_delete and match_no_delete(path_str):
                log_guardian("BLOCK", f"No-delete path: {path.name}")
                final_verdict = _stronger_verdict(
                    final_verdict, ("deny", f"Protected from deletion: {path.name}")
                )
                continue

    # ========== Emit final verdict ==========
    # C-1 fix: Now ALL layers have been evaluated

    if final_verdict[0] == "deny":
        log_guardian("DENY", f"{final_verdict[1]}: {cmd_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", "Would DENY")
            sys.exit(0)
        print(json.dumps(deny_response(final_verdict[1])))
        sys.exit(0)

    # ========== Handle Deletions with Archive ==========
    if any(is_delete_command(sub) for sub in sub_commands):
        if not all_paths:
            cmd_short = truncate_command(command, 80)
            log_guardian("DEBUG", f"Delete cmd, no paths extracted: {cmd_short}")
        else:
            existing_paths = [p for p in all_paths if p.exists()]
            untracked = [p for p in existing_paths if not git_is_tracked(str(p))]

            if not untracked and existing_paths:
                log_guardian(
                    "DEBUG",
                    f"All {len(existing_paths)} path(s) are git-tracked, no archive needed",
                )

            if untracked:
                if is_dry_run():
                    log_guardian("DRY-RUN", f"Would archive: {[p.name for p in untracked]}")
                else:
                    archive_dir, archived = archive_files(untracked, project_dir)
                    if archived:
                        create_deletion_log(archive_dir, archived, command)
                        log_guardian(
                            "ARCHIVE",
                            f"Archived {len(archived)} file(s) to {archive_dir.name}",
                        )

                        file_list = ", ".join(p.name for p in existing_paths[:3])
                        if len(existing_paths) > 3:
                            file_list += f", ... (+{len(existing_paths) - 3} more)"

                        print(
                            json.dumps(
                                ask_response(
                                    f"Archived {len(archived)} file(s) to {archive_dir.name}/\n"
                                    f"Files: {file_list}\n"
                                    "Proceed with deletion?"
                                )
                            )
                        )
                        sys.exit(0)
                    else:
                        log_guardian(
                            "WARN",
                            f"Archive FAILED for {len(untracked)} untracked file(s)",
                        )
                        file_list = ", ".join(p.name for p in untracked[:3])
                        if len(untracked) > 3:
                            file_list += f", ... (+{len(untracked) - 3} more)"

                        print(
                            json.dumps(
                                ask_response(
                                    f"ARCHIVE FAILED for {len(untracked)} file(s)!\n"
                                    f"Files: {file_list}\n"
                                    f"Data will be PERMANENTLY LOST if deleted.\n"
                                    "Proceed with deletion anyway?"
                                )
                            )
                        )
                        sys.exit(0)

            if existing_paths:
                log_guardian("ASK", f"Delete files: {[p.name for p in existing_paths[:3]]}")
                if is_dry_run():
                    log_guardian("DRY-RUN", "Would ASK")
                    sys.exit(0)
                file_list = ", ".join(p.name for p in existing_paths[:3])
                if len(existing_paths) > 3:
                    file_list += f", ... (+{len(existing_paths) - 3} more)"
                print(
                    json.dumps(
                        ask_response(
                            f"Delete {len(existing_paths)} file(s): {file_list}?"
                        )
                    )
                )
                sys.exit(0)

    # ========== Handle ask verdict (from Layer 0b or Layer 1) ==========
    if final_verdict[0] == "ask":
        # Try pre-commit before dangerous operation
        try:
            git_config = config.get("gitIntegration", {})
            pre_commit_config = git_config.get("preCommitOnDangerous", {})

            if pre_commit_config.get("enabled", False):
                if is_rebase_or_merge_in_progress():
                    log_guardian(
                        "WARN",
                        "Rebase/merge in progress - skipping pre-commit "
                        "(would corrupt state)",
                    )
                elif git_has_changes():
                    prefix = validate_commit_prefix(
                        pre_commit_config.get(
                            "messagePrefix", "pre-danger-checkpoint"
                        ),
                        default="pre-danger-checkpoint",
                    )
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    commit_msg = create_precommit_message(
                        prefix, command, timestamp
                    )

                    if is_dry_run():
                        log_guardian(
                            "DRY-RUN",
                            f"Would pre-commit: {commit_msg[:60]}...",
                        )
                    else:
                        if git_add_tracked():
                            if git_has_staged_changes():
                                if git_commit(commit_msg, no_verify=True):
                                    log_guardian(
                                        "INFO",
                                        f"Pre-commit created before: {cmd_preview}",
                                    )
                                else:
                                    log_guardian(
                                        "WARN",
                                        "Pre-commit failed: commit unsuccessful",
                                    )
                                    set_circuit_open(
                                        "pre-commit failed during dangerous operation"
                                    )
                            else:
                                log_guardian(
                                    "INFO",
                                    "No staged changes - skipping pre-commit "
                                    "(untracked only)",
                                )
                        else:
                            log_guardian(
                                "WARN",
                                "Pre-commit failed: unable to stage changes",
                            )
                            set_circuit_open(
                                "pre-commit staging failed during dangerous "
                                "operation"
                            )
        except Exception as e:
            log_guardian("WARN", f"Pre-commit failed: {e}")

        log_guardian("ASK", f"{final_verdict[1]}: {cmd_preview}")
        if is_dry_run():
            log_guardian("DRY-RUN", "Would ASK")
            sys.exit(0)
        print(json.dumps(ask_response(final_verdict[1])))
        sys.exit(0)

    # ========== Allow ==========
    if len(command) > 10 and not command.startswith(
        ("ls", "cd", "pwd", "echo", "cat", "type")
    ):
        log_guardian("ALLOW", cmd_preview)
    sys.exit(0)


if __name__ == "__main__":
    # TODO: Consider wrapping main() with with_timeout() using hookBehavior.timeoutSeconds.
    # Currently SKIPPED because:
    # 1. SIGALRM on Unix can interrupt git subprocess calls mid-execution, risking git state corruption
    # 2. Threading timeout on Windows cannot kill the running thread (it continues in background)
    # 3. Individual subprocess calls already have their own timeouts (5-30s)
    # 4. A blanket timeout could race with archive file operations, causing partial archives
    # If implemented, the HookTimeoutError should follow hookBehavior.onTimeout (default: "deny").
    try:
        main()
    except Exception as e:
        log_guardian("ERROR", f"Unhandled exception: {e}")
        set_circuit_open(f"bash_guardian crashed: {type(e).__name__}")
        # Use hookBehavior.onError from config (default: "deny" = fail-closed)
        try:
            error_action = get_hook_behavior().get("onError", "deny")
            response = make_hook_behavior_response(
                error_action,
                f"Guardian system error: {type(e).__name__}",
            )
            if response is not None:
                print(json.dumps(response))
        except Exception:
            # If hookBehavior lookup itself fails, fall back to deny (fail-closed)
            try:
                print(
                    json.dumps(
                        deny_response(
                            f"Guardian system error: {type(e).__name__}"
                        )
                    )
                )
            except Exception:
                pass
        sys.exit(0)
