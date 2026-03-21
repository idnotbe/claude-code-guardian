# Phase 1 Heredoc Redaction: Cross-Model Verification Report

**Date**: 2026-03-21
**Reviewers**: Codex 5.3 (codereviewer), Gemini 3.1 Pro (codereviewer)
**Coordinator**: Claude Opus 4.6
**Scope**: bash_guardian.py Phase 1 heredoc redaction (data structures, split_commands, _consume_heredoc_bodies, main)

---

## 1. Codex 5.3 Findings

### CRITICAL: Post-`<<` Redirections Invisible to Classifier
- **Verified**: YES (reproduced independently)
- Origin command is captured at `<<` parse time as `"".join(current).strip()` — this only includes text BEFORE `<<`. Any redirection appearing AFTER `<<` (e.g., `cat << EOF > script.sh`) is not part of `origin_cmd`.
- `_classify_heredoc_safety("cat", False)` returns `True` (safe), so the body is redacted even though the heredoc content gets written to `script.sh`.
- Worst case: `cat << EOF > >(bash)` executes the heredoc body in a subshell, and the body is completely hidden from Layer 0/0b pattern matching.
- **Confirmed bypass commands**:
  - `cat << EOF > script.sh` -- body written to file, redacted as safe
  - `cat << EOF >> script.sh` -- body appended to file, redacted as safe
  - `cat << EOF > >(bash)` -- body executed via process substitution, redacted as safe

### LOW: Quoted Redirection False Positives
- **Verified**: YES
- `_OUTPUT_REDIR_PATTERN` is a raw regex applied to the full command text, so `cat "literal > file" << EOF` triggers Rule 2 (UNSAFE) even though `> file` is inside quotes.
- This is conservative (fail-closed), not a bypass. Reduces false positive suppression effectiveness.

### LOW: Incomplete Wrapper Coverage in `_extract_base_command()`
- `env -i cat`, `time -p cat`, `command -- cat`, `timeout 5 cat`, `stdbuf -o0 cat` all return `''` (unknown) and trigger Rule 5 (UNSAFE).
- Fail-closed, not a bypass. Reduces feature effectiveness.

---

## 2. Gemini 3.1 Pro Findings

### CRITICAL: Unquoted Heredoc Command Substitution Bypass
- **Verified**: YES (reproduced independently)
- Bash expands `$(...)`, backticks, and `${...}` inside unquoted heredoc bodies. Since `cat << EOF` is classified SAFE, `cat << EOF\n$(rm -rf /)\nEOF` has its body redacted — hiding `$(rm -rf /)` from Layer 0/0b.
- The command substitution executes at shell runtime even though the guardian cannot see it.
- Note: This is only exploitable when the delimiter is unquoted (`EOF` not `'EOF'`). Quoted delimiters suppress expansion in bash.
- **Confirmed**: `cat << EOF\n$(rm -rf /)\nEOF` → body redacted, `$(rm -rf /)` invisible to pattern matching.

### HIGH: Unsafe Heredoc Bodies Missing from sub_commands List
- **Verified**: YES (reproduced independently)
- `split_commands()` consumes heredoc body lines without appending them to `sub_commands`. For unsafe heredocs (e.g., `bash << EOF\nrm -rf /protected\nEOF`), the body IS retained in `redacted_command` (correct for Layer 0/0b), but Layer 1 (Protected Path Scan) and Layer 3/4 (per-sub-command analysis) only see `['bash << EOF']`.
- Paths inside unsafe heredoc bodies are invisible to downstream layers.
- **Note**: This is a pre-existing architectural gap, not introduced by Phase 1. Phase 1 only added redaction; the heredoc body was already consumed before Phase 1.

### MEDIUM: Broken sudo Flag Parsing
- **Verified**: YES (reproduced independently)
- `sudo -H cat` → returns `''` (should return `'cat'`)
- `sudo -- cat` → returns `''` (should return `'cat'`)
- The while loop assumes all `-` prefixed args take exactly one argument via the nested `if` statement. `-H` (no argument) causes the loop to skip past `cat`.
- Fail-closed (Rule 5 UNSAFE), but causes unnecessary false positives.

### LOW: Fragile `origins` Truthiness Check
- `if classify and origins:` fails when `origins=[]`. Should be `origins is not None`.
- Theoretical only in current code (origins is always populated when classify=True), but brittle.

---

## 3. Agreement Between Models

| Finding | Codex | Gemini | Agreement |
|---------|-------|--------|-----------|
| Post-`<<` redirection bypass | CRITICAL | (not raised) | Codex only |
| Unquoted heredoc expansion bypass | (not raised) | CRITICAL | Gemini only |
| Unsafe bodies not in sub_commands | (not raised) | HIGH | Gemini only |
| sudo flag parsing broken | (not raised) | MEDIUM | Gemini only |
| Quoted redirection false positive | LOW | (not raised) | Codex only |
| Incomplete wrapper coverage | LOW | (not raised) | Codex only |
| origins truthiness | (not raised) | LOW | Gemini only |
| Fail-closed design is sound | POSITIVE | POSITIVE | **AGREE** |
| Newline-preserving redaction correct | POSITIVE | (not raised) | Codex only |
| Body range handling correct | POSITIVE | (not raised) | Codex only |
| _OUTPUT_REDIR_PATTERN well-crafted | (not raised) | POSITIVE | Gemini only |

