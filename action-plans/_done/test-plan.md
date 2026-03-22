---
status: done
progress: "2026-03-22: 완료. 211 tests + 43 subtests 작성, 전부 통과. 2 verification rounds 완료. 발견된 보안 취약점 3건은 characterization tests로 문서화됨 (수정은 별도 action plan: security-fixes.md)"
---

# TEST-PLAN.md -- Guardian Test Action Plan

Distilled from audit and security review. Prioritized by security impact.

## P0: Must Test Immediately (Security Bypass Vectors)

### Fail-closed validation
- [v] `is_symlink_escape()` fail-closed on OS errors (ELOOP, ENAMETOOLONG, EACCES) — `test_failopen_edgecases.py::TestSymlinkEscape_OSErrors`
- [v] `is_path_within_project()` fail-closed on exceptions — `test_failopen_edgecases.py::TestPathWithinProject_OSErrors`
- [v] `resolve_tool_path()` raises OSError (not silent) — `test_failopen_edgecases.py::TestResolveToolPath_ErrorHandling`
- [v] `run_path_guardian_hook()` denies when helpers fail — `test_failopen_edgecases.py::TestResolveToolPath_ErrorHandling`
- [v] Malformed-but-valid JSON protocol hole (`[]`, `"str"`, `123`) — `test_failopen_edgecases.py::TestProtocolHole_MalformedValidJSON`
- [v] Missing `file_path` returns allow characterization — `test_failopen_edgecases.py::TestMissingFilePath_WriteEdit`
- [v] Dry-run branches suppress deny output — `test_failopen_edgecases.py::TestDryRun_PathGuardians`
- [v] Wrapper inner fallback (crash-while-crash) produces deny — `test_failopen_edgecases.py::TestWrapperInnerFallback_FailClosed`
- [v] Hardlink alias detection via inode comparison — `test_failopen_edgecases.py::TestHardlinkAlias_Detection`

### Edit/Read/Write guardian smoke tests
- [v] Edit: allowed path, zeroAccess, readOnly, outside-project, symlink, malformed JSON, null byte — `test_path_guardian_smoke.py::TestEditGuardian_Smoke`
- [v] Read: allowed path, zeroAccess, readOnly allowed, outside-project, malformed JSON — `test_path_guardian_smoke.py::TestReadGuardian_Smoke`
- [v] Write: allowed path, zeroAccess, readOnly, noDelete, outside-project, missing file_path — `test_path_guardian_smoke.py::TestWriteGuardian_Smoke`
- [v] hookBehavior.onError=allow characterization — `test_path_guardian_smoke.py::TestHookBehavior_OnError`
- [v] Cross-tool consistency — `test_path_guardian_smoke.py::TestCrossToolConsistency`
- [v] ZeroAccess/ReadOnly/NoDelete pattern coverage — `test_path_guardian_smoke.py::Test*Patterns`
- [v] Self-guardian path protection — `test_path_guardian_smoke.py::TestSelfGuardianPaths`

### Auto-commit security tests
- [v] Secrets staging with includeUntracked=true (CHARACTERIZATION: secrets ARE committed) — `test_auto_commit.py::TestAutoCommit_SecurityCharacterization`
- [v] Pre-staged secrets with includeUntracked=false (CHARACTERIZATION: secrets ARE committed) — same
- [v] --no-verify behavior documented — same
- [v] Circuit breaker behavior — `test_auto_commit.py::TestAutoCommit_CircuitBreaker`

## P1: Should Test Soon (Protocol and Integration)

### Hook JSON protocol E2E
- [v] Bash hook: allow/deny/ask, malformed JSON, empty stdin, wrong tool_name — `test_hook_protocol_e2e.py::TestBashHook_Protocol`
- [v] Edit hook: allow/deny, JSON structure — `test_hook_protocol_e2e.py::TestEditHook_Protocol`
- [v] Read hook: allow/deny, readOnly allowed — `test_hook_protocol_e2e.py::TestReadHook_Protocol`
- [v] Write hook: allow/deny — `test_hook_protocol_e2e.py::TestWriteHook_Protocol`
- [v] Stop hook: exit 0, no permissionDecision, disabled graceful — `test_hook_protocol_e2e.py::TestStopHook_Protocol`
- [v] Error responses: malformed JSON, empty input, missing tool_input, non-empty reason, hookEventName — `test_hook_protocol_e2e.py::TestProtocol_ErrorResponses`

### Auto-commit functional tests
- [v] No changes, detached HEAD, rebase in progress — `test_auto_commit.py::TestAutoCommit_GitEdgeCases`
- [v] Staging failure non-fatal — same
- [v] Commit message format, truncation — `test_auto_commit.py::TestAutoCommit_CommitMessageFormat`
- [v] Configuration: disabled, onStop, prefix, dry-run — `test_auto_commit.py::TestAutoCommit_Configuration`
- [v] Fail-open: ImportError, exception — `test_auto_commit.py::TestAutoCommit_FailOpen`

### TOCTOU symlink check
- [v] Race window documented in test — `test_failopen_edgecases.py::TestSymlinkEscape_OSErrors::test_toctou_race_window_documented`

### CI/CD pipeline
- [v] GitHub Actions workflow — `.github/workflows/ci.yml`
- [v] Python 3.10/3.11/3.12 matrix — same
- [ ] Script-based tests (regression/) not pytest-compatible — `test_errno36_e2e.py`, `test_errno36_fix.py` have top-level `sys.exit()`

## P2: Should Test (Defense in Depth)

### Test migration and consolidation
- [v] Remove 3 duplicate root-level test files — deleted `test_guardian_p0p1_comprehensive.py`, `test_guardian_v2fixes.py`, `test_guardian_v2fixes_adversarial.py`
- [ ] Convert script-based tests to unittest/pytest (regression/, review/, usability/, patterns/)

### Parametrize repetitive tests
- [ ] Convert to `pytest.mark.parametrize` or `unittest.subTest`

### Coverage tooling
- [v] `pyproject.toml [tool.coverage]` config — `pyproject.toml`
- [ ] Add `pytest-cov` with minimum threshold enforcement

### pytest configuration
- [v] `pyproject.toml [tool.pytest.ini_options]` — testpaths, markers, norecursedirs
- [ ] Timeout tests not in pytest-compatible files

### sys.path import hardening
- [ ] Consider `importlib` or absolute imports

## Test Style Guide

When adding new tests, follow these conventions:
- Prefer `unittest.TestCase` for pytest discoverability
- Use the bootstrap import pattern (see `tests/README.md`)
- For hook E2E tests: use `subprocess.run()` to invoke the hook script with JSON on stdin
- Place tests in the appropriate category directory (see `tests/README.md` for boundaries)
- Security tests go in `tests/security/`; regression tests in `tests/regression/`

## Discovered Security Issues (Require Separate Fix Action Plan)

These were **discovered and characterized** during testing, but NOT fixed:

1. **P0: auto_commit.py commits secrets** — `git_add_all()` stages .env/*.pem//*.key without zeroAccessPaths filtering. `--no-verify` bypasses pre-commit hooks. → See `action-plans/security-fixes.md`
2. **P0: Non-dict JSON + onError=allow = silent bypass** — `[]`/`"str"`/`123` on stdin crashes into wrapper onError handler; with `onError=allow`, produces no output (implicit allow). → See `action-plans/security-fixes.md`
3. **P0: Missing file_path = explicit allow** — Empty/null/missing `file_path` returns `allow_response()` at `_guardian_utils.py:2454`, bypassing all path checks for Write/Edit. → See `action-plans/security-fixes.md`
