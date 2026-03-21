# Phase 0 Edge Case Analysis: _parse_heredoc_delimiter()

Analyzed commit: 6debefe (current HEAD on main)
Code location: `hooks/scripts/bash_guardian.py`, lines 443-507

---

## Edge Case 1: `cat << $'\EOF'` — backslash inside ANSI-C quoting

**Input to function:** `$'\EOF' rest` at position 0

**Code trace:**
- Matches `$` + `'` at line 461-462, enters ANSI-C branch.
- `quote_char = '`
- `i = 2`, now at `\` in `$'\EOF'`
- Line 467: `command[2] == '\'` and `i+1 < len` → true, so `i += 2` → `i = 4` (skips `\E`, now at `O`)
- `O` != `'` → `i = 5` (at `F`)
- `F` != `'` → `i = 6` (at `'`)
- `command[6] == '` → exits while loop
- `i < len` → `i = 7` (consumes closing quote)
- `raw_token = "$'\\EOF'"` (7 chars, indices 0-6)
- `delim = raw_token[2:-1]` = `\EOF` (literal backslash + EOF)

**What bash does:** In `$'...'`, `\E` is not a recognized ANSI-C escape sequence, so bash treats it as literal `\E`. The delimiter bash uses is literally `\EOF` (4 characters). The heredoc body must end with a line containing literally `\EOF`.

**What the code does:** Returns delimiter `\EOF` (the raw content between `$'` and `'`, with no escape processing). This is **correct by accident** — the code does not process ANSI-C escape sequences (`\n`, `\t`, `\x41`, etc.), it just extracts the raw text. For recognized escapes like `\n`, this diverges from bash (see below), but for unrecognized escapes like `\E`, the raw text happens to match what bash produces.

**Security concern:** LOW. The code does NOT process ANSI-C escape sequences into their actual character values. In bash, `$'\x45OF'` would produce `EOF` as the delimiter (since `\x45` = `E`), but the guardian would use `\x45OF` as the delimiter. This means the guardian's delimiter would NEVER match, causing unterminated-heredoc behavior, which is fail-closed. **Safe direction of divergence.**

---

## Edge Case 2: `cat << $'E\'OF'` — escaped single quote inside $'...'

**Input to function:** `$'E\'OF' rest` at position 0

