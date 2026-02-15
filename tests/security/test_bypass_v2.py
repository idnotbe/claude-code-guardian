#!/usr/bin/env python3
"""V2 Adversarial Bypass Testing for Bash Guardian.

Tests bypass vectors across all protection tiers:
- zeroAccess (.env, .pem, id_rsa, secrets.json)
- readOnly (poetry.lock, package-lock.json)
- noDelete (CLAUDE.md, LICENSE, .gitignore)

Also tests tokenizer (split_commands) edge cases identified by cross-model validation.
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _bootstrap  # noqa: F401, E402

from bash_guardian import (
    split_commands,
    glob_to_literals,
    scan_protected_paths,
    is_write_command,
    is_delete_command,
    extract_redirection_targets,
    extract_paths,
    _is_inside_quotes,
    _stronger_verdict,
)

passed = 0
failed = 0
bypasses = []  # Track successful bypasses

test_config = {
    "zeroAccessPaths": [
        ".env",
        ".env.*",
        ".env*.local",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_rsa.*",
        "id_ed25519",
        "id_ed25519.*",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "*.tfstate",
    ],
    "readOnlyPaths": [
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "*.lock",
    ],
    "noDeletePaths": [
        ".gitignore",
        "CLAUDE.md",
        "LICENSE",
        "LICENSE.*",
        "README.md",
        "Makefile",
        "package.json",
        "pyproject.toml",
    ],
    "bashPathScan": {
        "enabled": True,
        "scanTiers": ["zeroAccess"],
        "exactMatchAction": "deny",
        "patternMatchAction": "ask",
    },
}


def test(name, actual, expected, category="general"):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        is_bypass = False
        # Detect if this is a security bypass (expected block/deny but got allow)
        if expected in ("deny", "ask") and actual == "allow":
            is_bypass = True
            bypasses.append((name, category, expected, actual))
        elif expected is True and actual is False:
            is_bypass = True
            bypasses.append((name, category, "True", "False"))
        marker = " *** BYPASS ***" if is_bypass else ""
        print(f"FAIL: {name}{marker}")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {actual}")


def scan(cmd):
    """Shorthand: run scan_protected_paths and return verdict string."""
    v, r = scan_protected_paths(cmd, test_config)
    return v


# ============================================================
# SECTION 1: TOKENIZER (split_commands) BYPASS TESTS
# Based on Gemini cross-model validation findings
# ============================================================

print("=" * 60)
print("SECTION 1: Tokenizer (split_commands) Bypass Tests")
print("=" * 60)

# 1a. Parameter expansion ${VAR:-;}
# The tokenizer doesn't track ${...} blocks
result = split_commands('echo ${VAR:-;}')
# If ';' inside ${} is treated as separator, this will split incorrectly
test("tokenizer: ${VAR:-;} should NOT split at ;",
     len(result), 1, "tokenizer")

# 1b. Parameter expansion ${VAR//a|b/c}
result = split_commands('echo ${VAR//a|b/c}')
test("tokenizer: ${VAR//a|b/c} should NOT split at |",
     len(result), 1, "tokenizer")

# 1c. Arithmetic expansion $(( 5 | 3 ))
# The tokenizer tracks $() nesting so $(( should work
result = split_commands('echo $(( 5 | 3 ))')
test("tokenizer: $(( 5 | 3 )) should NOT split at |",
     len(result), 1, "tokenizer")

# 1d. Bare subshell (cd /tmp; ls)
result = split_commands('(cd /tmp; ls)')
# Tokenizer only tracks $() not ()
test("tokenizer: (cd /tmp; ls) bare subshell",
     len(result), 1, "tokenizer")

# 1e. Group command { echo a; echo b; }
result = split_commands('{ echo a; echo b; }')
# Tokenizer doesn't track {} groups
test("tokenizer: {echo a; echo b;} should NOT split (or split safely)",
     len(result), 1, "tokenizer")

# 1f. Heredoc with separator
result = split_commands('cat <<EOF\n;\nEOF')
# Tokenizer doesn't track heredocs
test("tokenizer: heredoc with ; should NOT split at ;",
     len(result), 1, "tokenizer")

# 1g. Case statement with ;;
result = split_commands('case $x in *) echo match ;; esac')
# ;; is case terminator, not two semicolons
test("tokenizer: case ;; should handle gracefully",
     len(result) <= 2, True, "tokenizer")

# 1h. ANSI-C quoting $'...'
# The $' is followed by a single-quote which the tokenizer treats normally
result = split_commands("echo $'hello;world'")
test("tokenizer: ANSI-C $'hello;world' should NOT split",
     len(result), 1, "tokenizer")

# 1i. Extended globbing !(*.txt|*.md)
result = split_commands('rm !(*.txt|*.md)')
test("tokenizer: extglob !(*.txt|*.md) should NOT split at |",
     len(result), 1, "tokenizer")

# 1j. [[ regex with | ]]
result = split_commands('[[ "value" =~ ^(a|b)$ ]]')
test("tokenizer: [[ regex | ]] should NOT split at |",
     len(result), 1, "tokenizer")

# 1k. Arithmetic (( x = 1 & 1 ))
result = split_commands('(( x = 1 & 1 ))')
test("tokenizer: (( x & y )) should NOT split at &",
     len(result), 1, "tokenizer")

# 1l. Comment with ;
result = split_commands('echo "safe" #; rm -rf /')
# Comments not tracked -- but in practice, Claude sends commands without #
test("tokenizer: comment #; rm should ideally not split",
     len(result), 1, "tokenizer")

# 1m. Here-string <<<
result = split_commands('cat <<< "hello;world"')
test("tokenizer: here-string <<< should not split at ;",
     len(result), 1, "tokenizer")


# ============================================================
# SECTION 2: ZERO-ACCESS PATH SCAN BYPASS TESTS
# ============================================================

print("\n" + "=" * 60)
print("SECTION 2: Zero-Access Path Scan Bypass Tests")
print("=" * 60)

# 2a. Basic -- should deny
test("scan: cat .env", scan("cat .env"), "deny", "zeroAccess")
test("scan: cat ./.env", scan("cat ./.env"), "deny", "zeroAccess")

# 2b. Variable expansion bypass -- .env never appears literally
test("scan: F=.env; cat $F (var expansion)",
     scan("F=.env; cat $F"), "deny", "zeroAccess")
# Note: The "F=.env" part contains ".env" literally, so Layer 1 catches it

# 2c. Pure variable -- no literal .env anywhere
test("scan: cat $HOME/.env (var in path)",
     scan("cat $HOME/.env"), "deny", "zeroAccess")

# 2d. Glob character class bypass: .en[v]
test("scan: cat .en[v] (char class)",
     scan("cat .en[v]"), "deny", "zeroAccess")

# 2e. Glob ? bypass: .en?
test("scan: cat .en? (question mark glob)",
     scan("cat .en?"), "deny", "zeroAccess")

# 2f. Path traversal: sub/../.env
test("scan: cat sub/../.env (path traversal)",
     scan("cat sub/../.env"), "deny", "zeroAccess")

# 2g. Tilde expansion: ~/.env
test("scan: cat ~/.env (tilde)",
     scan("cat ~/.env"), "deny", "zeroAccess")

# 2h. Indirect read via xargs
test("scan: echo .env | xargs cat",
     scan("echo .env | xargs cat"), "deny", "zeroAccess")

# 2i. Indirect read via find -exec
test("scan: find . -name .env -exec cat {} \\;",
     scan("find . -name .env -exec cat {} \\;"), "deny", "zeroAccess")

# 2j. Indirect via backticks
test("scan: cat `echo .env`",
     scan("cat `echo .env`"), "deny", "zeroAccess")

# 2k. Double-quoted .env -- does it bypass word boundary?
test("scan: cat \".env\"",
     scan('cat ".env"'), "deny", "zeroAccess")

# 2l. Single-quoted .env
test("scan: cat '.env'",
     scan("cat '.env'"), "deny", "zeroAccess")

# 2m. Brace expansion with .env
test("scan: cp {.env,backup}",
     scan("cp {.env,backup}"), "deny", "zeroAccess")

# 2n. Tab after .env (boundary char)
test("scan: cat .env\\t (tab boundary)",
     scan("cat .env\t"), "deny", "zeroAccess")

# 2o. Concatenation trick: .e""nv -- quotes in middle
test("scan: cat .e\"\"nv (empty quotes mid-word)",
     scan('cat .e""nv'), "allow", "zeroAccess-FP")
# This SHOULD be allow because .e""nv != .env in raw string

# 2p. Hex encoding (bash $'\x2e\x65\x6e\x76' = .env)
test("scan: cat $'\\x2e\\x65\\x6e\\x76' (hex encoded .env)",
     scan("cat $'\\x2e\\x65\\x6e\\x76'"), "deny", "zeroAccess")
# Raw scan would see the hex escapes, not ".env", so might miss

# 2q. Base64 decode bypass
test("scan: base64 -d <<< LmVudg== (base64 .env)",
     scan("base64 -d <<< LmVudg=="), "allow", "zeroAccess-FP")
# This should be allow -- base64 doesn't contain ".env"

# 2r. id_rsa access
test("scan: cat id_rsa", scan("cat id_rsa"), "deny", "zeroAccess")
test("scan: cat ./id_rsa", scan("cat ./id_rsa"), "deny", "zeroAccess")

# 2s. secrets.json access
test("scan: cat secrets.json", scan("cat secrets.json"), "deny", "zeroAccess")

# 2t. .pem access (suffix pattern)
test("scan: cat server.pem", scan("cat server.pem"), "ask", "zeroAccess")
test("scan: openssl x509 -in cert.pem",
     scan("openssl x509 -in cert.pem"), "ask", "zeroAccess")

# 2u. tfstate access
test("scan: cat terraform.tfstate",
     scan("cat terraform.tfstate"), "ask", "zeroAccess")

# 2v. .env.local (prefix pattern)
test("scan: cat .env.local", scan("cat .env.local"), "ask", "zeroAccess")
test("scan: cat .env.production",
     scan("cat .env.production"), "ask", "zeroAccess")

# 2w. Redirection bypass: input redirection from .env
test("scan: grep pass < .env (input redirection)",
     scan("grep pass < .env"), "deny", "zeroAccess")

# 2x. Output redirection to .env
test("scan: echo 'LEAKED=true' > .env (output redir)",
     scan("echo 'LEAKED=true' > .env"), "deny", "zeroAccess")

# 2y. Append redirection to .env
test("scan: echo 'NEW=val' >> .env (append)",
     scan("echo 'NEW=val' >> .env"), "deny", "zeroAccess")

# 2z. dd to write to .env
test("scan: dd if=/dev/zero of=.env bs=1 count=0",
     scan("dd if=/dev/zero of=.env bs=1 count=0"), "deny", "zeroAccess")

# ============================================================
# SECTION 2B: ENCODING/OBFUSCATION BYPASS ATTEMPTS
# These try to reference .env WITHOUT the literal ".env" appearing
# ============================================================

print("\n" + "=" * 60)
print("SECTION 2B: Encoding/Obfuscation Bypass Attempts")
print("=" * 60)

# These are the REAL adversarial tests -- can we reference .env
# without the scanner catching it?

# 2B-a. Glob with character class: .en[v]
# scan_protected_paths does raw string matching -- ".env" won't appear
test("obfuscation: cat .en[v] (glob char class) -- bypasses scan?",
     scan("cat .en[v]"), "allow", "zeroAccess-bypass")
# This IS a bypass of Layer 1 but needs Layer 3 to catch it

# 2B-b. Glob with ?: .en?
test("obfuscation: cat .en? (glob ?) -- bypasses scan?",
     scan("cat .en?"), "allow", "zeroAccess-bypass")

# 2B-c. Pure variable expansion with no literal
test("obfuscation: f=.env && cat $f (split into two cmds)",
     scan("f=.env && cat $f"), "deny", "zeroAccess-bypass")
# Layer 1 catches "f=.env" because .env is a literal in the assignment

# 2B-d. Variable with concatenation
test("obfuscation: a=.en; b=v; cat ${a}${b}",
     scan("a=.en; b=v; cat ${a}${b}"), "allow", "zeroAccess-bypass")
# ".env" never appears as a literal -- POTENTIAL BYPASS

# 2B-e. printf to construct filename
test("obfuscation: cat $(printf '.%s' env)",
     scan("cat $(printf '.%s' env)"), "allow", "zeroAccess-bypass")
# ".env" never appears

# 2B-f. eval with constructed string
test("obfuscation: eval 'cat .e''nv'",
     scan("eval 'cat .e''nv'"), "allow", "zeroAccess-bypass")
# Split quotes make ".env" not appear as literal

# 2B-g. Hex escape in $'...'
test("obfuscation: cat $'\\056env' (octal/hex .env)",
     scan("cat $'\\056env'"), "allow", "zeroAccess-bypass")
# \056 = '.' so this becomes .env at runtime

# 2B-h. Python one-liner to read
test("obfuscation: python3 -c 'open(\".env\").read()'",
     scan("python3 -c 'open(\".env\").read()'"), "deny", "zeroAccess-bypass")
# ".env" appears inside quotes but Layer 1 should still see it

# 2B-i. Python with chr() bypass
test("obfuscation: python3 -c 'open(chr(46)+\"env\").read()'",
     scan("python3 -c 'open(chr(46)+\"env\").read()'"), "allow", "zeroAccess-bypass")
# ".env" doesn't appear as a literal

# 2B-j. Symlink creation then read
test("obfuscation: ln -s .env safe_name && cat safe_name",
     scan("ln -s .env safe_name && cat safe_name"), "deny", "zeroAccess-bypass")
# ".env" appears in ln command

# 2B-k. Using /proc/self to read via fd
test("obfuscation: exec 3<.env; cat /proc/self/fd/3",
     scan("exec 3<.env; cat /proc/self/fd/3"), "deny", "zeroAccess-bypass")
# ".env" appears after < redirection

# 2B-l. Using rev to reconstruct
test("obfuscation: cat $(echo vne. | rev)",
     scan("cat $(echo vne. | rev)"), "allow", "zeroAccess-bypass")
# ".env" never appears

# 2B-m. Base64 decode
test("obfuscation: cat $(echo LmVudg== | base64 -d)",
     scan("cat $(echo LmVudg== | base64 -d)"), "allow", "zeroAccess-bypass")

# 2B-n. Using find without naming .env
test("obfuscation: find . -name '.e*' -maxdepth 1 -exec cat {} +",
     scan("find . -name '.e*' -maxdepth 1 -exec cat {} +"), "allow", "zeroAccess-bypass")

# 2B-o. Wildcard: cat .e*
test("obfuscation: cat .e* (wildcard)",
     scan("cat .e*"), "allow", "zeroAccess-bypass")

# ============================================================
# SECTION 3: READ-ONLY BYPASS TESTS
# ============================================================

print("\n" + "=" * 60)
print("SECTION 3: Read-Only Bypass Tests (Layer 3+4)")
print("=" * 60)

# These need BOTH the file to exist AND the command to be write-detected
# Layer 1 scan only checks zeroAccessPaths, so readOnly relies on Layer 3+4

# Test is_write_command detection
test("write: echo > poetry.lock", is_write_command("echo > poetry.lock"), True, "readOnly")
test("write: sed -i poetry.lock", is_write_command("sed -i 's/x/y/' poetry.lock"), True, "readOnly")
test("write: cp src poetry.lock", is_write_command("cp src poetry.lock"), True, "readOnly")
test("write: tee poetry.lock", is_write_command("tee poetry.lock"), True, "readOnly")
test("write: dd of=poetry.lock", is_write_command("dd if=/dev/zero of=poetry.lock"), True, "readOnly")

# Commands that should NOT trigger write detection
test("not-write: cat poetry.lock", is_write_command("cat poetry.lock"), False, "readOnly")
test("not-write: head poetry.lock", is_write_command("head poetry.lock"), False, "readOnly")

# Bypass attempts for write detection
test("write: chmod 777 poetry.lock (missed?)", is_write_command("chmod 777 poetry.lock"), False, "readOnly-bypass")
test("write: chown user poetry.lock (missed?)", is_write_command("chown user poetry.lock"), False, "readOnly-bypass")
test("write: touch poetry.lock (missed?)", is_write_command("touch poetry.lock"), False, "readOnly-bypass")
test("write: truncate -s 0 poetry.lock", is_write_command("truncate -s 0 poetry.lock"), False, "readOnly-bypass")
# Note: truncate IS in ask patterns but is_write_command doesn't catch it

# ============================================================
# SECTION 4: NO-DELETE BYPASS TESTS
# ============================================================

print("\n" + "=" * 60)
print("SECTION 4: No-Delete Bypass Tests (Layer 3+4)")
print("=" * 60)

# Test is_delete_command detection
test("delete: rm CLAUDE.md", is_delete_command("rm CLAUDE.md"), True, "noDelete")
test("delete: rm -f .gitignore", is_delete_command("rm -f .gitignore"), True, "noDelete")
test("delete: mv LICENSE /dev/null", is_delete_command("mv LICENSE /dev/null"), True, "noDelete")

# Bypass attempts for delete detection
test("delete: mv CLAUDE.md /tmp/ (not /dev/null)", is_delete_command("mv CLAUDE.md /tmp/"), False, "noDelete-bypass")
# mv to /tmp is effectively deletion but not to /dev/null

test("delete: > CLAUDE.md (truncate via redirect)", is_delete_command("> CLAUDE.md"), False, "noDelete-bypass")
# Truncating to empty is effectively deletion

test("delete: truncate -s 0 CLAUDE.md", is_delete_command("truncate -s 0 CLAUDE.md"), False, "noDelete-bypass")
# truncate is caught by ask patterns but not is_delete_command

test("delete: cp /dev/null CLAUDE.md", is_delete_command("cp /dev/null CLAUDE.md"), False, "noDelete-bypass")
# cp from /dev/null effectively empties the file

test("delete: python3 -c 'import os; os.unlink(\"CLAUDE.md\")'",
     is_delete_command("python3 -c 'import os; os.unlink(\"CLAUDE.md\")'"), True, "noDelete")

test("delete: git rm CLAUDE.md (missed?)",
     is_delete_command("git rm CLAUDE.md"), False, "noDelete-bypass")
# git rm deletes files but is_delete_command doesn't check for it

test("delete: git clean -f (missed?)",
     is_delete_command("git clean -f"), False, "noDelete-bypass")


# ============================================================
# SECTION 5: LAYER INTERACTION / CHAINING TESTS
# ============================================================

print("\n" + "=" * 60)
print("SECTION 5: Layer Interaction / Chaining Tests")
print("=" * 60)

# 5a. Innocuous cmd before dangerous
test("chain: ls; cat .env",
     scan("ls; cat .env"), "deny", "chain")

# 5b. Many cmds before payload
test("chain: echo a && echo b && echo c && cat .env",
     scan("echo a && echo b && echo c && cat .env"), "deny", "chain")

# 5c. Pipe chain
test("chain: ls | grep x | cat .env",
     scan("ls | grep x | cat .env"), "deny", "chain")

# 5d. Background + payload
test("chain: sleep 10 & cat .env",
     scan("sleep 10 & cat .env"), "deny", "chain")

# 5e. Newline separated
test("chain: echo safe\\ncat .env",
     scan("echo safe\ncat .env"), "deny", "chain")

# 5f. Complex multi-line with obfuscation
test("chain: echo a; echo b; a=.en; b=v; cat ${a}${b}",
     scan("echo a; echo b; a=.en; b=v; cat ${a}${b}"), "allow", "chain-bypass")
# Layer 1 doesn't see ".env" as a literal


# ============================================================
# SECTION 6: FALSE POSITIVE TESTS
# ============================================================

print("\n" + "=" * 60)
print("SECTION 6: False Positive Tests")
print("=" * 60)

# Ensure legitimate commands are NOT blocked
test("FP: npm install", scan("npm install"), "allow", "false-positive")
test("FP: pip install requests", scan("pip install requests"), "allow", "false-positive")
test("FP: git status", scan("git status"), "allow", "false-positive")
test("FP: ls -la", scan("ls -la"), "allow", "false-positive")
test("FP: echo hello world", scan("echo hello world"), "allow", "false-positive")
test("FP: python3 script.py", scan("python3 script.py"), "allow", "false-positive")
test("FP: cat README.md", scan("cat README.md"), "allow", "false-positive")
test("FP: grep -r TODO .", scan("grep -r TODO ."), "allow", "false-positive")

# Environment-like but NOT .env
test("FP: printenv", scan("printenv"), "allow", "false-positive")
test("FP: env", scan("env"), "allow", "false-positive")
test("FP: export PATH=foo", scan("export PATH=foo"), "allow", "false-positive")


# ============================================================
# SECTION 7: REDIRECTION TARGET EXTRACTION TESTS
# ============================================================

print("\n" + "=" * 60)
print("SECTION 7: Redirection Target Extraction")
print("=" * 60)

project_dir = Path("/tmp/test-project")

# Basic redirections
targets = extract_redirection_targets("echo x > output.txt", project_dir)
test("redir: echo x > output.txt",
     len(targets) > 0, True, "redirection")

targets = extract_redirection_targets("echo x >> append.txt", project_dir)
test("redir: echo x >> append.txt",
     len(targets) > 0, True, "redirection")

targets = extract_redirection_targets("cmd < input.txt", project_dir)
test("redir: cmd < input.txt",
     len(targets) > 0, True, "redirection")

# Quoted redirection should be skipped
targets = extract_redirection_targets('echo "x > y"', project_dir)
test("redir: echo \"x > y\" (quoted, should skip)",
     len(targets), 0, "redirection")

# Multiple redirections
targets = extract_redirection_targets("cmd > out.txt 2> err.txt", project_dir)
test("redir: cmd > out.txt 2> err.txt (two targets)",
     len(targets), 2, "redirection")


# ============================================================
# SUMMARY
# ============================================================

print("\n" + "=" * 60)
print(f"Tests passed: {passed}")
print(f"Tests failed: {failed}")
print(f"Total: {passed + failed}")

if bypasses:
    print(f"\n*** SECURITY BYPASSES FOUND: {len(bypasses)} ***")
    for name, cat, expected, actual in bypasses:
        print(f"  [{cat}] {name}: expected={expected}, got={actual}")
else:
    print("\nNo security bypasses found.")

if failed > 0 and not bypasses:
    print(f"\nFailed tests (non-bypass): {failed}")

print("=" * 60)
