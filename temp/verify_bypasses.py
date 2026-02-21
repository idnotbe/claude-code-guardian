import re

# The regex pattern provided by the user
pattern_str = r"""(?i)(?:^\s*|[;|&`({]\s*)(?:rm|rmdir|del|delete|deletion|remove-item)\b\s+.*\.claude(?:\s|/|[;&|)`'"]|$)"""
pattern = re.compile(pattern_str, re.DOTALL)

# Test cases: (description, command_string, should_match_regex)
# should_match_regex = True means the regex SHOULD block it.
# should_match_regex = False means the regex should NOT block it (safe command).
# If the command is DANGEROUS but should_match_regex is False, that's a BYPASS.

test_cases = [
    # --- BASELINE ---
    ("Basic rm", "rm .claude", True),
    ("rm with flag", "rm -rf .claude", True),
    ("rmdir", "rmdir .claude", True),
    
    # --- QUOTING & ESCAPING ---
    ("Backslash escape dot", r"rm \.claude", False), # Shell sees .claude. Regex sees \.
    ("Backslash escape char", r"rm .cl\aude", False), # Shell sees .claude. Regex sees \a.
    ("Single quoted", "rm '.claude'", True),
    ("Double quoted", 'rm ".claude"', True),
    ("Interspersed quotes 1", "rm .cl'au'de", False), # Shell sees .claude. Regex sees ' inside.
    ("Interspersed quotes 2", 'rm .cl"au"de', False),
    ("Empty quotes", 'rm .claude""', False), # Shell sees .claude. Regex might see ".claude" then ""?
    ("Concatenated quotes", "rm '.'claude", False),
    
    # --- INDIRECT EXECUTION ---
    ("Echo piped to sh", "echo rm .claude | sh", False), # Regex anchors start/sep. 'echo' is start.
    ("Eval", "eval 'rm .claude'", False), 
    ("Command substitution", "$(echo rm) .claude", False),
    ("Command substitution 2", "`echo rm` .claude", False),
    ("Exec", "exec rm .claude", False),
    ("Command alias", "command rm .claude", False),
    ("Builtin alias", "builtin rm .claude", False),
    
    # --- ALTERNATE PATHS ---
    ("Current dir prefix", "rm ./.claude", True), # .* matches ./
    ("Parent dir prefix", "rm ../repo/.claude", True),
    ("Multiple slashes", "rm .//.claude", True),
    ("Wildcard ?", "rm .cl?ude", False), # Shell expands to .claude. Regex sees ?
    ("Wildcard *", "rm .cl*", False),
    ("Character class", "rm .[c]laude", False),
    ("Brace expansion", "rm .claud{e,}", False), # Shell expands to .claude.
    
    # --- WHITESPACE / SEPARATORS ---
    ("Tab separator", "rm	.claude", True), # \s+ matches tab
    ("Newline in command", """rm
.claude""", True), # DOTALL? Yes.
    ("No space (invalid shell but regex check)", "rm.claude", False), # \b prevents this matching 'rm'
    
    # --- VARIABLES ---
    ("Variable path", "TARGET=.claude; rm $TARGET", False),
    ("Variable command", "CMD=rm; $CMD .claude", False),
    
    # --- OTHER COMMANDS (Technically bypasses if they delete) ---
    ("Unlink", "unlink .claude", False),
    ("Find delete", "find . -name .claude -delete", False),
    ("Git clean", "git clean -fdx", False),
    ("Mv to trash", "mv .claude /tmp/trash", False),
    ("Rsync delete", "rsync --delete -a empty/ .claude/", False),
    
    # --- FALSE POSITIVES (Safe commands blocked?) ---
    ("Echo rm string", "echo 'Do not run rm .claude'", False), 
    ("Grep search", "grep 'rm .claude' file.txt", False),
    ("Python script arg", "python script.py --cmd rm .claude", False), # Regex sees 'rm .claude' preceded by space?
]

print(f"{'TEST CASE':<30} | {'CMD':<40} | {'BLOCKED?':<8} | {'DANGEROUS?':<10} | {'RESULT'}")
print("-" * 100)

for desc, cmd, is_dangerous_target in test_cases:
    # We define "is_dangerous_target" as "This command intends to delete .claude"
    # EXCEPT for the "FALSE POSITIVES" section where we manually interpret.
    # Actually, let's just print if it matches or not.
    
    match = bool(pattern.search(cmd))
    
    # Interpretation
    # If match=True: Blocked.
    # If match=False: Allowed.
    
    # If it WAS a dangerous command (we assume most above are intended to be) AND Allowed -> BYPASS.
    # If it WAS a safe command AND Blocked -> FALSE POSITIVE.
    
    print(f"{desc:<30} | {cmd[:40]:<40} | {str(match):<8}")

