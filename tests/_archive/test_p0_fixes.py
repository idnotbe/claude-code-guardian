#!/usr/bin/env python3
"""Verification tests for P0 fixes."""

import re
import time
import json
import sys


def test_p0_1_redos():
    """P0-1: Verify eval pattern no longer has ReDoS."""
    # Read the actual pattern from config
    config_path = "/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json"
    with open(config_path) as f:
        config = json.load(f)

    eval_pattern = None
    for p in config["bashToolPatterns"]["block"]:
        if "eval" in p["pattern"].lower():
            eval_pattern = p["pattern"]
            break

    assert eval_pattern is not None, "Could not find eval pattern in config"
    print(f"Eval pattern: {eval_pattern}")

    # Verify no ReDoS: 20k char input must complete in <100ms
    bad_input = "eval " + "x" * 20000
    start = time.time()
    re.search(eval_pattern, bad_input)
    elapsed_ms = (time.time() - start) * 1000
    print(f"  20k char test: {elapsed_ms:.1f}ms (must be <100ms)")
    assert elapsed_ms < 100, f"ReDoS still present: {elapsed_ms:.1f}ms"

    # Verify pattern still matches intended inputs
    test_cases = [
        ('eval "' + 'rm' + ' file"', True, "double-quoted deletion"),
        ("eval '" + "rm" + " file'", True, "single-quoted deletion"),
        ("eval " + "rm" + " file", True, "unquoted deletion"),
        ("EVAL " + "rm" + "dir /tmp", True, "case insensitive"),
        ("echo hello", False, "benign command"),
    ]

    for cmd, should_match, desc in test_cases:
        result = re.search(eval_pattern, cmd)
        matched = result is not None
        status = "PASS" if matched == should_match else "FAIL"
        print(f"  {status}: '{cmd}' -> match={matched} (expected={should_match}) [{desc}]")
        assert matched == should_match, f"Pattern test failed: {desc}"

    print("P0-1: ALL TESTS PASS\n")


def test_p0_2_exact_match_action():
    """P0-2: Verify exactMatchAction is 'ask' not 'deny'."""
    config_path = "/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json"
    with open(config_path) as f:
        config = json.load(f)

    action = config["bashPathScan"]["exactMatchAction"]
    print(f"exactMatchAction: {action}")
    assert action == "ask", f"Expected 'ask', got '{action}'"
    print("P0-2: PASS\n")


def test_p0_3_verdict_fail_close():
    """P0-3: Verify unknown verdicts fail closed (treated as deny)."""
    # Read the actual code to verify
    py_path = "/home/idnotbe/projects/claude-code-guardian/hooks/scripts/bash_guardian.py"
    with open(py_path) as f:
        content = f.read()

    # Verify the .get() default uses _FAIL_CLOSE_PRIORITY (not 0)
    assert "_FAIL_CLOSE_PRIORITY" in content, "missing _FAIL_CLOSE_PRIORITY constant"
    assert ".get(candidate[0], _FAIL_CLOSE_PRIORITY)" in content, "candidate not using _FAIL_CLOSE_PRIORITY"
    assert ".get(current[0], _FAIL_CLOSE_PRIORITY)" in content, "current not using _FAIL_CLOSE_PRIORITY"
    assert ".get(candidate[0], 0)" not in content, "old default 0 still present for candidate"
    assert ".get(current[0], 0)" not in content, "old default 0 still present for current"
    assert "_FAIL_CLOSE_PRIORITY = max(_VERDICT_PRIORITY.values())" in content, "fail-close not derived from max"
    print("Code uses _FAIL_CLOSE_PRIORITY = max(_VERDICT_PRIORITY.values()) for fail-close")

    # Functional test: simulate the logic
    _VERDICT_PRIORITY = {"deny": 2, "ask": 1, "allow": 0}

    def _stronger_verdict(current, candidate):
        if _VERDICT_PRIORITY.get(candidate[0], 2) > _VERDICT_PRIORITY.get(current[0], 2):
            return candidate
        return current

    # Unknown verdict should beat allow (treated as deny-priority)
    r1 = _stronger_verdict(("allow", "ok"), ("unknown_garbage", "test"))
    print(f"  unknown vs allow -> {r1[0]} (expected: unknown wins)")
    assert r1 == ("unknown_garbage", "test")

    # Unknown verdict should tie with deny (deny kept as current)
    r2 = _stronger_verdict(("deny", "blocked"), ("unknown_garbage", "test"))
    print(f"  unknown vs deny -> {r2[0]} (expected: deny kept)")
    assert r2 == ("deny", "blocked")

    # Allow should not beat unknown
    r3 = _stronger_verdict(("unknown_garbage", "test"), ("allow", "ok"))
    print(f"  allow vs unknown -> {r3[0]} (expected: unknown kept)")
    assert r3 == ("unknown_garbage", "test")

    print("P0-3: ALL TESTS PASS\n")


if __name__ == "__main__":
    try:
        test_p0_1_redos()
        test_p0_2_exact_match_action()
        test_p0_3_verdict_fail_close()
        print("=" * 50)
        print("ALL P0 FIXES VERIFIED SUCCESSFULLY")
        print("=" * 50)
    except AssertionError as e:
        print(f"\nFAILURE: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