**Key observation**: The two models found completely complementary bugs. Neither duplicate the other's findings, which validates using multi-model review.

---

## 4. Coordinator Assessment

### Severity Ranking (Integrated)

1. **CRITICAL — Post-`<<` redirection bypass** (Codex)
   The most dangerous finding. `cat << EOF > >(bash)` is a real-world execution vector that completely evades Layer 0/0b. The fix is straightforward: classify against the full command line (including text after `<<`), not just the pre-`<<` prefix. This likely means capturing `origin_cmd` after the entire pre-body line is parsed (at newline handling time) rather than at `<<` detection time.

2. **CRITICAL — Unquoted heredoc expansion bypass** (Gemini)
   This is a deep bash semantics issue. However, its practical impact is somewhat mitigated: (a) Claude Code typically generates heredocs with quoted delimiters for file writes, and (b) `$(...)` inside a cat heredoc body will execute regardless of the guardian -- the guardian's job is to detect the pattern, not prevent shell expansion. The real risk is that Layer 0 block patterns won't see the expanded command. **Recommended fix**: If the heredoc delimiter is unquoted AND the body contains `$`, backtick, or `\`, classify as UNSAFE. This is simple and fail-closed.

3. **HIGH — Unsafe bodies not in sub_commands** (Gemini)
   Pre-existing architectural gap. Not a Phase 1 regression. However, Phase 1 should document this as a known limitation. Paths inside `bash << EOF` bodies have never been scanned by Layer 1/3/4 — Phase 1 doesn't make this worse (Layer 0 still sees them via redacted_command for unsafe heredocs).

4. **MEDIUM — sudo flag parsing** (Gemini)
   Causes false positives (unnecessary UNSAFE classification) for `sudo -H cat << EOF` and `sudo -- cat << EOF`. Should be fixed for feature effectiveness, but not a security issue.

5. **LOW — Quoted redirection false positive** (Codex)
   Conservative behavior. Would require token-level redirection detection to fix properly. Low priority.

6. **LOW — origins truthiness** (Gemini)
   Defensive fix: change `if classify and origins:` to `if classify and origins is not None:`. Trivial.

7. **LOW — Incomplete wrapper coverage** (Codex)
   Feature effectiveness issue. Can be improved incrementally.

---

## 5. Actionable Items

### Must Fix Before Ship (Security)

- [ ] **BUG-1**: Classify against full command line, not just pre-`<<` prefix.
  - Option A: Capture origin at newline (body consumption time) instead of at `<<` parse time.
  - Option B: After `<<` parsing completes, update origin to include remaining text on the same logical line.
  - Preference: Option B preserves F1-1 intent while fixing the gap.

- [ ] **BUG-2**: Mark unquoted heredocs containing `$`, `` ` ``, or `\` as UNSAFE.
  - Add a Rule 0 (or modify classifier) to check whether the delimiter was quoted.
  - Need to propagate quoted/unquoted flag from `_parse_heredoc_delimiter()` through to the classifier.
  - Alternative: scan the body text for expansion characters before classifying as safe. Simpler but requires body access at classification time.

### Should Fix (Correctness)

- [ ] **BUG-3**: Fix sudo flag parsing in `_extract_base_command()`.
  - Handle no-argument flags (`-H`, `-n`, `-k`, etc.) vs. argument-taking flags (`-u`, `-g`, `-C`, etc.).
  - Handle `--` terminator.

- [ ] **BUG-4**: Change `if classify and origins:` to `if classify and origins is not None:`.

### Tests to Add

- [ ] `cat << EOF > script.sh` — body must be RETAINED (post-`<<` redirect)
- [ ] `cat << EOF >> script.sh` — body must be RETAINED
- [ ] `cat << EOF > >(bash)` — body must be RETAINED
- [ ] `cat << EOF 1>out` — body must be RETAINED
- [ ] `cat << EOF &> out` — body must be RETAINED
- [ ] `cat << EOF\n$(rm -rf /)\nEOF` — body must be RETAINED (unquoted + expansion)
- [ ] `cat << 'EOF'\n$(rm -rf /)\nEOF` — body may be REDACTED (quoted, no expansion)
- [ ] `sudo -H cat << EOF` — should classify as safe (after sudo fix)
- [ ] `sudo -- cat << EOF` — should classify as safe (after sudo fix)
- [ ] `bash << EOF\nrm -rf /protected\nEOF` — verify `/protected` NOT in sub_commands (document known gap)

### Optional Improvements

- [ ] Token-level redirection detection instead of regex (fixes quoted false positives)
- [ ] Expand wrapper coverage: `timeout`, `stdbuf`, `ionice`, `taskset`
- [ ] Consider adding `awk` and `sed` to neither list (they're already fail-closed as unknown)

---

## 6. Summary

Phase 1's fail-closed architecture is fundamentally sound. The 5-rule classifier, newline-preserving redaction, and body range construction are correct. However, two critical bypass vectors exist:

1. **Post-`<<` redirections** are invisible to the classifier because origin is captured too early.
2. **Unquoted heredoc bodies with shell expansions** are classified as safe even though bash will execute command substitutions within them.

Both are fixable without major architectural changes. The sudo flag parsing and origins truthiness issues are secondary but should be addressed. The cross-model review was highly effective — neither model found the other's critical bug, demonstrating the value of independent multi-model verification.
