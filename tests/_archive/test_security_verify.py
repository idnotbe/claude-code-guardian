#!/usr/bin/env python3
"""Security verification tests for guardian bash bypass implementation.

Run from: /home/idnotbe/projects/claude-code-guardian/
"""
import sys
sys.path.insert(0, "hooks/scripts")
from bash_guardian import split_commands, glob_to_literals, _stronger_verdict, _is_inside_quotes

def test_glob_to_literals():
    print("=== glob_to_literals tests ===")
    cases = [
        # (pattern, expected_empty, description)
        ("*.pem", False, "suffix .pem should produce literal"),
        ("*.p12", False, "suffix .p12 should produce literal"),
        ("*.pfx", False, "suffix .pfx should produce literal"),
        ("*.tfstate", False, "suffix .tfstate should produce literal"),
        ("*.tfstate.backup", False, "suffix .tfstate.backup should produce literal"),
        ("*.env", True, "generic *.env should return []"),
        ("*.key", True, "generic *.key should return []"),
        ("*.log", True, "generic *.log should return []"),
        ("*credentials*.json", True, "wildcard credentials should return []"),
        ("*serviceAccount*.json", True, "wildcard serviceAccount should return []"),
    ]
    all_pass = True
    for pattern, expect_empty, desc in cases:
        result = glob_to_literals(pattern)
        if expect_empty and result:
            print(f"  FAIL: {desc}: got {result}, expected []")
            all_pass = False
        elif not expect_empty and not result:
            print(f"  FAIL: {desc}: got [], expected non-empty")
            all_pass = False
        else:
            print(f"  PASS: {desc}: {result}")

    # Exact and prefix patterns
    exact_cases = [
        ("secrets.yaml", ["secrets.yaml"], "exact match"),
        ("secrets.yml", ["secrets.yml"], "exact match yml"),
        ("secrets.json", ["secrets.json"], "exact match json"),
    ]
    for pattern, expected, desc in exact_cases:
        result = glob_to_literals(pattern)
        if result != expected:
            print(f"  FAIL: {desc}: got {result}, expected {expected}")
            all_pass = False
        else:
            print(f"  PASS: {desc}: {result}")

    return all_pass


def test_split_commands():
    print("\n=== split_commands tests ===")
    cases = [
        # (command, expected_count, description)
        ("echo safe\\; cat foo", 1, "escaped semicolon should NOT split"),
        ('echo "hello; world"', 1, "semicolon inside double quotes should NOT split"),
        ("echo 'hello; world'", 1, "semicolon inside single quotes should NOT split"),
        ("echo $(cmd1; cmd2)", 1, "semicolon inside $() should NOT split"),
        ("cmd1; cmd2", 2, "basic semicolon SHOULD split"),
        ("cmd1 && cmd2", 2, "double ampersand SHOULD split"),
        ("cmd1 || cmd2", 2, "double pipe SHOULD split"),
        ("cmd1 | cmd2", 2, "single pipe SHOULD split"),
        ("cat foo & echo done", 2, "background & SHOULD split"),
        ("cmd 2>&1", 1, "fd redirect should NOT split"),
        ("cmd &> /dev/null", 1, "redirect both should NOT split"),
        ("echo `cat foo; echo done`", 1, "semicolon inside backticks should NOT split"),
    ]
    all_pass = True
    for cmd, expected_count, desc in cases:
        result = split_commands(cmd)
        if len(result) != expected_count:
            print(f"  FAIL: {desc}: got {len(result)} parts {result}, expected {expected_count}")
            all_pass = False
        else:
            print(f"  PASS: {desc}: {result}")

    # Test subshell (Gemini finding)
    subshell_result = split_commands("(cd /tmp; rm foo)")
    print(f"  INFO: subshell (cd /tmp; rm foo) -> {subshell_result} (Gemini flagged this)")

    return all_pass


def test_verdict_aggregation():
    print("\n=== verdict aggregation tests ===")
    cases = [
        (("allow", ""), ("allow", ""), "allow", "allow + allow = allow"),
        (("allow", ""), ("ask", "reason1"), "ask", "allow + ask = ask"),
        (("allow", ""), ("deny", "reason2"), "deny", "allow + deny = deny"),
        (("ask", "reason1"), ("deny", "reason2"), "deny", "ask + deny = deny"),
        (("deny", "reason1"), ("ask", "reason2"), "deny", "deny + ask = deny (deny wins)"),
        (("deny", "reason1"), ("deny", "reason2"), "deny", "deny + deny = deny (first reason kept)"),
    ]
    all_pass = True
    for current, candidate, expected_verdict, desc in cases:
        result = _stronger_verdict(current, candidate)
        if result[0] != expected_verdict:
            print(f"  FAIL: {desc}: got {result[0]}, expected {expected_verdict}")
            all_pass = False
        else:
            print(f"  PASS: {desc}")

    # Test that deny from later layer overrides ask from earlier layer (C-1 core test)
    v = ("allow", "")
    v = _stronger_verdict(v, ("ask", "Layer 1 pattern match"))
    v = _stronger_verdict(v, ("deny", "Layer 3 zero access"))
    if v[0] != "deny":
        print(f"  FAIL: C-1 core test: Layer 1 ask + Layer 3 deny should = deny, got {v[0]}")
        all_pass = False
    else:
        print(f"  PASS: C-1 core test: Layer 1 ask + Layer 3 deny = deny")

    return all_pass


def test_is_inside_quotes():
    print("\n=== _is_inside_quotes tests ===")
    cases = [
        ('echo "hello > world"', 13, True, "> inside double quotes"),
        ("echo 'hello > world'", 13, True, "> inside single quotes"),
        ('echo hello > world', 11, False, "> outside quotes"),
        ('echo "escaped\\" > file"', 18, False, "> after escaped quote (outside)"),
    ]
    all_pass = True
    for cmd, pos, expected, desc in cases:
        result = _is_inside_quotes(cmd, pos)
        if result != expected:
            print(f"  FAIL: {desc}: pos={pos} in {cmd!r}, got {result}, expected {expected}")
            all_pass = False
        else:
            print(f"  PASS: {desc}")

    return all_pass


if __name__ == "__main__":
    results = []
    results.append(("glob_to_literals", test_glob_to_literals()))
    results.append(("split_commands", test_split_commands()))
    results.append(("verdict_aggregation", test_verdict_aggregation()))
    results.append(("is_inside_quotes", test_is_inside_quotes()))

    print("\n=== SUMMARY ===")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_pass = all(r[1] for r in results)
    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    sys.exit(0 if all_pass else 1)
