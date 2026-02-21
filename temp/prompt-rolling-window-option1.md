# Prompt: Implement Rolling Window Enforcement (Option 1 — Separate `memory_enforce.py`)

**Target repo**: `/home/idnotbe/projects/claude-memory/`
**Problem brief**: `/home/idnotbe/projects/ops/temp/rolling-window-problem-brief.md`

---

## Context

The claude-memory plugin triggers a Guardian approval popup during session rolling window enforcement. The root cause: the main agent runs `python3 -c "import json, glob; ... if count > max_retained: ..."` as inline Python, and Guardian's `is_write_command()` regex falsely matches the `>` comparison operator as a shell redirect. Guardian allows `.py` script file execution but blocks inline Python with `>`.

**Solution**: Replace the inline rolling window logic with a proper `memory_enforce.py` script. This also requires refactoring `memory_write.py` to expose the retire logic as a reusable function.

---

## What to Implement

There are 3 files to change and 1 new file to create. The lock timeout fix and timeout increase are **hard prerequisites** — they must land before `memory_enforce.py` is usable.

### Part 1: `memory_write.py` Changes

All changes are in `hooks/scripts/memory_write.py`.

#### 1A. Fix lock timeout fallback (CRITICAL — hard prerequisite)

In the `_flock_index.__enter__` method, the timeout branch currently proceeds without the lock:

```python
if time.monotonic() >= deadline:
    print(
        "[WARN] Index lock timeout; proceeding without lock",
        file=sys.stderr,
    )
    return self
```

This is dangerous — a timed-out process proceeds without mutual exclusion, enabling concurrent index corruption. **However**, we cannot simply raise `TimeoutError` from `__enter__` because all 6 existing callers (`do_create`, `do_update`, `do_retire`, `do_archive`, `do_unarchive`, `do_restore`) use `with _flock_index(index_path):` without catching `TimeoutError`. Raising would crash them with unhandled tracebacks. Existing tests (`test_lock_timeout`, `test_permission_denied_handling` in `test_arch_fixes.py`) also expect the current behavior.

**Solution: `require_acquired()` method**

Keep `__enter__` returning `self` with `self.acquired = False` on failure, but add a `require_acquired()` method that raises. Only callers that need strict lock enforcement (i.e., `memory_enforce.py`) call this method. Existing callers are unchanged.

```python
# Change the timeout branch:
if time.monotonic() >= deadline:
    print(
        "[WARN] Index lock timeout; proceeding without lock",
        file=sys.stderr,
    )
    return self  # self.acquired remains False

# Keep the OSError branch as-is (proceeds without lock):
except OSError:
    print(
        "[WARN] Could not create lock directory; proceeding without lock",
        file=sys.stderr,
    )
    return self  # self.acquired remains False
```

Add the `require_acquired()` method to the class:

```python
def require_acquired(self) -> None:
    """Raise TimeoutError if the lock was not acquired.

    Call this inside a `with` block when strict lock enforcement is needed.
    Existing callers (do_create, etc.) do NOT call this — they continue
    with the legacy "proceed without lock" behavior.

    Public API: used by memory_enforce.py.
    """
    if not self.acquired:
        raise TimeoutError(
            "LOCK_TIMEOUT_ERROR: Index lock not acquired. "
            "Another process may hold the lock. Retry later."
        )
```

**Why not raise from `__enter__` directly**: This preserves backward compatibility with all 6 existing callers and their tests. Migrating those callers to strict lock enforcement is a separate, broader improvement (the problem brief acknowledges this in Section 7: the fix benefits all operations, but the scope here is `memory_enforce.py`).

**How `memory_enforce.py` uses it**:
```python
with FlockIndex(index_path) as lock:
    lock.require_acquired()  # STRICT: raises if lock not held
    # ... scan + retire logic ...
```

#### 1B. Increase lock timeout

Change `_LOCK_TIMEOUT` from `5.0` to `15.0`:

```python
_LOCK_TIMEOUT = 15.0    # Max seconds to wait for lock
```

