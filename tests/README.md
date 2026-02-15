# Guardian Test Suite

Tests for bash_guardian.py and related guardian infrastructure.

## Directory Structure

    tests/
      _bootstrap.py          # Shared sys.path setup
      conftest.py            # Pytest bridge (auto-imports _bootstrap)
      test_guardian.py       # Phase 5 integration tests (foundation)
      test_guardian_utils.py # Unit tests for _guardian_utils.py (foundation)

      core/                  # Comprehensive P0/P1/V2 test suites
      security/              # Adversarial bypass and red-team tests
      regression/            # Bug-specific regression tests (Errno 36, etc.)
      review/                # Code review edge cases (pattern-level analysis)
      usability/             # False positive and usability checks
      patterns/              # Standalone regex verification scripts
      _archive/              # Superseded tests (excluded from test runs)

## Category Boundaries

- **review/**: Edge cases discovered during code review sessions. Tests focus on
  pattern-level analysis of specific fixes (F1-F10) -- e.g., "does this regex
  handle nested quotes correctly?"
- **usability/**: False positive rate analysis and fail-closed behavior impact on
  real developer workflows -- e.g., "does `echo foo > bar.txt` trigger a false
  positive prompt?"

## Running Tests

Individual test files can be run directly with Python:

    python3 tests/core/test_p0p1_comprehensive.py
    python3 tests/security/test_bypass_v2.py

Note: pytest is not a project dependency. If you have pytest installed, you can
also run tests via pytest. The conftest.py handles bootstrap automatically.

## Adding New Tests

1. Choose the appropriate category directory.
2. Add the bootstrap import at the top of your file:

       import sys
       from pathlib import Path
       sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
       import _bootstrap  # noqa: F401, E402

3. Import guardian modules directly:

       from bash_guardian import split_commands, is_write_command

**Exceptions**: Files that only use the standard library (e.g., raw regex tests
in `patterns/`) do not need `_bootstrap`. The root-level foundation tests
(`test_guardian.py`, `test_guardian_utils.py`) use their own sys.path setup.

## Categories

| Directory | Purpose | Test Style |
|-----------|---------|------------|
| core/ | Comprehensive suites covering all P0, P1, and V2 fixes | unittest |
| security/ | Adversarial bypass attempts, cross-model red-teaming | unittest + script |
| regression/ | Bug-specific tests (Errno 36, allowedExternalPaths) | script |
| review/ | Edge cases found during code review (pattern-level F1-F10 analysis) | script |
| usability/ | False positive rate analysis, fail-closed workflow impact | script |
| patterns/ | Standalone regex verification (use verify_ prefix) | script |
| _archive/ | Superseded tests, kept for reference (not collected by test runners) | N/A |
