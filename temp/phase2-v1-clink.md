# Phase 2 V1: Cross-Model Code Review

Reviewers: Codex 5.3, Gemini 3.1 Pro
Date: 2026-03-21
Scope: `extract_paths_from_interpreter_payload()` + F1 block modifications

---

## Codex 5.3 Findings

**Rating: 5/10**

### Security Bypass Vectors

1. **HIGH - Decoy literal suppresses F1 ASK.** The extractor scans _all_ quoted literals in the payload, not just arguments to destructive APIs. A payload like `python3 -c "decoy='safe/decoy.txt'; os.remove(target)"` produces a resolved in-project path even though the real target is unresolved. This downgrades unknown-target deletes from ASK to normal path validation and potentially ALLOW.

2. **HIGH - JS escape sequences bypass path matching.** The literal is passed to `Path()` without language-level unescaping. In Node, `\/` is `/`, so `node -e "fs.unlinkSync('.claude\\/settings.json')"` deletes `.claude/settings.json` but the guard resolves `.claude\/settings.json` instead, missing zeroAccess/noDelete checks.

3. **HIGH - Interpreter writes bypass guard entirely.** `is_write_command()` has no interpreter write detection. `check_interpreter_payload()` covers only delete-class APIs. Commands like `python3 -c "open('.env','w').write('x')"` return ALLOW under shipped config. (Known gap, not new to Phase 2, but Phase 2 does not address it.)

### Logic Issues

- Interpreter-extracted paths do not get the nonexistent-path handling that normal shell arguments do, creating behavioral divergence.

### Missing Test Coverage

- Decoy benign literal + unresolved destructive target
- JS/Node escaped slashes (`\/`)
- End-to-end verdicts through `main()` with interpreter-delete block patterns disabled
- Interpreter write APIs with dynamic targets
- Multiple destructive calls where only some targets resolve
- Nested `exec`/`eval` payloads with unrelated quoted strings
- Duplicate extracted paths / mixed resolved and unresolved targets

### Positives Noted

- Boundary enforcement via `relative_to` instead of string prefix checks
- Conservative rejection of interpolation markers
- Defense in depth from default interpreter-delete block rules in config

### Mitigating Factor

Under the shipped default config, interpreter deletes are blocked earlier by Layer 0 patterns, so the delete-side F1 downgrades are masked today. They become reachable if those patterns are relaxed.

---

## Gemini 3.1 Pro Findings

**Rating: 3/10**

### Security Bypass Vectors

1. **CRITICAL - Mixed path bypass (F2-1 logic flaw).** `is_within_project` silently drops out-of-bounds paths during extraction rather than flagging them. Attacker payload: `python3 -c "os.remove('/etc/passwd'); os.remove('./dummy.txt')"`. The out-of-bounds path is discarded, the benign path is returned, F1 assumes all targets are resolved and safe, bypassing the fail-closed ASK.

2. **HIGH - Dynamic path evasion.** Static regex cannot resolve dynamically constructed targets (`'etc/' + 'passwd'`, `chr(47) + 'root'`, `sys.argv[1]`). When paired with a benign string literal, F1 is tricked into allowing the destructive script.

3. **MEDIUM - Format string interpolation bypass (F2-2 gap).** Checks for `{` and `$` but misses C-style `%` formatting. `"%s/passwd" % "../../../../etc"` extracts `%s/passwd` as an in-bounds relative path while runtime resolves it elsewhere.

4. **MEDIUM - MIME-type over-filtering.** The heuristic (`literal.count('/') == 1 and '.' not in literal`) also filters valid extensionless file paths like `foo/bar` or `bin/bash`.

### Missing Test Coverage

- Triple quotes and raw strings (`r"C:\Windows\System32"`)
- Out-of-bounds globs (`/*`) silently dropped, keeping paths artificially clean
- Non-path literals in `print()` populating `interp_paths` and bypassing F1

### Architectural Critique

Gemini argued the fundamental approach is unsafe: statically analyzing arbitrary Python/Node payloads via regex to bypass the fail-closed ASK state cannot be made secure. The extractor should never be used to suppress ASK for destructive operations unless it can prove it extracted ALL operations.

### Recommended Fixes

1. Never silently drop paths -- return all extracted paths (including out-of-bounds) so Layer 4 validation explicitly blocks them
2. Revert/scope F1 bypass -- fail-closed (ASK) whenever any interpreter destructive API is detected, unless all operations are provably resolved
3. Add `%` to interpolation marker checks

---

## Agreement Matrix

