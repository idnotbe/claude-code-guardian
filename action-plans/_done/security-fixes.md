---
status: done
progress: "2026-03-22: 완료. 3개 P0 보안 취약점 모두 수정됨. 216 tests pass (characterization tests → fixed behavior assertions 업데이트 완료). Cross-model validated (Gemini 3.1 Pro)."
---

# SECURITY-FIXES.md -- Guardian Security Fix Action Plan

3 P0 security vulnerabilities discovered during test suite implementation (2026-03-22).
All have characterization tests proving the issue exists. Code fixes needed.

Origin: `action-plans/_done/test-plan.md` (Discovered Security Issues section)
Cross-model validated by: Opus 4.6, Codex 5.3, Gemini 3.1 Pro

## Phase 1: auto_commit.py secrets filtering (HIGHEST PRIORITY)

**Problem**: `auto_commit.py` stages and commits secrets without any zeroAccessPaths filtering.

**Fix applied**:
- [v] Created `git_add_filtered(include_untracked)` in `_guardian_utils.py` — lists files, filters against `match_zero_access()`, stages only safe files
- [v] Created `_unstage_secret_files(project_dir)` — checks `git diff --cached`, unstages any zeroAccessPaths matches, falls back to full `git reset HEAD` if targeted unstaging fails
- [v] Updated `auto_commit.py` to use `git_add_filtered()` instead of `git_add_all()`/`git_add_tracked()`
- [v] Updated `test_auto_commit.py` — security tests now assert secrets are NOT committed (48 tests pass)
- [v] Uses `-z` flag for safe filename parsing, chunks to avoid ARG_MAX

**Scope**: `hooks/scripts/_guardian_utils.py` (new functions), `hooks/scripts/auto_commit.py` (staging replacement)

## Phase 2: Non-dict JSON input validation in run_path_guardian_hook()

**Problem**: Non-dict JSON crashes into wrapper `onError` handler; with `onError=allow`, becomes bypass.

**Fix applied**:
- [v] Added `isinstance(input_data, dict)` check after `json.load()` in `run_path_guardian_hook()`
- [v] Non-dict JSON now produces explicit deny before reaching wrapper error handler
- [v] Updated characterization tests: `test_onerror_allow_with_json_array_is_bypass` → `test_onerror_allow_with_json_array_now_denied`

**Scope**: `hooks/scripts/_guardian_utils.py` (3-line addition at line ~2432)

## Phase 3: Missing file_path should deny for ALL tools

**Problem**: Empty/missing `file_path` returned explicit `allow`, bypassing all path checks.

**Fix applied**:
- [v] Changed `allow_response()` to `deny_response()` for empty/missing `file_path`
- [v] Applies to ALL tools (Write, Edit, Read) per Gemini 3.1 Pro recommendation
- [v] Updated 7 characterization tests from `_allows` → `_denies`
- [v] Updated 3 smoke tests from `_characterization` → `_denied`

**Scope**: `hooks/scripts/_guardian_utils.py` (2-line change at line ~2458)

## Verification

- [v] Characterization tests FAIL after fix (proving fix works) → updated to assert new behavior
- [v] Updated tests assert correct fixed behavior (deny instead of allow/None)
- [v] Full test suite: 1114 passed, 11 pre-existing failures (unrelated)
- [v] Cross-model review (Gemini 3.1 Pro) validated all 3 fix approaches
