# Phase 2 Verification Round 1: Security Review

**Reviewer**: reviewer-security
**Date**: 2026-02-18
**Scope**: Red-team the 3 hardening fixes applied in Phase 2

---

## VERDICT: PASS (for Phase 2 scope)

The 3 hardening fixes are correctly implemented and do NOT introduce regressions.
Several pre-existing bypass vectors were identified but are outside Phase 2 scope.

---

## Section 1: The 3 Hardening Fixes -- PASS

All 3 fixes work correctly:

### Fix 1: Leading whitespace -- PASS (7/7 tests)
| Test | Result |
|------|--------|
| `"  rm .claude/config"` | BLOCKED |
| `"\trm .claude/config"` | BLOCKED |
| `"   rm -rf .git/"` | BLOCKED |
| `"\t\trm _archive/x"` | BLOCKED |
| `"    rmdir .claude"` | BLOCKED |
| `"\t  rm .git/index"` | BLOCKED |
| `"  \t  rm .claude/settings.json"` | BLOCKED |

The `^\s*` anchor correctly catches all whitespace variants including `\v` (vertical tab), `\f` (form feed), and `\r` (carriage return), because Python's `\s` matches all Unicode whitespace.

### Fix 2: Brace groups -- PASS (5/5 tests)
| Test | Result |
|------|--------|
| `"{ rm .claude/x; }"` | BLOCKED |
| `"{ del .git/config; }"` | BLOCKED |
| `"{ rmdir _archive; }"` | BLOCKED |
| `"{rm .claude/x;}"` | BLOCKED |
| `"{ rm -rf .git; echo done; }"` | BLOCKED |

The `{` in the separator class `[;|&\`({]` correctly catches brace group syntax.

### Fix 3: Quoted paths -- PASS (8/8 tests)
| Test | Result |
|------|--------|
| `'rm ".claude/config"'` | BLOCKED |
| `"rm '.claude/config'"` | BLOCKED |
| `'rm ".git/config"'` | BLOCKED |
| `"rm '.git/config'"` | BLOCKED |
| `'del "_archive/x"'` | BLOCKED |
| `"del '_archive/x'"` | BLOCKED |
| `'rm -rf ".claude"'` | BLOCKED |
| `"rm -rf '.git'"` | BLOCKED |

The `'"` in the terminator class correctly handles quoted path boundaries.

---

## Section 2: False Positive Regressions -- PASS (10/10 tests)

| Test | Result |
|------|--------|
| `"python3 memory_write.py --action delete .claude/memory/MEMORY.md"` | ALLOWED |
| `"cat .claude/memory/MEMORY.md"` | ALLOWED |
| `"git status"` | ALLOWED |
| `"ls -la"` | ALLOWED |
| `"echo hello"` | ALLOWED |
| `"rm temp.txt"` | ALLOWED |
| `"git push origin main"` | ALLOWED |
| `"python3 -c 'print(1)'"` | ALLOWED |
| `"node -e 'console.log(1)'"` | ALLOWED |
| `"git log --oneline"` | ALLOWED |

No false positives introduced.

---

## Section 3: Red-Team Bypass Attempts

### 3a. Separator bypasses -- PASS (8/8)
All standard separators correctly caught: `;;`, `;`, `|`, `&&`, `||`, `(`, `{`, backtick.

### 3b. Pre-existing bypasses (NOT Phase 2 regressions)

The following bypass vectors were identified. ALL are pre-existing gaps that existed before Phase 2 and are NOT introduced or worsened by the hardening changes:

| Bypass | Severity | Caught by other layers? |
|--------|----------|------------------------|
| `command rm .claude/x` | MEDIUM | NO -- is_delete_command also misses it |
| `builtin rm .claude/x` | LOW | NO -- but `builtin` is bash-specific |
| `env rm .claude/x` | MEDIUM | NO -- is_delete_command also misses it |
| `sudo rm .claude/x` | MEDIUM | NO -- no sudo handling exists |
| `nohup rm .claude/x &` | LOW | Partially -- `&` splits command, but nohup prefix still masks rm |
| `nice rm .claude/x` | LOW | NO |
| `timeout 10 rm .claude/x` | LOW | NO |
| `sh -c "rm .claude/x"` | MEDIUM | NO -- rm is inside quoted argument |
| `<<<rm .claude/x` | LOW | NO -- here-string, exotic |
| `rm .cl''aude/config` | MEDIUM | NO -- shell concatenation obfuscation |
| `rm $'\x2eclaude'` | LOW | NO -- ANSI-C quoting, exotic |
| `rm .{claude}/config` | LOW | NO -- brace expansion |
| `rm .claud?/config` | LOW | NO -- glob pattern |
| `D=.claude; rm $D` | LOW | Partially -- `;` splits, but `rm $D` doesn't contain `.claude` |

**Note on newline injection**: `"echo x\nrm .claude/x"` is NOT caught by the regex (no `re.MULTILINE`), but IS handled by `bash_guardian.py`'s `split_commands()` which correctly splits on `\n` at line 230. After splitting, `"rm .claude/x"` is evaluated independently and BLOCKED.

### 3c. Severity Assessment of Pre-existing Gaps

**Context**: These bypasses require an adversarial actor who specifically knows the guardian's regex anchoring strategy. In the intended threat model (preventing AI agents from accidentally deleting protected paths), these are low-risk because:

1. AI agents don't typically use `command`, `builtin`, `env`, `sudo`, or shell concatenation tricks
2. The `command` and `env` prefixes are rarely needed for file deletion
3. Shell concatenation (`rm .cl''aude`) is an intentional obfuscation that an AI would have no reason to use

