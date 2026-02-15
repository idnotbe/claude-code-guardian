# Guardian Enhancement Brief

> Created: 2026-02-15 (from ops project analysis)
> Target repo: /home/idnotbe/projects/claude-code-guardian
> Open this file in a new Claude Code session in the guardian project

---

## Background

During ops project setup, two Guardian architectural gaps were discovered:

1. **allowedExternalPaths lacks read/write mode control** — Adding a path allows Read, Write, AND Edit. The only way to restrict to read-only is to pair with readOnlyPaths, which is a workaround, not a feature.

2. **Bash guardian doesn't check external paths** — `extract_paths()` in bash_guardian.py only extracts paths within the project. External paths (even those in allowedExternalPaths) are silently dropped and never checked against readOnlyPaths or zeroAccessPaths (except via Layer 1 raw string scan).

## Enhancement 1: Mode support for allowedExternalPaths

### Current format
```json
"allowedExternalPaths": [
  "/home/user/projects/sibling/**"
]
```
This allows Read + Write + Edit to all files in the path.

### Proposed format (backward-compatible)
```json
"allowedExternalPaths": [
  "/home/user/projects/read-only-sibling/**",
  { "path": "/home/user/projects/writable-sibling/**", "mode": "readwrite" }
]
```

Rules:
- **String entry** (existing): treated as `"mode": "read"` (READ-ONLY default — breaking change from current behavior but safer)
- **Object entry** (new): explicit mode control
  - `"read"` — only Read tool allowed, Write/Edit blocked
  - `"readwrite"` — Read + Write + Edit allowed

### Implementation location
- `_guardian_utils.py`: `match_allowed_external_path()` function (~line 2283-2340)
- Parse both string and object formats
- Return `(matched: bool, mode: str)` tuple instead of just `bool`
- In `run_path_guardian_hook()`, check mode and deny Write/Edit if mode is "read"

### Backward compatibility concern
Current behavior: string entries allow Read+Write+Edit.
New behavior: string entries would be read-only.

**THIS IS A BREAKING CHANGE.** Any existing configs using allowedExternalPaths for Write access would break.

Options:
(A) Default string to "read" (safer, breaking)
(B) Default string to "readwrite" (compatible, less safe)
(C) Default string to "readwrite" with deprecation warning, plan to change to "read" in v2

Recommendation: Option A. allowedExternalPaths is a new/rarely-used feature. The safer default is better. Document the change in CHANGELOG.

### With this enhancement, readOnlyPaths pairing becomes unnecessary
Currently the ops project has:
```json
"allowedExternalPaths": ["/home/.../sibling/**"],
"readOnlyPaths": ["/home/.../sibling/**"]  // <-- needed to prevent writes
```

After enhancement:
```json
"allowedExternalPaths": ["/home/.../sibling/**"]  // read-only by default
```
The readOnlyPaths entries for external paths can be removed.

---

## Enhancement 2: Bash guardian external path extraction

### Current behavior
`extract_paths()` in bash_guardian.py (~line 490-560) filters extracted paths:
- Only paths that pass `is_within_project()` are kept
- External paths are silently dropped
- Therefore never checked against readOnlyPaths or zeroAccessPaths in the path-based checks

### Problem
If an external path is in `allowedExternalPaths`, Bash commands like `sed -i /sibling/file.txt` bypass readOnlyPaths because the path is never extracted.

Layer 1 (raw command string scan) may catch some cases (e.g., if `.env` appears in the command), but it doesn't apply readOnlyPaths checking.

### Proposed fix
In `extract_paths()`, after filtering for project paths, ALSO include paths that match `allowedExternalPaths`. These paths should then go through the same readOnlyPaths/zeroAccessPaths checks as project paths.

### Implementation
1. In `extract_paths()`, add a second pass:
   ```python
   # Current: only keep project paths
   if is_within_project(path):
       extracted.append(path)
   # New: also keep allowed external paths
   elif match_allowed_external_path(path):
       extracted.append(path)
   ```
2. The subsequent readOnlyPaths/zeroAccessPaths checks will then apply to these external paths
3. With Enhancement 1's mode support, readOnlyPaths pairing won't be needed — the mode check in `run_path_guardian_hook()` handles it

### Edge case
If an external path matches BOTH allowedExternalPaths AND zeroAccessPaths (e.g., `/sibling/.env`), zeroAccessPaths should win (deny). This is already the case because zeroAccessPaths is checked BEFORE readOnlyPaths in the check order.

---

## Enhancement 3: Update ops project config after Guardian changes

After the Guardian enhancements are released:
1. Remove readOnlyPaths entries for external projects (no longer needed)
2. Update config comment/version
3. Verify all tests still pass

---

## Testing requirements

1. Unit tests for new `match_allowed_external_path()` return format
2. Unit tests for string vs object format parsing
3. Integration tests: Read external path (mode=read) → ALLOW
4. Integration tests: Write external path (mode=read) → DENY
5. Integration tests: Write external path (mode=readwrite) → ALLOW
6. Integration tests: Bash command with external path → correctly extracted and checked
7. Backward compatibility: existing string format works as read-only
8. Edge case: external path matching zeroAccessPaths → DENY regardless of mode

---

## Files to modify

| File | Change |
|------|--------|
| `hooks/scripts/_guardian_utils.py` | `match_allowed_external_path()` — return mode; `run_path_guardian_hook()` — check mode |
| `hooks/scripts/bash_guardian.py` | `extract_paths()` — include allowed external paths |
| `tests/test_guardian.py` (or equivalent) | New test cases |
| `CHANGELOG.md` | Document breaking change |
| `README.md` | Document new config format |

---

## References

- Analysis files in ops/temp/:
  - `guardian-config-proposal.md` — design rationale
  - `guardian-security-review.md` — security review
  - `guardian-usability-review.md` — usability review (Bash asymmetry discovery)
  - `guardian-rules-catalog.md` — complete rules catalog
  - `guardian-v1-verification.md` — functional test results
  - `guardian-v2-verification.md` — adversarial test results
