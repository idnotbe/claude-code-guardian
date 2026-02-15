# Advisory Test Author Output

## Date: 2026-02-15
## Task: #2 - Write tests for advisory fixes

## File Created
`tests/security/test_advisory_failclosed.py` — 26 tests across 9 test classes

## Test Results
**26/26 PASS** (0.330s)

## Test Classes and Coverage

| Class | Tests | Status |
|-------|-------|--------|
| TestAdvisory1_VariableShadowing | 1 | PASS |
| TestAdvisory2_TOCTOU_FailClosed | 4 | PASS |
| TestAdvisory3_ExpandPath_FailClosed | 4 | PASS |
| TestAdvisory3_NormalizePathForMatching_FailClosed | 3 | PASS |
| TestAdvisory3_MatchPathPattern_DefaultOnError | 4 | PASS |
| TestAdvisory3_DenyChecks_FailClosed | 4 | PASS |
| TestAdvisory3_IsSelfGuardianPath_FailClosed | 3 | PASS |
| TestAdvisory3_ResolveToolPath_FailClosed | 2 | PASS |
| TestAdvisory3_RunPathGuardianHook_ResolveFailure | 3 | PASS (subprocess with monkeypatch) |

## Regression Check
- test_p0p1_failclosed.py: 34/34 PASS
- test_p0p1_comprehensive.py: 180/180 PASS
- Zero regressions

## Fix Applied During Testing
- Subprocess monkeypatch wrapper needed `except SystemExit: pass` to properly capture stdout
  from `run_path_guardian_hook()` which calls `sys.exit(0)` after emitting deny JSON
