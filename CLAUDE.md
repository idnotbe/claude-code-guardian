# claude-code-guardian

**All automated tests for this plugin live in this repo.**

Security guardrails plugin for Claude Code's `--dangerously-skip-permissions` mode.
Hooks into Bash, Edit, Read, Write (PreToolUse) and Stop (auto-commit) events.

## Repository Layout

- `hooks/scripts/` -- All guardian logic (6 Python files + 1 bash script, ~4,220 LOC total)
- `tests/` -- Test suite (~631 methods across 7 subdirectories). See `tests/README.md` for details.
- `assets/` -- Default config and JSON schema
- `commands/`, `skills/`, `agents/` -- Plugin UX (init wizard, config guide, assistant)
- `action-plans/` -- 실행 계획 관리 (아래 Action Plans 섹션 참고)

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
- **SessionStart auto-activate is fail-open by design** -- config creation failure must never block session startup.

### Known Security Gaps (Priority Order)

Items 1-3 were **fixed** on 2026-03-22. See `action-plans/_done/security-fixes.md`.

1. ~~**Auto-commit secrets staging**~~ **FIXED**: `git_add_filtered()` filters files against `zeroAccessPaths` before staging. `_unstage_secret_files()` catches pre-staged secrets. Tests: `test_auto_commit.py`.
2. ~~**Non-dict JSON bypass**~~ **FIXED**: `isinstance(input_data, dict)` check in `run_path_guardian_hook()` denies non-dict JSON before it reaches wrapper `onError`. Tests: `test_failopen_edgecases.py::TestProtocolHole_MalformedValidJSON`.
3. ~~**Missing file_path bypass**~~ **FIXED**: Empty/missing `file_path` now returns deny for ALL tools. Tests: `test_failopen_edgecases.py::TestMissingFilePath_WriteEdit`.
4. **Normalization helpers fail-open**: `expand_path()`, `normalize_path()`, `normalize_path_for_matching()` return unresolved paths on exception. Defense-in-depth via independent checks mitigates risk.

### Coverage Gaps by Script

| Script | LOC | Test Coverage |
|--------|-----|---------------|
| `bash_guardian.py` | 1,289 | Extensive (core + security + regression + usability suites) |
| `_guardian_utils.py` | 2,426 | Substantial (fail-closed helpers, run_path_guardian_hook E2E, protocol holes, dry-run, hardlink alias) |
| `edit_guardian.py` | 86 | Substantial (smoke, protocol E2E, fail-closed, dry-run, wrapper fallback, hardlink alias) |
| `read_guardian.py` | 82 | Substantial (smoke, protocol E2E, fail-closed, dry-run, wrapper fallback) |
| `write_guardian.py` | 86 | Substantial (smoke, protocol E2E, fail-closed, dry-run, wrapper fallback, hardlink alias) |
| `auto_commit.py` | 173 | Substantial (43 tests: security characterization, circuit breaker, git edge cases, config) |
| `session_start.sh` | 76 | Full (28 tests in `tests/regression/test_session_start.py`) |

## Action Plans

실행 계획 파일은 `action-plans/`에 있다. 각 파일 상단에 YAML frontmatter로 상태를 관리한다.

- `status`: not-started | active | blocked | done
- `progress`: 현재 진행 상태 (자유 텍스트)

**규칙:**
- plan 파일 작업 시작/완료 시 frontmatter의 status와 progress를 업데이트할 것
- 완료된 plan은 `action-plans/_done/`으로 이동 (선택)
- `action-plans/_ref/`는 참고/역사적 문서

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
    hooks/scripts/session_start.sh      # SessionStart hook (auto-activate config)
    assets/guardian.default.json         # Default configuration
    assets/guardian.recommended.json     # Recommended configuration (auto-deployed)
    assets/guardian.schema.json          # Config schema
