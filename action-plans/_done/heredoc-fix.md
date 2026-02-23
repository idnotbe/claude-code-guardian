---
status: done
progress: "전체 완료 — 788 tests pass, 0 bypasses"
---

# Heredoc False Positive Fix + Tokenizer/Detection Hardening

**Date**: 2026-02-22
**Spec**: `temp/guardian-heredoc-fix-prompt.md`
**Target**: `hooks/scripts/bash_guardian.py` (1384 → 1724 lines, +340/-26)

## Problem

`bash_guardian.py`의 heredoc 처리 부재로 인해 false positive `[CONFIRM]` 팝업이 발생. claude-memory 플러그인에서 20시간 동안 7번 발생. 원인은 3개의 독립적 버그:

| 버그 | Layer | 증상 |
|------|-------|------|
| `split_commands()`가 heredoc body를 별도 명령어로 분리 | Layer 2 | JSON body의 `->` 화살표가 redirect로 오인 |
| `is_write_command()`가 따옴표 안의 `>`를 redirect로 인식 | Layer 4 | `"B->A->C"` 패턴에서 write 오탐 |
| `scan_protected_paths()`가 heredoc body를 스캔 | Layer 1 | heredoc body의 `.env` 언급이 보호 경로 경보 |

## 작업 내용

### Phase 1: 구현 검증 [v]

spec (`temp/guardian-heredoc-fix-prompt.md`) 대로 구현이 되어 있는지 검증.

| 검증 단계 | 방법 | 결과 |
|-----------|------|------|
| Diff 비교 | 4개 병렬 subagent (Fix별 1개) | spec 대비 정확히 일치 |
| 외부 모델 | Codex 5.3 + Gemini 3 Pro (pal clink) | 만장일치: 4 deviations은 개선 |
| Vibe Check | 메타인지 자가점검 | blind spot 1건 발견 (ln regression) → 해결 |
| End-to-End | 실제 memory 플러그인 명령어 시뮬레이션 | PASS |
| 독립 검증 Round 2 | 별도 agent가 전체 재검증 | ALL PASS or DEVIATION(+) |

**결과**: 4건의 spec 이탈 발견, 모두 보안 개선으로 확인.

| Deviation | 내용 | 판정 |
|-----------|------|------|
| Regex `[^|&;>]+` | redirect 패턴에 `>` 추가하여 multi-redirect 정확도 향상 | 개선 (Gemini: "CRITICAL IMPROVEMENT") |
| Comment tracking (9줄) | `#` 주석 내 `<< EOF`가 heredoc으로 오인되는 보안 gap 수정 | 개선 (Codex: "genuine security gap") |
| Extra test class (4 tests) | Comment tracking에 대한 회귀 테스트 | 개선 |
| Comment text in main() | 주석 문구 차이 (cosmetic) | 무영향 |

### Phase 2: 팀 구현 — Deviation 개선 + 사전 실패 18건 해결 [v]

3명의 teammate를 worktree 격리 환경에서 병렬 실행. 각 teammate는 독자적으로 subagent, vibe-check, pal clink (Codex + Gemini) 사용. Master plan의 Stream A+B를 Task A로 통합 (polish 범위), Stream C → Task C, Stream D → Task D로 매핑.

#### Task A: Deviation Polish + ln 테스트 수정 (polish-impl) [v]

| 항목 | 작업 | 상태 |
|------|------|------|
| Deviation 1 | redirect regex 테스트 2건 추가 | [v] |
| Deviation 2 | Comment-only sub-command를 Layer 1 scan에서 제외 (false positive 방지) | [v] |
| Deviation 2 | `${#}`, `$#`, `echo foo#bar` 엣지 케이스 테스트 추가 | [v] |
| ln 테스트 3건 | `\bln\s+` → `(?<![A-Za-z-])ln\s+` assertion 수정 | [v] |

**수정 파일**: `bash_guardian.py`, `tests/test_heredoc_fixes.py`, `tests/core/test_v2fixes.py`, `tests/security/test_v2_adversarial.py`

#### Task C: Tokenizer 7건 수정 (tokenizer-impl) [v]

`split_commands()`에 5개 새 state variable 추가, context-first ordering으로 구조 변경.

