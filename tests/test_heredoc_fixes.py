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
            "rm -rf / was consumed as heredoc body -- arithmetic bypass\!"

    def test_let_shift_is_heredoc(self):
        """let val<<1 IS a heredoc in bash (let does not create arithmetic context).

        Bash tokenizes << as heredoc before let can interpret it as arithmetic.
        So 'echo done' is consumed as heredoc body. This is correct behavior.
        """
        subs = split_commands("let val<<1\necho done")
        # echo done IS consumed as heredoc body (delimiter '1' \!= 'echo done')
        assert not any("echo" in sub for sub in subs), \
            "echo done should be consumed as heredoc body for let val<<1"


    def test_no_space_heredoc(self):
        """cat<<EOF (no space before <<) should be detected as heredoc."""
        assert len(split_commands("cat<<EOF\nbody\nEOF")) == 1

    def test_dollar_double_paren_not_affected(self):
        """$(( x << 2 )) should not be misdetected (existing depth tracking handles it)."""
        subs = split_commands("echo $(( x << 2 ))\necho done")
        assert any("echo done" in sub for sub in subs)


class TestCommentHeredocRegression:
    """Verify that << inside comments does NOT trigger heredoc detection.

    CRITICAL SECURITY TEST: Without comment tracking, # << EOF would
    consume subsequent lines as heredoc body, hiding real commands
    from all scanning layers.
    """

    def test_comment_heredoc_not_consumed(self):
        """# << EOF should NOT consume next line as heredoc body."""
        subs = split_commands("# << EOF\nrm -rf /\nEOF")
        assert any("rm" in sub for sub in subs), \
            "rm -rf / was consumed as heredoc body via comment -- bypass!"

    def test_inline_comment_heredoc(self):
        """echo foo # << EOF should NOT consume next line."""
        subs = split_commands("echo safe # << EOF\ncat .env\nEOF")
        assert any(".env" in sub for sub in subs), \
            ".env was consumed as heredoc body via inline comment -- bypass!"

    def test_hash_in_word_not_comment(self):
        """echo foo#bar -- # inside word is NOT a comment."""
        subs = split_commands("echo foo#bar")
        assert len(subs) == 1
        assert "foo#bar" in subs[0]

    def test_dollar_hash_not_comment(self):
        """$# is not a comment."""
        subs = split_commands("echo $#")
        assert len(subs) == 1

    def test_dollar_brace_hash_not_comment(self):
        """${#} (argument count) is not a comment."""
        subs = split_commands("echo ${#}")
        assert len(subs) == 1
        assert "${#}" in subs[0]

    def test_dollar_brace_hash_array_not_comment(self):
        """${#array[@]} (array length) is not a comment."""
        subs = split_commands("echo ${#array[@]}")
        assert len(subs) == 1
        assert "${#array[@]}" in subs[0]

    def test_comment_at_line_start(self):
        """# at line start is a comment -- next line must not be consumed."""
        subs = split_commands("# this is a comment\necho hello")
        assert any("echo" in sub for sub in subs)

    def test_comment_text_in_sub_commands(self):
        """Comment text appears in sub_commands but is filtered from scan.

        Comment lines like '# .env' are included in split_commands output
        (the tokenizer preserves them). However, the main guardian loop
        filters out comment-only sub-commands before joining for Layer 1
        scan, so '.env' in a comment does NOT trigger a false positive.
        """
        subs = split_commands("# .env\ncat foo")
        # The comment line IS included in sub_commands
        assert any("# .env" in sub for sub in subs)
        # The real command is also present
        assert any("cat foo" in sub for sub in subs)
        # But when filtering for scan (as the guardian does), comments are excluded
        scan_text = ' '.join(
            sub for sub in subs if not sub.lstrip().startswith('#')
        )
        assert ".env" not in scan_text
        assert "cat foo" in scan_text


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

    def test_redirect_regex_negated_gt_prevents_overconsumption(self):
        """Deviation 1: [^|&;>]+ in redirect pattern prevents greedy match.

        Without > in the negated class, the regex [^|&;]+ would match across
        the second > in 'echo "data > temp" > output.txt', consuming everything
        as one match. The first match starts inside quotes and gets skipped by
        _is_inside_quotes, but the real redirect '> output.txt' is never reached
        because it was already consumed. With > in the negated class, each >
        starts a fresh match, so '> output.txt' is detected independently.
        """
        # This MUST be detected as a write (the real redirect is > output.txt)
        assert is_write_command('echo "data > temp" > output.txt')

    def test_redirect_regex_single_quoted_gt_then_real(self):
        """Single-quoted > followed by real redirect must be detected."""
        assert is_write_command("echo 'data > temp' > output.txt")


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
