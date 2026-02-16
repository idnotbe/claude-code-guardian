# Final Fixes from V2 Verification

Applied based on temp/09-v2-dev.md and temp/10-v2-security.md findings.

## Changes Made to README.md

### From v2-security (FINDING-1, MEDIUM)
- Added security warning for `hookBehavior.onError/onTimeout: "allow"` misconfiguration
- Warns users this disables fail-closed behavior

### From v2-security (FINDING-2, LOW)
- Noted that pre-danger checkpoints also use `--no-verify`

### From v2-security (FINDING-3, LOW)
- Clarified self-guarding scope: covers Read/Edit/Write tools, not Bash
- Noted that bash-based config modification is covered by Layer 1 path scan and `.claude` deletion patterns

### From v2-dev (M1, MEDIUM)
- Added sample log output in Troubleshooting section showing real BLOCK/ALLOW/ASK/FALLBACK entries

### From v2-dev (M2, MEDIUM)
- Changed `timeoutSeconds` description to "(see notes below)" for clarity

### From v2-dev (L1, LOW)
- Changed "100KB" to "~100KB / 100,000 bytes" for precision

### From v2-dev (L2, LOW)
- Added concrete example: `.key` file blocked even in allowedExternalReadPaths

### From v2-dev (L3, LOW)
- Added "Skip to User Guide" note at top of "How It Works" section

### From v2-dev (Installation, minor)
- Added note: "Point `--plugin-dir` to the repository root, not to any subdirectory"

## Not Changed (by design)
- "Existential dread" phrasing kept (fits target audience of power users)
- 100KB rounding kept alongside exact value (both are useful)
