---
status: not-started
progress: "Plan written, not yet implemented"
---

# Interpreter-Heredoc Body Injection Bypass

**Date**: 2026-02-22
**Severity**: HIGH
**Discovered by**: verify-1b adversarial security verifier (temp/verification-1b.md, Section 2, Vector 2)
**Related**: `bash -c` / `sh -c` / `eval` wrapper bypass (documented in tests/core/test_tokenizer_edge_cases.py GAP comments)

## Problem

When a heredoc feeds an interpreter command (`bash`, `sh`, `source`, `python3`, etc.), the heredoc body is executable code. The guardian's heredoc-aware `split_commands()` correctly excludes the body from sub-command output (to prevent false positives on data heredocs like `cat << EOF`). However, this means the body content is **invisible to all guardian security layers**.

### Bypass Vectors

```bash
# Vector A: bash heredoc -- rm in body bypasses all layers
bash << EOF
rm -rf .git
EOF

# Vector B: source with /dev/stdin
source /dev/stdin << EOF
rm -rf .git
cat .env > /tmp/leaked
EOF

# Vector C: python interpreter heredoc
python3 << EOF
import os; os.remove('.env')
EOF

# Vector D: sh heredoc
sh << EOF
cat /etc/passwd > /tmp/exfil
EOF

# Vector E: other interpreters
perl << 'PERL'
unlink('.env');
PERL

node << 'JS'
require('fs').unlinkSync('.env')
JS
```

### Why It Bypasses All Layers

| Layer | What it sees | Result |
|-------|-------------|--------|
| Layer 1 (Protected Path Scan) | Scans joined sub-commands after `split_commands()`. Body excluded. | `.env` / `.git` in body invisible |
| Layer 2 (Command Decomposition) | `split_commands()` consumes body lines (line 476-506) | Body content not in sub-command list |
| Layer 3 (Path Extraction) | `extract_paths()` only sees `bash << EOF`, not body | No paths extracted from body |
| Layer 4 (Command Type Detection) | `is_delete_command()` / `is_write_command()` see `bash << EOF` | No delete/write patterns matched |

### Root Cause

`split_commands()` line 425-428 consumes heredoc bodies at depth-0 newlines. The main guardian (line 1437-1448) then joins sub-commands for Layer 1 scanning, but body content is already stripped. No layer distinguishes between data heredocs (`cat << EOF`) and interpreter heredocs (`bash << EOF`).

## Fix Approach

### Recommended: Pattern-Based Ask for Interpreter+Heredoc (Approach D from analysis)

Add a new check in the main guardian function (`bash_guardian.py`, around line 1450) that detects interpreter commands with heredoc operators and returns `"ask"` verdict.

#### Target Patterns

Sub-command starts with an interpreter AND contains `<<`:

```python
INTERPRETER_HEREDOC_PATTERNS = [
    # Shell interpreters
    r"^\s*(?:bash|sh|zsh|dash|ksh|csh|tcsh|fish)\s+.*<<",
    # source/dot command with heredoc via /dev/stdin
    r"^\s*(?:source|\.)\s+/dev/stdin\s*<<",
    # Script interpreters
    r"^\s*(?:python[23]?|python\d[\d.]*|py)\s+.*<<",
    r"^\s*(?:perl|ruby|node|deno|bun)\s+.*<<",
    # Explicit paths to interpreters
    r"^\s*(?:/usr)?/(?:s?bin|local/bin)/(?:bash|sh|zsh|dash|ksh|csh|tcsh|fish|python[23]?|perl|ruby|node|deno|bun)\s+.*<<",
    # Privilege escalation prefix
    r"^\s*sudo\s+(?:bash|sh|zsh|dash|python[23]?|perl|ruby|node)\s+.*<<",
]
```

#### Verdict

`"ask"` (not `"deny"`) -- legitimate uses of `bash << EOF` exist, but they warrant user confirmation in `--dangerously-skip-permissions` mode.

