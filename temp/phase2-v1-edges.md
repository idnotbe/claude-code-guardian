# Phase 2 V1: Edge Case Analysis

Reviewer: Claude Opus 4.6 (1M context)
Date: 2026-03-21
Files analyzed:
- `hooks/scripts/bash_guardian.py` lines 1243-1330, 1914-1956
- `hooks/scripts/_guardian_utils.py` lines 907-965
- `tests/regression/test_interpreter_path_resolution.py`

---

## Edge Case 1: Multiple paths in one payload
**Input**: `python3 -c "os.remove('./a.txt'); os.remove('./b.txt')"`
**Expected**: Both paths extracted
**Actual**: `_QUOTED_LITERAL_RE.finditer()` iterates all quoted literals in the payload. It finds `'./a.txt'` and `'./b.txt'` as separate matches. Both pass the path-likeness filter (start with `.`). Both are resolved relative to `project_dir` and checked via `is_within_project()`. If both are within project, both are returned.
**Verdict**: PASS

## Edge Case 2: Mixed valid/invalid paths
**Input**: `python3 -c "os.remove('./valid.txt'); os.remove('/etc/passwd')"`
**Expected**: Extract valid, reject outside-project one. F1 behavior?
**Actual**: The regex extracts both `'./valid.txt'` and `'/etc/passwd'`. `is_within_project()` passes `./valid.txt` and rejects `/etc/passwd`. `extract_paths_from_interpreter_payload()` returns `[project_dir/valid.txt]` (1 path). In the F1 block (line 1928), `interp_paths` is truthy, so `sub_paths = interp_paths` and the code falls through to normal path validation. **The `/etc/passwd` reference is silently dropped.** No ASK or DENY is generated for the out-of-project path. An attacker could craft: `python3 -c "os.remove('./decoy.txt'); os.remove('/etc/important')"` where the decoy path exists in-project and passes validation, while the real target is silently ignored by the guardian.
**Verdict**: BUG (security) -- When a payload contains BOTH in-project and out-of-project paths, the out-of-project paths are silently dropped. The F1 block should fire ASK if ANY extracted literal resolved to an out-of-project path, even when some paths did resolve successfully.

## Edge Case 3: Empty string literal
**Input**: `python3 -c "os.remove('')"`
**Expected**: What happens with `Path('')`?
**Actual**: The regex matches `''` and extracts empty string `""`. The path-likeness filter at line 1291 checks `'/' not in literal and not literal.startswith('.')`. Empty string fails both: `'/' not in ''` is True, `''.startswith('.')` is False. So the combined check `'/' not in literal and not literal.startswith('.')` evaluates to True (the skip condition), and the literal is skipped via `continue`. Returns `[]`.
**Verdict**: PASS -- Empty string is correctly rejected by the path-likeness filter.

## Edge Case 4: Dot path
**Input**: `python3 -c "os.remove('.')"`
**Expected**: Extracts `.`, resolves to project_dir. Is this dangerous?
**Actual**: The regex extracts `'.'`. Path-likeness filter: `'/' not in '.'` is True, `'.'.startswith('.')` is True, so the skip condition is False -- literal proceeds. `Path('.')` is constructed. It's not absolute, so `path = project_dir / Path('.')` which resolves to `project_dir` itself. `is_within_project(project_dir, project_dir)` returns True. The path `project_dir` is returned. In the path validation loop (line 1958), this path would be checked against zero-access, read-only, and symlink rules. `os.remove('.')` on a directory would fail at the OS level, but the guardian would ALLOW it since project_dir is within the project.
**Verdict**: CONCERN -- The dot path resolves to the project directory itself. While `os.remove('.')` would fail on Linux (EISDIR), `shutil.rmtree('.')` would not. The function does not distinguish between file and directory targets. If the parent command were `python3 -c "shutil.rmtree('.')"`, the guardian would extract `.` as a valid in-project path, skip the F1 ASK, and allow recursive deletion of the entire project directory. However, `shutil.rmtree` would separately trigger `is_delete_command()` which sets `is_delete=True`, and the path validation loop would process it -- but since the project root is a valid in-project path, it would be ALLOWED. This is arguably working as designed (the project CAN delete its own files) but worth noting.