This accommodates the wider critical section in `memory_enforce.py` (directory scan + multiple retirements within a single lock hold).

#### 1C. Rename `_flock_index` to `FlockIndex`

Rename the class from `_flock_index` to `FlockIndex`. This is now a public class (imported by `memory_enforce.py`). Follow PEP 8 class naming. Add a docstring/comment marking it as a stable public interface:

```python
class FlockIndex:
    """Portable lock for index mutations. Uses mkdir (atomic on all FS including NFS).

    Public API: imported by memory_enforce.py.
    """
```

Update all 6 internal references (`with _flock_index(index_path):` in `do_create`, `do_update`, `do_retire`, `do_archive`, `do_unarchive`, `do_restore`) to use `FlockIndex`.

#### 1D. Extract `retire_record()` from `do_retire()`

Extract the core retire logic into a new public function. The key distinction:
- `do_retire()` handles CLI argument parsing, path containment checks, output formatting, and acquires `FlockIndex`
- `retire_record()` handles ONLY the field-setting, atomic-write, and index-removal. It does NOT acquire the lock (caller is responsible).

**Signature:**

```python
def retire_record(target_abs: Path, reason: str, memory_root: Path, index_path: Path) -> dict:
    """Core retire logic. Caller MUST hold FlockIndex.

    Public API: used by do_retire() internally and by memory_enforce.py.

    Returns:
        {"status": "retired", "target": str, "reason": str} on success
        {"status": "already_retired", "target": str} if already retired (idempotent)

    Raises:
        json.JSONDecodeError: if target file has invalid JSON
        OSError/FileNotFoundError: if target file cannot be read
        ValueError: if target_abs is not under the project root (rel_path computation)
        RuntimeError: if target is archived (must unarchive first)
    """
```

**Implementation — extract from the current `do_retire()` function:**

The logic to extract is the section INSIDE `do_retire()`'s `with _flock_index(index_path):` block, plus the field-setting code above it. **Intentional behavioral change**: In the current code, file reading and field-setting happen OUTSIDE the lock, and only the atomic write + index removal happen inside. The refactored `retire_record()` does ALL of this (read + mutate + write + index removal) and is called from within the caller's lock scope. This eliminates a TOCTOU gap between reading and writing, and is a deliberate improvement.

Specifically:

1. Read the target file (JSON load)
2. Check idempotency: if already `retired`, return `{"status": "already_retired", ...}`
3. Check: if `archived`, raise `RuntimeError("Archived memories must be unarchived before retiring")`
4. Set retirement fields: `record_status`, `retired_at`, `retired_reason`, `updated_at`
5. Clear archived fields (`archived_at`, `archived_reason`)
6. Append change entry to `changes[]` (with CHANGES_CAP enforcement)
7. Compute `rel_path` **relative to project root** (NOT relative to CWD):
   ```python
   project_root = memory_root.parent.parent  # .claude/memory -> .claude -> project
   rel_path = str(target_abs.relative_to(project_root))
   ```
8. `atomic_write_json(str(target_abs), data)`
9. `remove_from_index(index_path, rel_path)`
10. Return result dict

**Then refactor `do_retire()` to call it:**

```python
def do_retire(args, memory_root: Path, index_path: Path) -> int:
    """Handle --action retire (soft retire)."""
    target = Path(args.target)
    target_abs = Path.cwd() / target if not target.is_absolute() else target

    if _check_path_containment(target_abs, memory_root, "RETIRE"):
        return 1

    if not target_abs.exists():
        print(f"RETIRE_ERROR\ntarget: {args.target}\nfix: File does not exist.")
        return 1

    reason = args.reason or "No reason provided"

    with FlockIndex(index_path):
        try:
            result = retire_record(target_abs, reason, memory_root, index_path)
        except (json.JSONDecodeError, OSError) as e:
            print(f"READ_ERROR\ntarget: {args.target}\nerror: {e}")
            return 1

    print(json.dumps(result))
    return 0
```

