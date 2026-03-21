# Phase 2 V1: Security Audit

**Auditor**: Claude Opus 4.6 (1M context)
**Date**: 2026-03-21
**Scope**: `extract_paths_from_interpreter_payload()` (lines 1243-1330), F1 block (lines 1914-1956), test suite (22 tests)

---

## Bypass Vectors Found

### CRITICAL-1: Decoy Literal Attack — Benign Path Suppresses F1 ASK for Obfuscated Destructive Path

**Exploit**:
```bash
python3 -c "os.remove('./src/main.py'); os.remove(chr(46)+chr(103)+chr(105)+chr(116))"
```

**Mechanism**: The regex extracts `./src/main.py` as a valid string literal path within the project. Since `interp_paths` is non-empty, the F1 block routes the command through normal path validation (line 1928-1937) instead of firing ASK. The `chr()` expression — which constructs `.git` at runtime — is completely invisible to string literal extraction.

**Impact**: An AI agent generating "cleanup" code can include a benign path literal as a decoy alongside an obfuscated destructive target. The guardian validates the decoy path (which passes all checks), and the destructive operation executes undetected.

**Verified**: Yes. `extract_paths_from_interpreter_payload()` returns `[PosixPath('<project>/src/main.py')]`, suppressing F1 ASK, while `chr(46)+'env'` or `chr(46)+chr(103)+chr(105)+chr(116)` runs undetected.

**Likelihood**: MODERATE. An AI agent would not typically use `chr()` encoding unprompted. However, a deliberately adversarial prompt or a confused agent "cleaning up" files could produce this pattern. More importantly, simple string concatenation variants work too (see CRITICAL-2).

**Fix**: When `interp_paths` is non-empty BUT fewer paths are extracted than the number of destructive API calls in the payload, escalate to ASK. Alternatively, count the number of string-literal arguments to destructive APIs vs. the number of resolved paths — if there's a mismatch, the unresolved arguments may be obfuscated.

---

### CRITICAL-2: String Concatenation Decoy — Single-Character Literal "." Suppresses F1 ASK

**Exploit**:
```bash
python3 -c "os.remove('.' + 'env')"
```

**Mechanism**: The regex extracts two literals: `"."` and `"env"`. The `"."` literal passes the "starts with `.`" filter (line 1291), resolves to `project_dir / "."` which is `project_dir` itself, and passes `is_within_project()`. Since `interp_paths` is non-empty (contains `project_dir`), F1 ASK is suppressed. The actual target `.env` is constructed at runtime via concatenation and is invisible.

**Impact**: This is a MORE REALISTIC variant of CRITICAL-1. String concatenation is a common Python pattern. An AI agent could easily produce `os.remove('.' + 'env')` or `os.remove('./' + secret_name)`.

**Verified**: Yes. Returns `[PosixPath('<project_dir>')]` — the project directory itself, suppressing F1 ASK.

**Likelihood**: HIGH. String concatenation is idiomatic Python. An AI agent could generate this pattern naturally without any adversarial intent.

**Fix**:
1. Reject extracted paths that resolve to exactly `project_dir` (a directory removal would need `os.rmdir`/`shutil.rmtree`, not `os.remove`).
2. More robustly: reject single-character path literals like `"."` or `"/"` that are too generic to be meaningful targets.
3. Best: count destructive API calls vs. resolved paths (same as CRITICAL-1 fix).

---

### LOW-1: Glob Expansion Without `recursive=True` Is Safe But Could Be Confusing

**Observation**: `glob.glob(str(path))` at line 1315 is called without `recursive=True`. This means `**` patterns won't recursively expand. This is safe (fail-closed: fewer paths found means F1 ASK fires). However, if a future maintainer "fixes" this by adding `recursive=True`, the glob could expand to many more paths and potentially DoS the validation loop.

**Impact**: None currently. Future risk only.

**Fix**: Add a comment documenting that `recursive=True` is intentionally omitted for security.

---

### LOW-2: `data/file` (No Dot, No Leading Specifier) Filtered as MIME Type — False Negative

