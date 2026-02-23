---
status: active
progress: "P0 일부 완료, P1/P2 대부분 미착수"
---

# TEST-PLAN.md -- Guardian Test Action Plan

Distilled from audit and security review. Prioritized by security impact.

## P0: Must Test Immediately (Security Bypass Vectors)

### Fail-open exception paths
- **Target**: `is_symlink_escape()` (`_guardian_utils.py:927-972`)
  - Returns `False` on any exception -- bypasses symlink protection
  - Test with: extremely long paths (ENAMETOOLONG), invalid characters, paths causing `resolve()` to fail, symlink loops
- **Target**: `is_path_within_project()` (`_guardian_utils.py:974-1003`)
  - Returns `True` on exception -- allows outside-project operations
  - Returns `True` when `CLAUDE_PROJECT_DIR` is missing
  - Test with: missing project dir env, permission errors, non-existent paths, Windows path edge cases
- **Target**: `resolve_tool_path()` (`_guardian_utils.py:2142-2163`)
  - On OSError, returns unresolved path -- subsequent checks may use wrong path
- **Verify**: `run_path_guardian_hook()` still denies when these helpers fail

### Edit/Read/Write guardian smoke tests
- **Target**: `edit_guardian.py` (75 LOC), `read_guardian.py` (71 LOC), `write_guardian.py` (75 LOC)
  - Zero tests currently
  - Test via subprocess: feed JSON on stdin, assert stdout JSON decisions
  - Cases: allowed path (allow), zeroAccessPath (deny), readOnlyPath for write (deny), outside-project path (deny), symlink escape (deny), malformed JSON input (deny -- fail-closed)

### Auto-commit security tests
- **Target**: `auto_commit.py:145` -- unconditional `--no-verify`
  - Test that secrets (.env, *.pem, *.key) matching zeroAccessPaths are not staged
  - Test `includeUntracked=true` does not stage sensitive files
- **Target**: Circuit breaker behavior
  - Test that circuit state file handling works correctly

## P1: Should Test Soon (Protocol and Integration)

### Hook JSON protocol E2E
- Test full stdin/stdout JSON flow for all 5 hooks (Bash, Edit, Read, Write, Stop)
- Validate `hookSpecificOutput.permissionDecision` format matches Claude Code expectations
- Test error responses (malformed JSON input, missing fields, empty input)

### Auto-commit functional tests
- Mock git subprocess calls
- Test: no changes to commit, detached HEAD, rebase in progress, staging failure
- Test: git identity config (user.name / user.email)
- Test: commit message format

### TOCTOU symlink check
- `is_symlink_escape()` checks at hook time; target could be swapped before tool execution
- Document limitation if not fixable; add regression test for the check-then-use window

### CI/CD pipeline
- GitHub Actions: run `python -m pytest tests/core/ tests/security/ -v` on push
- Python matrix: 3.10, 3.11, 3.12
- Add proper exit codes to script-based tests or convert to unittest

## P2: Should Test (Defense in Depth)

### Test migration and consolidation
- Remove 3 duplicate root-level test files (`test_guardian_p0p1_comprehensive.py`, `test_guardian_v2fixes.py`, `test_guardian_v2fixes_adversarial.py`) -- these duplicate files in `core/` and `security/`
- Convert script-based tests (regression/, review/, usability/, patterns/) to unittest or pytest
  - At minimum: ensure proper exit codes for CI compatibility
  - Ideally: use `pytest.mark.parametrize` for repetitive patterns

### Parametrize repetitive tests
- Many tests repeat the same assertion pattern across different commands
- Convert to `pytest.mark.parametrize` or `unittest.subTest`

### Coverage tooling
- Add `pytest-cov` with minimum threshold (suggest 70% given security-critical nature)
- Add `.coveragerc` or `pyproject.toml [tool.coverage]` config
- Exclude `_archive/` and `patterns/verify_*` from collection

### pytest configuration
- Add `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]`
- Configure: testpaths, exclude patterns, markers
- Define markers for slow tests (ReDoS timing tests)

### sys.path import hardening
- All guardian scripts use `sys.path.insert(0, ...)` for imports
- Consider `importlib` or absolute imports to reduce import hijacking surface
- Lower priority since it requires write access to plugin directory

## Test Style Guide

When adding new tests, follow these conventions:
- Prefer `unittest.TestCase` for pytest discoverability
- Use the bootstrap import pattern (see `tests/README.md`)
- For hook E2E tests: use `subprocess.run()` to invoke the hook script with JSON on stdin
- Place tests in the appropriate category directory (see `tests/README.md` for boundaries)
- Security tests go in `tests/security/`; regression tests in `tests/regression/`