**Critical detail — relative path computation:**

The index stores paths relative to the project root (e.g., `.claude/memory/sessions/foo.json`). Currently `do_retire()` uses `rel_path = str(target)` where `target` is `Path(args.target)` — the original CLI argument. This works because the CLI caller passes relative paths from the project root.

But `retire_record()` (called by `memory_enforce.py`) won't have the original CLI argument. It will have `target_abs` (absolute path). So it MUST compute `rel_path` relative to `memory_root.parent.parent` (the project root), NOT relative to CWD:

```python
# Inside retire_record():
project_root = memory_root.parent.parent  # .claude/memory -> .claude -> project root
rel_path = str(target_abs.relative_to(project_root))
# If this raises ValueError, the target is not under the project root — fail loudly.
# Do NOT use a fallback (it would produce a wrong path, and remove_from_index would
# silently fail, leaving an orphaned index entry).
```

This is important because `memory_enforce.py` may be invoked with a different CWD than the original `memory_write.py --action create` call. Using CWD-based computation would produce a different `rel_path` than what's stored in the index, causing the `remove_from_index()` call to silently fail. If `ValueError` is raised, it means something is seriously wrong with the path configuration and should fail visibly.

### Part 2: New `memory_enforce.py`

Create `hooks/scripts/memory_enforce.py`.

#### Structure:

```python
#!/usr/bin/env python3
"""Rolling window enforcement for claude-memory.

Scans a category folder for active memories and retires the oldest
when the count exceeds the configured max_retained limit.

Usage:
    python3 memory_enforce.py --category session_summary [--max-retained 5] [--dry-run]
"""

import os
import sys

# ── venv bootstrap (MUST come before any memory_write imports) ──────────
_venv_python = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '.venv', 'bin', 'python3'
)
if os.path.isfile(_venv_python) and os.path.realpath(sys.executable) != os.path.realpath(_venv_python):
    try:
        import pydantic  # noqa: F401
    except ImportError:
        os.execv(_venv_python, [_venv_python] + sys.argv)

# ── sys.path setup (required for memory_write import) ──────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# ── imports ─────────────────────────────────────────────────────────────
import argparse
import json
from pathlib import Path

from memory_write import (  # noqa: E402
    retire_record,
    FlockIndex,
    CATEGORY_FOLDERS,
)

# ── constants ───────────────────────────────────────────────────────────
MAX_RETIRE_ITERATIONS = 10  # Safety valve: never retire more than this in one run
DEFAULT_MAX_RETAINED = 5
```

**Note**: The `sys.path.insert` is required because `memory_write.py` is in the same directory but may not be on Python's module search path depending on how the script is invoked (especially after the venv bootstrap `os.execv`). This follows the same pattern as `memory_draft.py` (lines 41-43).

#### Root Derivation:

```python
def _resolve_memory_root() -> Path:
    """Find .claude/memory/ directory.

    Strategy:
    1. $CLAUDE_PROJECT_ROOT environment variable (set by Claude Code)
    2. Walk CWD upward looking for .claude/memory/
    3. Hard error if not found
    """
    project_root_env = os.environ.get("CLAUDE_PROJECT_ROOT")
    if project_root_env:
        candidate = Path(project_root_env) / ".claude" / "memory"
        if candidate.is_dir():
            return candidate

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / ".claude" / "memory"
        if candidate.is_dir():
            return candidate

    print("ERROR: Cannot find .claude/memory/ directory.", file=sys.stderr)
    print("Ensure CLAUDE_PROJECT_ROOT is set or run from within the project.", file=sys.stderr)
    sys.exit(1)
```

#### Config Reading:

```python
def _read_max_retained(memory_root: Path, category: str, cli_override: int | None) -> int:
    """Read max_retained from memory-config.json, with CLI override."""
    if cli_override is not None:
        return cli_override

    config_path = memory_root / "memory-config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config.get("categories", {}).get(category, {}).get("max_retained", DEFAULT_MAX_RETAINED)
        except (json.JSONDecodeError, OSError):
            pass

    return DEFAULT_MAX_RETAINED
```

