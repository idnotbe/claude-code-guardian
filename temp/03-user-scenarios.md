# User Scenarios for Claude Code Guardian

Comprehensive user scenarios designed from a developer's perspective, covering every common workflow with the security guardrails plugin.

---

## Scenario 1: First-Time Installation & Setup

### User's Goal
A developer wants to add security guardrails to their Claude Code `--dangerously-skip-permissions` workflow so they can work at full speed without risking accidental data destruction.

### Prerequisites
- Python 3.10+ installed and available as `python3`
- Git installed
- Claude Code installed and functional
- An existing project directory with a git repository

### Step-by-Step Actions

1. **Clone the plugin repository**
   ```bash
   git clone https://github.com/idnotbe/claude-code-guardian
   ```

2. **Launch Claude Code with the plugin loaded**
   ```bash
   claude --plugin-dir /path/to/claude-code-guardian --dangerously-skip-permissions
   ```

3. **Run the setup wizard**
   ```
   /guardian:init
   ```
   The wizard will:
   - Check for existing config at `.claude/guardian/config.json`
   - Auto-detect the project type (Node.js, Python, Rust, Go, etc.) by scanning for `package.json`, `pyproject.toml`, `Cargo.toml`, etc.
   - Detect `.env` files, Docker configs, CI/CD configs, and migration directories
   - Build a tailored configuration with smart defaults
   - Present a human-readable summary (blocked commands, ask-confirm commands, protected files, git integration settings)
   - Wait for user confirmation before writing config

4. **Verify Guardian is active** -- Run a known-blocked command to confirm hooks are working:
   ```
   Ask Claude to: "cat .env"
   ```
   Expected: Guardian blocks the operation even if `.env` does not exist.

5. **Optionally make the plugin load persistent** by adding an alias:
   ```bash
   # In ~/.bashrc or ~/.zshrc
   alias claude='claude --plugin-dir /path/to/claude-code-guardian'
   ```

### Documentation Needed
- README.md: Installation section (manual install steps, Python/Git requirements)
- README.md: Setup section (`/guardian:init` explanation)
- README.md: "How It Works" section (understanding the hook system)

### Expected Outcomes
- Config file created at `.claude/guardian/config.json`
- Five hooks registered: Bash, Read, Edit, Write (PreToolUse) and Auto-Commit (Stop)
- Dangerous commands are blocked or prompt for confirmation
- Secret files are inaccessible
- Auto-commit creates checkpoints on session stop

### Common Pitfalls
- **Forgetting `--plugin-dir`**: Without this flag, no hooks are loaded and the user has zero protection. The `--dangerously-skip-permissions` mode runs completely unguarded.
- **Using `python` instead of `python3`**: On Linux/WSL, `python` may not exist or may point to Python 2. The hooks require `python3`.
- **Not verifying hooks loaded**: Users should always test with a blocked command at the start of each session. If `cat .env` succeeds silently, hooks are not active.
- **Skipping `/guardian:init`**: Without running the wizard, Guardian still works using built-in defaults from `assets/guardian.default.json`. The defaults are secure but not project-tailored.

---

## Scenario 2: Understanding Default Security

### User's Goal
A developer who just installed Guardian wants to understand what is blocked, what prompts for confirmation, and what runs freely with the default configuration.

### Prerequisites
- Guardian installed and loaded (Scenario 1 completed)
- Default config active (either via `/guardian:init` or built-in defaults)

### Step-by-Step Actions

1. **Review what's hard-blocked** (always denied, no user prompt):
   - `rm -rf /` or `rm -rf *` -- root/system deletion
   - `rm .git`, `rm .claude`, `rm _archive` -- critical directory deletion
   - `git push --force` (but NOT `--force-with-lease`)
   - `git filter-branch`, `git reflog expire/delete` -- history destruction
   - `find ... -delete` -- find with delete action
   - `shred` -- secure file destruction
   - `curl ... | bash` (or `sh`, `python`, etc.) -- remote script execution
   - Fork bombs (`:(){...};:` pattern)
   - Command substitution with deletion (`$(rm ...)`, `` `rm ...` ``)
   - `eval rm/del/shred` -- eval with deletion
   - Interpreter-mediated deletions: `python os.remove`, `node unlinkSync`, `perl unlink`, `ruby File.delete`, etc.

2. **Review what prompts for confirmation** (ask before running):
   - `rm -rf <directory>` (recursive/force deletion of non-root paths)
   - `del`, `Remove-Item` (Windows deletion commands)
   - `git reset --hard`, `git clean -fd`, `git checkout -- .` -- discarding changes
   - `git stash drop`, `git branch -d/-D` -- dropping stash/branches
   - `git push --force-with-lease` -- safer force push
   - `truncate` -- file truncation
   - `mv .env`, `mv .git`, `mv .claude`, `mv CLAUDE.md` -- moving protected files
   - `mv ... ../` or `mv ... /tmp/` -- moving files outside project
   - SQL: `DROP TABLE/DATABASE`, `TRUNCATE TABLE`, `DELETE FROM ... ;` (without WHERE)
   - `find -exec rm/del/shred`, `xargs rm/del/shred`

