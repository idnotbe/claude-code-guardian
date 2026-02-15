# Master Plan: External Path Access Control Improvement

## Problem Statement
`allowedExternalPaths` treats Read/Write/Edit identically. No way to allow read-only access to external paths without also allowing writes.

## Current Flow (run_path_guardian_hook, _guardian_utils.py:2211-2337)
1. Input parse → 2. Symlink escape → 3. Path within project (allowedExternalPaths) → 4. Self-guardian → 5. Zero access → 6. ReadOnly → 7. Allow

## Design Options

### Option A: New `allowedExternalReadPaths` config field
- `allowedExternalPaths` → read+write+edit (existing, backward compatible)
- `allowedExternalReadPaths` → read-only access to external paths
- Simple, clean, minimal schema change
- Backward compatible

### Option B: Mixed format with mode
- `allowedExternalPaths: ["/path", {"path": "/path2", "mode": "read"}]`
- More flexible but complex schema
- Backward compatible (strings default to "readwrite")

### Option C: Separate read/write fields
- `allowedExternalReadPaths` (read-only external)
- `allowedExternalWritePaths` (write/edit external)
- Remove ambiguity from `allowedExternalPaths`
- Breaking change if we remove original field

## Chosen Approach: TBD by Architect Agent

## Team Structure

### Phase 1: Architecture & Design
- **Architect Agent** → `temp/01-architecture.md`

### Phase 2: Test-First Development
- **Test Writer Agent** → creates test files based on architecture

### Phase 3: Implementation
- **Implementer Agent** → implements changes per architecture + passes tests

### Phase 4: Validation Round 1
- **Security Reviewer** → `temp/03-validation-r1-security.md`
- **API/Schema Reviewer** → `temp/03-validation-r1-schema.md`
- **Backward Compat Reviewer** → `temp/03-validation-r1-compat.md`

### Phase 5: Validation Round 2
- **Integration Tester** → `temp/04-validation-r2-integration.md`
- **Edge Case Reviewer** → `temp/04-validation-r2-edge.md`
- **Final Sign-off** → `temp/04-validation-r2-final.md`

## Files to Modify (Expected)
- `hooks/scripts/_guardian_utils.py` - Core logic
- `assets/guardian.default.json` - Default config
- `assets/guardian.schema.json` - Schema
- `tests/regression/test_allowed_external.py` - Existing tests
- New test file for the feature
- `skills/config-guide/references/schema-reference.md` - Docs
- `agents/config-assistant.md` - Docs

## Status: STARTING
