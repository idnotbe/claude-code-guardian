# 3-Model Comparison Analysis

## Question 1: "hooks" key 제거?
| Model | Answer | Confidence |
|-------|--------|-----------|
| Claude (me) | Yes, remove | High |
| Codex 5.3 | Yes, remove | High |
| Gemini 3 Pro | Yes, remove | High |
| **Consensus** | **Unanimous: Remove "hooks" key** | |

## Question 2: .claude-plugin/ 처리 방법
| Model | Recommendation |
|-------|---------------|
| Claude (me) | Stepwise — fix hooks first, then decide scope |
| Codex 5.3 | **Keep .claude-plugin/** — don't double-load; inline is expected in dev repo |
| Gemini 3 Pro | **Move plugin.json to root**, remove .claude-plugin/ |
| Claude Code Guide | `--plugin-dir` looks for `.claude-plugin/plugin.json` (NOT root plugin.json) |

### Critical Finding
**Gemini is WRONG** about moving plugin.json to root.
- `--plugin-dir` expects manifest at `.claude-plugin/plugin.json`
- Confirmed by Claude Code docs AND vibe-check plugin (working example: `.claude-plugin/plugin.json` in ~/projects/vibe-check/)
- Moving to root would break `--plugin-dir` loading

### Codex is CORRECT
- `.claude-plugin/` should stay
- Inline auto-discovery when inside plugin's own repo is EXPECTED development behavior
- In other projects, use `--plugin-dir` via plugin-dirs

## Question 3: Can --plugin-dir and inline coexist?
| Model | Answer |
|-------|--------|
| Codex 5.3 | Yes but may double-load — avoid listing same plugin in both |
| Gemini 3 Pro | They conflict (partly wrong — they CAN coexist if not same plugin) |
| Claude Code Guide | Both load; no built-in way to disable inline |

## Scope Clarification
- "inline" = auto-discovered from .claude-plugin/ when CWD is plugin repo (DEV MODE)
- "project scope" via --plugin-dir = loaded in OTHER projects via plugin-dirs
- "user scope" = installed via /install into ~/.claude/plugins/
- **Guardian is NOT in user scope** — it's not in installed_plugins.json

## "Marketplace 'inline' not found" Error
- This is a **cosmetic display issue** in `/plugin` command
- "inline" is a virtual identifier for locally-discovered plugins
- Not a real marketplace, so lookup fails in display
- Does NOT affect plugin functionality
- Hooks still load and work (first auto-load succeeds)

## Final Recommendation
1. **Fix hooks duplication**: Remove `"hooks"` key from plugin.json ← fixes the actual error
2. **Keep .claude-plugin/**: It's the correct manifest location for both inline and --plugin-dir
3. **Keep guardian commented in own plugin-dirs**: Prevents double-loading when in this repo
4. **For other projects**: Add `~/projects/claude-code-guardian` to THEIR plugin-dirs
5. **"Marketplace inline" error**: Cosmetic — no code fix needed, Claude Code should handle this better
