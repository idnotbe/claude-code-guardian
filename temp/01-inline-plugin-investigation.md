# inline[0] Plugin Investigation

## Problem
- `inline[0] Plugin · unknown · ✘ failed to load · 1 error` 에러 발생
- 사용자가 이 플러그인이 뭔지, 필요 없으면 삭제하길 원함

## Root Cause Found
`ccyolo` bash function in `~/.bashrc`:
```bash
ccyolo() {
  claude --dangerously-skip-permissions \
    --plugin-dir ~/projects/claude-memory \      # <-- THIS IS inline[0]
    --plugin-dir ~/projects/claude-code-guardian \
    --plugin-dir ~/projects/vibe-check \
    --plugin-dir ~/projects/deepscan \
    --plugin-dir ~/projects/prd-creator \
    "$@"
}
```

- `inline[0]` = 첫 번째 `--plugin-dir` = `claude-memory`
- `claude-memory`의 plugin.json은 존재하고 유효해 보이나 로드 실패

## Investigation Results

### Ruled OUT (공식 지원 확인됨)
- ~~hooks.json의 `"description"` 필드~~ → 공식 문서에 예시 있음
- ~~`"type": "prompt"` hook type~~ → 공식 지원
- ~~`PostToolUse`, `UserPromptSubmit` event types~~ → 공식 지원
- ~~Python script errors~~ → 모든 스크립트 import 성공
- ~~JSON syntax~~ → 모두 valid
- ~~파일 누락~~ → 모든 참조 파일 존재

### Most Likely Cause: `"engines"` field in plugin.json
- claude-memory에만 존재하는 유일한 필드: `"engines": {"claude-code": ">=1.0.0"}`
- 정상 작동하는 4개 플러그인 중 어느 것도 `engines` 필드 없음
- plugin.json 스키마가 `additionalProperties: false`이면 미인식 필드에서 전체 로드 실패
- 이름이 "unknown"으로 표시되는 것도 plugin.json 파싱 자체가 실패함을 시사

## Options
- A: `ccyolo`에서 `--plugin-dir ~/projects/claude-memory` 줄을 제거
- B: claude-memory 플러그인의 로드 에러를 수정
- C: 조건부 로딩 (프로젝트별로 다른 플러그인 세트)

## External Opinions

### Codex (codex 5.3)
- **추천**: Option 1 (alias에서 제거) + Option 3 (프로젝트별 alias)
- **로드 실패 원인 추정**:
  - `UserPromptSubmit` 이벤트가 플러그인에서 미지원
  - `type: "prompt"` hooks의 `model`/`timeout`/`statusMessage` 필드가 미지원
  - hooks.json 최상위 `description` 필드 (가능성 낮음)
- **디버깅 방법**: UserPromptSubmit 블록 삭제 후 재시도 → prompt hook 필드 단순화 후 재시도

### Gemini (gemini 3 pro)
- ❌ 할당량 소진으로 응답 불가

### Vibe Check
- 계획은 올바른 방향
- **주의**: 완전 삭제보다 주석 처리가 나음 (사용자의 자체 플러그인이므로)
- 실패 원인도 설명해줘야 나중에 수정 가능

## Final Decision
- `~/.bashrc`에서 `--plugin-dir ~/projects/claude-memory` 줄을 **주석 처리**
- 실패 원인 설명 (hook schema 호환성 문제)
- 필요시 프로젝트별 alias 제안
