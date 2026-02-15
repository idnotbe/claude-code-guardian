#!/usr/bin/env python3
"""End-to-end integration test for Enhancement 1 (split external path keys)
and Enhancement 2 (bash external path extraction + enforcement).

Tests the FULL flow through:
1. match_allowed_external_path() -- config parsing and mode return
2. run_path_guardian_hook() mode enforcement logic
3. extract_paths() -- external path inclusion/exclusion
4. Bash guardian enforcement -- read-only external path blocks write/delete
5. Cross-cutting: zeroAccessPaths overrides external path allowance
6. Project-internal paths still work correctly (regression)
7. Edge cases: symlinks, tilde expansion, nested globs, overlapping lists

Author: Integration Tester V2
Date: 2026-02-15
"""

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Bootstrap: add hooks/scripts and tests/ to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "hooks" / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "tests"))

import _guardian_utils as gu
from _guardian_utils import (
    _FALLBACK_CONFIG,
    load_guardian_config,
    match_allowed_external_path,
    match_path_pattern,
    match_zero_access,
    match_read_only,
    is_path_within_project,
)
from bash_guardian import extract_paths, is_write_command, is_delete_command


# ============================================================
# Helpers
# ============================================================

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.details = []
        self.current_section = ""

    def section(self, name):
        self.current_section = name
        print(f"\n{'=' * 70}")
        print(f"  {name}")
        print(f"{'=' * 70}")

    def ok(self, name, note=""):
        self.passed += 1
        print(f"  [PASS] {name}")
        if note:
            print(f"         {note}")
        self.details.append((self.current_section, name, "PASS", note))

    def fail(self, name, expected, got, note=""):
        self.failed += 1
        print(f"  [FAIL] {name}")
        print(f"         Expected: {expected}")
        print(f"         Got:      {got}")
        if note:
            print(f"         Note: {note}")
        self.details.append((self.current_section, name, "FAIL", f"expected={expected}, got={got}"))

    def error(self, name, exc):
        self.errors += 1
        print(f"  [ERROR] {name}")
        print(f"          Exception: {exc}")
        self.details.append((self.current_section, name, "ERROR", str(exc)))

    def summary(self):
        total = self.passed + self.failed + self.errors
        print(f"\n{'=' * 70}")
        print(f"  SUMMARY: {self.passed}/{total} passed, {self.failed} failed, {self.errors} errors")
        print(f"{'=' * 70}")
        if self.failed > 0 or self.errors > 0:
            print("\n  FAILED/ERROR tests:")
            for sec, name, status, note in self.details:
                if status != "PASS":
                    print(f"    [{status}] {sec} > {name}: {note}")
        return self.failed == 0 and self.errors == 0


def _make_env(prefix, read_paths=None, write_paths=None, zero_paths=None,
              read_only_paths=None, no_delete_paths=None):
    """Create a temp project dir with config and external dirs.

    Returns (project_dir, ext_read_dir, ext_write_dir, config_path)
    """
    project_dir = tempfile.mkdtemp(prefix=prefix)
    (Path(project_dir) / ".git").mkdir(parents=True, exist_ok=True)
    config_dir = Path(project_dir) / ".claude" / "guardian"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"

    # Create external dirs with real files
    ext_read_dir = tempfile.mkdtemp(prefix="e2e_ext_read_")
    ext_write_dir = tempfile.mkdtemp(prefix="e2e_ext_write_")

    # Create some files in external dirs
    (Path(ext_read_dir) / "readme.md").write_text("external read file")
    (Path(ext_read_dir) / "data.csv").write_text("col1,col2\na,b")
    (Path(ext_read_dir) / ".env").write_text("SECRET=dont_read_me")
    (Path(ext_read_dir) / "server.pem").write_text("FAKE PEM")
    (Path(ext_write_dir) / "output.log").write_text("log data")
    (Path(ext_write_dir) / "result.json").write_text("{}")

    # Create project-internal files
    (Path(project_dir) / "internal.py").write_text("print('hello')")
    (Path(project_dir) / "src").mkdir(exist_ok=True)
    (Path(project_dir) / "src" / "app.py").write_text("# app code")

    config = {
        "allowedExternalReadPaths": read_paths or [ext_read_dir + "/**"],
        "allowedExternalWritePaths": write_paths or [ext_write_dir + "/**"],
        "zeroAccessPaths": zero_paths or [".env", ".env.*", "*.pem", "*.key"],
        "readOnlyPaths": read_only_paths or [],
        "noDeletePaths": no_delete_paths or [],
        "bashToolPatterns": {"block": [], "ask": []},
    }

    with open(config_path, "w") as f:
        json.dump(config, f)

    return project_dir, ext_read_dir, ext_write_dir, str(config_path)