**Recommendation**: For future hardening, consider adding `sudo`, `env`, `command`, `nice`, `nohup`, `timeout`, `busybox` to the command prefix recognition in both the regex anchor and `is_delete_command()`. This is a separate task from Phase 2.

---

## Section 4: ReDoS Risk Assessment -- PASS

The `.*` in the middle of the pattern was the primary concern. Tested with adversarial inputs:

| Input | Size | Time | Result |
|-------|------|------|--------|
| `rm AAAA...AAAA.claude/x` | 100 chars | 0.0000s | Matched |
| `rm AAAA...AAAA.claude/x` | 1,000 chars | 0.0002s | Matched |
| `rm AAAA...AAAA.claude/x` | 10,000 chars | 0.0002s | Matched |
| `rm AAAA...AAAA` (no match) | 100 chars | 0.0000s | No match |
| `rm AAAA...AAAA` (no match) | 1,000 chars | 0.0005s | No match |
| `rm AAAA...AAAA` (no match) | 10,000 chars | 0.0014s | No match |
| `rm ;|&;|&...;|&.claude/x` | 9,000 chars | 0.0007s | Matched |
| `[10k spaces]rm .claude/x` | 10,000 chars | 0.0005s | Matched |

**Assessment**: No ReDoS risk. All inputs processed in under 2ms even at 10k characters. The pattern performs linearly because:
- The `\s+` after `\b` prevents overlap with the `.*`
- The terminator class `(?:\s|/|[;&|)\`'"]|$)` has no overlap with the preceding `.*\.claude`
- Python's regex engine handles this structure efficiently

Additionally, `MAX_COMMAND_LENGTH` (100KB default) provides a hard cap as a fail-close defense.

---

## Section 5: Pattern Consistency Across Files -- PASS

All 5 target files contain the correctly hardened patterns:

| File | .git | .claude | _archive |
|------|------|---------|----------|
| `assets/guardian.default.json` | OK | OK | OK |
| `hooks/scripts/_guardian_utils.py` (fallback) | OK | OK | OK |
| `tests/test_guardian_utils.py` | OK | OK | N/A* |
| `tests/test_guardian.py` | OK | N/A** | OK |
| `/home/idnotbe/projects/ops/.claude/guardian/config.json` | OK | OK | OK |

\* test_guardian_utils.py test config only has .git and .claude patterns
\** test_guardian.py test config only has .git and _archive patterns

The patterns are byte-for-byte consistent across all files (after accounting for JSON escaping vs Python raw string format).

---

## Section 6: Defense-in-Depth Confirmation -- PASS

`bash_guardian.py` implements a multi-layer defense:

1. **Layer 0a**: Block patterns (regex) -- the patterns we hardened
2. **Layer 0b**: Ask patterns (regex)
3. **Layer 1**: `scan_protected_paths()` -- raw string scan for protected path literals
4. **Layer 2**: `split_commands()` -- command decomposition handling `;`, `&&`, `||`, `|`, `&`, `\n`
5. **Layer 3**: `extract_paths()` -- path extraction from arguments
6. **Layer 4**: `match_zero_access()`, `match_read_only()`, `match_no_delete()` -- path-based checks
7. **Layer F1**: Fail-closed safety net for write/delete commands where no paths could be resolved

Key confirmations:
- `split_commands()` correctly handles `\n` as a separator (line 230)
- `is_delete_command()` is called per-sub-command after splitting
- `match_no_delete()` protects `.git/**`, `.claude/**`, `_archive/**` paths
- The fail-close on unresolved paths (Layer F1) catches cases where path extraction fails

---

## Section 7: DO NOT CHANGE Items -- PASS

| Item | Status |
|------|--------|
| `bash_guardian.py` `is_delete_command()` (lines 610-616) | Unchanged |
| SQL DELETE pattern in `guardian.default.json` (line 147) | Unchanged |
| `del\s+` ask pattern in `guardian.default.json` (line 91) | Unchanged |

---

## Section 8: External AI Review (Gemini)

Gemini identified 7 bypass categories. My assessment of each:

| Gemini Finding | My Verdict | Notes |
|----------------|------------|-------|
| Newline injection | Pre-existing, mitigated | `split_commands()` handles `\n` at Layer 2 |
| Shell concatenation (`.cl''aude`) | Pre-existing, valid gap | No mitigation in any layer |
| Command prefixes (`sudo`, `env`) | Pre-existing, valid gap | No prefix stripping in any layer |
| Variable expansion (`rm $D`) | Pre-existing, partially mitigated | `;` separator splits `D=.claude; rm $D` |
| Wildcards/globbing | Pre-existing, valid gap | Regex requires literal `.claude` |
| ANSI-C quoting (`$'\x2e'`) | Pre-existing, very exotic | Unlikely in AI agent context |
| Indirect execution (`find -exec`) | Already handled | Caught by `find -exec` and `xargs` ask patterns |

Gemini's recommendation to use AST parsing is architecturally sound but out of scope for Phase 2. The regex-based approach is a practical balance of security and complexity for the AI agent threat model.

---

## Summary

| Category | Verdict |
|----------|---------|
| Fix 1: Leading whitespace | PASS |
| Fix 2: Brace groups | PASS |
| Fix 3: Quoted paths | PASS |
| False positive regressions | PASS (0 regressions) |
| ReDoS risk | PASS (linear performance) |
| Pattern consistency (5 files) | PASS |
| Defense-in-depth | PASS |
| DO NOT CHANGE items | PASS |
| Pre-existing bypasses | N/A (out of scope, documented for future work) |

**Overall: PASS** -- The 3 hardening fixes are correctly implemented, consistent across all files, introduce no regressions, and do not create ReDoS vulnerabilities.