| Finding | Codex | Gemini | Severity | Agreement |
|---------|-------|--------|----------|-----------|
| Decoy literal suppresses F1 ASK | HIGH - scans all literals, not just destructive API args | CRITICAL - mixed path bypass, silent drop of OOB paths | HIGH-CRITICAL | **AGREE** - Same root cause, different framing. Codex focuses on "any literal works as decoy," Gemini focuses on "OOB paths silently dropped." Both conclude F1 ASK is incorrectly suppressed. |
| Dynamic path evasion (concat, chr, vars) | HIGH - acknowledged as inherent limitation | HIGH - same conclusion | HIGH | **AGREE** - Both identify that static regex cannot resolve dynamic paths and this is exploitable with decoy literals. |
| JS escape sequences (`\/`) | HIGH - verified with Node runtime | Not mentioned | HIGH | **DISAGREE** - Only Codex identified this. Gemini did not test language-level escape handling. |
| Format string `%` bypass | Not mentioned | MEDIUM - `%s/passwd` bypasses F2-2 | MEDIUM | **DISAGREE** - Only Gemini identified this. Codex did not examine `%`-style formatting. |
| MIME-type over-filtering | Not mentioned | MEDIUM - extensionless paths filtered | MEDIUM | **DISAGREE** - Only Gemini flagged this. |
| Interpreter writes undetected | HIGH - confirmed ALLOW end-to-end | Not mentioned explicitly | HIGH | **PARTIAL** - Codex confirmed this existing gap; Gemini did not address it. |
| Nonexistent-path handling divergence | Noted - interp paths skip this | Not mentioned | LOW-MEDIUM | **DISAGREE** - Only Codex noted. |
| Architectural unsoundness of approach | Implied (rated 5/10) | Explicit (rated 3/10, "fundamentally unsafe") | DESIGN | **AGREE** on skepticism, **DISAGREE** on severity. Codex treats it as improvable; Gemini treats it as fundamentally broken. |
| Lack of end-to-end main() tests | Noted | Noted (indirectly) | MEDIUM | **AGREE** |

---

## Actionable Items

### Must Fix

1. **Decoy literal / mixed path bypass** (Codex HIGH + Gemini CRITICAL)
   - Root cause: The extractor returns ANY path-like literal, and OOB paths are silently filtered out. If even one benign in-project literal exists alongside an unresolved destructive target, F1 ASK is suppressed.
   - Fix options:
     - **(A) Conservative:** Keep F1 at ASK for ALL interpreter destructive commands, regardless of extraction results. Use extracted paths only for enriching the ASK message, not for bypassing it.
     - **(B) Structural:** Return all extracted paths (including OOB) and let Layer 4 validation handle them. Also require that the number of extracted paths matches the number of detected destructive API calls.
     - **(C) Minimal:** Only extract paths from arguments syntactically attached to known destructive calls (os.remove(...), fs.unlinkSync(...)), not from arbitrary string literals.
   - Recommended: Option A (safest, simplest) or C (preserves usability intent).

2. **JS escape sequence bypass** (Codex HIGH)
   - `\/` in JS strings resolves to `/` at runtime but the extractor passes `\/` to Path().
   - Fix: Either reject any literal containing `\` in double-quoted strings, or add per-language unescape logic before path construction.

3. **Add `%` to F2-2 interpolation rejection** (Gemini MEDIUM)
   - Simple one-line fix: add `or '%' in literal` to the interpolation marker check at line 1287.

### Should Fix

4. **MIME-type filter tightening** (Gemini MEDIUM)
   - Current filter drops extensionless paths like `foo/bar`. Options:
     - Add a whitelist of known MIME type prefixes (`application`, `text`, `image`, `audio`, `video`, `multipart`, `font`, `model`, `message`)
     - Or remove the filter entirely (conservative approach -- let Layer 4 handle it)

5. **End-to-end `main()` tests** (Both reviewers)
   - Add tests that go through the full `main()` path with configs that disable Layer 0 interpreter-delete blocks, then assert verdicts for:
     - Decoy literal + unresolved target
     - Mixed OOB + in-bounds paths
     - JS escaped path literals
     - Format string payloads

6. **Nonexistent-path handling parity** (Codex)
   - Ensure interpreter-extracted paths receive the same nonexistent-path treatment as shell-argument paths.

### Nice to Have

7. **Interpreter write detection** (Codex HIGH, but pre-existing gap)
   - Extend `check_interpreter_payload()` to cover write APIs (`open(,'w')`, `Path.write_text`, `fs.writeFileSync`, etc.)
   - This is a pre-existing gap, not introduced by Phase 2, but Phase 2 is the natural place to address it.

8. **Architectural reconsideration** (Gemini)
   - Consider whether the extractor should ever suppress F1 ASK for destructive operations. The conservative position is that it should only enrich the ASK message, never suppress it.
   - Counter-argument: this would make all interpreter commands prompt the user, reducing usability for legitimate cleanup scripts.

---

## Summary

Both reviewers independently identified the same critical flaw: the extractor scans all string literals (not just destructive API arguments) and silently drops out-of-bounds paths, which allows a decoy literal to suppress the F1 fail-closed ASK. This is the highest-priority fix.

Codex uniquely identified the JS escape sequence bypass (`\/`). Gemini uniquely identified the `%` format string bypass and MIME-type over-filtering. Both findings are valid and should be addressed.

The reviewers diverge on architectural assessment: Codex rates 5/10 (improvable), Gemini rates 3/10 (fundamentally flawed). The truth likely sits in between -- the approach can be made safe with option A (never suppress ASK, only enrich it) or option C (bind extraction to destructive API arguments only), but the current implementation as-shipped has real bypass vectors.

**Mitigating factor:** Under the shipped default config, interpreter deletes are blocked at Layer 0 before F1 ever fires, so these bypasses are latent rather than immediately exploitable. They become reachable if Layer 0 patterns are relaxed.