**Observation**: A path like `data/file` (single `/`, no dot, doesn't start with `.` or `/`) is incorrectly filtered as a MIME type (line 1301-1305). This means `python3 -c "os.remove('data/file')"` would NOT extract the path, causing F1 ASK to fire unnecessarily.

**Impact**: False positive (unnecessary ASK prompt). This is fail-closed, so it's a usability issue, not a security issue. The MIME filter is deliberately conservative.

**Fix**: Could add a heuristic: MIME types typically follow `type/subtype` where both parts are lowercase alpha. But the current conservative approach is safer.

---

### INFO-1: `is_write_command()` Does Not Detect Interpreter-Mediated Writes (Pre-Existing)

**Observation**: `python3 -c "open('./file','w').write('data')"`, `node -e "fs.writeFileSync('./f','d')"`, `python3 -c "Path('./f').write_text('d')"` — none of these are detected by `is_write_command()`. This means the F1 block never fires for interpreter write operations, and Phase 2 path resolution never activates for writes.

**Impact**: Interpreter-mediated writes bypass the entire path validation pipeline. This is a pre-existing gap, not introduced by Phase 2, and is noted as "covered by Phase 2b ask patterns" in the code comments. However, no such ask patterns exist in the current config.

**Fix**: Out of scope for Phase 2 audit. Should be tracked separately for Phase 2b or Phase 3.

---

## Regex Analysis: `_QUOTED_LITERAL_RE`

### Correctness

The regex `(?:'([^'\\]*(?:\\.[^'\\]*)*)'|"([^"\\]*(?:\\.[^"\\]*)*)")` correctly handles:
- Single-quoted strings with backslash escapes
- Double-quoted strings with backslash escapes
- Nested opposite quotes (e.g., `"it's"`)

### Edge Cases

| Input | Behavior | Security Impact |
|-------|----------|-----------------|
| Triple-quoted `'''path'''` | Extracts two empty strings + `path` | Empty strings are filtered out (no `/` or `.` prefix). `path` has no `/` or `.` prefix, so filtered too. **Safe**. |
| Raw string `r"/etc/passwd"` | Extracts `/etc/passwd` | Boundary check catches it. **Safe**. |
| f-string `f"./file.txt"` (no `{}`) | Extracts `./file.txt` | Literal f-string without interpolation. Extraction is correct. **Safe**. |
| String concat `"." + "env"` | Extracts `"."` and `"env"` separately | `"."` resolves to project_dir. See **CRITICAL-2**. |
| Bytes literal `b'\x2e\x65\x6e\x76'` | Extracts `\x2e\x65\x6e\x76` as string | Not a valid path (contains `\x`). **Safe**. |
| Escaped quotes `"path\"mid"` | Regex handles correctly | **Safe**. |

---

## F1 Block Logic Analysis

### Flow correctness

```
is_write or is_delete AND no sub_paths?
  |
  +-- check_interpreter_payload() -> is_interp?
       |
       +-- YES: extract paths
       |    |
       |    +-- paths found: route through validation (CONCERN: decoy attack)
       |    +-- no paths: enriched F1 ASK (safe)
       |
       +-- NO: standard F1 ASK (safe, unchanged behavior)
```

The `else` branch (not interpreter) correctly falls through to standard F1 ASK. The `is_interp=True, no paths` branch correctly fires enriched F1 ASK. The vulnerability is exclusively in the `is_interp=True, paths found` branch.

### `interp_detail` string injection

The `api_name` is extracted via `interp_detail.rsplit(": ", 1)[-1]`, which returns the `match.group()` from `_DESTRUCTIVE_API_PATTERN`. Since the pattern is a compiled regex matching specific API names (e.g., `os.remove`, `shutil.rmtree`), the extracted string is constrained to those patterns. **No injection risk.**

---

## Test Coverage Gaps

### Missing: Decoy literal attack
No test verifies that a benign extractable path COMBINED with an obfuscated destructive call (via `chr()`, string concatenation, `exec()`, `__import__()`, etc.) does not suppress F1 ASK when it should not be suppressed.

### Missing: String concatenation creates false path extraction
No test covers `os.remove('.' + 'env')` where `"."` is extracted as a valid path, resolving to project_dir and suppressing F1 ASK.

### Missing: Multiple destructive API calls with partial path resolution
No test covers a payload with N destructive API calls but only M < N extractable string literal paths.

### Missing: Glob with parent traversal
The existing glob tests only cover in-project patterns. No test covers `../*` glob patterns or absolute path globs like `/tmp/*`.

### Missing: `_QUOTED_LITERAL_RE` edge cases
No tests for triple-quoted strings, raw strings, or escaped quotes within the regex.

### Missing: Path that resolves to project_dir itself
No test verifies that extracting `"."` as a path (which becomes `project_dir`) is handled correctly.

### Adequate: Core functionality
The 22 existing tests adequately cover: basic extraction, URL filtering, MIME filtering, interpolation rejection, boundary checks, prefix confusion, glob expansion, F1 enriched messages, and non-interpreter fallback.

---

## Verdict

**PASS WITH CONCERNS**

### Rationale

Phase 2 correctly implements the core design: extract string literal paths from interpreter payloads, validate them through the existing security pipeline, and fall back to F1 ASK when extraction fails. The boundary check uses `Path.relative_to()` (not `str.startswith`), symlink escapes are caught via `.resolve()`, and all error paths fail-closed.

However, **CRITICAL-1 and CRITICAL-2 represent genuine bypass vectors** where a decoy benign path suppresses the F1 ASK safety net while an obfuscated destructive operation executes undetected. CRITICAL-2 (string concatenation) is particularly concerning because it represents a natural code pattern that an AI agent could produce without adversarial intent.

### Recommended actions before merge

1. **MUST FIX (CRITICAL-1/2)**: Add a "path count vs. destructive API count" check. If the payload contains N calls to destructive APIs but only M < N paths were resolved, the unresolved calls should still trigger F1 ASK. Implementation sketch:
   ```python
   api_count = len(list(_DESTRUCTIVE_API_PATTERN.finditer(payload)))
   if len(interp_paths) < api_count:
       # Some destructive calls have unresolvable targets
       # Fire ASK despite having some resolved paths
   ```

2. **SHOULD FIX**: Add tests for decoy literal attack and string concatenation scenarios.

3. **NICE TO HAVE**: Add a comment explaining why `recursive=True` is not passed to `glob.glob()`.
