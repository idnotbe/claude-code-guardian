# Phase 2 Implementation Spec

## Goal
Reduce F1 ASK frequency for legitimate interpreter operations by extracting paths from `-c`/`-e` payloads. When F1 would fire AND command is interpreter: extract paths → route through normal path validation. If no paths extracted → enriched F1 ASK.

## 2a: `extract_paths_from_interpreter_payload(command, project_dir) -> list[Path]`

**Location**: `hooks/scripts/bash_guardian.py`, near `extract_paths()` (around line 1250)

**Algorithm**:
1. Call `extract_interpreter_payload(command)` from `_guardian_utils` to get payload
2. If None → return []
3. Regex-extract single/double-quoted string literals from payload
4. For each literal:
   - Must look like path (`/` in it or starts with `.`)
   - Skip URLs (`://`)
   - Skip MIME types (single `/`, not starting with `.` or `/`)
   - **F2-2 MEDIUM**: Reject literals containing `{}` or `$` (interpolation markers → unresolvable)
   - Resolve relative to project_dir
   - **F2-1 CRITICAL**: Project boundary check via `Path.relative_to()` (NOT `str.startswith()`)
   - Expand globs (project-internal only, also using `relative_to()`)
5. Return list of resolved paths, or [] if none

## 2b: Modify F1 block in `main()`

**Location**: `bash_guardian.py` lines 1824-1831 (the `if (is_write or is_delete) and not sub_paths:` block)

**Change**:
```
if (is_write or is_delete) and not sub_paths:
    op_type = "delete" if is_delete else "write"

    # Check if interpreter command with extractable paths
    from _guardian_utils import check_interpreter_payload
    is_interp, interp_detail = check_interpreter_payload(sub_cmd)
    if is_interp:
        interp_paths = extract_paths_from_interpreter_payload(sub_cmd, project_dir)
        if interp_paths:
            sub_paths = interp_paths
            all_paths.extend(sub_paths)
            log_guardian("DEBUG", f"F1: Resolved {len(interp_paths)} path(s) from interpreter payload")
            # Fall through to path validation loop
        else:
            api_info = f" via {interp_detail}" if interp_detail else ""
            final_verdict = _stronger_verdict(
                final_verdict,
                ("ask", f"Detected {op_type}{api_info} but could not resolve target paths")
            )
    else:
        final_verdict = _stronger_verdict(
            final_verdict,
            ("ask", f"Detected {op_type} but could not resolve target paths"),
        )
```

Note: `check_interpreter_payload` is already imported at line 1404 in `is_delete_command()`. Move the import to module-level or use local import.

## 2c: Enrich F1 ASK messages

Already handled in 2b above — the `api_info` suffix adds detected API name.

Also modify `check_interpreter_payload()` in `_guardian_utils.py` to return the matched API name (currently returns `(bool, str)` where str is the full reason — extract just the API name for the enrichment).

## Key references in existing code

- `extract_interpreter_payload()`: `_guardian_utils.py:913` — extracts -c/-e payload string
- `check_interpreter_payload()`: `_guardian_utils.py:989` — checks for destructive APIs
- `_DESTRUCTIVE_API_PATTERN`: `_guardian_utils.py:907` — compiled pattern
- `_INTERPRETER_PREFIXES`: `_guardian_utils.py:885` — interpreter regex
- `extract_paths()`: `bash_guardian.py:1242` — existing path extraction for shell args
- `_is_within_project_or_would_be()`: `bash_guardian.py:1336` — uses `resolve(strict=False)`
- `is_within_project()`: uses `Path.relative_to()` at `bash_guardian.py:1362`
- F1 block: `bash_guardian.py:1824-1831`

## Security invariants

1. F2-1: Use `Path.relative_to()` for project boundary, NOT `str.startswith()` (avoids `/tmp/proj` vs `/tmp/proj_evil` confusion)
2. F2-2: Reject interpolation markers `{}` and `$` in literals
3. Fail-closed: empty return → F1 ASK fires (unchanged behavior)
4. ALL extracted paths go through full validation pipeline (zeroAccess, readOnly, noDelete, symlink)
5. Non-interpreter commands: standard F1 ASK unchanged
