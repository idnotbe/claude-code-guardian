# Final Fixes - Master Plan

## 5 Items to Fix

### Fix 1: Fixed Issues table detail (V2 Consistency FAIL)
- **File**: KNOWN-ISSUES.md, Fixed Issues table at bottom
- **Problem**: Round 2 fixes only say "Round 2" without individual detail
- **Fix**: Ensure each Round 2 entry has a brief but clear description matching the body entries

### Fix 2: README config example warning (V2 Consistency FAIL)
- **File**: README.md, lines ~100-102
- **Problem**: Partial config example might be copy-pasted without required fields
- **Fix**: Add a more prominent warning that this is a partial example

### Fix 3: Hook verification test assumes .env exists (V2 User Perspective FLAG)
- **File**: README.md, line ~153 and ~185
- **Problem**: "try to read a .env file" assumes user has one
- **Fix**: Provide a complete test instruction that works for any user

### Fix 4: Terminology consistency (V2 User Perspective NOTE)
- **File**: README.md, lines ~84 and ~86
- **Problem**: "sensible defaults" vs "built-in defaults" inconsistency
- **Fix**: Pick one term and use it consistently

### Fix 5: Add SCOPE-02 to KNOWN-ISSUES
- **File**: KNOWN-ISSUES.md
- **Problem**: hookBehavior.timeoutSeconds not enforced at hook level is undocumented
- **Fix**: Add SCOPE-02 entry documenting the deliberate design decision

## Team Structure

### Phase 1: Parallel Fix Teams
- **Team A (Teammate A1 + A2)**: README fixes (Fix 2, 3, 4)
- **Team B (Teammate B1 + B2)**: KNOWN-ISSUES fixes (Fix 1, 5)

### Phase 2: Verification Round 1
- **Teammate V1**: Accuracy (did the fixes land correctly?)
- **Teammate V2**: Completeness (was anything missed?)

### Phase 3: Verification Round 2
- **Teammate V3**: Cross-doc consistency
- **Teammate V4**: User perspective

## Output Files
- temp/final-fixes/team-a-fixes.md
- temp/final-fixes/team-b-fixes.md
- temp/final-fixes/verification-r1.md
- temp/final-fixes/verification-r2.md
