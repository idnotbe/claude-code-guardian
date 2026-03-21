"""Phase 0 tests: _parse_heredoc_delimiter() fixes for backslash + ANSI-C quoting.

Tests verify that:
1. Backslash-escaped delimiters are correctly stripped (\\EOF -> EOF)
2. ANSI-C quoted delimiters ($'EOF') are correctly parsed
3. Locale translation delimiters ($"EOF") are correctly parsed
4. Subsequent commands after heredoc bodies are NOT silently consumed
5. Existing quoted/bare-word delimiters still work correctly
"""
import unittest
import sys
from pathlib import Path

# Bootstrap imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401

from bash_guardian import _parse_heredoc_delimiter, split_commands


class TestParseHeredocDelimiterBackslash(unittest.TestCase):
    """Tests for backslash-escaped heredoc delimiters."""

    def test_backslash_eof_strips_backslash(self):
        """cat << \\EOF should use 'EOF' as delimiter, not '\\EOF'."""
        delim, raw, pos = _parse_heredoc_delimiter(r'\EOF rest', 0)
        self.assertEqual(delim, 'EOF')
        self.assertEqual(raw, r'\EOF')

    def test_backslash_eof_split_commands(self):
        """Backslash delimiter: subsequent rm -rf .git must appear as sub-command."""
        cmd = 'cat << \\EOF\nsafe content\nEOF\nrm -rf .git'
        result = split_commands(cmd)
        # rm -rf .git must NOT be consumed as heredoc body
        self.assertIn('rm -rf .git', result)

    def test_backslash_end_marker(self):
        """cat << \\END_MARKER should use 'END_MARKER'."""
        delim, raw, pos = _parse_heredoc_delimiter(r'\END_MARKER rest', 0)
        self.assertEqual(delim, 'END_MARKER')

    def test_double_backslash_eof(self):
        r"""cat << \\EOF: \\ -> literal \, then EOF literal. Delimiter = \EOF."""
        delim, raw, pos = _parse_heredoc_delimiter('\\\\EOF rest', 0)
        self.assertEqual(delim, '\\EOF')

    def test_backslash_middle(self):
        """cat << E\\OF should strip backslash from middle."""
        delim, raw, pos = _parse_heredoc_delimiter(r'E\OF rest', 0)
        self.assertEqual(delim, 'EOF')


class TestParseHeredocDelimiterAnsiC(unittest.TestCase):
    """Tests for ANSI-C quoted heredoc delimiters ($'...')."""

    def test_ansi_c_quote_strips_prefix(self):
        """cat << $'EOF' should use 'EOF' as delimiter."""
        delim, raw, pos = _parse_heredoc_delimiter("$'EOF' rest", 0)
        self.assertEqual(delim, 'EOF')
        self.assertEqual(raw, "$'EOF'")

    def test_ansi_c_split_commands(self):
        """ANSI-C delimiter: subsequent dangerous command must be visible."""
        cmd = "cat << $'EOF'\nsafe body\nEOF\nrm -rf .git"
        result = split_commands(cmd)
        self.assertIn('rm -rf .git', result)

    def test_ansi_c_with_escape_in_delim(self):
        """$'E\\nOF' — escape inside delimiter string decoded."""
        delim, raw, pos = _parse_heredoc_delimiter("$'E\\nOF' rest", 0)
        # ANSI-C escape \n decoded to actual newline (matches bash behavior)
        self.assertEqual(delim, 'E\nOF')

    def test_ansi_c_empty_delimiter(self):
        """$'' — empty ANSI-C delimiter."""
        delim, raw, pos = _parse_heredoc_delimiter("$'' rest", 0)
        self.assertEqual(delim, '')


class TestParseHeredocDelimiterLocale(unittest.TestCase):
    """Tests for locale translation heredoc delimiters ($\"...\")."""

    def test_locale_quote_strips_prefix(self):
        """cat << $\"EOF\" should use 'EOF' as delimiter."""
        delim, raw, pos = _parse_heredoc_delimiter('$"EOF" rest', 0)
        self.assertEqual(delim, 'EOF')
        self.assertEqual(raw, '$"EOF"')

    def test_locale_split_commands(self):
        """Locale delimiter: subsequent dangerous command must be visible."""
        cmd = 'cat << $"EOF"\nsafe body\nEOF\nrm -rf .git'
        result = split_commands(cmd)
        self.assertIn('rm -rf .git', result)


