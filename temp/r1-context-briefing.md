# Round 1 Context Briefing

## Mission
Evaluate two action plans in claude-code-guardian for rationality, considering BOTH the guardian plugin's security perspective AND the claude-memory plugin's operational perspective.

## The Two Action Plans

### Plan A: `action-plans/heredoc-pattern-false-positives.md`
- **Problem**: Layer 0/0b scan raw command strings before `split_commands()`, so heredoc body content (docs, tutorials, seed data) triggers false DENY/ASK.
- **Severity**: MEDIUM (usability, not security)
- **Fix**: Move `split_commands()` before Layer 0/0b, with selective body retention (data commands strip bodies, interpreter commands retain them).
- **Key design**: `_DATA_HEREDOC_COMMANDS` allowlist (fail-closed: unknown = interpreter = retain body for scanning).
- **Subsumes**: `interpreter-heredoc-bypass.md` mechanism — interpreter heredoc bodies get scanned because they're NOT in the data allowlist.

### Plan B: `action-plans/interpreter-path-resolution.md`
- **Problem**: F1 safety net fires false ASK when interpreter `-c` commands use destructive APIs but `extract_paths()` can't resolve targets from source code payloads.
- **Severity**: MEDIUM (usability, not security)
- **Origin**: claude-memory plugin operational experience (python3 -c cleanup of .staging/ files).
- **Fix**: Add `extract_paths_from_interpreter_payload()` that extracts string literal paths from interpreter code, only activates when F1 would fire anyway.
- **Key design**: Fail-closed — if no paths extracted, F1 still fires.

### Existing Related Plan: `action-plans/interpreter-heredoc-bypass.md`
- **Problem**: Interpreter heredoc bodies (bash << EOF) are invisible to all security layers.
- **Severity**: HIGH (security bypass)
- **Fix**: Pattern-based ask for interpreter+heredoc combos.
- **Note**: Plan A claims to subsume this plan's mechanism.

## Two Perspectives to Consider

### Guardian Perspective
- Security invariant: fail-closed end-to-end
- Don't introduce parsing differentials
- Test coverage is critical
- Complexity budget: bash_guardian.py is already 1,289 LOC

### claude-memory Perspective
- Operational pain: false positives disrupt automated workflows
- The .staging/ cleanup use case is real and recurring
- Prompt injection is a concern (see indirect-prompt-injection tech-debt record)
- Agents generate straightforward code, not obfuscated payloads

## Current Codebase State (key lines in main())
- Line 1423: `match_block_patterns(command)` — scans RAW string (Layer 0)
- Line 1437: `match_ask_patterns(command)` — scans RAW string (Layer 0b)
- Line 1442: `sub_commands = split_commands(command)` — heredoc-aware split
- Line 1450-1452: `scan_text` joins sub-commands (Layer 1, already fixed)
- Line 1476-1481: F1 safety net fires when write/delete detected but no paths
