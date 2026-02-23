# Action Plans Migration Working Memory

## 최종 상태: 완료

### 외부 모델 컨센서스
- Codex (codex 5.3), Gemini (gemini-3-pro), Claude (opus 4.6) 3개 모델 모두 동의:
  - 완료된 팀 plan → `_ref/` (역사적 조정 기록이므로)
  - TEST-PLAN.md → `test-plan.md` (서브디렉토리 내 kebab-case)
  - CLAUDE.md:34, README.md:871 참조 업데이트 필수

### 변경된 파일 목록

| 파일 | 변경 사유 |
|------|-----------|
| `action-plans/README.md` | **신규** - 시스템 규칙 문서 |
| `action-plans/test-plan.md` | **이동** - `TEST-PLAN.md` → frontmatter 추가 + kebab-case |
| `action-plans/_done/.gitkeep` | **신규** - 빈 디렉토리 유지 |
| `action-plans/_ref/.gitkeep` | **신규** - 빈 디렉토리 유지 |
| `action-plans/_ref/doc-gap-analysis-team-plan.md` | **이동** - `temp/00-team-plan.md` → frontmatter 추가 |
| `action-plans/_ref/regex-fix-team-plan.md` | **이동** - `temp/team-plan.md` → frontmatter 추가 |
| `action-plans/_ref/heredoc-fix-master-plan.md` | **이동** - `temp/heredoc-fix/MASTER-PLAN.md` → frontmatter 추가 + 자기참조 경로 수정 |
| `CLAUDE.md` | **수정** - Repository Layout에 action-plans 추가, TEST-PLAN.md 참조 업데이트, Action Plans 섹션 추가 |
| `README.md` | **수정** - TEST-PLAN.md 참조 → action-plans/test-plan.md |

### 삭제된 파일/디렉토리

| 대상 | 사유 |
|------|------|
| `TEST-PLAN.md` (루트) | `action-plans/test-plan.md`로 이동 |
| `temp/00-team-plan.md` | `action-plans/_ref/doc-gap-analysis-team-plan.md`로 이동 |
| `temp/team-plan.md` | `action-plans/_ref/regex-fix-team-plan.md`로 이동 |
| `temp/heredoc-fix/MASTER-PLAN.md` | `action-plans/_ref/heredoc-fix-master-plan.md`로 이동 |
| `action plans/` (공백 포함 디렉토리) | 비어 있었음, `action-plans/`로 대체 |

### 검증 결과
- **1차 검증** (Explore agent): 9/9 PASS - 구조, frontmatter, 삭제, 참조, .gitignore, 콘텐츠 보존
- **2차 독립 검증** (별도 Explore agent): 9/9 PASS - 파일시스템, kebab-case, P0/P1/P2 섹션 보존
