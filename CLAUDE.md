# claude-code-guardian

**All automated tests for this plugin live in this repo.**

Security guardrails plugin for Claude Code's `--dangerously-skip-permissions` mode.
Hooks into Bash, Edit, Read, Write (PreToolUse) and Stop (auto-commit) events.

## Repository Layout

- `hooks/scripts/` -- All guardian logic (6 Python files, ~3,900 LOC total)
- `tests/` -- Test suite (~1,009 methods across 6 subdirectories). See `tests/README.md` for details.
- `assets/` -- Default config and JSON schema
- `commands/`, `skills/`, `agents/` -- Plugin UX (init wizard, config guide, assistant)

## Development Rules

### Testing Requirements

- **Any PR touching `hooks/scripts/*guardian*.py` or `_guardian_utils.py` MUST include tests** covering the changed behavior.
- Run the unittest-based suites: `python -m pytest tests/core/ tests/security/ -v`
- Run individual files directly: `python3 tests/core/test_p0p1_comprehensive.py`
- Tests use `conftest.py` + `_bootstrap.py` for pytest compatibility. pytest is not a dependency.
- See `tests/README.md` for directory structure, category boundaries, and how to add tests.

### Security Invariants

- **Fail-closed end-to-end**: All security hooks (Bash, Edit, Read, Write) must deny on error or timeout. Helper functions used for boundary checks must not fail-open.
- **Hook output contract**: Hooks emit `hookSpecificOutput.permissionDecision` JSON (`deny`/`ask`/`allow`) on stdout. See `_guardian_utils.py` deny/ask/allow helpers.
- **Thin wrappers**: `edit_guardian.py`, `read_guardian.py`, `write_guardian.py` are thin entrypoints calling `run_path_guardian_hook()`. Keep them minimal.
- **Auto-commit is fail-open by design** -- commit failure must never block session termination.

### Known Security Gaps (Priority Order)

These are the most critical untested paths. See `TEST-PLAN.md` for the full action plan.

1. **Fail-open exception paths**: `is_symlink_escape()` (`_guardian_utils.py:927`) returns `False` on exception; `is_path_within_project()` (`_guardian_utils.py:974`) returns `True` on exception. Both undermine fail-closed semantics -- crafted paths that trigger `OSError` bypass protections.
2. **Auto-commit `--no-verify`**: `auto_commit.py:145` unconditionally bypasses pre-commit hooks. Combined with `includeUntracked=true`, can commit secrets.
3. **Zero test coverage**: `edit_guardian.py`, `read_guardian.py`, `write_guardian.py`, and `auto_commit.py` have no tests at all.

### Coverage Gaps by Script

| Script | LOC | Test Coverage |
|--------|-----|---------------|
| `bash_guardian.py` | 1,231 | Extensive (core + security + regression + usability suites) |
| `_guardian_utils.py` | 2,308 | Partial (functions tested via bash_guardian; path guardian paths untested) |
| `edit_guardian.py` | 75 | None |
| `read_guardian.py` | 71 | None |
| `write_guardian.py` | 75 | None |
| `auto_commit.py` | 173 | None |

## Quick Reference

    # Run core + security tests
    python -m pytest tests/core/ tests/security/ -v

    # Run all unittest-compatible tests
    python -m pytest tests/core/ tests/security/ tests/regression/ -v

    # Run a single test file
    python3 tests/security/test_bypass_v2.py

Key source files:

    hooks/scripts/bash_guardian.py       # Bash command interception
    hooks/scripts/_guardian_utils.py   # Shared logic (path checks, config, patterns)
    hooks/scripts/edit_guardian.py       # Edit hook entrypoint
    hooks/scripts/read_guardian.py       # Read hook entrypoint
    hooks/scripts/write_guardian.py      # Write hook entrypoint
    hooks/scripts/auto_commit.py        # Stop hook (auto-commit checkpoint)
    assets/guardian.default.json         # Default configuration
    assets/guardian.schema.json          # Config schema