| # | 문제 | 수정 |
|---|------|------|
| 1 | `${VAR:-;}` — `;`에서 분리 | `param_expansion_depth` 추가 |
| 2 | `${VAR//a\|b/c}` — `\|`에서 분리 | 동일 |
| 3 | `(cd /tmp; ls)` — bare subshell 분리 | bare `(` depth tracking 추가 |
| 4 | `{echo a; echo b;}` — brace group 분리 | `brace_group_depth` 추가 |
| 5 | `!(*.txt\|*.md)` — extglob `\|` 분리 | `extglob_depth` 추가 |
| 6 | `[[ regex \| ]]` — conditional `\|` 분리 | `bracket_depth` 추가 |
| 7 | `(( x & y ))` — arithmetic `&` 분리 | arithmetic 내 separator skip 추가 |

**보안 hardening**: `}` inside `$()` desync 방지 (`depth == 0` guard on `param_expansion_depth` decrement).

#### Task D: Scan/Detection 8건 수정 (detection-impl) [v]

| # | 문제 | 수정 |
|---|------|------|
| 1 | `cat .en[v]` glob bypass | `_expand_glob_chars()` 함수 추가 |
| 2 | `cat .en?` glob bypass | glob-? regex + post-match validation |
| 3 | `cat $'\x2e\x65\x6e\x76'` hex bypass | `_decode_ansi_c_strings()` 함수 추가 |
| 4 | `chmod 777 poetry.lock` read-only | 테스트 expectation 수정 (코드는 정상) |
| 5 | `chown user poetry.lock` read-only | 동일 |
| 6 | `touch poetry.lock` read-only | 동일 |
| 7 | `> CLAUDE.md` truncation | 테스트 expectation 수정 (코드는 정상) |
| 8 | `git rm CLAUDE.md` | 테스트 expectation 수정 (코드는 정상) |

**신규 함수**:
- `_decode_ansi_c_strings()`: `$'...'` 디코딩 (`\xHH`, `\uHHHH`, `\UHHHHHHHH`, `\NNN`, standard escapes)
- `_expand_glob_chars()`: 단일 문자 bracket class 확장 (`[v]` → `v`)

### Phase 3: 검증 Round 1 (v1-lead) [v]

| 항목 | 결과 |
|------|------|
| pytest (core + security + heredoc) | 671 passed, 0 failed |
| standalone bypass tests | 101 passed, 0 failed, 0 bypasses |
| regression tests (errno36) | 16 passed, 0 failed |
| compile check | OK |
| custom edge case tests | 47/49 passed |

**발견 2건**:

| # | Severity | 내용 | 조치 |
|---|----------|------|------|
| 1 | MEDIUM | `{ rm -rf /; }` brace group 내 delete 미감지 (regression) | `({` 를 `is_delete_command` regex에 추가 → **수정 완료** |
| 2 | LOW | `echo hello \> world` backslash `>` false positive | 무조치 (fail-safe 방향) |

### Phase 4: 검증 Round 2 (v2-lead) [v]

Gemini 3.1 Pro의 creative bypass 18종 테스트 + Codex structural review.

| 항목 | 결과 |
|------|------|
| pytest | 671 passed, 0 failed |
| standalone bypass | 101 passed, 0 bypasses |
| regression | 16 passed |
| Gemini creative bypass (18종) | 3 NEW bypass + 15 pre-existing |
| Codex structural review | 3 findings |

**발견 4건**:

| # | Severity | 내용 | 조치 |
|---|----------|------|------|
| 1 | HIGH | glob-? `re.search` first-match-only bypass (`???? .en?` 패턴) | `re.finditer`로 교체 → **수정 완료** |
| 2 | MEDIUM | ANSI-C decoder: `\c` truncation, `\x00` null byte, `\E` escape 누락 | 3건 모두 추가 → **수정 완료** |
| 3 | MEDIUM | `]]`/`}` inside `$()` depth desync | `depth == 0` guard 추가 → **수정 완료** |
| 4 | LOW | `is_delete_command` false positive with `({` in quotes | 무조치 (fail-safe, pre-existing 패턴) |

### Phase 5: V2 수정 후 최종 검증 [v]

| 항목 | 결과 |
|------|------|
| compile check | OK |
| pytest (core + security + heredoc) | **671 passed**, 0 failed |
| standalone bypass tests | **101 passed**, 0 failed, 0 bypasses |
| regression tests | **16 passed**, 0 failed |
| V2 Fix 개별 검증 (6건) | **6/6 PASS** |
| **총계** | **788 tests, 0 failures, 0 security bypasses** |

