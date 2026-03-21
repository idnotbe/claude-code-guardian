# Phase 2 V2 Cross-Model Verification Report

**Date**: 2026-03-21
**Reviewers**: Codex 5.3 (codereviewer), Gemini 3.1 Pro (codereviewer), Claude Opus 4.6 (coordinator)
**Target**: `extract_paths_from_interpreter_payload()` + F1 integration block
**Scope**: Verify V1 fixes, find remaining bypass vectors

---

## V1 Fix Verification Results

| Fix | Codex 5.3 | Gemini 3.1 Pro | Coordinator | Consensus |
|-----|-----------|----------------|-------------|-----------|
| 1. `.`/`./` trivial rejection | CORRECT (but incomplete) | INCOMPLETE | INCOMPLETE | Needs hardening |
| 2. `%` interpolation rejection | CORRECT | CORRECT | CORRECT | VERIFIED |
| 3. `\` backslash rejection | CORRECT | CORRECT | CORRECT | VERIFIED |
| 4. MIME prefix allowlist | Nearly complete (missing `haptics/`, `example/`) | CORRECT (only `example/` missing) | Missing `haptics/` | Needs minor addition |

### Fix 1 Detail: `.`/`./` Rejection - INCOMPLETE

Both reviewers found the fix is too narrow. The `stripped_literal.rstrip('/') in ('', '.')` check catches:
- `'.'` -> stripped = `'.'` -> REJECTED
- `'./'` -> stripped = `'.'` -> REJECTED
- `'.///'` -> stripped = `'.'` -> REJECTED

But it MISSES:
- `'./.'` -> stripped = `'./.'` -> NOT in `('', '.')` -> PASSES -> resolves to project root
- `'././'` -> stripped = `'././'` -> PASSES -> resolves to project root

**Coordinator verification**: Confirmed. `Path('./.').resolve()` == project root. This is a real bypass of the decoy prevention.

### Fix 2 Detail: `%` Rejection - VERIFIED

Both reviewers confirm this is correctly implemented. Conservative (will reject legitimate `%` in filenames) but fail-closed is the right stance.

### Fix 3 Detail: `\` Backslash Rejection - VERIFIED

Both reviewers explicitly confirm this is NOT too aggressive:
- POSIX paths use `/` (forward slash), not `\` (backslash)
- `extract_interpreter_payload()` strips outer shell quote escapes BEFORE the regex runs
- A path like `/home/user/file.txt` contains only `/`, no `\`
- Windows-style paths would trigger ASK, which is acceptable fail-closed behavior

### Fix 4 Detail: MIME Prefix Allowlist - NEARLY COMPLETE

Current tuple: `application/, text/, image/, audio/, video/, multipart/, font/, model/, message/`

Missing per IANA registry:
- `haptics/` (RFC 9695, registered 2024) - Codex found this
- `example/` (RFC 4735, documentation/testing only) - Both found this

**Risk**: LOW. `haptics/` is extremely uncommon in real code. `example/` is documentation-only. However, for completeness both should be added.

---

## New Findings

### FINDING 1: CRITICAL - Mixed Paths Silent Dropping Bypass

**Both reviewers independently found this. This is the most important finding.**

**Location**: `bash_guardian.py:1340-1345` (in extract function) + `bash_guardian.py:1950` (F1 block)

**Attack vector**:
```python
python3 -c "os.remove('../etc/passwd'); os.remove('./valid.txt')"
```

**What happens**:
1. `extract_paths_from_interpreter_payload()` extracts two path-like literals: `../etc/passwd` and `./valid.txt`
2. `../etc/passwd` resolves outside project -> `is_within_project()` returns False -> **silently dropped**
3. `./valid.txt` (if it exists in project) -> accepted -> added to paths list
4. Function returns `[PosixPath('.../valid.txt')]` (non-empty)
5. F1 block (line 1950) sees `interp_paths` is non-empty -> skips ASK
6. Only `valid.txt` goes through normal validation -> PASSES
7. The `os.remove('../etc/passwd')` executes WITHOUT user confirmation

**Impact**: Any attacker who includes one valid in-project path alongside a malicious out-of-project path completely defeats the fail-closed F1 safety net.

**Fix**: If ANY extracted literal resolves to a path-like string that fails the project boundary check, the entire function must return `[]` to trigger F1 ASK. The presence of an out-of-project path is a stronger signal than the presence of an in-project path.

### FINDING 2: HIGH - Unrelated Literal Decoy (Codex)

**Location**: `bash_guardian.py:1280` (regex scans ALL quoted literals, not just destructive API arguments)

**Attack vector**:
```python
python3 -c "print('docs/readme.md'); os.remove(target_var)"
```

**What happens**:
1. Regex extracts `docs/readme.md` from the print statement (unrelated to the delete)
2. `os.remove(target_var)` has no string literal -> nothing extracted for it
3. `docs/readme.md` resolves within project -> returned
4. F1 sees non-empty paths -> skips ASK
5. The real delete target (`target_var`) is unresolved and unvalidated

**Impact**: Any quoted path-like string ANYWHERE in the payload (comments, print statements, logging, variable assignments) can suppress F1 ASK for an unresolvable destructive call.

**Note**: This is a more general version of the decoy attack. The V1 fix for `.`/`./` addressed a specific case, but the root cause (treating any extracted literal as proof of successful path resolution) remains.

### FINDING 3: HIGH - `./.` Decoy Bypass (Gemini)

**Location**: `bash_guardian.py:1306-1308`

**Attack vector**:
```python
python3 -c "os.remove('./.'); os.remove(secret_target)"
```

`'./.`' passes the trivial literal check (`stripped_literal = './.'`, not in `('', '.')`), resolves to project root, passes `is_within_project()`, and suppresses the F1 ASK.