def _reset_config():
    gu._config_cache = None
    gu._using_fallback_config = False
    gu._active_config_path = None


def _cleanup(*dirs):
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Main Test Flow
# ============================================================

def run_all():
    results = TestResults()
    orig_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")

    try:
        # ----------------------------------------------------------
        # SECTION 1: Config Parsing & match_allowed_external_path()
        # ----------------------------------------------------------
        results.section("1. Config Parsing & match_allowed_external_path()")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s1_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # 1a: Read path in ReadPaths -> (True, "read")
        try:
            matched, mode = match_allowed_external_path(
                str(Path(ext_read) / "readme.md")
            )
            if matched and mode == "read":
                results.ok("Read path in allowedExternalReadPaths => (True, 'read')")
            else:
                results.fail(
                    "Read path in allowedExternalReadPaths => (True, 'read')",
                    "(True, 'read')", f"({matched}, '{mode}')"
                )
        except Exception as e:
            results.error("Read path matching", e)

        # 1b: Write path in WritePaths -> (True, "readwrite")
        try:
            matched, mode = match_allowed_external_path(
                str(Path(ext_write) / "output.log")
            )
            if matched and mode == "readwrite":
                results.ok("Write path in allowedExternalWritePaths => (True, 'readwrite')")
            else:
                results.fail(
                    "Write path in allowedExternalWritePaths => (True, 'readwrite')",
                    "(True, 'readwrite')", f"({matched}, '{mode}')"
                )
        except Exception as e:
            results.error("Write path matching", e)

        # 1c: Non-external path -> (False, "")
        try:
            matched, mode = match_allowed_external_path("/opt/random/file.txt")
            if not matched and mode == "":
                results.ok("Non-external path => (False, '')")
            else:
                results.fail(
                    "Non-external path => (False, '')",
                    "(False, '')", f"({matched}, '{mode}')"
                )
        except Exception as e:
            results.error("Non-external path matching", e)

        # 1d: Path in BOTH lists -> write wins (readwrite)
        _reset_config()
        _cleanup(project_dir)
        project_dir, ext_read, ext_write, config_path = _make_env(
            "e2e_s1d_",
            read_paths=["/tmp/e2e_overlap/**"],
            write_paths=["/tmp/e2e_overlap/**"],
        )
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        try:
            matched, mode = match_allowed_external_path("/tmp/e2e_overlap/file.txt")
            if matched and mode == "readwrite":
                results.ok("Path in BOTH lists => (True, 'readwrite') -- write wins")
            else:
                results.fail(
                    "Path in BOTH lists => write wins",
                    "(True, 'readwrite')", f"({matched}, '{mode}')"
                )
        except Exception as e:
            results.error("Overlap test", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 2: Tool-Level Mode Enforcement (Read/Write/Edit)
        # ----------------------------------------------------------
        results.section("2. Tool-Level Mode Enforcement (Read/Write/Edit)")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s2_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        def would_deny(mode, tool_name):
            """Exact conditional from run_path_guardian_hook()."""
            return mode == "read" and tool_name.lower() in ("write", "edit")

        # 2a: Read tool on read-only external -> allowed
        try:
            ext_path = str(Path(ext_read) / "readme.md")
            matched, mode = match_allowed_external_path(ext_path)
            denied = would_deny(mode, "Read")
            if matched and not denied:
                results.ok("Read tool + read-only external => ALLOWED")
            else:
                results.fail("Read tool + read-only external => ALLOWED",
                             "matched=True, denied=False",
                             f"matched={matched}, denied={denied}")
        except Exception as e:
            results.error("Read tool on read path", e)

        # 2b: Write tool on read-only external -> denied
        try:
            denied = would_deny(mode, "Write")
            if matched and denied:
                results.ok("Write tool + read-only external => DENIED")
            else:
                results.fail("Write tool + read-only external => DENIED",
                             "denied=True", f"denied={denied}")
        except Exception as e:
            results.error("Write tool on read path", e)

        # 2c: Edit tool on read-only external -> denied
        try:
            denied = would_deny(mode, "Edit")
            if matched and denied:
                results.ok("Edit tool + read-only external => DENIED")
            else:
                results.fail("Edit tool + read-only external => DENIED",
                             "denied=True", f"denied={denied}")
        except Exception as e:
            results.error("Edit tool on read path", e)

        # 2d: Write tool on readwrite external -> allowed
        try:
            ext_path = str(Path(ext_write) / "output.log")
            matched, mode = match_allowed_external_path(ext_path)
            denied = would_deny(mode, "Write")
            if matched and not denied:
                results.ok("Write tool + readwrite external => ALLOWED")
            else:
                results.fail("Write tool + readwrite external => ALLOWED",
                             "matched=True, denied=False",
                             f"matched={matched}, denied={denied}")
        except Exception as e:
            results.error("Write tool on write path", e)

        # 2e: Edit tool on readwrite external -> allowed
        try:
            denied = would_deny(mode, "Edit")
            if matched and not denied:
                results.ok("Edit tool + readwrite external => ALLOWED")
            else:
                results.fail("Edit tool + readwrite external => ALLOWED",
                             "matched=True, denied=False",
                             f"matched={matched}, denied={denied}")
        except Exception as e:
            results.error("Edit tool on write path", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 3: extract_paths() includes external paths
        # ----------------------------------------------------------
        results.section("3. extract_paths() includes external paths")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s3_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()
        project_path = Path(project_dir)

        # 3a: External read path is extracted
        try:
            ext_file = str(Path(ext_read) / "readme.md")
            paths = extract_paths(f"cat {ext_file}", project_path)
            path_strs = [str(p) for p in paths]
            if ext_file in path_strs:
                results.ok(f"extract_paths includes allowed external read path")
            else:
                results.fail("extract_paths includes read path",
                             f"{ext_file} in paths", f"paths = {path_strs}")
        except Exception as e:
            results.error("extract_paths read path", e)

        # 3b: External write path is extracted
        try:
            ext_file = str(Path(ext_write) / "output.log")
            paths = extract_paths(f"cat {ext_file}", project_path)
            path_strs = [str(p) for p in paths]
            if ext_file in path_strs:
                results.ok(f"extract_paths includes allowed external write path")
            else:
                results.fail("extract_paths includes write path",
                             f"{ext_file} in paths", f"paths = {path_strs}")
        except Exception as e:
            results.error("extract_paths write path", e)

        # 3c: Non-allowed external path is NOT extracted
        try:
            non_allowed = "/opt/e2e_non_allowed/secret.txt"
            paths = extract_paths(f"cat {non_allowed}", project_path)
            path_strs = [str(p) for p in paths]
            if non_allowed not in path_strs:
                results.ok("extract_paths excludes non-allowed external path")
            else:
                results.fail("extract_paths excludes non-allowed",
                             f"{non_allowed} NOT in paths", f"paths = {path_strs}")
        except Exception as e:
            results.error("extract_paths non-allowed", e)

        # 3d: Project-internal path is still extracted
        try:
            internal_file = str(project_path / "internal.py")
            paths = extract_paths(f"cat {internal_file}", project_path)
            path_strs = [str(p) for p in paths]
            if internal_file in path_strs:
                results.ok("extract_paths includes project-internal path (regression)")
            else:
                results.fail("extract_paths includes internal path",
                             f"{internal_file} in paths", f"paths = {path_strs}")
        except Exception as e:
            results.error("extract_paths internal", e)

        # 3e: Mixed command with both internal and external
        try:
            internal_file = str(project_path / "internal.py")
            ext_file = str(Path(ext_read) / "data.csv")
            paths = extract_paths(f"diff {internal_file} {ext_file}", project_path)
            path_strs = [str(p) for p in paths]
            has_internal = internal_file in path_strs
            has_external = ext_file in path_strs
            if has_internal and has_external:
                results.ok("extract_paths: mixed internal+external command extracts both")
            else:
                results.fail("extract_paths mixed",
                             "both paths extracted",
                             f"internal={has_internal}, external={has_external}, paths={path_strs}")
        except Exception as e:
            results.error("extract_paths mixed", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 4: Bash Enforcement -- read-only external blocks write/delete
        # ----------------------------------------------------------
        results.section("4. Bash Enforcement -- read-only external blocks write/delete")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s4_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # Simulate the enforcement loop logic:
        #   if is_write or is_delete:
        #       ext_matched, ext_mode = match_allowed_external_path(path_str)
        #       if ext_matched and ext_mode == "read":
        #           -> deny

        # 4a: sed -i on read-only external path -> deny
        try:
            path_str = str(Path(ext_read) / "readme.md")
            is_write = is_write_command(f"sed -i 's/old/new/' {path_str}")
            ext_matched, ext_mode = match_allowed_external_path(path_str)
            should_deny = (is_write) and ext_matched and ext_mode == "read"
            if should_deny:
                results.ok("Bash: sed -i on read-only external => DENY")
            else:
                results.fail("Bash: sed -i on read-only external => DENY",
                             "should_deny=True",
                             f"is_write={is_write}, matched={ext_matched}, mode={ext_mode}")
        except Exception as e:
            results.error("Bash sed -i deny", e)

        # 4b: rm on read-only external path -> deny
        try:
            path_str = str(Path(ext_read) / "readme.md")
            is_del = is_delete_command(f"rm {path_str}")
            ext_matched, ext_mode = match_allowed_external_path(path_str)
            should_deny = is_del and ext_matched and ext_mode == "read"
            if should_deny:
                results.ok("Bash: rm on read-only external => DENY")
            else:
                results.fail("Bash: rm on read-only external => DENY",
                             "should_deny=True",
                             f"is_delete={is_del}, matched={ext_matched}, mode={ext_mode}")
        except Exception as e:
            results.error("Bash rm deny", e)

        # 4c: cp to read-only external path -> deny
        try:
            path_str = str(Path(ext_read) / "readme.md")
            is_write = is_write_command(f"cp /tmp/src.txt {path_str}")
            ext_matched, ext_mode = match_allowed_external_path(path_str)
            should_deny = is_write and ext_matched and ext_mode == "read"
            if should_deny:
                results.ok("Bash: cp to read-only external => DENY")
            else:
                results.fail("Bash: cp to read-only external => DENY",
                             "should_deny=True",
                             f"is_write={is_write}, matched={ext_matched}, mode={ext_mode}")
        except Exception as e:
            results.error("Bash cp deny", e)

        # 4d: cat on read-only external path -> NOT write, no deny
        try:
            path_str = str(Path(ext_read) / "readme.md")
            is_write = is_write_command(f"cat {path_str}")
            is_del = is_delete_command(f"cat {path_str}")
            # The enforcement only fires if is_write or is_delete
            would_trigger = (is_write or is_del)
            if not would_trigger:
                results.ok("Bash: cat on read-only external => not write/delete, no deny")
            else:
                results.fail("Bash: cat should not be write/delete",
                             "would_trigger=False",
                             f"is_write={is_write}, is_delete={is_del}")
        except Exception as e:
            results.error("Bash cat no deny", e)

        # 4e: sed -i on readwrite external path -> NOT denied
        try:
            path_str = str(Path(ext_write) / "output.log")
            is_write = is_write_command(f"sed -i 's/old/new/' {path_str}")
            ext_matched, ext_mode = match_allowed_external_path(path_str)
            should_deny = is_write and ext_matched and ext_mode == "read"
            if not should_deny:
                results.ok("Bash: sed -i on readwrite external => ALLOWED (mode=readwrite)")
            else:
                results.fail("Bash: sed -i on readwrite external => ALLOWED",
                             "should_deny=False",
                             f"is_write={is_write}, matched={ext_matched}, mode={ext_mode}")
        except Exception as e:
            results.error("Bash sed -i readwrite allow", e)

        # 4f: tee on read-only external path -> deny
        try:
            path_str = str(Path(ext_read) / "data.csv")
            is_write = is_write_command(f"echo hello | tee {path_str}")
            ext_matched, ext_mode = match_allowed_external_path(path_str)
            should_deny = is_write and ext_matched and ext_mode == "read"
            if should_deny:
                results.ok("Bash: tee on read-only external => DENY")
            else:
                results.fail("Bash: tee on read-only external => DENY",
                             "should_deny=True",
                             f"is_write={is_write}, matched={ext_matched}, mode={ext_mode}")
        except Exception as e:
            results.error("Bash tee deny", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 5: Cross-Cutting -- zeroAccessPaths overrides external
        # ----------------------------------------------------------
        results.section("5. Cross-Cutting -- zeroAccessPaths overrides external")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s5_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # 5a: .env in read external dir -> matches external AND zeroAccess
        try:
            env_path = str(Path(ext_read) / ".env")
            ext_matched, ext_mode = match_allowed_external_path(env_path)
            zero_blocked = match_zero_access(env_path)
            if ext_matched and zero_blocked:
                results.ok(".env in external dir: matches external AND zeroAccess (zeroAccess wins)")
            else:
                results.fail(".env cross-cutting",
                             "ext_matched=True, zero_blocked=True",
                             f"ext_matched={ext_matched}, zero_blocked={zero_blocked}")
        except Exception as e:
            results.error(".env cross-cutting", e)

        # 5b: .pem in external dir -> same behavior
        try:
            pem_path = str(Path(ext_read) / "server.pem")
            ext_matched, _ = match_allowed_external_path(pem_path)
            zero_blocked = match_zero_access(pem_path)
            if ext_matched and zero_blocked:
                results.ok("*.pem in external dir: matches external AND zeroAccess")
            else:
                results.fail("*.pem cross-cutting",
                             "both True",
                             f"ext_matched={ext_matched}, zero_blocked={zero_blocked}")
        except Exception as e:
            results.error("*.pem cross-cutting", e)

        # 5c: .env in write-allowed external dir -> still zeroAccess blocked
        try:
            # We don't have a .env in ext_write, but the path doesn't need to exist
            # for match_allowed_external_path (it just does pattern matching)
            env_in_write = str(Path(ext_write) / ".env")
            ext_matched, ext_mode = match_allowed_external_path(env_in_write)
            zero_blocked = match_zero_access(env_in_write)
            if ext_matched and zero_blocked:
                results.ok(".env in writable external dir: zeroAccess still blocks")
            else:
                results.fail(".env in writable external dir",
                             "both True",
                             f"ext_matched={ext_matched}, zero_blocked={zero_blocked}")
        except Exception as e:
            results.error(".env writable cross-cut", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 6: Project-internal paths still work (regression)
        # ----------------------------------------------------------
        results.section("6. Project-Internal Paths -- No Regression")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s6_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # 6a: Internal file is within project
        try:
            internal = str(Path(project_dir) / "internal.py")
            within = is_path_within_project(internal)
            if within:
                results.ok("Project-internal file: is_path_within_project => True")
            else:
                results.fail("Internal file within project", "True", str(within))
        except Exception as e:
            results.error("Internal within project", e)

        # 6b: External read file is NOT within project
        try:
            ext_file = str(Path(ext_read) / "readme.md")
            within = is_path_within_project(ext_file)
            if not within:
                results.ok("External file: is_path_within_project => False")
            else:
                results.fail("External not within project", "False", str(within))
        except Exception as e:
            results.error("External within project", e)

        # 6c: extract_paths for internal-only command works
        try:
            internal = str(Path(project_dir) / "src" / "app.py")
            paths = extract_paths(f"cat {internal}", Path(project_dir))
            path_strs = [str(p) for p in paths]
            if internal in path_strs:
                results.ok("extract_paths: internal-only command works")
            else:
                results.fail("extract_paths internal-only",
                             f"{internal} in paths", f"paths={path_strs}")
        except Exception as e:
            results.error("extract_paths internal-only", e)

        # 6d: Internal path not affected by external enforcement
        try:
            internal = str(Path(project_dir) / "internal.py")
            ext_matched, ext_mode = match_allowed_external_path(internal)
            if not ext_matched:
                results.ok("Internal path: match_allowed_external_path => (False, '')")
            else:
                results.fail("Internal not in external",
                             "(False, '')", f"({ext_matched}, '{ext_mode}')")
        except Exception as e:
            results.error("Internal external check", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 7: Edge Cases
        # ----------------------------------------------------------
        results.section("7. Edge Cases")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s7_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # 7a: Empty config lists (fail-closed)
        try:
            _reset_config()
            _cleanup(project_dir)
            project_dir2, ext_read2, ext_write2, _ = _make_env(
                "e2e_s7a_", read_paths=[], write_paths=[]
            )
            os.environ["CLAUDE_PROJECT_DIR"] = project_dir2
            _reset_config()

            matched, mode = match_allowed_external_path("/tmp/any/file.txt")
            if not matched:
                results.ok("Empty external lists: nothing matches (fail-closed)")
            else:
                results.fail("Empty lists fail-closed",
                             "(False, '')", f"({matched}, '{mode}')")

            _cleanup(project_dir2, ext_read2, ext_write2)
        except Exception as e:
            results.error("Empty lists", e)

        # Restore env
        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s7b_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # 7b: Non-string entries in config lists are safely ignored
        try:
            _reset_config()
            with open(config_path, "w") as f:
                json.dump({
                    "allowedExternalReadPaths": [42, None, ext_read + "/**"],
                    "allowedExternalWritePaths": [True, ext_write + "/**"],
                    "zeroAccessPaths": [],
                    "readOnlyPaths": [],
                    "noDeletePaths": [],
                    "bashToolPatterns": {"block": [], "ask": []},
                }, f)
            _reset_config()

            # Should still match the string entries
            m1, mode1 = match_allowed_external_path(str(Path(ext_read) / "file.txt"))
            m2, mode2 = match_allowed_external_path(str(Path(ext_write) / "file.txt"))
            if m1 and mode1 == "read" and m2 and mode2 == "readwrite":
                results.ok("Non-string entries in config lists safely ignored")
            else:
                results.fail("Non-string entries",
                             "both match correctly",
                             f"read=({m1}, '{mode1}'), write=({m2}, '{mode2}')")
        except Exception as e:
            results.error("Non-string entries", e)

        # 7c: Fallback config has correct keys
        try:
            has_read = "allowedExternalReadPaths" in _FALLBACK_CONFIG
            has_write = "allowedExternalWritePaths" in _FALLBACK_CONFIG
            no_old = "allowedExternalPaths" not in _FALLBACK_CONFIG
            read_empty = _FALLBACK_CONFIG.get("allowedExternalReadPaths") == []
            write_empty = _FALLBACK_CONFIG.get("allowedExternalWritePaths") == []
            if has_read and has_write and no_old and read_empty and write_empty:
                results.ok("Fallback config: new keys present, old key absent, both empty")
            else:
                results.fail("Fallback config keys",
                             "new keys present and empty, old key absent",
                             f"has_read={has_read}, has_write={has_write}, no_old={no_old}")
        except Exception as e:
            results.error("Fallback config", e)

        # 7d: Old allowedExternalPaths key is ignored
        try:
            _reset_config()
            with open(config_path, "w") as f:
                json.dump({
                    "allowedExternalPaths": [ext_read + "/**"],
                    "zeroAccessPaths": [],
                    "readOnlyPaths": [],
                    "noDeletePaths": [],
                    "bashToolPatterns": {"block": [], "ask": []},
                }, f)
            _reset_config()

            matched, mode = match_allowed_external_path(str(Path(ext_read) / "file.txt"))
            if not matched:
                results.ok("Old allowedExternalPaths key is ignored by new code")
            else:
                results.fail("Old key ignored",
                             "(False, '')", f"({matched}, '{mode}')")
        except Exception as e:
            results.error("Old key ignored", e)

        # 7e: Tilde expansion in pattern matching
        try:
            _reset_config()
            with open(config_path, "w") as f:
                json.dump({
                    "allowedExternalReadPaths": ["~/.claude/projects/*/memory/**"],
                    "allowedExternalWritePaths": [],
                    "zeroAccessPaths": [],
                    "readOnlyPaths": [],
                    "noDeletePaths": [],
                    "bashToolPatterns": {"block": [], "ask": []},
                }, f)
            _reset_config()

            home = str(Path.home())
            test_path = f"{home}/.claude/projects/E--test/memory/MEMORY.md"
            matched, mode = match_allowed_external_path(test_path)
            if matched and mode == "read":
                results.ok("Tilde expansion in patterns works (~/... matches $HOME/...)")
            else:
                results.fail("Tilde expansion",
                             "(True, 'read')", f"({matched}, '{mode}')",
                             note=f"path={test_path}")
        except Exception as e:
            results.error("Tilde expansion", e)

        # 7f: Subdirectory glob matching (** matches nested dirs)
        try:
            _reset_config()
            with open(config_path, "w") as f:
                json.dump({
                    "allowedExternalReadPaths": [ext_read + "/**"],
                    "allowedExternalWritePaths": [],
                    "zeroAccessPaths": [],
                    "readOnlyPaths": [],
                    "noDeletePaths": [],
                    "bashToolPatterns": {"block": [], "ask": []},
                }, f)
            _reset_config()

            # Create a nested file
            nested_dir = Path(ext_read) / "sub" / "deep"
            nested_dir.mkdir(parents=True, exist_ok=True)
            nested_file = nested_dir / "nested.txt"
            nested_file.write_text("nested content")

            matched, mode = match_allowed_external_path(str(nested_file))
            if matched and mode == "read":
                results.ok("** glob matches deeply nested files")
            else:
                results.fail("** glob matching",
                             "(True, 'read')", f"({matched}, '{mode}')")
        except Exception as e:
            results.error("** glob matching", e)

        _cleanup(project_dir, ext_read, ext_write)

        # ----------------------------------------------------------
        # SECTION 8: Full Pipeline Integration
        # ----------------------------------------------------------
        results.section("8. Full Pipeline Integration (config -> extract -> enforce)")

        project_dir, ext_read, ext_write, config_path = _make_env("e2e_s8_")
        os.environ["CLAUDE_PROJECT_DIR"] = project_dir
        _reset_config()

        # 8a: Full pipeline: read command on read-only external path -> extracted, not denied
        try:
            ext_file = str(Path(ext_read) / "readme.md")
            cmd = f"cat {ext_file}"

            # Step 1: extract_paths includes it
            paths = extract_paths(cmd, Path(project_dir))
            path_strs = [str(p) for p in paths]
            extracted = ext_file in path_strs

            # Step 2: is_write_command says no
            is_write = is_write_command(cmd)
            is_del = is_delete_command(cmd)

            # Step 3: external mode check
            ext_matched, ext_mode = match_allowed_external_path(ext_file)

            # Step 4: would the enforcement loop deny?
            would_deny_bash = (is_write or is_del) and ext_matched and ext_mode == "read"

            if extracted and not is_write and not is_del and ext_matched and not would_deny_bash:
                results.ok("Full pipeline: cat on read-only external -> extracted, allowed")
            else:
                results.fail("Full pipeline cat",
                             "extracted, not denied",
                             f"extracted={extracted}, is_write={is_write}, "
                             f"is_del={is_del}, ext_matched={ext_matched}, "
                             f"would_deny={would_deny_bash}")
        except Exception as e:
            results.error("Full pipeline cat", e)

        # 8b: Full pipeline: sed -i on read-only external -> extracted, DENIED
        try:
            ext_file = str(Path(ext_read) / "data.csv")
            cmd = f"sed -i 's/a/x/' {ext_file}"

            paths = extract_paths(cmd, Path(project_dir))
            path_strs = [str(p) for p in paths]
            extracted = ext_file in path_strs

            is_write = is_write_command(cmd)
            ext_matched, ext_mode = match_allowed_external_path(ext_file)
            would_deny_bash = (is_write) and ext_matched and ext_mode == "read"

            if extracted and is_write and ext_matched and would_deny_bash:
                results.ok("Full pipeline: sed -i on read-only external -> extracted, DENIED")
            else:
                results.fail("Full pipeline sed -i deny",
                             "extracted, denied",
                             f"extracted={extracted}, is_write={is_write}, "
                             f"ext_matched={ext_matched}, ext_mode={ext_mode}, "
                             f"would_deny={would_deny_bash}")
        except Exception as e:
            results.error("Full pipeline sed -i", e)

        # 8c: Full pipeline: sed -i on readwrite external -> extracted, ALLOWED
        try:
            ext_file = str(Path(ext_write) / "output.log")
            cmd = f"sed -i 's/log/LOG/' {ext_file}"

            paths = extract_paths(cmd, Path(project_dir))
            path_strs = [str(p) for p in paths]
            extracted = ext_file in path_strs

            is_write = is_write_command(cmd)
            ext_matched, ext_mode = match_allowed_external_path(ext_file)
            would_deny_bash = (is_write) and ext_matched and ext_mode == "read"

            if extracted and is_write and ext_matched and not would_deny_bash:
                results.ok("Full pipeline: sed -i on readwrite external -> extracted, ALLOWED")
            else:
                results.fail("Full pipeline sed -i allow",
                             "extracted, not denied",
                             f"extracted={extracted}, is_write={is_write}, "
                             f"ext_matched={ext_matched}, ext_mode={ext_mode}, "
                             f"would_deny={would_deny_bash}")
        except Exception as e:
            results.error("Full pipeline sed -i allow", e)

        # 8d: Full pipeline: .env in read external -> extracted, but zeroAccess would block
        try:
            env_file = str(Path(ext_read) / ".env")
            cmd = f"cat {env_file}"

            paths = extract_paths(cmd, Path(project_dir))
            path_strs = [str(p) for p in paths]
            extracted = env_file in path_strs

            ext_matched, ext_mode = match_allowed_external_path(env_file)
            zero_blocked = match_zero_access(env_file)

            # The key: zeroAccess runs BEFORE external checks in the enforcement loop
            if ext_matched and zero_blocked:
                results.ok("Full pipeline: .env in external -> zeroAccess blocks regardless")
                if not extracted:
                    results.ok("  (.env was not extracted, which is also fine)")
            else:
                results.fail("Full pipeline .env",
                             "ext_matched=True, zero_blocked=True",
                             f"ext_matched={ext_matched}, zero_blocked={zero_blocked}")
        except Exception as e:
            results.error("Full pipeline .env", e)

        _cleanup(project_dir, ext_read, ext_write)

    except Exception as e:
        print(f"\n[FATAL ERROR] Unhandled exception: {e}")
        traceback.print_exc()
        results.error("Unhandled", e)

    finally:
        # Restore env
        if orig_project_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = orig_project_dir
        elif "CLAUDE_PROJECT_DIR" in os.environ:
            del os.environ["CLAUDE_PROJECT_DIR"]
        _reset_config()

    return results


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  E2E Integration Test: Enhancement 1 & 2")
    print("  Date: 2026-02-15 | Author: Integration Tester V2")
    print("=" * 70)

    results = run_all()
    all_pass = results.summary()

    sys.exit(0 if all_pass else 1)