3. **Review protected file paths**:

   | Protection Level | Files | Effect |
   |-----------------|-------|--------|
   | **Zero Access** | `.env`, `.env.*`, `*.pem`, `*.key`, `*.pfx`, `*.p12`, `id_rsa*`, `id_ed25519*`, `~/.ssh/**`, `~/.gnupg/**`, `~/.aws/**`, `~/.config/gcloud/**`, `~/.azure/**`, `~/.kube/**`, `*credentials*.json`, `*serviceAccount*.json`, `firebase-adminsdk*.json`, `*.tfstate`, `secrets.yaml/yml/json` | Cannot be read or written by any tool |
   | **Read Only** | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`, `Pipfile.lock`, `Cargo.lock`, `Gemfile.lock`, `composer.lock`, `go.sum`, `*.lock`, `node_modules/**`, `dist/**`, `build/**`, `__pycache__/**`, `.venv/**`, `venv/**`, `target/**`, `vendor/**` | Can be read, cannot be written or edited |
   | **No Delete** | `.gitignore`, `.gitattributes`, `.gitmodules`, `CLAUDE.md`, `LICENSE*`, `README*`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, `.github/**`, `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/**`, `azure-pipelines.yml`, `Dockerfile*`, `docker-compose*`, `.dockerignore`, `Makefile`, `pyproject.toml`, `package.json`, `tsconfig.json`, `Cargo.toml`, `go.mod` | Can be read and edited, cannot be deleted via `rm` or overwritten via Write tool |

4. **Review Git integration defaults**:
   - Auto-commit on session stop: **enabled** (commits tracked changes when Claude Code exits)
   - Pre-danger checkpoints: **enabled** (commits before risky operations like `git reset --hard`)
   - Include untracked files: **disabled** (only tracked files are auto-committed)
   - Commit identity: `Guardian Auto-Commit <guardian@claude-code.local>`
   - Commit prefix: `auto-checkpoint`

5. **Understand bash path scanning** (Layer 1 defense):
   - Enabled by default, scans `zeroAccess` tier
   - Catches references to protected file names inside bash commands (e.g., `python3 script.py --file .env`)
   - Uses word-boundary matching to reduce false positives
   - Default action: `ask` for both exact and pattern matches

### Documentation Needed
- README.md: "What It Catches" section
- `assets/guardian.default.json`: Full default configuration reference
- `assets/guardian.schema.json`: Schema with field descriptions

### Expected Outcomes
- User understands the three-tier protection model (block/ask/allow for commands, zero-access/read-only/no-delete for files)
- User knows which operations will be silently blocked vs. prompted vs. allowed
- User understands that Guardian is fail-closed: errors and timeouts result in denial

### Common Pitfalls
- **Expecting `--force-with-lease` to be blocked**: It is in the `ask` list, not `block`. User will be prompted but can proceed.
- **Expecting lock files to be completely protected**: They are read-only, meaning Claude can read them but cannot write to them. Direct `rm` through bash is blocked by the ask-patterns, not by `readOnlyPaths`.
- **Assuming noDeletePaths prevents editing**: `noDeletePaths` only prevents deletion (`rm`, `git rm`) and overwrite via the Write tool. The Edit tool can still modify these files.
- **Thinking Guardian blocks all interpreter file deletion**: Guardian catches known APIs (`os.remove`, `shutil.rmtree`, `unlinkSync`, etc.) at the bash command level, but cannot catch arbitrary code patterns inside scripts.

---

## Scenario 3: Customizing Allowed Commands

### User's Goal
A developer's legitimate workflow is being blocked or prompted unnecessarily, and they want to adjust the command patterns.

### Prerequisites
- Guardian installed with a config file at `.claude/guardian/config.json`

### Step-by-Step Actions

#### Sub-scenario 3a: Move a command from "block" to "ask"
Example: The team uses `git push --force` in a specific workflow.

1. Open `.claude/guardian/config.json`
2. Find the pattern in `bashToolPatterns.block`:
   ```json
   {"pattern": "git\\s+push\\s[^;|&\\n]*(?:--force(?!-with-lease)|-f\\b)", "reason": "Force push to remote (destructive)"}
   ```
3. Remove it from `block` and add it to `ask`:
   ```json
   {"pattern": "git\\s+push\\s[^;|&\\n]*(?:--force(?!-with-lease)|-f\\b)", "reason": "Force push (moved from block by team policy)"}
   ```
4. Save the file. Changes take effect on the next tool call.

#### Sub-scenario 3b: Add a new blocked command
Example: Block `npm publish` in this project.

1. Use the config assistant:
   ```
   "Block npm publish in this project"
   ```
   Or manually add to `bashToolPatterns.block`:
   ```json
   {"pattern": "npm\\s+publish", "reason": "Publishing to npm registry"}
   ```

#### Sub-scenario 3c: Add a new ask-confirm command
Example: Require confirmation before `docker push`.

1. Add to `bashToolPatterns.ask`:
   ```json
   {"pattern": "docker\\s+(?:push|tag)", "reason": "Pushing/tagging Docker images"}
   ```

#### Sub-scenario 3d: Use the Config Assistant naturally
Instead of editing JSON, use the config assistant agent:
- "block terraform destroy"
- "make npm publish require confirmation"
- "remove the block on git filter-branch" (assistant will warn about security implications)

### Documentation Needed
- `assets/guardian.schema.json`: `bashToolPatterns` field documentation
- `skills/config-guide/SKILL.md`: Pattern writing guide
- `agents/config-assistant.md`: Understanding the assistant's capabilities

### Expected Outcomes
- Modified commands match new block/ask behavior immediately
- Pattern regex is syntactically valid and specific enough to avoid false positives
- Config file passes schema validation

### Common Pitfalls
- **Regex escaping**: JSON requires double-backslash (`\\s+`) where regex uses single-backslash (`\s+`). Forgetting this is the most common config error.
- **Overly broad patterns**: A pattern like `rm` would match `rm` inside words like `format`. Use `\brm\s+` or prefix anchoring.
- **Forgetting the `reason` field**: Both `pattern` and `reason` are required for every entry.
- **Adding duplicate patterns**: The init wizard may have already added project-specific patterns. Check existing entries before adding.

---

## Scenario 4: Customizing Path Restrictions

### User's Goal
A developer needs to protect additional files or allow access to files that are currently blocked.

### Prerequisites
- Guardian installed with a config file

### Step-by-Step Actions

#### Sub-scenario 4a: Add a secret file to zero-access
Example: Protect `config/secrets.yaml` and `*.p8` Apple push notification keys.

1. Add to `zeroAccessPaths` in config.json:
   ```json
   "zeroAccessPaths": [
     ".env",
     "*.pem",
     "config/secrets.yaml",
     "*.p8"
   ]
   ```

#### Sub-scenario 4b: Protect database migrations from deletion
Example: Prevent deletion of `migrations/` directory contents.

1. Add to `noDeletePaths`:
   ```json
   "noDeletePaths": [
     "migrations/**",
     "db/migrate/**"
   ]
   ```

#### Sub-scenario 4c: Allow reading files outside the project
Example: A dev tool needs to read `~/.config/myapp/settings.json`.

1. Add to `allowedExternalReadPaths`:
   ```json
   "allowedExternalReadPaths": [
     "~/.config/myapp/**"
   ]
   ```
   This allows Read tool access but blocks Write/Edit. Zero-access and symlink checks still apply.

#### Sub-scenario 4d: Allow writing files outside the project
Example: A build process writes to `/opt/deploy/`.

1. Add to `allowedExternalWritePaths`:
   ```json
   "allowedExternalWritePaths": [
     "/opt/deploy/**"
   ]
   ```
   This allows Read, Write, and Edit tool access. Zero-access and symlink checks still apply.

#### Sub-scenario 4e: Use the Config Assistant
- "Protect `.env.production` as zero-access"
- "Make `alembic/versions/` no-delete"
- "Allow reading from `~/.aws/config`" (assistant will warn this is a sensitive path)

### Documentation Needed
- `assets/guardian.schema.json`: Path array field documentation
- Glob pattern syntax explanation (`**` for recursive, `*` for single-level, `~` for home)
- Explanation of protection hierarchy: zero-access > read-only > no-delete

### Expected Outcomes
- New path patterns are enforced on the next tool call
- External path exceptions only bypass the "outside project" check -- zero-access and symlink checks still apply
- No-delete paths still allow Edit tool modifications (only rm-style deletion and Write-tool overwrites are blocked)

### Common Pitfalls
- **Using `/` for directory matching instead of `/**`**: The pattern `migrations/` does not match files inside the directory. Use `migrations/**` for recursive matching.
- **Expecting `allowedExternalReadPaths` to bypass zero-access**: Even if a path is in the allowed-external list, zero-access patterns still block it. These are independent checks.
- **Misunderstanding no-delete vs. read-only**: `noDeletePaths` blocks deletion and Write-tool overwrite of existing files, but Edit tool can still modify the file content. `readOnlyPaths` blocks both Write and Edit.
- **Case sensitivity**: On Linux, path matching is case-sensitive. On macOS and Windows, it is case-insensitive.

---

## Scenario 5: Understanding Block Messages

### User's Goal
Claude attempted an operation that Guardian blocked, and the developer needs to understand why and decide what to do.

### Prerequisites
- Guardian active with hooks loaded

### Step-by-Step Actions

1. **Read the block message**. Guardian provides a reason in every denial:
   - `"Protected path: .env"` -- file is in `zeroAccessPaths`
   - `"Read-only file: package-lock.json"` -- file is in `readOnlyPaths`
   - `"Protected from deletion: README.md"` -- file is in `noDeletePaths`
   - `"Protected from overwrite: LICENSE"` -- Write tool on a noDelete file
   - `"Path is outside project directory"` -- file is not in the project tree and not in allowedExternal* paths
   - `"Symlink points outside project: link.txt"` -- symlink escape attempt
   - `"Protected system file: config.json"` -- Guardian self-guarding its own config
   - `"Root or full system deletion"` -- catastrophic rm pattern matched
   - `"Force push to remote (destructive)"` -- git push --force matched
   - `"Detected write but could not resolve target paths"` -- fail-closed safety net
   - `"Protected path reference detected: .env"` -- bash command string contains a protected filename (Layer 1 scan)

2. **Check the log file** for detailed context:
   ```
   .claude/guardian/guardian.log
   ```
   The log shows the full decision chain: which layer caught the command, what patterns matched, the resolved file path, and the final verdict.

3. **Decide how to respond**:
   - If the block was correct: Rephrase the request to Claude, avoiding the blocked operation
   - If you need an exception: Modify `config.json` to adjust rules (see Scenarios 3 and 4)
   - If you need to understand the rule: Ask the config assistant: "Why was [command] blocked?"

4. **Use the config assistant for troubleshooting**:
   ```
   "Why was 'rm -rf dist/' blocked?"
   ```
   The assistant will identify the matching pattern (`rm\\s+-[rRf]+` in the `ask` list) and explain the rule.

### Documentation Needed
- README.md: Troubleshooting section (log file location, common issues table)
- Block reason messages (enumerated in the code, should be in docs)
- Config assistant capabilities for troubleshooting

### Expected Outcomes
- User understands which specific rule triggered the block
- User can check the log for full context
- User can modify config or rephrase the request to proceed

### Common Pitfalls
- **Confusing "ask" with "block"**: An "ask" verdict means Claude Code will prompt the user for confirmation -- the user can approve the operation. A "deny" verdict means the operation is silently blocked with no option to proceed.
- **Not checking the log**: The block message on stdout is brief. The log file at `.claude/guardian/guardian.log` contains the full decision chain including which layer triggered and the command preview.
- **Assuming Guardian is broken**: If a legitimate operation is blocked, it is usually due to a pattern being broader than expected, not a bug. Check which specific pattern matched.

---

## Scenario 6: Configuration File Management

### User's Goal
A developer needs to understand where Guardian configs live, how the resolution chain works, and how to manage configs across environments.

### Prerequisites
- Guardian installed

### Step-by-Step Actions

1. **Understand the config resolution chain** (evaluated in order, first found wins):
   1. `$CLAUDE_PROJECT_DIR/.claude/guardian/config.json` -- project-specific config (created by `/guardian:init`)
   2. `$CLAUDE_PLUGIN_ROOT/assets/guardian.default.json` -- plugin default (bundled with the repo)
   3. Hardcoded `_FALLBACK_CONFIG` -- emergency fallback if both files are missing/corrupt

2. **Create a project config** (recommended):
   ```
   /guardian:init
   ```
   This creates `.claude/guardian/config.json` in your project directory.

3. **Understand the fallback behavior**:
   - If your project config has invalid JSON, Guardian logs an error and falls back to the plugin default
   - If both files are missing, a hardcoded minimal config activates (protects `.git`, `.claude`, `_archive`)
   - You can check if fallback is active by looking at the log: `[FALLBACK] Invalid JSON in ...`

4. **Commit the config to version control**:
   ```bash
   git add .claude/guardian/config.json
   git commit -m "Add Guardian security configuration"
   ```
   The config file is safe to commit -- it contains only security rules, never secrets.

5. **Validate the config manually**:
   Compare against the schema at `assets/guardian.schema.json`. The schema enforces:
   - Required fields: `version`, `hookBehavior`, `bashToolPatterns`
   - Valid `hookBehavior` values: `allow`, `deny`, `ask` for `onTimeout`/`onError`
   - `timeoutSeconds`: 1-60 range
   - Pattern rules must have both `pattern` and `reason`
   - No additional properties (typos are caught)

6. **Understand Guardian system files** (created at runtime):
   - `.claude/guardian/guardian.log` -- log file (auto-rotates at 1MB)
   - `.claude/guardian/.circuit_open` -- circuit breaker state file
   - `_archive/` -- archived files before deletion (at project root)

### Documentation Needed
- README.md: Configuration section (resolution chain, example config)
- `assets/guardian.schema.json`: Full schema reference
- Explanation that config is safe to commit to version control

### Expected Outcomes
- User knows exactly where their config lives and which config is active
- User understands what happens when config is missing or corrupt
- User knows the config is safe to version-control

### Common Pitfalls
- **Editing the wrong file**: Editing `assets/guardian.default.json` (the plugin bundled default) instead of `.claude/guardian/config.json` (the project config). The plugin default is overridden by any project config.
- **JSON syntax errors**: A single trailing comma or missing quote makes the entire config invalid, triggering fallback to defaults. Use a JSON validator.
- **Not noticing fallback is active**: If config loading fails, Guardian silently falls back. Check `guardian.log` for `[FALLBACK]` messages.
- **Expecting a global config**: There is no user-wide `~/.config/guardian/config.json`. Configuration is per-project or per-plugin-default.

---

## Scenario 7: Auto-Commit Behavior

### User's Goal
A developer wants to understand and configure the automatic git checkpoint system that preserves work.

### Prerequisites
- Guardian installed in a git repository
- Git properly configured in the project

### Step-by-Step Actions

1. **Understand default auto-commit behavior**:
   - **On session stop**: When Claude Code exits, Guardian automatically commits all tracked file changes. This creates a checkpoint so work is never lost.
   - **Before dangerous operations**: When a command triggers an "ask" verdict (e.g., `git reset --hard`), Guardian commits tracked changes first, so you can roll back if the dangerous operation goes wrong.
   - **Commit identity**: Uses `Guardian Auto-Commit <guardian@claude-code.local>` so auto-commits are distinguishable from manual commits.
   - **Untracked files**: By default, untracked files are NOT included in auto-commits.

2. **Configure auto-commit settings** in `gitIntegration`:
   ```json
   "gitIntegration": {
     "autoCommit": {
       "enabled": true,
       "onStop": true,
       "messagePrefix": "auto-checkpoint",
       "includeUntracked": false
     },
     "preCommitOnDangerous": {
       "enabled": true,
       "messagePrefix": "pre-danger-checkpoint"
     },
     "identity": {
       "email": "guardian@claude-code.local",
       "name": "Guardian Auto-Commit"
     }
   }
   ```

3. **Disable auto-commit entirely**:
   ```json
   "gitIntegration": {
     "autoCommit": {
       "enabled": false
     }
   }
   ```
   Or use the config assistant: "Disable auto-commit"

4. **Include untracked files** (use with caution):
   ```json
   "autoCommit": {
     "includeUntracked": true
   }
   ```
   **Security warning**: Combined with `--no-verify` (which auto-commit always uses), this can commit secrets that would normally be caught by pre-commit hooks.

5. **Customize the commit message prefix**:
   ```json
   "autoCommit": {
     "messagePrefix": "wip-checkpoint"
   }
   ```
   Prefix is limited to 30 characters. Total commit message is limited to 72 characters (Git convention).

6. **Understand the circuit breaker**:
   - If auto-commit fails, Guardian opens a circuit breaker to prevent repeated failures
   - Auto-commits are skipped while the circuit is open
   - The circuit auto-resets after 1 hour
   - Manual reset: delete `.claude/guardian/.circuit_open`

7. **Understand skip conditions** -- auto-commit is skipped when:
   - `gitIntegration.autoCommit.enabled` is false
   - `gitIntegration.autoCommit.onStop` is false
   - Circuit breaker is open
   - Detached HEAD state (commits would be orphaned)
   - Rebase or merge in progress (would corrupt state)
   - No changes to commit
   - No staged changes after staging
   - Dry-run mode is active

### Documentation Needed
- README.md: "Safety checkpoints" description
- `assets/guardian.schema.json`: `gitIntegration` section
- README.md: Circuit breaker explanation
- KNOWN-ISSUES.md: `--no-verify` security gap documentation

### Expected Outcomes
- Auto-commits appear in git log with the configured prefix and identity
- Work is preserved even if Claude Code crashes or the user exits unexpectedly
- Pre-danger checkpoints create a rollback point before risky operations

### Common Pitfalls
- **`includeUntracked: true` with `--no-verify`**: Auto-commit always uses `--no-verify` to bypass pre-commit hooks (since it runs during session stop and must not block termination). If `includeUntracked` is also enabled, untracked files containing secrets could be committed without pre-commit hook scanning.
- **Expecting auto-commit to work in detached HEAD**: Guardian correctly skips auto-commit in detached HEAD state because commits would be orphaned.
- **Not squashing auto-commits**: Auto-commits accumulate. Consider periodic `git rebase -i` to squash checkpoint commits into meaningful commits.
- **Circuit breaker confusion**: If auto-commits stop happening, check for `.claude/guardian/.circuit_open`. Delete it to resume.

---

## Scenario 8: Multi-Project Setup

### User's Goal
A developer works on multiple projects and wants different Guardian configurations for each.

### Prerequisites
- Guardian plugin cloned once
- Multiple project directories

### Step-by-Step Actions

1. **Same plugin, different configs**: Guardian is installed once as a plugin directory. Each project gets its own config:
   ```
   ~/projects/frontend/.claude/guardian/config.json   (Node.js-specific)
   ~/projects/backend/.claude/guardian/config.json     (Python-specific)
   ~/projects/infra/.claude/guardian/config.json        (Terraform-specific)
   ```

2. **Set up each project**:
   ```bash
   # In project A
   cd ~/projects/frontend
   claude --plugin-dir ~/tools/claude-code-guardian --dangerously-skip-permissions
   /guardian:init    # Detects Node.js, generates tailored config
   ```
   ```bash
   # In project B
   cd ~/projects/backend
   claude --plugin-dir ~/tools/claude-code-guardian --dangerously-skip-permissions
   /guardian:init    # Detects Python, generates tailored config
   ```

3. **Use the shell alias for convenience**:
   ```bash
   alias claude='claude --plugin-dir ~/tools/claude-code-guardian'
   ```
   Now every project uses Guardian, but each project's config is independent.

4. **Share configs across similar projects**: Copy a config from one project to another:
   ```bash
   cp ~/projects/frontend/.claude/guardian/config.json ~/projects/frontend-v2/.claude/guardian/config.json
   ```

5. **Version-control each project's config independently**:
   Each project's `.claude/guardian/config.json` should be committed to that project's git repository.

### Documentation Needed
- README.md: Installation section (single plugin, multiple projects)
- README.md: Configuration section (per-project config resolution)
- Explanation of `CLAUDE_PROJECT_DIR` environment variable role

### Expected Outcomes
- Each project has independent security rules
- Plugin updates (`git pull` in the plugin directory) apply to all projects
- Project configs are version-controlled per-project

### Common Pitfalls
- **Editing the plugin default instead of project config**: Changes to `~/tools/claude-code-guardian/assets/guardian.default.json` affect ALL projects that don't have their own config. This is usually not what you want.
- **Forgetting to run `/guardian:init` in a new project**: Without a project config, the plugin default applies. It works, but is not project-tailored.
- **Plugin updates overwriting default config**: Running `git pull` in the plugin directory updates `assets/guardian.default.json`. If you rely on the default (no project config), this may change your security rules.

---

## Scenario 9: Debugging & Troubleshooting

### User's Goal
Something is not working as expected -- commands are being blocked that should not be, or commands are not being blocked that should be.

### Prerequisites
- Guardian installed and loaded

### Step-by-Step Actions

1. **Check if hooks are loaded**:
   At the start of your session, ask Claude to `cat .env`. If the operation succeeds without being blocked, hooks are not active.

2. **Check the log file**:
   ```
   .claude/guardian/guardian.log
   ```
   Log entries include:
   - `[ALLOW]` -- operation was allowed (with command preview)
   - `[BLOCK]` -- operation was denied (with reason)
   - `[ASK]` -- operation requires user confirmation (with reason)
   - `[SCAN]` -- Layer 1 path scan result
   - `[ARCHIVE]` -- file archived before deletion
   - `[DRY-RUN]` -- dry-run mode actions
   - `[ERROR]` -- errors during hook execution
   - `[WARN]` -- warnings (config validation, staging failures, etc.)
   - `[FALLBACK]` -- config loading failed, using fallback

3. **Enable dry-run mode** to test without blocking:
   ```bash
   CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/guardian --dangerously-skip-permissions
   ```
   In dry-run mode, hooks log what they WOULD do but do not actually block operations.

4. **Common issue: unexpected blocks**

   | Symptom | Likely Cause | Solution |
   |---------|-------------|----------|
   | Command blocked but shouldn't be | Pattern too broad | Check which pattern matched in the log; narrow the regex |
   | File access blocked | Path matches zero-access or read-only pattern | Check path against all three path arrays in config |
   | External file access blocked | Path is outside project directory | Add to `allowedExternalReadPaths` or `allowedExternalWritePaths` |
   | Write to lock file blocked | File is in `readOnlyPaths` | This is intended; remove from `readOnlyPaths` if you need writes |
   | Operation blocked with "Guardian system error" | Hook script crashed | Check `guardian.log` for the stack trace |

5. **Common issue: missing blocks**

   | Symptom | Likely Cause | Solution |
   |---------|-------------|----------|
   | Dangerous command not caught | Pattern does not match the specific syntax | Add a more specific pattern to `bashToolPatterns.block` or `bashToolPatterns.ask` |
   | Secret file readable | File not in `zeroAccessPaths` patterns | Add the glob pattern |
   | Commands running without any hook check | Hooks not loaded | Verify `--plugin-dir` flag is set correctly |

6. **Common issue: auto-commit not working**

   | Symptom | Likely Cause | Solution |
   |---------|-------------|----------|
   | No auto-commits on stop | Circuit breaker open | Delete `.claude/guardian/.circuit_open` |
   | No auto-commits on stop | Detached HEAD state | Check out a branch |
   | No auto-commits on stop | Rebase/merge in progress | Complete or abort the rebase/merge |
   | No auto-commits on stop | Config disabled | Check `gitIntegration.autoCommit.enabled` and `onStop` |
   | Auto-commit creates empty commit | All changes are untracked and `includeUntracked` is false | Set `includeUntracked: true` or manually `git add` first |

7. **Check config validation errors** in the log:
   ```
   [WARN] Config validation: ...
   ```
   These indicate the config file structure does not match the schema. Guardian will still work but may ignore invalid fields.

8. **Reset the circuit breaker**:
   ```bash
   rm .claude/guardian/.circuit_open
   ```
   Or wait 1 hour for automatic reset.

### Documentation Needed
- README.md: Troubleshooting section (log location, common issues)
- README.md: Disabling Guardian section (dry-run mode)
- Log format documentation
- Circuit breaker documentation

### Expected Outcomes
- User can identify the root cause of unexpected behavior
- Log file provides detailed decision chain for every hook invocation
- Dry-run mode allows safe testing of config changes

### Common Pitfalls
- **Log file rotation**: The log auto-rotates at 1MB. If looking for older entries, check for rotated logs.
- **Stale config cache**: Each hook invocation is a separate Python process, so config is re-read each time. There is no stale cache issue.
- **Confusing circuit breaker with config**: The circuit breaker only affects auto-commit. It does not affect Bash/Read/Edit/Write security hooks.

---

## Scenario 10: Upgrading the Plugin

### User's Goal
A developer wants to get the latest version of Guardian with new patterns and fixes.

### Prerequisites
- Guardian installed via `git clone`

### Step-by-Step Actions

1. **Pull the latest changes**:
   ```bash
   cd /path/to/claude-code-guardian
   git pull
   ```

2. **Check the CHANGELOG**:
   ```bash
   cat CHANGELOG.md
   ```
   Review what changed -- new patterns, bug fixes, security improvements.

3. **Check for config schema changes**:
   Compare your project config against the updated `assets/guardian.schema.json`. New fields may be available.

4. **Optionally re-run the setup wizard** to get new project-specific patterns:
   ```
   /guardian:init
   ```
   The wizard will detect the existing config and ask whether to review it for improvements or start fresh.

5. **Verify hooks still work** after update:
   Test with a known-blocked command like `cat .env`.

### Documentation Needed
- README.md: "To update, run `git pull` in the cloned directory"
- CHANGELOG.md: Version history
- Migration notes if config format changes between versions

### Expected Outcomes
- Plugin code updated with latest patterns and fixes
- Existing project configs continue to work (backward compatible)
- New default patterns available in `assets/guardian.default.json`

### Common Pitfalls
- **Expecting project configs to update automatically**: Running `git pull` only updates the plugin defaults. Your project config at `.claude/guardian/config.json` is not affected. New default patterns are only used if you have no project config.
- **Breaking changes in config format**: Check if the `version` field in the default config changed. Major version bumps may require config migration.
- **Marketplace install**: Marketplace integration is currently experimental and unverified. Manual git-based installation is the reliable update path.

---

## Scenario 11: Security Audit

### User's Goal
A security-minded developer or team lead wants to review exactly what Guardian protects and identify any gaps.

### Prerequisites
- Guardian installed with a config file
- Understanding of the project's threat model

### Step-by-Step Actions

1. **Review the current configuration**:
   Use the config assistant: "Show guardian config"
   Or directly read `.claude/guardian/config.json`.

2. **Audit blocked commands** (`bashToolPatterns.block`):
   - Are all catastrophic operations listed?
   - Are interpreter-mediated deletions covered? (Python, Node, Perl, Ruby)
   - Are project-specific dangerous commands included? (e.g., `terraform destroy`, `npm publish`)

3. **Audit ask-confirm commands** (`bashToolPatterns.ask`):
   - Is anything in `ask` that should be in `block`?
   - Are SQL destructive operations covered?
   - Are `find -exec rm` and `xargs rm` patterns present?

4. **Audit zero-access paths**:
   - Are ALL secret files covered? (`.env*`, credentials, keys, cloud configs)
   - Are service account JSON files covered?
   - Are Terraform state files covered? (contains secrets)

5. **Audit read-only paths**:
   - Are lock files protected from accidental write?
   - Are build output directories protected?
   - Are virtual environment directories protected?

6. **Audit no-delete paths**:
   - Are critical project files protected? (LICENSE, README, Dockerfile, CI configs)
   - Are database migration files protected?

7. **Review known limitations**:
   - Guardian does not protect against determined human adversaries crafting bypass commands
   - Cannot catch all possible code patterns inside interpreter scripts
   - Does not protect operations run outside Claude Code
   - `noDeletePaths` is only enforced for Bash delete commands and Write tool overwrites; Edit tool can still modify content
   - `hookBehavior.timeoutSeconds` is not enforced as a blanket hook timeout
   - Auto-commit uses `--no-verify` unconditionally

8. **Review fail-closed behavior**:
   - `hookBehavior.onTimeout`: should be `deny` (default)
   - `hookBehavior.onError`: should be `deny` (default)
   - Import failures in hook scripts trigger immediate deny
   - Malformed JSON input triggers deny

9. **Review the bash path scan configuration**:
   ```json
   "bashPathScan": {
     "enabled": true,
     "scanTiers": ["zeroAccess"],
     "exactMatchAction": "ask",
     "patternMatchAction": "ask"
   }
   ```
   Consider:
   - Should `scanTiers` include `readOnly` and `noDelete`?
   - Should `exactMatchAction` be `deny` instead of `ask`?

10. **Check for bypass vectors**:
    - Compound commands: Guardian splits on `;`, `&&`, `||`, `|`, `&`, newlines
    - Command substitution: `$(...)` and backticks are tracked for nesting
    - Backslash escapes: `\;` is not treated as a delimiter
    - Path traversal: `resolve(strict=False)` prevents `../` attacks
    - Null bytes in paths: Rejected
    - Symlink escapes: Detected and blocked
    - Self-guarding: Guardian config file is protected from modification by Claude

### Documentation Needed
- KNOWN-ISSUES.md: Full list of known limitations and accepted risks
- README.md: "Does not protect against" and "Does protect against" sections
- README.md: Failure modes section
- CLAUDE.md: Known security gaps and coverage gaps tables

### Expected Outcomes
- Complete understanding of what is and is not protected
- Identification of project-specific gaps
- Informed decisions about acceptable risk levels

### Common Pitfalls
- **Assuming 100% coverage**: Guardian is a defense-in-depth layer, not a complete security solution. It should be used alongside git backups, CI/CD checks, and standard access controls.
- **Not auditing custom patterns**: Custom regex patterns may have unintended false positives or false negatives. Test them with representative commands.
- **Overlooking the `_archive` directory**: Guardian archives untracked files to `_archive/` before deletion. This directory should be in `.gitignore` and periodically cleaned.

---

## Scenario 12: Advanced -- Adding Custom Patterns

### User's Goal
A developer needs to add complex regex patterns for command matching beyond simple string patterns.

### Prerequisites
- Familiarity with regex syntax
- Understanding of JSON string escaping

### Step-by-Step Actions

1. **Understand the pattern matching system**:
   - Patterns are Python regex (compatible with the `re` module)
   - Patterns are searched (not matched) against the full command string
   - Case-insensitive matching requires `(?i)` prefix
   - JSON requires double-escaping: `\s` becomes `\\s`, `\b` becomes `\\b`

2. **Write a pattern with alternatives**:
   Block both `terraform destroy` and `terraform apply --auto-approve`:
   ```json
   {"pattern": "terraform\\s+(?:destroy|apply\\s+.*--auto-approve)", "reason": "Dangerous Terraform operations"}
   ```

3. **Write a case-insensitive pattern**:
   Block `DROP TABLE` regardless of case:
   ```json
   {"pattern": "(?i)drop\\s+table", "reason": "SQL DROP TABLE"}
   ```

4. **Write a pattern with negative lookahead**:
   Block `git push --force` but NOT `--force-with-lease`:
   ```json
   {"pattern": "git\\s+push\\s[^;|&\\n]*(?:--force(?!-with-lease)|-f\\b)", "reason": "Force push (not force-with-lease)"}
   ```

5. **Write a pattern for interpreter commands**:
   Block Python scripts that use `subprocess.run` with `shell=True`:
   ```json
   {"pattern": "(?:py|python[23]?)\\s[^|&\\n]*subprocess\\.run\\([^)]*shell\\s*=\\s*True", "reason": "Python subprocess with shell=True"}
   ```

6. **Test the pattern** using dry-run mode:
   ```bash
   CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/guardian
   ```
   Then trigger the pattern and check the log for `[DRY-RUN]` entries.

7. **Be aware of ReDoS protection**:
   - If the `regex` Python package is installed, patterns run with a 0.5-second timeout
   - Without it, standard `re` module is used (no timeout protection)
   - Avoid nested quantifiers that can cause catastrophic backtracking (e.g., `(a+)+`)

### Documentation Needed
- `skills/config-guide/references/schema-reference.md`: Regex pattern cookbook
- `skills/config-guide/SKILL.md`: Writing regex patterns section
- `assets/guardian.schema.json`: Pattern rule schema

### Expected Outcomes
- Custom patterns match intended commands without false positives
- Patterns are valid regex and pass JSON parsing
- Testing via dry-run confirms correct behavior

### Common Pitfalls
- **Double-escaping gotcha**: In JSON, you need `\\s` for `\s`. A single `\s` in JSON is just `s` (the backslash is consumed by JSON parsing).
- **Overly broad patterns**: A pattern like `rm` will match any command containing those two letters. Always use word boundaries (`\\b`) or whitespace anchors (`\\s+`).
- **Catastrophic backtracking**: Patterns like `(a+)+b` can take exponential time on non-matching input. Guardian has ReDoS protection if the `regex` package is installed, but avoid pathological patterns.
- **Forgetting the `reason` field**: Every pattern requires both `pattern` and `reason`. The reason appears in block messages to help users understand why a command was denied.
- **Not testing with dry-run**: Always test new patterns in dry-run mode before deploying.

---

## Scenario 13: Advanced -- Network/External Command Control

### User's Goal
A developer wants to control what network-accessing and external commands Claude can run.

### Prerequisites
- Understanding of which commands access the network
- Guardian installed with a config file

### Step-by-Step Actions

1. **Block remote script execution** (already in defaults):
   ```json
   {"pattern": "(?:curl|wget)[^|]*\\|\\s*(?:bash|sh|zsh|python|perl|ruby|node)", "reason": "Remote script execution (pipe to interpreter)"}
   ```
   This blocks `curl ... | bash` and similar piped-to-interpreter patterns.

2. **Add confirmation for package installs**:
   ```json
   {"pattern": "pip\\s+install\\s+(?!-r|-e)", "reason": "Installing Python package"},
   {"pattern": "npm\\s+install\\s+(?!-D|--save-dev)", "reason": "Installing npm package (non-dev)"},
   {"pattern": "cargo\\s+install", "reason": "Installing Rust crate"}
   ```

3. **Block or ask for publish/deploy commands**:
   ```json
   {"pattern": "npm\\s+publish", "reason": "Publishing to npm registry"},
   {"pattern": "docker\\s+push", "reason": "Pushing Docker image"},
   {"pattern": "(?:mvn|gradle)\\s+deploy", "reason": "Deploying artifacts"},
   {"pattern": "cargo\\s+publish", "reason": "Publishing to crates.io"}
   ```

4. **Control external tool execution**:
   ```json
   {"pattern": "npx\\s+", "reason": "Running npx package (may download and execute code)"}
   ```

5. **Control cloud CLI commands**:
   ```json
   {"pattern": "aws\\s+(?:s3\\s+rm|ec2\\s+terminate|rds\\s+delete)", "reason": "Destructive AWS operation"},
   {"pattern": "gcloud\\s+(?:compute\\s+instances\\s+delete|sql\\s+instances\\s+delete)", "reason": "Destructive GCP operation"},
   {"pattern": "az\\s+(?:vm\\s+delete|group\\s+delete)", "reason": "Destructive Azure operation"}
   ```

6. **Protect cloud credentials** (already in defaults):
   ```json
   "zeroAccessPaths": [
     "~/.aws/**",
     "~/.config/gcloud/**",
     "~/.azure/**",
     "~/.kube/**"
   ]
   ```

### Documentation Needed
- README.md: "What It Catches" (remote script execution)
- Default config reference: network-related patterns
- Pattern examples for common cloud CLIs

### Expected Outcomes
- Network-accessing commands require confirmation or are blocked
- Package publish/deploy operations are controlled
- Cloud credentials are zero-access protected
- Remote script execution (pipe to interpreter) is always blocked

### Common Pitfalls
- **Blocking legitimate `curl`/`wget`**: The default pattern only blocks piping to interpreters. Plain `curl https://api.example.com` is allowed. Be careful not to add patterns so broad they block all HTTP requests.
- **Not covering all package managers**: If your project uses multiple package managers (npm, pip, cargo), add patterns for each.
- **Cloud CLI patterns going stale**: Cloud CLIs change syntax. Periodically review your custom patterns against current CLI documentation.

---

## Scenario 14: File Deletion with Archive Safety Net

### User's Goal
A developer needs to delete files and wants to understand how Guardian's archive system protects against accidental data loss.

### Prerequisites
- Guardian installed and active
- Files to be deleted in the project directory

### Step-by-Step Actions

1. **Understand the archive flow** when Claude runs a delete command (e.g., `rm temp-file.txt`):
   - Guardian detects the delete command
   - Extracts file paths from the command
   - For untracked files (not in git): copies them to `_archive/` before deletion
   - For tracked files: no archive needed (recoverable via `git checkout`)
   - Prompts user for confirmation with archive details

2. **Archive location and naming**:
   ```
   _archive/20260216_143025_temp-file.txt/
   ├── temp-file.txt              (the archived copy)
   └── _deletion_log.json         (metadata: timestamp, command, original path)
   ```
   - Format: `_archive/{YYYYMMDD_HHMMSS}_{title}/`
   - Title is derived from the first file name (sanitized)
   - For multiple files: `_archive/{timestamp}_{first-file}_and_{N}_more/`

3. **Archive limits**:
   - Maximum file size: 100MB per file (larger files are skipped with a warning)
   - Maximum total size: 500MB (archiving stops when exceeded)
   - Maximum files: 50 files per archive operation
   - Symlinks are preserved as symlinks (not dereferenced)

4. **Recovery from archive**:
   ```bash
   # Find archived files
   ls _archive/

   # Restore a file
   cp _archive/20260216_143025_temp-file.txt/temp-file.txt ./temp-file.txt

   # Check deletion log for context
   cat _archive/20260216_143025_temp-file.txt/_deletion_log.json
   ```

5. **Archive failure handling**:
   - If archive fails (permission error, disk full, etc.): Guardian warns the user that data will be PERMANENTLY LOST and asks for confirmation before proceeding
   - Permission errors, disk full, and other filesystem errors are individually handled and logged

6. **Cleanup the archive** periodically:
   ```bash
   rm -rf _archive/   # After verifying you don't need the archived files
   ```
   Add `_archive/` to `.gitignore` to prevent committing archived files.

### Documentation Needed
- README.md: "Safety checkpoints" section (archive description)
- Archive naming convention and metadata format
- Recovery procedures
- `.gitignore` recommendation for `_archive/`

### Expected Outcomes
- Untracked files are preserved before deletion
- User is informed about archive results before confirming deletion
- Archive metadata captures original path, timestamp, and triggering command
- Archive failures trigger explicit warnings with data loss risk notice

### Common Pitfalls
- **Not adding `_archive/` to `.gitignore`**: Without this, archived files may be committed to git. The `_archive/` directory is protected from deletion by default (the `rm _archive` pattern is in the block list).
- **Assuming ALL files are archived**: Only untracked files are archived. Tracked files are recoverable via git.
- **Ignoring archive failure warnings**: If the archive fails, the deletion can still proceed if the user confirms. This means permanent data loss.
- **Large file limits**: Files over 100MB are silently skipped during archiving. Check the log for "Skipping large file" warnings.

---

## Scenario 15: Dry-Run Mode for Testing

### User's Goal
A developer wants to test Guardian configuration changes without actually blocking operations.

### Prerequisites
- Guardian installed

### Step-by-Step Actions

1. **Enable dry-run mode**:
   ```bash
   CLAUDE_HOOK_DRY_RUN=1 claude --plugin-dir /path/to/guardian --dangerously-skip-permissions
   ```

2. **Run operations as normal**. In dry-run mode:
   - Block verdicts are logged as `[DRY-RUN] Would DENY` but the operation proceeds
   - Ask verdicts are logged as `[DRY-RUN] Would ASK` but the operation proceeds
   - Archive operations are logged as `[DRY-RUN] Would archive: [files]` but no files are copied
   - Auto-commits are logged as `[DRY-RUN] Would auto-commit` but no commit is created
   - Pre-danger checkpoints are logged as `[DRY-RUN] Would pre-commit` but no commit is created

3. **Review the log** to see what would have happened:
   ```
   cat .claude/guardian/guardian.log
   ```
   Look for `[DRY-RUN]` entries.

4. **Valid values for `CLAUDE_HOOK_DRY_RUN`**:
   - `1`, `true`, `yes` (case-insensitive) -- enable dry-run
   - Any other value or unset -- normal operation

5. **Disable dry-run** by removing the environment variable or setting it to any other value.

### Documentation Needed
- README.md: "Disabling Guardian" section (dry-run mode)
- Log format for dry-run entries

### Expected Outcomes
- All operations proceed without blocking
- Full decision chain is logged for review
- Config changes can be safely tested

### Common Pitfalls
- **Forgetting dry-run is active**: In dry-run mode, NO operations are blocked. This means your session is completely unprotected. Always remove `CLAUDE_HOOK_DRY_RUN` when done testing.
- **Not checking the log**: The whole point of dry-run is to check the log. The `[DRY-RUN]` entries show exactly what would have been blocked.

---

## Scenario 16: Self-Guarding Protection

### User's Goal
A developer wants to understand how Guardian protects its own configuration from being modified by the AI agent.

### Prerequisites
- Guardian installed with a config file

### Step-by-Step Actions

1. **Understand what is self-guarded**:
   Guardian protects its own config file (`.claude/guardian/config.json`) from being modified by Claude through the Edit, Write, or Read tools. This prevents the AI agent from weakening security rules.

2. **Attempt to modify the config through Claude**:
   If Claude tries to edit `.claude/guardian/config.json`, Guardian blocks with:
   ```
   Protected system file: config.json
   ```

3. **Modify the config as a human**:
   Edit the file directly in your editor (VS Code, vim, etc.) or use the `/guardian:init` wizard. The protection only applies to Claude's tool calls, not to direct human editing.

4. **The config assistant can suggest changes** but must use the human to apply them:
   The config assistant agent reads the config and suggests modifications, but the actual file writes go through the Edit/Write hooks which enforce self-guarding.

### Documentation Needed
- README.md: "Guardian also protects its own configuration file"
- Explanation of self-guarding scope (config file only, not the entire plugin directory)

### Expected Outcomes
- AI agent cannot weaken security rules by modifying the config
- Humans can still edit the config directly
- Self-guarding applies to Edit, Write, and Read tool calls on the config path

### Common Pitfalls
- **Expecting the entire plugin directory to be protected**: Only the project-level config file (`.claude/guardian/config.json`) is self-guarded. The plugin directory (`hooks/scripts/*.py`, `assets/*.json`) is not protected by self-guarding -- it is typically outside the project tree.
- **Bash commands can still access the config**: Self-guarding is enforced through the Read/Edit/Write hooks. A bash command like `cat .claude/guardian/config.json` would be caught by the bash path scan (Layer 1), but `sed` or `echo >` commands targeting the config would need to match the bash command patterns.

---

## Cross-Scenario Reference: Hook Decision Flow

For all scenarios, this is the decision flow Guardian uses for **Bash commands**:

```
1. Layer 0: Block patterns (catastrophic)     -> DENY if matched
2. Layer 0b: Ask patterns (dangerous)         -> Accumulate verdict
3. Layer 1: Protected path scan (raw string)  -> Accumulate verdict
4. Layer 2: Split compound commands
5. Layer 3: Extract paths from each sub-command (args + redirections)
6. Layer 4: Classify as read/write/delete
7. Per-path checks:
   - Symlink escape                           -> DENY
   - Zero-access match                        -> DENY
   - Read-only match (write commands)         -> DENY
   - External read-only (write/delete)        -> DENY
   - No-delete match (delete commands)        -> DENY
8. Fail-closed safety net: write/delete with no resolved paths -> ASK
9. Aggregate: deny > ask > allow
10. If delete with existing untracked files: archive then ASK
11. If ask: pre-commit checkpoint, then ASK
12. Otherwise: ALLOW
```

For **Read/Edit/Write** tools:

```
1. Parse input (fail-closed on malformed JSON)
2. Symlink escape check                       -> DENY
3. Project boundary check                     -> DENY (unless in allowedExternal*)
4. Self-guardian check (config.json)          -> DENY
5. Zero-access check                          -> DENY
6. Read-only check (Edit/Write only)          -> DENY
7. No-delete check (Write only, existing files) -> DENY
8. Otherwise: ALLOW
```

---

## Summary Matrix: Scenarios vs. Documentation Needs

| Scenario | README | Schema | Config Guide | KNOWN-ISSUES | Init Wizard |
|----------|--------|--------|-------------|-------------|-------------|
| 1. Installation | Primary | - | - | UX-07 | Primary |
| 2. Default Security | Primary | Reference | - | SCOPE-01, SCOPE-02 | - |
| 3. Custom Commands | Reference | Primary | Primary | - | - |
| 4. Custom Paths | Reference | Primary | Primary | - | - |
| 5. Block Messages | Primary | - | Primary | - | - |
| 6. Config Management | Primary | Reference | - | - | Reference |
| 7. Auto-Commit | Primary | Reference | Reference | --no-verify gap | - |
| 8. Multi-Project | Primary | - | - | - | Reference |
| 9. Debugging | Primary | - | Reference | All | - |
| 10. Upgrading | Primary | - | - | Marketplace | - |
| 11. Security Audit | Reference | Reference | - | Primary | - |
| 12. Custom Patterns | Reference | Primary | Primary | - | - |
| 13. Network Control | Reference | Reference | Reference | - | Reference |
| 14. Archive Safety | Primary | - | - | - | - |
| 15. Dry-Run Mode | Primary | - | - | UX-11 | - |
| 16. Self-Guarding | Reference | - | - | - | - |