## 최종 변경 사항 요약

### 수정된 파일

| 파일 | 변경 내용 |
|------|----------|
| `hooks/scripts/bash_guardian.py` | +340/-26 lines. Heredoc parser, tokenizer 5개 state variable, ANSI-C decoder, glob expander, comment filter, V1/V2 finding fixes |
| `tests/test_heredoc_fixes.py` | 35+ tests. Heredoc, quote-aware write, comment regression, delimiter parsing |
| `tests/core/test_v2fixes.py` | ln pattern assertion 수정 |
| `tests/security/test_v2_adversarial.py` | ln symlink assertion 수정 (2건) |
| `tests/security/test_bypass_v2.py` | chmod/chown/touch/truncation/git-rm expectation 수정 (8건) |
| `plugin.json` | version bump 1.0.0 → 1.1.0 |

### 신규 함수/메소드

| 함수 | 위치 | 용도 |
|------|------|------|
| `_parse_heredoc_delimiter()` | bash_guardian.py | heredoc delimiter 파싱 (bare/quoted) |
| `_consume_heredoc_bodies()` | bash_guardian.py | heredoc body 소비 (fail-closed) |
| `_decode_ansi_c_strings()` | bash_guardian.py | `$'...'` ANSI-C 문자열 디코딩 |
| `_expand_glob_chars()` | bash_guardian.py | 단일 문자 glob bracket class 확장 |

### 보안 특성 보존 확인

| 속성 | 상태 |
|------|------|
| fail-closed (import 실패 → deny) | 보존 |
| fail-closed (JSON 파싱 실패 → deny) | 보존 |
| fail-closed (미처리 예외 → deny) | 보존 |
| fail-closed (unterminated heredoc → 끝까지 소비) | 보존 |
| ReDoS 없음 | 확인 (선형 시간 regex) |
| `param_expansion_depth` desync 방지 | `depth == 0` guard |
| `bracket_depth` desync 방지 | `depth == 0` guard |
| `brace_group_depth` desync 방지 | `depth == 0` guard |

## 알려진 제한 사항 (out of scope)

Static analysis의 본질적 한계로, 다음은 탐지 불가. V2 검증에서 Gemini 3.1 Pro가 제시한 18종 creative bypass 중 15종이 이 범주에 해당 (vectors 4-18):
- `cat .e""nv` — inline empty quote stripping (shell word normalization 필요)
- `cat $(printf '.%s' env)` — runtime string construction
- `cat $(echo vne. | rev)` — runtime reversal
- `a=.en; b=v; cat ${a}${b}` — split variable concatenation
- `cat .en*` — asterisk glob (단일 문자가 아닌 와일드카드)
- `cat \.env` — backslash escaping

## 검증 방법론

| 단계 | 방법 | 외부 모델 | 독립성 |
|------|------|-----------|--------|
| Phase 1 | 4 병렬 diff agent + vibe-check | Codex 5.3 + Gemini 3 Pro | 독립 (6 관점) |
| Phase 2 | 3 worktree-isolated teammate | 각 teammate가 독립적으로 Codex/Gemini 사용 | 격리 |
| Phase 3 (V1) | v1-lead: 49 custom edge case + 다관점 review | — | 독립 |
| Phase 4 (V2) | v2-lead: creative bypass 18종 + structural review + adversarial tests | Gemini 3.1 Pro + Codex | 독립 |
| Phase 5 | team lead: V2 fix 적용 + 개별 검증 6건 + 전체 suite 재실행 | — | 직접 |

## 관련 파일

| 파일 | 용도 |
|------|------|
| `temp/guardian-heredoc-fix-prompt.md` | 원본 구현 spec |
| `temp/heredoc-fix-verification-report.md` | Phase 1 검증 보고서 |
| `temp/team-master-plan.md` | Phase 2 팀 계획 |
| `temp/task-a-progress.md` | Task A (polish) 진행 기록 |
| `temp/task-c-progress.md` | Task C (tokenizer) 진행 기록 |
| `temp/task-d-progress.md` | Task D (detection) 진행 기록 |
| `temp/verification-round1.md` | V1 검증 보고서 (v1-lead) |
| `temp/verification-round2.md` | V2 검증 보고서 (v2-lead) |