**Coordinator verification**: CONFIRMED via `python3 -c "from pathlib import Path; print(Path('./.').resolve())"` -> project root.

### FINDING 4: MEDIUM - String Concatenation Bypass (Gemini)

**Location**: `bash_guardian.py:1245-1247` (regex extracts individual literals)

**Attack vector**:
```python
python3 -c "os.remove('../' + 'etc/passwd')"
```

The regex extracts `../` and `etc/passwd` as separate literals. `../` resolves outside project (dropped). `etc/passwd` resolves as `project_dir/etc/passwd` which may exist or not. If it doesn't exist, it's dropped (no file on disk). But this connects to the broader mixed-paths issue.

### FINDING 5: LOW - Missing MIME Types (Codex)

`haptics/` (RFC 9695) missing from allowlist. Unlikely to cause real issues but trivial to fix.

---

## Agreement Matrix

| Finding | Codex 5.3 | Gemini 3.1 Pro | Coordinator |
|---------|-----------|----------------|-------------|
| Mixed paths bypass | CRITICAL | CRITICAL | CRITICAL |
| Unrelated literal decoy | CRITICAL (broader framing) | -- (subsumed under mixed paths) | HIGH |
| `./.` decoy bypass | -- | HIGH | HIGH (confirmed) |
| String concat bypass | -- | MEDIUM | MEDIUM |
| `.`/`./` fix incomplete | Noted | INCOMPLETE | INCOMPLETE |
| `%` fix correct | CORRECT | CORRECT | CORRECT |
| `\` fix correct, not over-aggressive | CORRECT | CORRECT | CORRECT |
| MIME mostly complete | Missing `haptics/`, `example/` | Missing `example/` only | Missing `haptics/` |
| Backslash false positives on POSIX? | NO | NO | NO |

### Ratings

| Reviewer | Rating | Key Justification |
|----------|--------|-------------------|
| Codex 5.3 | 5/10 | Core bypass remains: any extracted literal suppresses ASK |
| Gemini 3.1 Pro | 4/10 | Silently dropping out-of-project paths breaks fail-closed |
| Coordinator | 5/10 | V1 fixes are solid but the mixed-paths issue is fundamental |

---

## Final Actionable Items (Priority Order)

### P0: MUST FIX before merge

1. **Mixed paths fail-closed**: If ANY literal resolves to a path-like target that fails `is_within_project()`, return `[]` immediately. The presence of an out-of-project literal means the payload contains targets the extractor cannot fully validate, so the fail-closed F1 ASK must fire.

   Implementation sketch:
   ```python
   # Track whether any path-like literal was rejected
   has_rejected_path = False

   for match in _QUOTED_LITERAL_RE.finditer(payload):
       ...
       # After all filters but before is_within_project:
       if not is_within_project(path, project_dir):
           has_rejected_path = True
           continue
       paths.append(path)

   # If any path was outside project, fail closed
   if has_rejected_path:
       return []

   return paths
   ```

2. **Harden `.`/`./` check**: After resolving the path, reject if `path.resolve() == project_dir.resolve()`. This catches `./.`, `././`, etc.

   Implementation sketch:
   ```python
   # After path = project_dir / literal:
   if path.resolve() == project_dir.resolve():
       continue
   ```

### P1: SHOULD FIX

3. **Add `haptics/` to MIME prefix allowlist**: Trivial one-line addition for IANA completeness.

4. **Consider `example/` in MIME allowlist**: Very low priority but completes the IANA set.

### P2: ACCEPTED LIMITATION (per threat model)

5. **Unrelated literal decoy**: A quoted path in a print() or comment can suppress F1 ASK. This is partially mitigated by P0 item 1 (mixed paths fail-closed). The remaining risk (all literals are in-project but the actual destructive target is a variable) is accepted per the threat model: AI agents generate straightforward code with literal paths, not variable-based indirection. Layer 0 patterns also independently block common interpreter delete patterns in default config.

6. **String concatenation**: Individual string fragments from `"../" + "etc/passwd"` are extracted separately. After P0 item 1, the `../` fragment would trigger fail-closed (resolves outside project), so this is mitigated.

---

## Summary

The 4 V1 fixes are largely correctly implemented. The `%` rejection, `\` backslash rejection, and MIME prefix allowlist are all solid and verified by both external reviewers as well as the coordinator. The backslash check does NOT cause false positives on legitimate POSIX paths.

However, both Codex 5.3 and Gemini 3.1 Pro independently identified the same critical architectural flaw: the function silently drops out-of-project paths instead of failing closed. This means a payload containing both a safe in-project path and a dangerous out-of-project path will suppress the F1 ASK and only validate the safe path. This must be fixed before the feature can be considered secure.

Additionally, the `.`/`./` trivial literal check needs hardening to catch equivalent forms like `./.` that resolve to the project root.
