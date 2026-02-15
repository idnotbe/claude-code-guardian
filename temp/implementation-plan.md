# Enhancement 1 & 2: allowedExternalPaths Mode Support + Bash External Path Extraction

## Context

`allowedExternalPaths`에 경로를 추가하면 Read/Write/Edit 모두 허용된다. 읽기 전용으로 제한하려면 `readOnlyPaths`를 별도로 설정해야 하는 불편함이 있다. 또한 Bash guardian의 `extract_paths()`가 프로젝트 외부 경로를 무시하므로, `sed -i /external/file` 같은 명령이 readOnlyPaths/zeroAccessPaths 체크를 우회한다.

## Enhancement 1: `allowedExternalPaths` 모드 지원

### 변경 1-1: `match_allowed_external_path()` 반환값 변경

**파일**: `hooks/scripts/_guardian_utils.py:1220-1234`

현재: `bool` 반환
변경: `tuple[bool, str]` 반환 — `(matched, mode)`

- String entry → `"read"` (breaking change, safer default)
- Object `{"path": "...", "mode": "readwrite"}` → 명시적 모드

### 변경 1-2: `run_path_guardian_hook()`에서 모드 체크

**파일**: `hooks/scripts/_guardian_utils.py:2282-2297`

- `match_allowed_external_path()` 반환 tuple 처리
- mode=read일 때 Write/Edit tool 차단

### 변경 1-3: 스키마 업데이트

**파일**: `assets/guardian.schema.json:109-116`

`allowedExternalPaths.items`를 `oneOf`로 변경 (string | object)

### 변경 1-4: config validation 업데이트

**파일**: `hooks/scripts/_guardian_utils.py` — `validate_guardian_config()`

`allowedExternalPaths` 항목이 string 또는 `{path, mode}` object인지 검증

## Enhancement 2: Bash guardian 외부 경로 추출

### 변경 2-1: `extract_paths()`에서 allowed external 경로 포함

**파일**: `hooks/scripts/bash_guardian.py:546-557`

`is_within_project()` 체크 후 `match_allowed_external_path` 추가

### 변경 2-2: bash_guardian.py import 추가

`match_allowed_external_path`를 import 목록에 추가

## 수정 파일 요약

| 파일 | 변경 |
|------|------|
| `hooks/scripts/_guardian_utils.py` | 반환값 변경, 모드 체크, 검증 추가 |
| `hooks/scripts/bash_guardian.py` | 외부 경로 포함, import 추가 |
| `assets/guardian.schema.json` | oneOf 스키마 |

## 테스트

새 테스트 파일: `tests/core/test_external_path_mode.py`

## 검증

```bash
python -m pytest tests/core/test_external_path_mode.py -v
python -m pytest tests/core/ tests/security/ -v
```