class TestParseHeredocDelimiterExisting(unittest.TestCase):
    """Regression: existing delimiter forms still work."""

    def test_bare_word(self):
        delim, raw, pos = _parse_heredoc_delimiter('EOF rest', 0)
        self.assertEqual(delim, 'EOF')
        self.assertEqual(raw, 'EOF')

    def test_single_quoted(self):
        delim, raw, pos = _parse_heredoc_delimiter("'EOF' rest", 0)
        self.assertEqual(delim, 'EOF')
        self.assertEqual(raw, "'EOF'")

    def test_double_quoted(self):
        delim, raw, pos = _parse_heredoc_delimiter('"EOF" rest', 0)
        self.assertEqual(delim, 'EOF')
        self.assertEqual(raw, '"EOF"')

    def test_empty_at_end(self):
        delim, raw, pos = _parse_heredoc_delimiter('', 0)
        self.assertEqual(delim, '')

    def test_bare_word_with_tabs(self):
        """<<- uses tab-stripped delimiter; bare word should still work."""
        cmd = 'cat <<- EOF\n\tbody\n\tEOF\nrm -rf .git'
        result = split_commands(cmd)
        self.assertIn('rm -rf .git', result)


class TestKnownDivergences(unittest.TestCase):
    """Document known divergences from bash behavior (all fail-closed)."""

    def test_backslash_dollar_quote_diverges_failclosed(self):
        r"""cat << \$'EOF' — guardian uses $'EOF' as delim, bash uses $EOF.

        Known divergence (edge case 10): backslash before $ prevents ANSI-C
        detection. Bare-word handler reads \$'EOF' and produces delim=$'EOF'.
        Bash would interpret as literal $ + single-quoted 'EOF' = $EOF.
        Divergence is fail-closed: guardian's delimiter never matches $EOF
        → heredoc unterminated → subsequent commands consumed → safe.
        """
        cmd = "cat << \\$'EOF'\nbody\n$EOF\nrm -rf .git"
        result = split_commands(cmd)
        # Guardian's delimiter $'EOF' doesn't match $EOF → unterminated
        # → rm -rf .git is consumed as body (fail-closed)
        self.assertNotIn('rm -rf .git', result)

    def test_ansi_c_hex_escape_decoded(self):
        r"""$'\x45OF' — guardian decodes \x45 to 'E', producing delim='EOF'.

        ANSI-C escape sequences are decoded using _decode_ansi_c_strings().
        This prevents bypass where attacker uses hex-encoded delimiter to
        hide commands: bash sees EOF, guardian must also see EOF.
        """
        delim, raw, pos = _parse_heredoc_delimiter("$'\\x45OF' rest", 0)
        self.assertEqual(delim, 'EOF')  # \x45 = 'E'

    def test_ansi_c_hex_escape_split_commands(self):
        r"""$'\x45OF' bypass prevention: rm -rf / after EOF must be visible."""
        cmd = "cat << $'\\x45OF'\nEOF\nrm -rf /\n\\x45OF"
        result = split_commands(cmd)
        # Guardian's delimiter is now EOF (decoded). Body terminates at EOF.
        # rm -rf / appears as a separate sub-command.
        self.assertIn('rm -rf /', result)

    def test_unterminated_ansi_c_quote_failclosed(self):
        """$'EOF (no closing quote) — consumes entire remaining input."""
        delim, raw, pos = _parse_heredoc_delimiter("$'EOF", 0)
        # Unterminated: ANSI-C handler reads to end of input
        # Degenerate [2:-1] slice on consumed content
        # In split_commands, this means everything becomes one sub-command
        result = split_commands("cat << $'EOF\nbody\nEO\necho done")
        self.assertEqual(len(result), 1)  # fail-closed: everything consumed


class TestHeredocBodyConsumptionSecurity(unittest.TestCase):
    """Verify that heredoc body content doesn't leak as sub-commands."""

    def test_backslash_delim_body_not_leaked(self):
        """With \\EOF, body lines must be consumed, not leaked."""
        cmd = 'cat << \\EOF\nrm -rf /\nEOF\necho done'
        result = split_commands(cmd)
        self.assertNotIn('rm -rf /', result)
        self.assertIn('echo done', result)

    def test_ansi_c_delim_body_not_leaked(self):
        """With $'EOF', body lines must be consumed."""
        cmd = "cat << $'EOF'\nrm -rf /\nEOF\necho done"
        result = split_commands(cmd)
        self.assertNotIn('rm -rf /', result)
        self.assertIn('echo done', result)

    def test_locale_delim_body_not_leaked(self):
        """With $\"EOF\", body lines must be consumed."""
        cmd = 'cat << $"EOF"\nrm -rf /\nEOF\necho done'
        result = split_commands(cmd)
        self.assertNotIn('rm -rf /', result)
        self.assertIn('echo done', result)

    def test_unterminated_backslash_heredoc_fails_closed(self):
        """Unterminated heredoc with backslash delim: all remaining consumed (fail-closed)."""
        cmd = 'cat << \\EOF\nrm -rf /\nnever ends'
        result = split_commands(cmd)
        # rm -rf / should NOT appear as a sub-command
        self.assertNotIn('rm -rf /', result)
        self.assertNotIn('never ends', result)


if __name__ == '__main__':
    unittest.main()
