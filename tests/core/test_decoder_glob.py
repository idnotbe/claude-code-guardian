#!/usr/bin/env python3
"""Unit tests for _decode_ansi_c_strings() and _expand_glob_chars().

These internal functions had ZERO direct test coverage. This file provides
direct unit tests to catch decoder/glob regressions.

Run: python3 -m pytest tests/core/test_decoder_glob.py -v
  or: python3 tests/core/test_decoder_glob.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    _decode_ansi_c_strings,
    _expand_glob_chars,
    scan_protected_paths,
)

# Config that matches what glob_to_literals() will actually produce literals for.
# NOTE: "*.env" is filtered out by glob_to_literals() because "env" is in
# generic_words. Use exact patterns like ".env" and ".env.*" instead.
SCAN_CONFIG = {
    "zeroAccessPaths": [
        ".env",
        ".env.*",
        ".env*.local",
        "*.pem",
        "id_rsa",
        "id_rsa.*",
        "id_ed25519",
        "id_ed25519.*",
    ],
    "bashPathScan": {
        "enabled": True,
        "exactMatchAction": "ask",
        "patternMatchAction": "ask",
    },
}


# ============================================================
# _decode_ansi_c_strings() unit tests
# ============================================================


class TestDecodeAnsiCStrings(unittest.TestCase):
    """Direct unit tests for the ANSI-C string decoder."""

    # -- Hex escapes (\xHH) --

    def test_hex_decodes_dotenv(self):
        r"""$'\x2e\x65\x6e\x76' -> .env"""
        result = _decode_ansi_c_strings("$'\\x2e\\x65\\x6e\\x76'")
        self.assertEqual(result, ".env")

    def test_hex_single_char(self):
        r"""$'\x41' -> A"""
        result = _decode_ansi_c_strings("$'\\x41'")
        self.assertEqual(result, "A")

    def test_hex_null_byte_becomes_space(self):
        r"""$'\x00' -> space (V2-fix: null byte replaced with space)."""
        result = _decode_ansi_c_strings("$'\\x00'")
        self.assertEqual(result, " ")

    # -- Octal escapes WITHOUT leading zero (\NNN) --

    def test_octal_no_leading_zero_dotenv(self):
        r"""$'\56\145\156\166' -> .env (3-digit octal, no leading zero)."""
        result = _decode_ansi_c_strings("$'\\56\\145\\156\\166'")
        self.assertEqual(result, ".env")

    def test_octal_single_digit(self):
        r"""$'\7' -> BEL (single octal digit)."""
        result = _decode_ansi_c_strings("$'\\7'")
        self.assertEqual(result, "\x07")

    def test_octal_two_digit(self):
        r"""$'\56' -> '.' (two octal digits = 46 decimal)."""
        result = _decode_ansi_c_strings("$'\\56'")
        self.assertEqual(result, ".")

    # -- Octal escapes WITH leading zero (\0NNN) --

    def test_octal_leading_zero_dot(self):
        r"""$'\056' -> '.' (leading-zero octal, 3 digits consumed: 056 = 46)."""
        result = _decode_ansi_c_strings("$'\\056'")
        self.assertEqual(result, ".")

    def test_octal_leading_zero_max_3_digits(self):
        r"""$'\0145' consumes only 3 octal digits: '014' -> chr(12) + literal '5'.

        This is a critical edge case: the decoder reads at most 3 octal digits.
        \0145 -> \014 (form-feed) + literal '5', NOT 'e' (which would be octal 145).
        """
        result = _decode_ansi_c_strings("$'\\0145'")
        self.assertEqual(result, chr(0o014) + "5")
        self.assertNotEqual(result, "e")

    def test_octal_leading_zero_full_sequence_not_dotenv(self):
        r"""$'\056\0145\0156\0166' does NOT produce '.env' due to 3-digit limit.

        Only \056 produces '.'; the \0NNN sequences consume 3 digits each,
        producing control chars + leftover digits instead of 'e', 'n', 'v'.
        """
        result = _decode_ansi_c_strings("$'\\056\\0145\\0156\\0166'")
        self.assertTrue(result.startswith("."))
        self.assertNotIn("env", result)

    # -- Unicode 16-bit (\uHHHH) --

    def test_unicode_16bit_dotenv(self):
        r"""$'\u002e\u0065\u006e\u0076' -> .env"""
        result = _decode_ansi_c_strings("$'\\u002e\\u0065\\u006e\\u0076'")
        self.assertEqual(result, ".env")

    def test_unicode_16bit_single(self):
        r"""$'\u0041' -> A"""
        result = _decode_ansi_c_strings("$'\\u0041'")
        self.assertEqual(result, "A")

    def test_unicode_16bit_non_ascii(self):
        r"""$'\u00e9' -> e-with-acute."""
        result = _decode_ansi_c_strings("$'\\u00e9'")
        self.assertEqual(result, "\u00e9")

    # -- Unicode 32-bit (\UHHHHHHHH) --

    def test_unicode_32bit_dotenv(self):
        r"""$'\U0000002e\U00000065\U0000006e\U00000076' -> .env"""
        result = _decode_ansi_c_strings(
            "$'\\U0000002e\\U00000065\\U0000006e\\U00000076'"
        )
        self.assertEqual(result, ".env")

    def test_unicode_32bit_emoji(self):
        r"""$'\U0001f600' -> grinning face emoji (high codepoint)."""
        result = _decode_ansi_c_strings("$'\\U0001f600'")
        self.assertEqual(result, "\U0001f600")

    def test_unicode_32bit_out_of_range(self):
        r"""\U codepoint > 0x10FFFF should not be decoded -- falls through to raw."""
        result = _decode_ansi_c_strings("$'\\U00110000'")
        self.assertNotEqual(len(result), 1)

    # -- Control char escape (\c) --

    def test_control_c_terminates_string(self):
        r"""$'\cE' -> empty string (V2-fix: \c terminates ANSI-C string)."""
        result = _decode_ansi_c_strings("$'\\cE'")
        self.assertEqual(result, "")

    def test_control_c_truncates_remaining(self):
        r"""$'hello\cEworld' -> 'hello' (\c discards everything after it)."""
        result = _decode_ansi_c_strings("$'hello\\cEworld'")
        self.assertEqual(result, "hello")

    # -- Standard escapes --

    def test_standard_escapes_newline_tab_return(self):
        r"""$'\n\t\r' -> newline, tab, carriage return."""
        result = _decode_ansi_c_strings("$'\\n\\t\\r'")
        self.assertEqual(result, "\n\t\r")

    def test_standard_escape_alert(self):
        r"""$'\a' -> BEL."""
        result = _decode_ansi_c_strings("$'\\a'")
        self.assertEqual(result, "\a")

    def test_standard_escape_backslash(self):
        r"""$'\\' -> literal backslash."""
        result = _decode_ansi_c_strings("$'\\\\'")
        self.assertEqual(result, "\\")

    def test_standard_escape_single_quote(self):
        r"""$'\'' -> literal single quote."""
        result = _decode_ansi_c_strings("$'\\''")
        self.assertEqual(result, "'")

    def test_escape_e_lowercase(self):
        r"""$'\e' -> ESC (0x1b)."""
        result = _decode_ansi_c_strings("$'\\e'")
        self.assertEqual(result, "\x1b")

    def test_escape_E_uppercase(self):
        r"""$'\E' -> ESC (0x1b), same as \e (V2-fix)."""
        result = _decode_ansi_c_strings("$'\\E'")
        self.assertEqual(result, "\x1b")

    def test_escape_backspace(self):
        r"""$'\b' -> backspace."""
        result = _decode_ansi_c_strings("$'\\b'")
        self.assertEqual(result, "\b")

    def test_escape_formfeed(self):
        r"""$'\f' -> form feed."""
        result = _decode_ansi_c_strings("$'\\f'")
        self.assertEqual(result, "\f")

    def test_escape_vertical_tab(self):
        r"""$'\v' -> vertical tab."""
        result = _decode_ansi_c_strings("$'\\v'")
        self.assertEqual(result, "\v")

    # -- Mixed / partial ANSI-C --

    def test_mixed_partial_ansi_c(self):
        r"""$'\x2e'env -> .env (ANSI-C + plain text concatenation)."""
        result = _decode_ansi_c_strings("$'\\x2e'env")
        self.assertEqual(result, ".env")

    def test_piecewise_concatenation(self):
        r"""$'\x2e'$'\x65'$'\x6e'$'\x76' -> .env (piecewise ANSI-C)."""
        result = _decode_ansi_c_strings("$'\\x2e'$'\\x65'$'\\x6e'$'\\x76'")
        self.assertEqual(result, ".env")

    def test_no_ansi_c_string_passthrough(self):
        """Plain command without $'...' should pass through unchanged."""
        cmd = "cat /etc/passwd"
        result = _decode_ansi_c_strings(cmd)
        self.assertEqual(result, cmd)

    def test_mixed_ansi_and_plain(self):
        r"""cat $'\x2e'env -> cat .env"""
        result = _decode_ansi_c_strings("cat $'\\x2e'env")
        self.assertEqual(result, "cat .env")

    def test_multiple_ansi_c_strings(self):
        r"""Two separate $'...' sequences in one command."""
        result = _decode_ansi_c_strings("echo $'\\x41' $'\\x42'")
        self.assertEqual(result, "echo A B")

    def test_empty_ansi_c_string(self):
        """$'' decodes to empty string."""
        result = _decode_ansi_c_strings("$''")
        self.assertEqual(result, "")


# ============================================================
# _expand_glob_chars() unit tests
# ============================================================


class TestExpandGlobChars(unittest.TestCase):
    """Direct tests for single-char glob bracket expansion."""

    def test_single_char_bracket_dot(self):
        """[.]env -> .env (single-char bracket = literal)."""
        result = _expand_glob_chars("[.]env")
        self.assertEqual(result, ".env")

    def test_single_char_bracket_letter(self):
        """[e]nv -> env"""
        result = _expand_glob_chars("[e]nv")
        self.assertEqual(result, "env")

    def test_negated_class_unchanged(self):
        """[!x]env -> unchanged (negation = real glob, not single char)."""
        result = _expand_glob_chars("[!x]env")
        self.assertEqual(result, "[!x]env")

    def test_posix_negation_unchanged(self):
        """[^x]env -> unchanged (caret negation = real glob)."""
        result = _expand_glob_chars("[^x]env")
        self.assertEqual(result, "[^x]env")

    def test_range_unchanged(self):
        """[a-z]env -> unchanged (range = real glob)."""
        result = _expand_glob_chars("[a-z]env")
        self.assertEqual(result, "[a-z]env")

    def test_multi_char_unchanged(self):
        """[abc]env -> unchanged (multiple chars = real glob)."""
        result = _expand_glob_chars("[abc]env")
        self.assertEqual(result, "[abc]env")

    def test_escaped_char_in_brackets(self):
        r"""[\v]env -> venv (backslash-escaped single char)."""
        result = _expand_glob_chars("[\\v]env")
        self.assertEqual(result, "venv")

    def test_empty_brackets_unchanged(self):
        """[]env -> unchanged (no match for single-char pattern)."""
        result = _expand_glob_chars("[]env")
        self.assertEqual(result, "[]env")

    def test_no_brackets_passthrough(self):
        """Plain text without brackets passes through unchanged."""
        cmd = "cat .env"
        result = _expand_glob_chars(cmd)
        self.assertEqual(result, cmd)

    def test_multiple_brackets(self):
        """[.]e[n]v -> .env (two single-char brackets)."""
        result = _expand_glob_chars("[.]e[n]v")
        self.assertEqual(result, ".env")

    def test_bracket_in_command_context(self):
        """cat [.]env -> cat .env"""
        result = _expand_glob_chars("cat [.]env")
        self.assertEqual(result, "cat .env")


# ============================================================
# Integration: scan_protected_paths with obfuscation
# ============================================================


class TestObfuscationIntegration(unittest.TestCase):
    """Integration tests: scan_protected_paths detects obfuscated paths.

    scan_protected_paths normalizes commands via _decode_ansi_c_strings and
    _expand_glob_chars before scanning. It does NOT handle brace expansion
    or empty-quote stripping (those are handled at other layers).

    The config uses exactMatchAction/patternMatchAction = "ask", so detected
    paths produce "ask" verdict (not "deny"). We check for != "allow".
    """

    # -- Baseline: literal protected paths --

    def test_literal_dotenv_detected(self):
        """Baseline: literal .env should be detected."""
        verdict, _ = scan_protected_paths("cat .env", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow")

    def test_literal_id_rsa_detected(self):
        """Baseline: literal id_rsa should be detected."""
        verdict, _ = scan_protected_paths("cat id_rsa", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow")

    # -- ANSI-C hex obfuscation --

    def test_ansi_hex_dotenv_detected(self):
        r"""cat $'\x2e\x65\x6e\x76' should detect .env via ANSI-C decoding."""
        verdict, reason = scan_protected_paths(
            "cat $'\\x2e\\x65\\x6e\\x76'", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    def test_ansi_hex_id_rsa_detected(self):
        r"""cat $'\x69\x64\x5f\x72\x73\x61' -> id_rsa."""
        verdict, reason = scan_protected_paths(
            "cat $'\\x69\\x64\\x5f\\x72\\x73\\x61'", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow", f"Should detect id_rsa: {reason}")

    # -- ANSI-C unicode obfuscation --

    def test_ansi_unicode16_dotenv_detected(self):
        r"""cat $'\u002e\u0065\u006e\u0076' -> .env via unicode-16 decoding."""
        verdict, reason = scan_protected_paths(
            "cat $'\\u002e\\u0065\\u006e\\u0076'", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    def test_ansi_unicode32_dotenv_detected(self):
        r"""cat $'\U0000002e\U00000065\U0000006e\U00000076' -> .env."""
        verdict, reason = scan_protected_paths(
            "cat $'\\U0000002e\\U00000065\\U0000006e\\U00000076'", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    # -- ANSI-C octal (no leading zero) --

    def test_ansi_octal_dotenv_detected(self):
        r"""cat $'\56\145\156\166' -> .env via octal decoding."""
        verdict, reason = scan_protected_paths(
            "cat $'\\56\\145\\156\\166'", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    # -- Glob bracket obfuscation --

    def test_glob_bracket_dot_detected(self):
        """cat [.]env -> .env after glob expansion."""
        verdict, reason = scan_protected_paths("cat [.]env", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    def test_glob_bracket_multiple_detected(self):
        """cat [.]e[n]v -> .env after multiple glob expansions."""
        verdict, reason = scan_protected_paths("cat [.]e[n]v", SCAN_CONFIG)
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    # -- Piecewise ANSI-C obfuscation --

    def test_piecewise_ansi_detected(self):
        r"""cat $'\x2e'$'\x65'$'\x6e'$'\x76' -> .env via piecewise decode."""
        verdict, reason = scan_protected_paths(
            "cat $'\\x2e'$'\\x65'$'\\x6e'$'\\x76'", SCAN_CONFIG
        )
        self.assertNotEqual(verdict, "allow", f"Should detect .env: {reason}")

    # -- Techniques NOT handled by scan_protected_paths (Layer 1) --

    def test_empty_quotes_not_detected(self):
        r"""cat .e""nv -> allow (scan_protected_paths does not strip empty quotes).

        Empty-quote obfuscation is caught at other layers, not Layer 1.
        """
        verdict, _ = scan_protected_paths('cat .e""nv', SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    def test_brace_expansion_not_detected(self):
        """cat .{e,x}nv -> allow (scan_protected_paths does not expand braces).

        Brace expansion is caught at other layers, not Layer 1.
        """
        verdict, _ = scan_protected_paths("cat .{e,x}nv", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    # -- Safe commands: no false positives --

    def test_safe_command_allow(self):
        """ls -la should not trigger any detection."""
        verdict, _ = scan_protected_paths("ls -la", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    def test_envsubst_not_false_positive(self):
        """envsubst should not trigger .env detection."""
        verdict, _ = scan_protected_paths("envsubst < template", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")

    def test_environment_not_false_positive(self):
        """'environment' should not trigger .env detection."""
        verdict, _ = scan_protected_paths("echo environment", SCAN_CONFIG)
        self.assertEqual(verdict, "allow")


if __name__ == "__main__":
    unittest.main()