#### Active Session Scanning:

```python
def _scan_active(category_dir: Path) -> list[dict]:
    """Scan category folder for active memory files.

    Returns list of dicts sorted by created_at (oldest first):
        [{"path": Path, "data": dict, "id": str, "created_at": str}, ...]
    """
    results = []
    if not category_dir.is_dir():
        return results

    for f in sorted(category_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Skipping corrupted file {f.name}: {e}", file=sys.stderr)
            continue

        status = data.get("record_status", "active")  # absent = active (pre-v4 compat)
        if status == "active":
            results.append({
                "path": f,
                "data": data,
                "id": data.get("id", f.stem),
                "created_at": data.get("created_at", ""),
            })

    # Sort oldest first; filename as tiebreaker for identical timestamps
    results.sort(key=lambda s: (s["created_at"], s["path"].name))
    return results
```

#### Deletion Guard:

```python
def _deletion_guard(session_data: dict, session_id: str) -> None:
    """Warn if session contains unique content not captured elsewhere.

    Advisory only — does not block retirement.
    """
    content = session_data.get("content", {})
    unique_items = []

    for field in ("completed", "blockers", "next_actions"):
        items = content.get(field, [])
        if items:
            unique_items.extend(items[:3])  # Sample first 3 items

    if unique_items:
        sample = "; ".join(str(item) for item in unique_items[:5])
        print(
            f"[WARN] Session {session_id} contains content that may not be captured "
            f"elsewhere: {sample}. Content preserved during 30-day grace period.",
            file=sys.stderr,
        )
```

#### Main Enforcement Logic:

```python
def enforce_rolling_window(
    memory_root: Path,
    category: str,
    max_retained: int,
    dry_run: bool = False,
) -> dict:
    """Enforce rolling window for a category.

    Args:
        memory_root: Path to .claude/memory/ directory
        category: Category name (e.g., "session_summary")
        max_retained: Maximum active memories to keep
        dry_run: If True, print what would be retired without acting

    Returns summary dict:
        {"retired": [str, ...], "active_count": int, "max_retained": int}
    """
    index_path = memory_root / "index.md"

    folder_name = CATEGORY_FOLDERS.get(category)
    if not folder_name:
        print(f"ERROR: Unknown category '{category}'", file=sys.stderr)
        sys.exit(1)

    category_dir = memory_root / folder_name

    if not category_dir.is_dir():
        return {"retired": [], "active_count": 0, "max_retained": max_retained}

    retired_list = []

    if dry_run:
        # Dry-run: compute excess once, list what WOULD be retired (no lock needed)
        active = _scan_active(category_dir)
        excess = len(active) - max_retained
        if excess <= 0:
            return {"retired": [], "active_count": len(active), "max_retained": max_retained}

        excess = min(excess, MAX_RETIRE_ITERATIONS)
        for victim in active[:excess]:
            _deletion_guard(victim["data"], victim["id"])
            print(
                f"[ROLLING_WINDOW] Would retire: {victim['id']} "
                f"(created: {victim['created_at']})",
                file=sys.stderr,
            )
            retired_list.append(victim["id"])

        return {
            "retired": retired_list,
            "active_count": len(active) - len(retired_list),
            "max_retained": max_retained,
            "dry_run": True,
        }

    # Real enforcement: acquire lock for the entire scan-retire cycle
    with FlockIndex(index_path) as lock:
        lock.require_acquired()  # STRICT: raises TimeoutError if lock not held

        active = _scan_active(category_dir)
        excess = len(active) - max_retained

        if excess <= 0:
            return {"retired": [], "active_count": len(active), "max_retained": max_retained}

        excess = min(excess, MAX_RETIRE_ITERATIONS)

        for victim in active[:excess]:
            _deletion_guard(victim["data"], victim["id"])

            try:
                result = retire_record(
                    target_abs=victim["path"],
                    reason="Session rolling window: exceeded max_retained limit",
                    memory_root=memory_root,
                    index_path=index_path,
                )
                retired_list.append(victim["id"])
                remaining = len(active) - len(retired_list)
                print(
                    f"[ROLLING_WINDOW] Retired {victim['id']} "
                    f"(active: {remaining}/{max_retained})",
                    file=sys.stderr,
                )
            except FileNotFoundError as e:
                # File disappeared between scan and retire (rare, non-fatal)
                print(
                    f"[WARN] File gone before retire {victim['id']}: {e}. Continuing.",
                    file=sys.stderr,
                )
                continue
            except Exception as e:
                # Structural error — stop the loop
                print(
                    f"[WARN] Failed to retire {victim['id']}: {e}. Stopping enforcement loop.",
                    file=sys.stderr,
                )
                break

    return {
        "retired": retired_list,
        "active_count": len(active) - len(retired_list),
        "max_retained": max_retained,
    }
```

