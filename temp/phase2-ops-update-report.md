# Phase 2: Ops Config Update Report

## File Changed
`/home/idnotbe/projects/ops/.claude/guardian/config.json`

## Changes Applied (3 patterns)

| Line | Target | Old Pattern | New Pattern |
|------|--------|-------------|-------------|
| 18 | `.git` | `(?i)(?:rm\|rmdir\|del\|remove-item).*\.git(?:\s\|/\|$)` | `(?i)(?:^\s*\|[;\|&`({]\s*)(?:rm\|rmdir\|del\|delete\|deletion\|remove-item)\b\s+.*\.git(?:\s\|/\|[;&\|)`'"]\|$)` |
| 22 | `.claude` | `(?i)(?:rm\|rmdir\|del\|remove-item).*\.claude(?:\s\|/\|$)` | `(?i)(?:^\s*\|[;\|&`({]\s*)(?:rm\|rmdir\|del\|delete\|deletion\|remove-item)\b\s+.*\.claude(?:\s\|/\|[;&\|)`'"]\|$)` |
| 26 | `_archive` | `(?i)(?:rm\|rmdir\|del\|remove-item).*_archive(?:\s\|/\|$)` | `(?i)(?:^\s*\|[;\|&`({]\s*)(?:rm\|rmdir\|del\|delete\|deletion\|remove-item)\b\s+.*_archive(?:\s\|/\|[;&\|)`'"]\|$)` |

## What Changed (OLD -> fully hardened)

The ops config had OLD patterns with NO anchoring. The update applied the full hardening in one step:

1. **Added start anchor with whitespace**: `(?:^\s*|[;|&`({]\s*)` -- catches leading whitespace, brace groups, and all separator contexts
2. **Expanded command list**: Added `delete`, `deletion` to the command group
3. **Added word boundary**: `\b\s+` after command group prevents false positives
4. **Enhanced terminator**: `[;&|)`'"]` catches quoted paths and more separator contexts

## Validation

- JSON syntax: VALID (python3 json.load)
- Regex compilation: All 3 patterns compile successfully
- Functional tests passed:
  - `rm -rf .git/` -- basic rm (matched)
  - `  rm .git/` -- leading whitespace (matched)
  - `{ rm .git/; }` -- brace group (matched)
  - `rm ".git"` -- quoted path (matched)
  - Same tests passed for `.claude` and `_archive` targets
