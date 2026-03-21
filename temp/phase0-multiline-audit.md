# re.MULTILINE Audit: Per-Pattern Analysis

**Date**: 2026-03-21
**Context**: Phase 0b of heredoc-scanning-redesign.md
**Current flags**: `re.IGNORECASE | re.DOTALL` (no `re.MULTILINE`)

## Background

`re.MULTILINE` changes the behavior of `^` and `$` anchors:
- Without `re.MULTILINE`: `^` matches start-of-string, `$` matches end-of-string
- With `re.MULTILINE`: `^` matches start-of-line, `$` matches end-of-line

`re.DOTALL` makes `.` match newlines (already enabled).

## Analysis: Block Patterns (guardian.default.json)

| # | Pattern | Uses `^`/`$`? | MULTILINE Impact | Recommendation |
|---|---------|---------------|------------------|----------------|
| 1 | `rm\s+-[rRf]+\s+/(?:\s*$\|\*)` | `$` | HARMFUL: `$` currently requires end-of-string. With MULTILINE, `rm -rf /\ncat file` would match via end-of-line. But this pattern already catches the critical case. In heredoc bodies, MULTILINE would cause false positives on `rm -rf /` appearing in documentation. | **DEFER** |
| 2 | `(?:^\\s*\|[;\|&\`({]\\s*)(?:rm\|rmdir\|...)\\b\\s+.*\\.git(?:\\s\|/\|[;&\|)\`'\"]\|$)` | `^`, `$` | HARMFUL: `^` would match start-of-any-line, `$` end-of-any-line. In multiline commands, would match `rm .git` appearing on any line — including heredoc body content. | **DEFER** |
| 3-4 | Same structure as #2 for .claude, _archive | `^`, `$` | Same as #2 | **DEFER** |
| 5 | `git\s+push\s[^;\|&\\n]*(?:--force(?!-with-lease)\|-f\\b)` | `\n` in char class | NO IMPACT: Uses `\n` in negated char class `[^;\|&\\n]*`, not `^`/`$` | **NO CHANGE** |
| 6-8 | git filter-branch, reflog | None | NO IMPACT | **NO CHANGE** |
| 9 | `(?i)find\s+.*\s+-delete` | None | NO IMPACT | **NO CHANGE** |
| 10 | `shred\s+` | None | NO IMPACT | **NO CHANGE** |
| 11 | `(?:curl\|wget)[^\|]*\\|\s*(?:bash\|sh\|...)` | None | NO IMPACT | **NO CHANGE** |
| 12 | Fork bomb | None | NO IMPACT | **NO CHANGE** |
| 13-14 | `\$\([^)]*(?:rm\|...)...\)`, backtick variant | None | NO IMPACT | **NO CHANGE** |
| 15 | `(?i)eval\s+...` | None | NO IMPACT | **NO CHANGE** |
| 16-19 | Interpreter deletion patterns | `\n` in char class | NO IMPACT: Uses `[^\|&\\n]*` | **NO CHANGE** |

### Block patterns (guardian.recommended.json — additional patterns)

| Pattern | Uses `^`/`$`? | MULTILINE Impact | Recommendation |
|---------|---------------|------------------|----------------|
| nc/netcat reverse shell | None | NO IMPACT | **NO CHANGE** |
| base64 -d \| bash | None | NO IMPACT | **NO CHANGE** |
| mkfs | None | NO IMPACT | **NO CHANGE** |
| dd of=/dev/ | None | NO IMPACT | **NO CHANGE** |
| /dev/tcp/udp | None | NO IMPACT | **NO CHANGE** |
| xxd \| bash | None | NO IMPACT | **NO CHANGE** |
| openssl enc \| bash | None | NO IMPACT | **NO CHANGE** |
| LD_PRELOAD | None | NO IMPACT | **NO CHANGE** |
| bash -c rm .claude | None | NO IMPACT | **NO CHANGE** |
| eval rm .claude | None | NO IMPACT | **NO CHANGE** |
| perl/ruby truncate | `\n` in char class | NO IMPACT | **NO CHANGE** |
| setfacl/setfattr .claude | None | NO IMPACT | **NO CHANGE** |
| install .claude | None | NO IMPACT | **NO CHANGE** |
| ln .claude | `$` | HARMFUL: Would match on line boundary | **DEFER** |
| kill/pkill guard | None | NO IMPACT | **NO CHANGE** |
| chmod .claude | `$` | HARMFUL: Would match on line boundary | **DEFER** |
| python os.chmod .claude | None | NO IMPACT | **NO CHANGE** |

## Analysis: Ask Patterns

| Pattern | Uses `^`/`$`? | MULTILINE Impact | Recommendation |
|---------|---------------|------------------|----------------|
| `rm\s+-[rRf]+` | None | NO IMPACT | **NO CHANGE** |
| del, Remove-Item | None | NO IMPACT | **NO CHANGE** |
| git reset --hard | None | NO IMPACT | **NO CHANGE** |
| git clean | None | NO IMPACT | **NO CHANGE** |
| git checkout -- . | None | NO IMPACT | **NO CHANGE** |
| git stash drop | None | NO IMPACT | **NO CHANGE** |
| git push --force-with-lease | `\n` in char class | NO IMPACT | **NO CHANGE** |
| git branch -dD | None | NO IMPACT | **NO CHANGE** |
| truncate | None | NO IMPACT | **NO CHANGE** |
| mv .env/.git/.claude | None | NO IMPACT | **NO CHANGE** |
| mv CLAUDE.md | None | NO IMPACT | **NO CHANGE** |
| mv outside project | None | NO IMPACT | **NO CHANGE** |
| SQL DROP | None | NO IMPACT | **NO CHANGE** |
| SQL TRUNCATE | None | NO IMPACT | **NO CHANGE** |
| `(?i)delete\s+from\s+\w+(?:\s*;\|\s*$\|\s+--)` | `$` | MIXED: Would match `DELETE FROM table` at end-of-line (good for multiline SQL). But also increases false positives in heredoc bodies containing SQL documentation. | **DEFER** |
| find -exec rm | None | NO IMPACT | **NO CHANGE** |
| xargs rm | None | NO IMPACT | **NO CHANGE** |
| npm publish, etc (recommended) | None | NO IMPACT | **NO CHANGE** |
| sudo | None | NO IMPACT | **NO CHANGE** |
| crontab | None | NO IMPACT | **NO CHANGE** |

## Summary

### Patterns affected by re.MULTILINE:
- **5 patterns** use `$` in ways that would change behavior with `re.MULTILINE`
- **2 patterns** use `^` in ways that would change behavior with `re.MULTILINE`
- All affected patterns would see **INCREASED false positives** in heredoc body content

### Decision: DEFER re.MULTILINE

Adding `re.MULTILINE` would:
1. **Increase false positives** for heredoc body content containing dangerous-looking commands
2. Phase 1's redaction makes this less of a concern (safe bodies are removed before scanning)
3. BUT Phase 1 must ship and be validated first — changing anchor behavior simultaneously compounds risk

**After Phase 1 ships**, re-evaluate:
- If redaction works correctly, `re.MULTILINE` could be safely added for the 5 affected patterns
- Each pattern should be individually tested with the new redaction behavior
- The `^` patterns (#2-4) would benefit most — they'd catch `rm .git` at the start of ANY command in a compound pipeline, not just the first
