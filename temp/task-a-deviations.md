# Task A: Polish Deviations + Fix ln Tests

## Overview
Formalize 3 deviations as first-class features and fix 3 pre-existing ln test failures.

## Part 1: Deviation Polish

### Deviation 1 - Regex `[^|&;>]+`
**File**: `hooks/scripts/bash_guardian.py:772`
**Current**: `(r">\s*['\"]?[^|&;>]+", True)` (has extra `>` vs original spec)
**Action**: Add a test to `tests/test_heredoc_fixes.py` proving why the `>` in the negated class is needed.
Example test: `echo "data > temp" > output.txt` — with spec regex, `re.finditer` consumes the quoted `>` match, skipping the real redirect.

### Deviation 2 - Comment tracking
**File**: `hooks/scripts/bash_guardian.py:231-239`
**Action**: Review edge cases:
- `${#}` — should NOT be treated as comment (variable length)
- `echo foo#bar` — NOT a comment (# inside word)
- `# << EOF` at line start — IS a comment
- Consider: `# .env` still appears in sub_commands and could trigger false positive in Layer 1 scan. Evaluate stripping comment-only sub-commands from scan_text.

### Deviation 3 - Extra tests
**File**: `tests/test_heredoc_fixes.py:137-167` (TestCommentHeredocRegression)
**Action**: Verify tests are comprehensive. Add any missing edge cases from deviation 2 review.

## Part 2: Fix 3 ln Test Failures

### Failure 1: `tests/core/test_v2fixes.py::TestF2_LnWritePattern::test_ln_pattern_in_source`
**Current**: `self.assertIn(r'\bln\s+', content)` — looks for old pattern
**Code has**: `(?<![A-Za-z-])ln\s+` (tuple format)
**Fix**: Update assertion to match the actual pattern string in the tuple format.

### Failure 2: `tests/security/test_v2_adversarial.py::TestP1_4_MetadataBypass::test_ln_symlink_not_detected`
**Current**: `self.assertFalse(is_write_command("ln -s /etc/passwd link"))`
**Reality**: `ln` IS now detected as write (pattern `(?<![A-Za-z-])ln\s+` matches)
**Fix**: Flip to `assertTrue` and update docstring.

### Failure 3: `tests/security/test_v2_adversarial.py::TestKnownGaps::test_ln_symlink_gap`
**Current**: `self.assertFalse(is_write_command("ln -s /etc/passwd link"))`
**Same issue**: `ln` is now detected. Flip to `assertTrue` and update docstring.

## Validation
After changes: `python3 -m pytest tests/test_heredoc_fixes.py tests/core/test_v2fixes.py::TestF2_LnWritePattern tests/security/test_v2_adversarial.py::TestP1_4_MetadataBypass::test_ln_symlink_not_detected tests/security/test_v2_adversarial.py::TestKnownGaps::test_ln_symlink_gap -v`