#### CLI Entry Point:

```python
def main():
    parser = argparse.ArgumentParser(
        description="Enforce rolling window retention for claude-memory categories."
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=list(CATEGORY_FOLDERS.keys()),
        help="Category to enforce rolling window on",
    )
    parser.add_argument(
        "--max-retained",
        type=int,
        default=None,
        help=f"Override max_retained (default: from config or {DEFAULT_MAX_RETAINED})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be retired without actually retiring",
    )
    args = parser.parse_args()

    # Validate --max-retained
    if args.max_retained is not None and args.max_retained < 1:
        print("ERROR: --max-retained must be >= 1", file=sys.stderr)
        sys.exit(1)

    memory_root = _resolve_memory_root()
    max_retained = _read_max_retained(memory_root, args.category, args.max_retained)

    try:
        result = enforce_rolling_window(memory_root, args.category, max_retained, args.dry_run)
    except TimeoutError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

### Part 3: SKILL.md Updates

In `skills/memory-management/SKILL.md`:

#### 3A. Phase 3 instructions

After the existing Phase 3 save section (around line 190, "After all saves, enforce session rolling window if session_summary was created"), replace the existing rolling window instruction with:

```markdown
After all saves, if session_summary was created, enforce the rolling window:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/hooks/scripts/memory_enforce.py" --category session_summary
```

This replaces the previous inline Python enforcement. The script automatically reads `max_retained` from `memory-config.json` and retires the oldest sessions to stay within the limit.
```

#### 3B. Session Rolling Window section

Update the "How It Works" section to reflect that enforcement is now via `memory_enforce.py`:

Replace step 4 ("Retire oldest: Call `memory_write.py --action retire ...`") with:

```markdown
4. **Retire oldest**: Handled automatically by `memory_enforce.py`. The script acquires the index lock, scans for active sessions, and retires excess sessions in a single atomic operation. The retirement reason is "Session rolling window: exceeded max_retained limit".
```

Remove the detailed algorithm steps (scan, sort, retire loop) since those are now internal to the script. Keep the configuration and manual cleanup sections unchanged.

---

## What NOT to Do

1. **Do NOT modify `hooks.json`**. `memory_enforce.py` is NOT a hook — it is called by the main agent as a regular script, just like `memory_write.py`.
2. **Do NOT add `--root` as a CLI argument**. Root is derived internally to avoid Guardian's path scanner.
3. **Do NOT use `Path.cwd()` for computing relative paths** in `retire_record()`. Use `memory_root.parent.parent` (the project root).
4. **Do NOT call `do_retire()` from `memory_enforce.py`**. Call `retire_record()` directly (no lock acquisition, since the enforce script already holds the lock).
5. **Do NOT add new dependencies**. `memory_enforce.py` uses only stdlib + memory_write imports.
6. **Do NOT change `memory-config.default.json`**. The `max_retained` field already exists.
7. **Do NOT change the existing 6 action handlers** (`do_create`, `do_update`, `do_retire`, `do_archive`, `do_unarchive`, `do_restore`) beyond the `FlockIndex` rename and `do_retire`'s refactoring to call `retire_record()`. Specifically: do NOT add `try/except TimeoutError` to these handlers — the `require_acquired()` approach is designed to keep them backward-compatible.
8. **Do NOT pass `--max-retained 0` or negative values**. The CLI validates `>= 1`.