#### Implementation Location

In `bash_guardian.py`, in the per-sub-command analysis loop (around line 1453):

```python
for sub_cmd in sub_commands:
    # NEW: Check for interpreter+heredoc bypass
    if _is_interpreter_heredoc(sub_cmd):
        final_verdict = _stronger_verdict(
            final_verdict,
            ("ask", f"Interpreter command with heredoc: {sub_cmd[:60]}")
        )
```

### Edge Cases to Handle

1. **`env bash << EOF`** -- `env` prefix before interpreter
2. **`command bash << EOF`** -- `command` builtin prefix
3. **`/usr/bin/bash << EOF`** -- full path to interpreter
4. **`bash -x << EOF`** -- flags between interpreter and heredoc
5. **`exec 3<< EOF`** -- fd redirection heredoc (NOT an interpreter heredoc)
6. **`cat << EOF | bash`** -- pipe into interpreter (body goes to `cat`, then piped)
7. **`sudo bash << EOF`** -- privilege escalation prefix before interpreter

### What This Does NOT Fix

- `bash -c "rm -rf .git"` -- the `-c` wrapper bypass remains a separate gap
- `printf '\x2e\x65\x6e\x76'` -- runtime path construction (inherent static analysis limitation)
- Heredoc body injection via pipe: `cat << EOF | bash` -- the body feeds `cat` not `bash`, but output pipes to `bash`. This is a variant that needs separate analysis.

## Testing Plan

### New Tests (tests/security/)

```python
class TestInterpreterHeredocBypass(unittest.TestCase):
    """Test detection of interpreter+heredoc bypass vectors."""

    def test_bash_heredoc_detected(self):
        """bash << EOF should trigger ask verdict."""
        # After fix: verdict should be "ask"

    def test_sh_heredoc_detected(self):
        """sh << EOF should trigger ask verdict."""

    def test_source_stdin_heredoc_detected(self):
        """source /dev/stdin << EOF should trigger ask verdict."""

    def test_python_heredoc_detected(self):
        """python3 << EOF should trigger ask verdict."""

    def test_cat_heredoc_not_detected(self):
        """cat << EOF should NOT trigger (data heredoc, not interpreter)."""

    def test_bash_heredoc_with_flags(self):
        """bash -x << EOF should trigger."""

    def test_fullpath_interpreter_detected(self):
        """/usr/bin/bash << EOF should trigger."""

    def test_env_prefix_interpreter(self):
        """env bash << EOF should trigger."""

    def test_pipe_to_interpreter_variant(self):
        """cat << EOF | bash -- document behavior (separate vector)."""
```

### Regression Tests

- Verify `cat << EOF` with `.env` in body still does NOT trigger false positive
- Verify existing heredoc tests still pass (168 tests in new files)

## Scope and Priority

| Item | Priority | Effort |
|------|----------|--------|
| Pattern detection for interpreter+heredoc | P0 | Small (regex + check function) |
| Tests for new detection | P0 | Small (10-15 test methods) |
| `bash -c` / `eval` wrapper detection (related gap) | P1 | Medium (needs split_commands awareness) |
| `cat << EOF \| bash` pipe variant | P1 | Medium (needs pipeline analysis) |
| Runtime path construction documentation | P2 | Trivial (document as known limitation) |

## Relationship to Existing Gaps

This finding is in the same class as the `bash -c` wrapper bypass documented in `tests/core/test_tokenizer_edge_cases.py` (TestWrapperBypass class). Both are "interpreter wrapping" attacks where dangerous commands hide inside a wrapper that the guardian doesn't unwrap. The heredoc variant is MORE dangerous because:

1. Multi-line: can contain arbitrary complex scripts
2. Body is explicitly excluded from scanning (by design)
3. Common pattern in legitimate scripts, making detection more nuanced

Consider addressing both `bash -c` and `bash <<` gaps together in the implementation.
