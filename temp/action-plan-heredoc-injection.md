# Working Memory: Heredoc Body Injection Action Plan

## Finding Source
- Discovered by: verify-1b (adversarial security verifier) during test migration verification
- Full report: temp/verification-1b.md, Section 2, Vector 2
- Date: 2026-02-22

## The Vulnerability
When a heredoc feeds an interpreter (`bash`, `sh`, `source`, `python3`, etc.),
the heredoc body IS executable code. But the guardian:
1. `split_commands()` correctly consumes heredoc body (line 476-506) -- body is excluded from sub-commands
2. Layer 1 scans joined sub-commands AFTER body exclusion (line 1437-1448) -- body text invisible
3. Layer 3+4 per-sub-command analysis only sees `bash << EOF`, not the body content
4. `is_delete_command()` doesn't detect `bash <<` or `source /dev/stdin <<` as dangerous

## Attack Vectors (from verify-1b)
```bash
# Vector A: bash heredoc
bash << EOF
rm -rf .git
EOF

# Vector B: source with /dev/stdin
source /dev/stdin << EOF
rm -rf .git
EOF

# Vector C: python interpreter heredoc
python3 << EOF
import os; os.remove('.env')
EOF

# Vector D: sh heredoc
sh << EOF
cat /etc/passwd > /tmp/leaked
EOF
```

## Why Current Design Excludes Body
Line 1437-1439 comment explains:
> After heredoc-aware split_commands(), heredoc body content is excluded,
> so .env/.pem in heredoc bodies no longer trigger false positives.

This is correct for DATA heredocs (cat << EOF) but WRONG for INTERPRETER heredocs.

## Key Code Locations
- `split_commands()`: line 82 (entry), line 425-428 (heredoc body consumption)
- `_consume_heredoc_bodies()`: line 476-506
- Layer 1 scan: line 1436-1448 (joins sub-commands, scans)
- `is_delete_command()`: line 1019-1053
- `is_write_command()`: line 1056-1105

## Possible Fix Approaches (brainstorm)

### Approach A: Block interpreter+heredoc at Layer 4
Add patterns to `is_delete_command` / `is_write_command` that match:
- `bash\s+<<`, `sh\s+<<`, `zsh\s+<<`, `dash\s+<<`
- `source\s+/dev/stdin\s*<<`, `\.\s+/dev/stdin\s*<<`
- `python[23]?\s+<<`, `perl\s+<<`, `ruby\s+<<`, `node\s+<<`
Pro: Simple, targeted
Con: Only catches delete/write -- interpreter heredoc can do anything

### Approach B: Block interpreter+heredoc at main guardian level
Add a new check before Layer 1: if the sub-command starts with an interpreter
and has a heredoc, verdict = "ask" regardless of body content.
Pro: Catches all interpreter heredocs, not just delete/write
Con: More invasive change

### Approach C: Scan heredoc body when command is an interpreter
When `split_commands()` encounters a heredoc, preserve the body text.
In the main guardian, if the command is an interpreter, also scan the body.
Pro: Most thorough -- detects .env in body of `bash << EOF`
Con: Most complex, may introduce false positives for legitimate scripts

### Approach D: Hybrid (recommended by verify-1b)
Add block/ask patterns for interpreter+heredoc combinations.
Simple pattern-match: if sub-command matches `(bash|sh|source|python.*|...) << `, verdict = "ask".
Pro: Simple, direct, covers the attack surface
Con: May false-positive on legitimate `bash << EOF` usage

## Self-Critique

### What am I missing?
1. `bash -c "rm ..."` is ALREADY a known gap (documented in test_tokenizer_edge_cases.py GAP comments) -- this new finding is in the SAME class but different mechanism
2. Heredoc body injection is arguably MORE dangerous than `bash -c` because the body can contain arbitrary multi-line scripts
3. The fix should probably address BOTH `bash -c` and `bash <<` together
4. Need to consider: `env bash <<`, `command bash <<`, `/usr/bin/bash <<`, `/bin/sh <<`
5. `exec` is another interpreter-like command: `exec 3<<EOF`

### What's the blast radius?
- False positive risk: Users legitimately running `bash << EOF` in scripts
- But in `--dangerously-skip-permissions` mode, any `bash <<` is suspicious
- Reasonable to "ask" rather than "deny" -- let the user decide

### Priority
- HIGH: This bypasses ALL guardian layers
- But: Requires the LLM to generate the specific pattern
- Realistic threat: prompt injection instructing LLM to use `bash << EOF` to hide commands

## Existing Format Reference
Read action-plans/test-plan.md and action-plans/_done/ for formatting.

## Draft Status
- [x] Research code paths
- [x] Document attack vectors
- [x] Brainstorm approaches
- [x] Self-critique
- [x] Write action plan
- [x] Review action plan (subagent: NEEDS_FIX -> 3 corrections applied)
  - Fixed line reference 1437-1444 -> 1437-1448
  - Added missing interpreters to full-path pattern (dash, ksh, csh, tcsh, fish, deno, bun)
  - Added sudo prefix pattern and edge case
- [x] Final verification (re-read + line number spot-check against source)