---

## Test Cases

Write tests for these scenarios:

**`memory_enforce.py` tests:**
1. **Rolling window triggers**: 6 active sessions, max_retained=5 → retires 1 oldest
2. **No trigger**: 5 active sessions, max_retained=5 → 0 retirements
3. **Multiple retirements**: 8 active sessions, max_retained=5 → retires 3 oldest
4. **Correct ordering**: retires by `created_at` (oldest first), with filename tiebreaker
5. **Custom max_retained from CLI**: `--max-retained 3` overrides config
6. **Custom max_retained from config**: config says 3, no CLI flag → uses 3
7. **Corrupted JSON skipped**: one file has invalid JSON → skipped with warning, others processed
8. **`retire_record()` failure**: mock a structural error → warning logged, loop breaks, partial results returned
9. **File disappears between scan and retire**: delete a file after `_scan_active()` → `FileNotFoundError` caught, `continue` to next victim
10. **`--dry-run`**: prints what would be retired, JSON output includes `"dry_run": true`, no files modified
11. **Empty directory**: sessions folder doesn't exist → 0 retirements, exit 0
12. **Memory root discovery**: test `CLAUDE_PROJECT_ROOT` env var → CWD fallback → error when neither works
13. **Lock not acquired → `require_acquired()` raises**: mock `FlockIndex` with `acquired=False` → `TimeoutError` raised → script exits with error
14. **`--max-retained 0` rejected**: CLI validation rejects with error
15. **`--max-retained -1` rejected**: CLI validation rejects with error

**`memory_write.py` tests:**
16. **`require_acquired()` raises when not acquired**: `FlockIndex` with `acquired=False` → `TimeoutError`
17. **`require_acquired()` passes when acquired**: `FlockIndex` with `acquired=True` → no error
18. **Existing `test_lock_timeout` still passes**: `FlockIndex` timeout still returns `self` (not raise), `acquired=False`
19. **Existing `test_permission_denied_handling` still passes**: OSError still returns `self`, `acquired=False`
20. **`retire_record()` matches `do_retire()` behavior**: same retirement fields, same change entry format
21. **`retire_record()` relative path**: verify `rel_path` is computed relative to `memory_root.parent.parent`, not `Path.cwd()`
22. **`retire_record()` on already-retired file**: returns `{"status": "already_retired", ...}` (idempotent)
23. **`retire_record()` on archived file**: raises `RuntimeError`
24. **`FlockIndex` rename**: verify all 6 action handlers use `FlockIndex` (no remaining `_flock_index`)

---

## Verification Checklist

After implementation, verify:

- [ ] `python3 memory_enforce.py --category session_summary` runs without Guardian popup
- [ ] `python3 memory_enforce.py --category session_summary --dry-run` outputs JSON to stdout
- [ ] `FlockIndex.require_acquired()` raises `TimeoutError` when lock not held
- [ ] `FlockIndex` is used consistently (no remaining `_flock_index` references)
- [ ] `retire_record()` is importable from `memory_write`
- [ ] `memory_enforce.py` has venv bootstrap AND `sys.path.insert` before imports
- [ ] SKILL.md references `memory_enforce.py` for rolling window
- [ ] ALL existing `memory_write.py` tests still pass — especially `test_lock_timeout` and `test_permission_denied_handling` (backward compatibility)
- [ ] The `rel_path` in `retire_record()` uses `memory_root.parent.parent`, not `Path.cwd()`
- [ ] `--max-retained 0` and `--max-retained -1` are rejected by CLI validation
- [ ] No `ValueError` fallback in `rel_path` computation (let it propagate)