## Edge Case 5: Path with spaces
**Input**: `python3 -c "os.remove('./my file.txt')"`
**Expected**: Regex handles spaces in path
**Actual**: `_QUOTED_LITERAL_RE` matches everything between quotes. The extracted literal is `./my file.txt` (spaces preserved). `Path('./my file.txt')` works fine. `project_dir / Path('./my file.txt')` resolves correctly. Spaces in paths are handled by `Path()` natively.
**Verdict**: PASS

## Edge Case 6: Path with special chars (escaped tab)
**Input**: `python3 -c "os.remove('./file\ttab.txt')"`
**Expected**: Handles escaped characters
**Actual**: The regex captures `\t` as a literal backslash followed by `t` (since `_QUOTED_LITERAL_RE` handles `\\.` sequences). The extracted literal is `./file\ttab.txt` (with literal backslash-t, not a tab character). If the shell has already expanded `\t` to an actual tab before the hook receives the command, the regex still matches it since `[^"\\]*` allows any non-quote non-backslash character including tab. Either way, `Path()` handles it.
**Verdict**: PASS -- But note the extracted path may differ from what Python would actually interpret at runtime (Python's `\t` = tab character, but the regex captures it as literal `\t` in single-quoted context). This is a theoretical mismatch but not exploitable since the guardian is being conservative.

## Edge Case 7: Deeply nested path
**Input**: `python3 -c "os.remove('./a/b/c/d/e/f/g.txt')"`
**Expected**: Should work
**Actual**: Regex extracts `./a/b/c/d/e/f/g.txt`. Path-likeness: has `/` so passes. No glob chars, no interpolation markers, not a URL, not a MIME type. `Path('./a/b/c/d/e/f/g.txt')` is relative, resolved against `project_dir`. `is_within_project()` passes.
**Verdict**: PASS

## Edge Case 8: Perl -e payload
**Input**: `perl -e "unlink('./temp.txt')"`
**Expected**: `extract_interpreter_payload` handles perl
**Actual**: `_INTERPRETER_PREFIXES` matches `perl `. `re.search(r'(?:^|\s)(-[ce])\s+', rest)` finds `-e`. Payload `unlink('./temp.txt')` is extracted. `_QUOTED_LITERAL_RE` finds `./temp.txt`. `check_interpreter_payload()` detects `unlink` via `(?<!\.)\\bunlink\\b`. Both extraction and detection work.
**Verdict**: PASS

## Edge Case 9: Ruby -e payload
**Input**: `ruby -e "File.delete('./temp.txt')"`
**Expected**: Handles ruby
**Actual**: `_INTERPRETER_PREFIXES` matches `ruby `. `-e` flag found. Payload extracted. `_QUOTED_LITERAL_RE` finds `./temp.txt`. `check_interpreter_payload()` detects `File.delete`. Works correctly.
**Verdict**: PASS

## Edge Case 10: Multiple interpreter flags
**Input**: `python3 -B -u -c "os.remove('./temp.txt')"`
**Expected**: `-c` is found despite preceding flags
**Actual**: `_INTERPRETER_PREFIXES` matches `python3 `. `rest = '-B -u -c "os.remove(\'./temp.txt\')"'`. `re.search(r'(?:^|\s)(-[ce])\s+', rest)` scans the full `rest` string and finds ` -c ` at the correct position. Payload is extracted correctly.
**Verdict**: PASS

## Edge Case 11: Payload with no quotes at all
**Input**: `python3 -c os.remove(path)`
**Expected**: No quoted strings found, returns empty
**Actual**: `extract_interpreter_payload()` returns `'os.remove(path)'` via the unquoted branch (line 961). `_QUOTED_LITERAL_RE.finditer('os.remove(path)')` finds 0 matches. Returns `[]`.
**Verdict**: PASS

## Edge Case 12: Single character directory path (`./`)
**Input**: `python3 -c "os.remove('./')"`
**Expected**: Starts with `.` but is just the directory
**Actual**: Regex extracts `./`. Path-likeness: has `/` so passes. `Path('./')` is relative, resolved to `project_dir / './'` = `project_dir`. `is_within_project()` returns True. Same concern as Edge Case 4 -- resolves to project root.
**Verdict**: CONCERN -- Same as Edge Case 4. The `./` directory path resolves to project root and would be returned as a valid path.

## Edge Case 13: Newlines in payload
**Input**: `python3 -c "import os\nos.remove('./f.txt')"`
**Expected**: Handles embedded newlines
**Actual**: Two sub-cases: (a) Literal `\n` in the command string (backslash-n): `extract_interpreter_payload()` extracts the full payload. `_QUOTED_LITERAL_RE` handles `\n` as an escaped character inside the payload regex. (b) Actual newline character: `_QUOTED_LITERAL_RE` uses `[^"\\]*` which does NOT exclude newlines by default (Python regex `.` doesn't match newlines, but character classes like `[^"\\]` DO match newlines). So the regex works across newlines. Tested: `./f.txt` is extracted correctly in both cases.
**Verdict**: PASS

## Edge Case 14: Empty payload
**Input**: `python3 -c ""`
**Expected**: Empty string, regex finds no literals
**Actual**: `extract_interpreter_payload()` handles this: `payload_start = '""'`, starts with `"`, `_find_closing_quote` finds closing quote at index 1, returns `payload_start[1:1]` = `""` (empty string). `_QUOTED_LITERAL_RE.finditer("")` yields 0 matches. Returns `[]`.
**Verdict**: PASS

## Edge Case 15: `is_within_project()` with unresolved path
**Input**: Path to a file that doesn't exist
**Expected**: `path.resolve()` should still work
**Actual**: `is_within_project()` (line 1548-1552) calls `path.resolve()` which in Python 3.6+ uses `strict=False` by default. For non-existent paths, `resolve()` resolves as much as possible and leaves the rest as-is. For example, `Path('/tmp/proj/nonexistent/deep/file.txt').resolve()` returns the same path with symlinks resolved in existing prefixes. Since the non-existent suffix stays under the project directory, `relative_to()` succeeds. This is correct behavior -- the path doesn't need to exist for boundary checking.
**Verdict**: PASS

## Edge Case 16: `all_paths.extend(sub_paths)` double-counting
**Input**: Any interpreter command where F1 fires and resolves paths
**Expected**: No double-counting
**Actual**: Line 1911: `sub_paths = paths + redir_paths` (for this sub_cmd). Line 1912: `all_paths.extend(sub_paths)`. The F1 block at line 1917 only fires when `not sub_paths` (i.e., `sub_paths` is empty). So line 1912 extended `all_paths` with `[]` (no-op). Then line 1930-1931: `sub_paths = interp_paths; all_paths.extend(sub_paths)`. This extends `all_paths` with the interpreter paths exactly once. **No double-counting occurs** because the initial `sub_paths` was empty.
**Verdict**: PASS -- The logic is correct. `all_paths.extend([])` at line 1912 is a no-op, and the interpreter paths are added exactly once at line 1931.

---

## Additional Finding A: MIME type filter causes false negatives on directory paths
**Input**: `python3 -c "shutil.rmtree('src/utils')"`
**Expected**: `src/utils` extracted as a valid path
**Actual**: The MIME type filter at lines 1301-1305 checks: `literal.count('/') == 1 and not literal.startswith('.') and not literal.startswith('/') and '.' not in literal`. The path `src/utils` has 1 slash, doesn't start with `.` or `/`, and contains no dots. It matches ALL conditions and is **incorrectly filtered as a MIME type**. Same for `build/output`, `temp/cache`, `data/raw`, and any `dir/subdir` path without dots or leading `.`/`/`.
**Verdict**: BUG (false negative) -- Valid directory paths like `src/utils`, `build/output`, `temp/cache` are silently dropped by the MIME type filter. This means `python3 -c "shutil.rmtree('src/utils')"` would have its path rejected, causing F1 to fire an ASK prompt (fail-closed, not fail-open), but the path information is lost. The MIME filter needs a more precise heuristic, e.g., checking against a known MIME type list or requiring no `/` in the first component.

## Additional Finding B: `check_interpreter_payload` gates F1 interpreter path on destructive APIs only
**Input**: `python3 -c "open('./data.csv', 'w').write('')"` (write, not delete)
**Expected**: F1 should attempt interpreter path resolution for write operations too
**Actual**: `is_write_command()` returns True for this command. `sub_paths` is empty (no shell-level path args). F1 block fires at line 1917. `check_interpreter_payload()` (line 1922) checks for `_DESTRUCTIVE_API_PATTERN` which only includes delete-class operations (os.remove, shutil.rmtree, etc.). `open(..., 'w')` is NOT in `_DESTRUCTIVE_APIS`. So `check_interpreter_payload()` returns `(False, "")`. The F1 block goes to `else` (line 1951) and fires standard F1 ASK: "Detected write but could not resolve target paths". **The interpreter path extraction is never attempted** even though `extract_paths_from_interpreter_payload()` could have resolved `./data.csv`.
**Verdict**: CONCERN -- The F1 enrichment only fires for interpreter commands with destructive APIs. Write-class interpreter commands (open, write, chmod) fall through to the generic F1 ASK without attempting path resolution. This is a design limitation, not a bug, since the fail-closed ASK still protects. But it means Phase 2 doesn't reduce false F1 ASKs for write-class interpreter commands. The `check_interpreter_payload` function name is misleading in this context -- it checks for destructive APIs, not just whether it's an interpreter command.

## Additional Finding C: `_INTERPRETER_PREFIXES` regex has a minor anchoring issue
**Input**: `notpython3 -c "os.remove('./f.txt')"`
**Expected**: Should NOT match (not a real interpreter)
**Actual**: `_INTERPRETER_PREFIXES` uses `(?:^|[\s;|&])` as the left anchor. For `notpython3`, the regex uses `search()` and finds `python3` embedded within `notpython3`. However, the alternation `(?:^|[\s;|&])` requires the match to start at the beginning of string or after a whitespace/shell metachar. `notpython3` starts at `^`, but the pattern is `(?:^|[\s;|&])(?:/[\w./]*)?(?:py|python...)`. The `^` anchor matches at position 0, the optional path prefix `(?:/[\w./]*)?` matches nothing, then `python3` must match at position 0 -- but position 0 is `n`, not `p`. So it tries position 3 (`p`), but position 3 is not preceded by `^` or `[\s;|&]`. Wait -- `search()` tries every position. At position 3, `[\s;|&]` doesn't match `t`. At no position does the full pattern match.
**Verdict**: PASS -- The left anchor correctly prevents matching `python3` inside other words. Tested more carefully: `notpython3` does NOT match because no position satisfies both the left anchor and the interpreter name.

---

## Summary

**16 primary edge cases + 3 additional findings = 19 total items**

| Verdict | Count | Items |
|---------|-------|-------|
| PASS | 14 | 1, 3, 5, 7, 8, 9, 10, 11, 13, 14, 15, 16, C |
| BUG | 2 | 2 (silent drop of out-of-project paths), A (MIME filter false negatives) |
| CONCERN | 3 | 4/12 (dot/slash paths resolve to project root), 6 (escape char mismatch), B (write-class interpreter commands skip path resolution) |

### Critical Bug: Edge Case 2 -- Silent drop of out-of-project paths

When `extract_paths_from_interpreter_payload()` returns a mix of in-project and out-of-project paths, only the in-project paths are returned. The F1 block sees `interp_paths` as truthy and skips the ASK. This means an attacker can include an innocuous in-project path alongside a malicious out-of-project path to suppress the F1 ASK entirely.

**Recommended fix**: Track rejected-out-of-project count in `extract_paths_from_interpreter_payload()`. If any literals resolved to paths outside the project boundary, either:
(a) Return `[]` to force F1 ASK (most conservative), or
(b) Return the valid paths but also return a flag indicating some paths were rejected, so the F1 block can still fire an ASK alongside the path validation.

### Bug: Additional Finding A -- MIME type filter

The MIME type heuristic (`count('/') == 1 and '.' not in literal`) incorrectly filters valid directory paths like `src/utils`. This is fail-closed (F1 ASK fires) but means the Phase 2 optimization fails to reduce false prompts for a common path pattern.

**Recommended fix**: Replace the MIME heuristic with a positive match against common MIME type patterns (e.g., `re.match(r'^[a-z]+/[a-z][-a-z+.]*$', literal)`) rather than a negative exclusion of path-like strings.
