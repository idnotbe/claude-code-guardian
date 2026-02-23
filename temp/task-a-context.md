# Task A Context: Fix v1.0.1 Security Items in guardian.recommended.json

## Objective
Apply the 4 deferred v1.0.1 security fixes to `assets/guardian.recommended.json`.

## Items to Fix

### 1. `.git/hooks/**` → readOnlyPaths 추가
**Why**: Write guardian은 `.git/hooks/pre-commit`에 쓰기를 허용함. `.git`은 noDeletePaths에만 있고, readOnlyPaths나 zeroAccessPaths에는 없음. prompt injection이 malicious git hook을 작성한 후 auto-commit이 `--no-verify`로 실행되는 시나리오가 가능.
**Fix**: `readOnlyPaths`에 `.git/hooks/**` 추가 (`.git/**` 전체는 너무 넓음 - `.git/config` 등은 편집 필요할 수 있음)

### 2. `curl | /bin/bash` 절대경로 바이패스 강화
**Current pattern (line 177)**: `(?:curl|wget)[^|]*\|\s*(?:bash|sh|zsh|python|perl|ruby|node)`
**Problem**: `/bin/bash`, `/usr/bin/bash`, `/usr/bin/env bash` 등 절대경로로 인터프리터를 지정하면 매치되지 않음.
**Fix**: 인터프리터 매치 부분을 `(?:(?:/usr)?(?:/bin/|/local/bin/)?(?:env\s+)?)?(?:bash|sh|zsh|python[23]?|perl|ruby|node)` 같은 형태로 강화. 정확한 regex는 false positive 없이 동작하도록 주의.

### 3. `rm --recursive --force` 긴 플래그 패턴 추가
**Current patterns**:
- Block (line 141): `rm\s+-[rRf]+\s+/(?:\s*$|\*|\s+)` — 루트 삭제만
- Ask (line 243): `rm\s+-[rRf]+` — 짧은 플래그만
**Problem**: `rm --recursive --force /` 또는 `rm --recursive dir/` 가 매치되지 않음.
**Fix**: block에 `rm\s+--(?:recursive|force)[\s-]+.*--(?:recursive|force)[\s-]+/` 추가하거나, ask에 `rm\s+--(?:recursive|force)` 추가. False positive 주의.

### 4. `crontab`, `LD_PRELOAD` 패턴 추가 고려
- `crontab -e` / `crontab -r`: persistence attack vector. Ask tier 적합.
- `LD_PRELOAD=`: library injection. Block tier 적합 (보통 악의적 용도).
**Fix**:
  - Ask: `{"pattern": "crontab\\s+", "reason": "'crontab' -- schedules persistent tasks, verify this is intended"}`
  - Block: `{"pattern": "LD_PRELOAD=", "reason": "LD_PRELOAD -- library injection (can intercept any system call)"}`

## Files
- Config: `/home/idnotbe/projects/claude-code-guardian/assets/guardian.recommended.json`
- Schema: `/home/idnotbe/projects/claude-code-guardian/assets/guardian.schema.json`
- Verification R1: `/home/idnotbe/projects/claude-code-guardian/temp/verification-r1.md`
- Verification R2: `/home/idnotbe/projects/claude-code-guardian/temp/verification-r2.md`

## Constraints
- JSON must remain valid and schema-compliant
- Regex must compile with Python's `re` module
- No false positives on common developer workflows
- Maintain the existing $comment and reason field style
