# impl-decoder: Result Summary

## File Created

`/home/idnotbe/projects/claude-code-guardian/tests/core/test_decoder_glob.py`

## Test Results

**58 tests, all passing** (0.05s)

## Test Breakdown

### TestDecodeAnsiCStrings (33 tests)
Direct unit tests for `_decode_ansi_c_strings()` covering:

- **Hex escapes** (`\xHH`): dotenv decoding, single char, null byte -> space
- **Octal without leading zero** (`\NNN`): dotenv, single/two digit
- **Octal with leading zero** (`\0NNN`): dot, 3-digit max consumption edge case, full sequence showing it does NOT produce ".env"
- **Unicode 16-bit** (`\uHHHH`): dotenv, single char, non-ASCII
- **Unicode 32-bit** (`\UHHHHHHHH`): dotenv, emoji, out-of-range codepoint
- **Control char** (`\c`): terminates string, truncates remaining content
- **Standard escapes**: `\n`, `\t`, `\r`, `\a`, `\\`, `\'`, `\e`, `\E`, `\b`, `\f`, `\v`
- **Mixed/partial**: partial ANSI-C + plain text, piecewise concatenation, multiple sequences, passthrough, empty string

### TestExpandGlobChars (11 tests)
Direct unit tests for `_expand_glob_chars()` covering:

- Single-char bracket -> literal (dot, letter)
- Negated class (`[!x]`) unchanged
- POSIX negation (`[^x]`) unchanged
- Range (`[a-z]`) unchanged
- Multi-char class unchanged
- Escaped char in brackets (`[\v]` -> `v`)
- Empty brackets unchanged
- Passthrough, multiple brackets, command context

### TestObfuscationIntegration (14 tests)
Integration tests for `scan_protected_paths()` with obfuscation:

- **Baseline detection**: literal `.env`, `id_rsa`
- **ANSI-C hex**: `.env` and `id_rsa` via hex encoding
- **ANSI-C unicode**: 16-bit and 32-bit unicode encoding
- **ANSI-C octal**: no-leading-zero octal encoding
- **Glob bracket**: single and multiple bracket obfuscation
- **Piecewise ANSI-C**: split across multiple `$'...'` sequences
- **Boundary documentation**: empty quotes and brace expansion correctly return "allow" (handled at other layers)
- **False positive checks**: `ls -la`, `envsubst`, `environment`

## Key Findings

1. **Octal with leading zero 4-digit edge case**: `\0145` consumes only 3 digits (`014` = form-feed), leaving `5` as literal. This means `$'\056\0145\0156\0166'` does NOT produce ".env". Correct encoding without leading zero is `$'\56\145\156\166'`.

2. **`glob_to_literals()` filters generic patterns**: `*.env` is filtered out because "env" is in the `generic_words` set. Tests must use specific patterns like `.env` (exact match) instead.

3. **`scan_protected_paths` does NOT handle**: empty-quote stripping or brace expansion. Those obfuscation techniques are caught at other layers (extract_paths).

4. **`\c` escape**: Terminates the ANSI-C string entirely (discards everything after `\c`), not just the next character. `$'\cE'` produces empty string, not a control character.