**Code trace:**
- Enters ANSI-C branch, `quote_char = '`
- `i = 2`, at `E`
- `E` != `'` → `i = 3` (at `\`)
- Line 467: `command[3] == '\'` and `i+1 < len` → true, skips `\'` → `i = 5` (now at `O`)
- `O` → `i = 6`, `F` → `i = 7`, now at `'`
- `command[7] == '` → exits while loop
- `i = 8` (consumes closing quote)
- `raw_token = "$'E\\'OF'"` (8 chars)
- `delim = raw_token[2:-1]` = `E\'OF` (5 chars: E, \, ', O, F)

**What bash does:** In `$'...'`, `\'` is a recognized escape for a literal single quote. So the delimiter is `E'OF` (4 chars).

**What the code does:** Returns `E\'OF` (5 chars, with literal backslash and quote).

**Security concern:** MEDIUM-LOW. The guardian's delimiter `E\'OF` will never match a line containing `E'OF` in the heredoc body. This means the heredoc body is never terminated from the guardian's perspective → all subsequent lines are consumed → fail-closed. **Safe direction.** However, this could cause false positives where legitimate commands after the heredoc are swallowed as body content. This is a usability issue, not a security issue.

---

## Edge Case 3: `cat << $''` — empty ANSI-C delimiter

**Input to function:** `$'' rest` at position 0

**Code trace:**
- Enters ANSI-C branch, `quote_char = '`
- `i = 2`, at `'` (immediately the closing quote)
- `command[2] == '` → exits while loop immediately
- `i = 3` (consumes closing quote)
- `raw_token = "$''"` (3 chars)
- `delim = raw_token[2:-1]` = `''[2:-1]` → Wait, raw_token is `$''`, so `raw_token[2:-1]` = `'`... No.
  - `raw_token = "$''"`, length 3
  - `raw_token[2:-1]` = `"$''"[2:-1]` = `"'"[0:0]`... Let me be more careful.
  - `raw_token = "$''"` → characters are `$`, `'`, `'` → length 3
  - `raw_token[2:-1]` → from index 2 to index 2 (exclusive) → empty string `''`
  - `len(raw_token) >= 3` → true → `delim = ''`

**What bash does:** Bash treats `$''` as an empty string. `cat << $''` creates a heredoc with an empty-string delimiter. The first empty line terminates it.

**What the code does:** Returns delimiter `''` (empty string).

**Security concern:** MODERATE. An empty delimiter means `_consume_heredoc_bodies` compares each line (after `rstrip('\r')` and optional tab-stripping) against `''`. An empty line `""` would match. But if all body lines are non-empty, the heredoc never terminates → fail-closed. The real concern is: could an attacker use an empty delimiter to cause the guardian to terminate the heredoc on the FIRST empty line, when bash also terminates on the first empty line? In that case, behavior matches bash → **no security issue**. The empty delimiter case is obscure but correctly handled.

---

## Edge Case 4: `cat << \` — trailing backslash at end of input (no char after \)

**Input to function:** `\` at position 0 (assuming nothing follows)

**Code trace:**
- `\` is not `$`, not `'`/`"` → falls to bare-word path (line 490)
- `start = 0`
- `command[0] = '\'`, which is not in stop set → `i = 1`
- `i >= len(command)` → exits while loop
- `raw_token = '\'` (1 char)
- Backslash processing: `j = 0`, `raw_token[0] == '\'`, but `j + 1 < len(raw_token)` → `0 + 1 < 1` → FALSE
- Falls to else: `delim_chars.append('\\')`, `j = 1`
- `delim = '\'`

**What bash does:** `cat << \` at end of input — bash treats the trailing backslash as a line continuation. It would wait for more input. In a non-interactive script context with no more input, this is a syntax error.

**What the code does:** Returns delimiter `\` (literal backslash). This means `_consume_heredoc_bodies` looks for a line containing just `\`. Since there's no more input, the heredoc is unterminated → fail-closed.

**Security concern:** NONE. The trailing backslash becomes a delimiter that's unlikely to match anything. Fail-closed behavior.

---

## Edge Case 5: `cat << \\` followed by space — double backslash delimiter

**Input to function:** `\\ rest` at position 0 (in Python source; the actual string is two backslashes followed by ` rest`)

Wait — need to be precise. In the actual command string at runtime, `cat << \\` would have the input to _parse_heredoc_delimiter be two characters: `\`, `\`, then space.

**Code trace (input: `\\ rest`, i.e., backslash + backslash + space + rest):**
- Falls to bare-word path
- `start = 0`
- `command[0] = '\'` not in stop set → `i = 1`
- `command[1] = '\'` not in stop set → `i = 2`
- `command[2] = ' '` IS in stop set → exits while loop
- `raw_token = '\\\\'` (2 backslash chars)
- Backslash processing: `j = 0`, `raw_token[0] == '\'`, `j + 1 < 2` → true, append `raw_token[1]` which is `\` → `delim_chars = ['\\']`, `j = 2`
- `delim = '\'` (single backslash)

**What bash does:** `cat << \\` — the `\\` is a backslash-escaped backslash, producing literal `\` as delimiter. Bash looks for a line containing just `\` to end the heredoc.

**What the code does:** Returns delimiter `\` (single backslash). **Correct. Matches bash.**

**Security concern:** NONE. Correct behavior.

---

## Edge Case 6: `cat << $"E\"OF"` — escaped double quote inside $"..."

**Input to function:** `$"E\"OF" rest` at position 0

The actual string content: `$`, `"`, `E`, `\`, `"`, `O`, `F`, `"`, ` `, `r`, `e`, `s`, `t`

**Code trace:**
- Matches `$` + `"` at line 461-462, enters ANSI-C/locale branch
- `quote_char = '"'`
- `i = 2`, at `E`
- `E` != `"` → `i = 3` (at `\`)
- Line 467: `command[3] == '\'` and `i+1 < len` → true, skips `\"` → `i = 5` (at `O`)
- `O` → `i = 6`, `F` → `i = 7`, now at `"`
- `command[7] == '"'` → exits while loop
- `i = 8` (consumes closing quote)
- `raw_token = '$"E\\"OF"'` (8 chars: `$`, `"`, `E`, `\`, `"`, `O`, `F`, `"`)
- `delim = raw_token[2:-1]` = `E\"OF` (5 chars: E, \, ", O, F)

**What bash does:** In `$"..."`, `\"` is an escape for literal double-quote. The delimiter is `E"OF` (4 chars).

**What the code does:** Returns `E\"OF` (5 chars). The delimiter includes the raw backslash.

**Security concern:** MEDIUM-LOW. Same pattern as edge case 2. The guardian's delimiter `E\"OF` will never match a body line `E"OF` → heredoc never terminates → fail-closed. Safe but potential false positive (usability issue, not security issue).

---

## Edge Case 7: `cat << 'EOF` — unterminated single quote (existing behavior, regression check)

**Input to function:** `'EOF` at position 0

**Code trace (single/double quote branch, line 478):**
- `command[0] = '` → enters quoted path
- `quote_char = '`
- `start = 0`, `i = 1`
- `command[1] = E` → `i = 2`, `command[2] = O` → `i = 3`, `command[3] = F` → `i = 4`
- `i >= len(command)` → exits while loop
- `i < len(command)` → FALSE → does NOT consume closing quote
- `raw_token = "'EOF"` (4 chars)
- `delim = raw_token[1:-1]` = `EO` (2 chars)

**What bash does:** `cat << 'EOF` is a syntax error (unterminated quote). But if we're lenient, bash would wait for more input.

**What the code does:** Returns delimiter `EO`. This is a degenerate result from the `[1:-1]` slice on an unterminated quote. The delimiter `EO` is unlikely to match anything meaningful → fail-closed.

**Security concern:** NONE. This is pre-existing behavior, not affected by the Phase 0 change. The result is wrong but safely wrong (fail-closed direction). No regression.

---

## Edge Case 8: `cat << $'EOF` — unterminated ANSI-C quote

**Input to function:** `$'EOF` at position 0

**Code trace:**
- Matches `$` + `'` → enters ANSI-C branch
- `quote_char = '`
- `i = 2`, at `E`
- `E` → `i = 3`, `O` → `i = 4`, `F` → `i = 5`
- `i >= len(command)` → exits while loop
- `i < len(command)` → FALSE → does NOT consume closing quote
- `raw_token = "$'EOF"` (5 chars)
- `len(raw_token) >= 3` → true → `delim = raw_token[2:-1]` = `EO` (2 chars)

**What bash does:** Syntax error (unterminated `$'...`).

**What the code does:** Returns delimiter `EO` (strips `$'` from front and `F` from back via `[2:-1]`).

**Security concern:** LOW. Wrong delimiter, but safely wrong. If the attacker tries `cat << $'EOF\nrm -rf /\nEO\necho safe`, the guardian would terminate the heredoc at `EO` and expose `echo safe` as a command. But since `EO` is a garbage delimiter, the attacker can't predict useful behavior. And in bash this is a syntax error anyway, so no real command would execute.

**Note:** The `[2:-1]` slicing on unterminated input is a minor code smell. It would be cleaner to check for unterminated state and return `''` (fail-closed with empty delimiter → first empty line terminates, or consuming everything). But the current behavior is not exploitable.

---

## Edge Case 9: Interaction with `_consume_heredoc_bodies()`

**Question:** Does the Phase 0 fix change anything about body consumption?

**Analysis:** `_consume_heredoc_bodies()` receives `(delim, strip_tabs)` tuples and does exact string matching: `cmp_line == delim` (line 535). The Phase 0 fix changes what `delim` value gets passed in, but does NOT change `_consume_heredoc_bodies()` itself.

**Key interactions:**

1. **ANSI-C escape sequences not processed (edge cases 1, 2, 6):** The delimiter passed to `_consume_heredoc_bodies` contains raw backslash sequences (e.g., `\n`, `\'`). Bash would interpret these, so the actual delimiter in bash might be different. The guardian's delimiter is "more raw" → less likely to match → fail-closed.

2. **Empty delimiter from `$''` (edge case 3):** Passed as `''` to `_consume_heredoc_bodies`. Line comparison `cmp_line == ''` matches any empty line. This matches bash behavior.

3. **Backslash-stripped bare words:** A `\EOF` delimiter correctly becomes `EOF` after stripping. `_consume_heredoc_bodies` will match body lines against `EOF`. This matches bash behavior — **the primary bug this fix addresses**.

**Security concern:** NONE for the fix itself. The fix improves correctness for the most common case (bare-word backslash escaping). The ANSI-C divergence is pre-existing and fail-closed.

---

## Edge Case 10: `cat << \$'EOF'` — backslash before $ — ANSI-C or literal?

**Input to function:** `\$'EOF' rest` at position 0

**Code trace:**
- `command[0] = '\'` which is NOT `$` → does NOT enter ANSI-C branch
- `command[0] = '\'` which is NOT `'`/`"` → does NOT enter quoted branch
- Falls to bare-word path (line 490)
- `start = 0`
- Consume until stop character: `\`, `$`, `'`, `E`, `O`, `F`, `'` — NONE of these are in stop set `' \t\n;|&<>()'`
- Hits space at position 7 → exits while loop
- `raw_token = "\$'EOF'"` (7 chars: `\`, `$`, `'`, `E`, `O`, `F`, `'`)
- Backslash processing:
  - `j=0`: `\` with `j+1 < 7` → append `$`, `j=2`
  - `j=2`: `'` → append `'`, `j=3`
  - `j=3`: `E` → append `E`, `j=4`
  - `j=4`: `O` → append `O`, `j=5`
  - `j=5`: `F` → append `F`, `j=6`
  - `j=6`: `'` → append `'`, `j=7`
- `delim = "$'EOF'"` (6 chars: `$`, `'`, `E`, `O`, `F`, `'`)

**What bash does:** `\$` in a bare-word context makes the `$` literal (no longer a special character). So `\$'EOF'` is: literal `$`, then `'EOF'` is a single-quoted string yielding `EOF`. Bash concatenates: `$` + `EOF` = `$EOF`. The delimiter is `$EOF`.

**What the code does:** Returns `$'EOF'` (6 chars, including the quotes). This is WRONG compared to bash.

**Security concern:** MODERATE. This is the most interesting divergence found.
- The guardian thinks the delimiter is `$'EOF'` (6 chars with quotes)
- Bash thinks the delimiter is `$EOF` (4 chars)
- The guardian will look for a body terminator line `$'EOF'` which will never appear
- The heredoc body from the guardian's perspective never terminates → all subsequent lines consumed → **fail-closed**
- In bash, the heredoc terminates at line `$EOF`, and subsequent commands execute
- So the guardian would fail to see/scan commands that bash does execute after `$EOF`

**Wait — is this actually a security issue?** If an attacker crafts:
```
cat << \$'EOF'
innocent body
$EOF
rm -rf .git
```
Bash terminates the heredoc at `$EOF` and runs `rm -rf .git`. The guardian swallows `rm -rf .git` as heredoc body because it's looking for `$'EOF'` delimiter. The dangerous command is **hidden from the guardian**.

**HOWEVER:** This requires the command to actually reach bash. The guardian processes the command BEFORE it reaches bash. If the guardian fails to detect `rm -rf .git` as a sub-command, it may ALLOW the overall command. So the dangerous command runs unchecked.

**This is a genuine bypass vector.** Severity depends on whether the guardian's other layers (pattern matching on the raw command string) would catch `rm -rf .git` embedded in what the guardian thinks is a heredoc body.

Let me check: the guardian runs `split_commands()` to break the input into sub-commands, and then scans each sub-command for dangerous patterns. If `rm -rf .git` is consumed as heredoc body by `split_commands()`, it would NOT be scanned as a command.

**BUT:** Looking at the broader bash_guardian.py architecture — the raw command string is ALSO scanned by Layer 1 (protected path scan) which does pattern matching on the entire raw command. So `rm -rf .git` in the raw string would likely still be caught by path-based pattern matching regardless of how split_commands() parses it.

**Revised assessment:** LOW-MODERATE. The `split_commands()` divergence is real and could theoretically hide commands from sub-command-level analysis, but the guardian's multi-layer architecture (raw string scanning + sub-command scanning) provides defense in depth. The raw string scan would still see `rm -rf .git`.

---

## Vibe Check: Is this fix over-engineered or under-engineered?

### Under-engineered aspects:

1. **No ANSI-C escape sequence processing.** The code treats `$'...'` content as raw text between `$'` and `'`, without interpreting `\n`, `\t`, `\x41`, `\0`, `\'`, `\\`, etc. This means:
   - `$'\x45OF'` → guardian sees delimiter `\x45OF`, bash sees `EOF`
   - `$'E\nOF'` → guardian sees `E\nOF` (5 chars), bash sees `E` + newline + `OF` (4 chars with embedded newline — an exotic delimiter that's practically unusable)
   - All divergences are in the fail-closed direction, so this is acceptable for Phase 0.

2. **No concatenated token handling.** Bash allows `E'OF'`, `"E"OF`, `'E'OF`, `E"O"'F'` etc. as heredoc delimiters (all become `EOF`). The guardian only handles the case where the ENTIRE delimiter is one token type. This is a pre-existing limitation, not introduced by Phase 0.

3. **Edge case 10 (`\$'EOF'`) is a real parsing divergence** that could theoretically hide commands. Needs documentation at minimum, ideally a fix in Phase 1.

### Over-engineered aspects:

None. The fix is minimal and targeted. It adds exactly two code paths:
- ANSI-C/locale prefix detection (17 lines)
- Backslash processing in bare words (10 lines)

Both are straightforward and handle the most common real-world cases.

### What's missing:

1. **Unterminated ANSI-C quote handling** (edge case 8) produces a silently wrong delimiter via `[2:-1]` slicing. Should explicitly detect and return `''` for fail-closed.

2. **The `\$` + quote interaction** (edge case 10) is the biggest gap. When a backslash precedes `$`, the `$` should lose its special meaning, and subsequent `'...'` should be parsed as regular single quotes by the bare-word consumer. But since the bare-word consumer doesn't stop at quotes, it gobbles the quotes as literal characters. This produces a wrong delimiter. Fixing this properly requires the bare-word path to handle embedded quotes — a significant parser change better left for Phase 1.

3. **No explicit test for edge case 10.** The existing test suite does not cover `\$'EOF'`. This is the most security-relevant gap.

---

## Summary Table

| # | Edge Case | Bash Result | Code Result | Match? | Security |
|---|-----------|-------------|-------------|--------|----------|
| 1 | `$'\EOF'` | `\EOF` | `\EOF` | YES* | None |
| 2 | `$'E\'OF'` | `E'OF` | `E\'OF` | NO | Safe (fail-closed) |
| 3 | `$''` | empty | empty | YES | None |
| 4 | `\` (trailing) | syntax error | `\` | N/A | Safe (fail-closed) |
| 5 | `\\` + space | `\` | `\` | YES | None |
| 6 | `$"E\"OF"` | `E"OF` | `E\"OF` | NO | Safe (fail-closed) |
| 7 | `'EOF` (untermd) | syntax error | `EO` | N/A | Safe (fail-closed, pre-existing) |
| 8 | `$'EOF` (untermd) | syntax error | `EO` | N/A | Safe but sloppy |
| 9 | Body consumption | — | unchanged | — | None |
| 10 | `\$'EOF'` | `$EOF` | `$'EOF'` | **NO** | **LOW-MODERATE bypass risk** |

*Edge case 1 matches by accident — `\E` is not a recognized ANSI-C escape, so raw text happens to equal bash's interpretation.

## Recommendations for Phase 1

1. **Add test for edge case 10** (`\$'EOF'`) and document as known divergence.
2. **Harden unterminated ANSI-C/locale quote** (edge case 8): detect and return empty delimiter.
3. **Consider whether ANSI-C escape processing is needed** — current lack of processing is fail-closed, so it's safe but could cause false positives with exotic delimiters.
4. **Edge case 10 fix** requires the bare-word path to recognize when a backslash-escaped `$` is followed by quotes, treating the quotes as bare-word characters that should be consumed but included literally. This is the most important fix.
