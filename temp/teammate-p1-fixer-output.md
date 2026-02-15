# P1 Fix: noDeletePaths Enforcement in Write Tool Hook

## What was done

Added a `noDeletePaths` check to `run_path_guardian_hook()` in `hooks/scripts/_guardian_utils.py` (lines 2374-2389).

The new check is placed **after** the readOnly check block and **before** the `# ========== Allow ==========` section, following the existing tier ordering:

1. Symlink escape
2. Project boundary + external admission
3. Self-guardian
4. zeroAccessPaths
5. readOnlyPaths
6. **noDeletePaths (NEW - Write tool only, existing files only)**
7. Allow

## Code added (lines 2374-2389)

```python
    # ========== Check: No Delete (Write tool -- content destruction prevention) ==========
    if tool_name.lower() == "write" and match_no_delete(path_str):
        # Only block if file already exists (overwrite = data destruction)
        # Creating a new file that happens to match noDeletePaths is allowed
        resolved = expand_path(file_path)
        if resolved.exists():
            log_guardian("BLOCK", f"No-delete path overwrite ({tool_name}): {path_preview}")
            if is_dry_run():
                log_guardian("DRY-RUN", f"Would DENY {tool_name} (no-delete overwrite)")
                sys.exit(0)
            reason = (
                f"Protected from overwrite: {Path(file_path).name}"
                "\nThis file is in noDeletePaths. Use Edit tool for partial modifications."
            )
            print(_json.dumps(deny_response(reason)))
            sys.exit(0)
```

## Semantic reasoning

| Operation | Behavior | Rationale |
|-----------|----------|-----------|
| `Write` overwrite existing noDelete file | **BLOCKED** | Write replaces entire content = data destruction |
| `Write` create new file matching noDelete pattern | **ALLOWED** | No existing data to destroy |
| `Edit` modify existing noDelete file | **ALLOWED** | Edit makes surgical changes, preserves content |
| `Read` existing noDelete file | **ALLOWED** | Reading never destroys data |
| `rm` noDelete file via Bash | **BLOCKED** | Existing behavior in bash_guardian.py |

This preserves the documented semantics: noDeletePaths files "can be read and written but not deleted."

## Dependencies used (all already available in scope)

- `match_no_delete(path_str)` - checks path against noDeletePaths config patterns
- `expand_path(file_path)` - resolves path to absolute Path object
- `deny_response(reason)` - generates deny JSON response
- `log_guardian(level, msg)` - logging helper
- `is_dry_run()` - dry-run mode check
- `_json` - imported at top of `run_path_guardian_hook()` as `import json as _json`
- `Path` - from `pathlib` (already imported at module level)

## Test results

- **Core tests**: 180/180 passed (no regressions)
- **Security tests**: Pre-existing failures only (3 bash pattern bypasses unrelated to this change)
- **Regression tests**: 73/73 passed (no regressions)
- **Module load**: Clean import, no syntax errors

## File modified

- `/home/idnotbe/projects/claude-code-guardian/hooks/scripts/_guardian_utils.py` (lines 2374-2389 added)
