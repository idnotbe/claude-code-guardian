# Stop Hook Error Analysis

## 9 Stop Hooks Breakdown

| # | Source | Type | Description |
|---|--------|------|-------------|
| 1 | claude-memory | prompt | Session summary check |
| 2 | claude-memory | prompt | Decision check |
| 3 | claude-memory | prompt | Runbook entry check |
| 4 | claude-memory | prompt | Constraint check |
| 5 | claude-memory | prompt | Tech debt check |
| 6 | claude-memory | prompt | Preference check |
| 7 | guardian | command | auto_commit.py |
| 8 | hookify | command | stop.py |
| 9 | project settings | command | Sound playback |

**Total: 9** — matches exactly!

## "JSON validation failed" — 6 errors

The 6 errors are almost certainly from the **claude-memory** plugin's 6 prompt-based Stop hooks.

### Why?
- All 6 are `type: "prompt"` hooks that ask a model to output JSON
- The prompts include extra fields (`lifecycle_event`, `cud_recommendation`)
  that may not be in Claude Code's expected Stop hook response schema
- OR the model occasionally outputs non-JSON (markdown wrapping, extra text)
- Claude Code validates hook output against a schema → "JSON validation failed"

### Evidence
- The other 3 hooks (guardian, hookify, project sound) are `type: "command"`
  and should work fine (guardian/hookify output proper JSON, sound outputs nothing)
- 9 total - 6 errors = 3 successes → matches the 3 command-based hooks

## Additional Issue Found
claude-memory's plugin.json has `"hooks": "./hooks/hooks.json"` — same duplicate
hooks bug that guardian just fixed! This means claude-memory would also show
"Duplicate hooks file detected" error.
