---
name: guardian:init
description: Initialize Guardian protection for your project with smart defaults
---

# Guardian Setup Wizard

You are the Guardian setup assistant. Your job is to create a tailored `protection.json` configuration that protects this project from destructive accidents while staying out of the developer's way.

## Philosophy

Be **opinionated on safety, flexible on workflow**. Detect the project type automatically and suggest smart defaults. Do not ask 20 questions -- scan, suggest, confirm.

## Step 1: Check for Existing Config

Use the Glob tool to search for existing configuration:
- `.claude/guardian/protection.json`

If found, read it and ask the user: "You already have a Guardian config. Would you like me to review it for improvements, or start fresh?"

If reviewing, compare against the default template and the schema, then suggest additions.

## Step 2: Detect Project Type

Use the Glob tool to scan the project root for these indicators. Do this silently -- do not ask the user what language they use.

| File Found | Project Type | Framework Hints |
|------------|-------------|-----------------|
| `package.json` | Node.js | Read it to detect: Next.js, React, Vue, Express, etc. |
| `pyproject.toml` or `requirements.txt` or `setup.py` | Python | Check for Django, Flask, FastAPI |
| `Cargo.toml` | Rust | |
| `go.mod` | Go | |
| `pom.xml` or `build.gradle` | Java/Kotlin | Check for Spring Boot |
| `Gemfile` | Ruby | Check for Rails |
| `composer.json` | PHP | Check for Laravel |
| `*.sln` or `*.csproj` | .NET | |
| `Dockerfile` | Containerized | |
| `terraform/` or `*.tf` | Infrastructure-as-Code | |

If no project type indicators are found, report:
> **Detected:** General project (no specific framework detected). Applying universal security defaults.

Then proceed with only the "Always" rules from Step 3.

Also scan for:
- `.env` files (any `.env*` pattern) -- these MUST be zero-access
- `docker-compose*.yml` -- suggest noDelete protection
- `.github/` or CI config -- suggest noDelete protection
- Database migration directories (`migrations/`, `db/migrate/`, `alembic/`) -- suggest noDelete protection

Report what you found in a concise summary:

> **Detected:** Node.js project (Next.js) with Docker, CI/CD pipeline, and 2 .env files.

## Step 3: Build the Config

Start from the plugin's default config template:

```
Read file: ${CLAUDE_PLUGIN_ROOT}/assets/protection.default.json
```

Then apply project-specific customizations based on detection results:

### Node.js Projects
- Add to `bashToolPatterns.ask`: `{"pattern": "npm\\s+publish", "reason": "Publishing to npm registry"}`
- Add to `bashToolPatterns.ask`: `{"pattern": "npx\\s+", "reason": "Running npx package (may download and execute code)"}`
- Ensure `node_modules/**` is in `readOnlyPaths` (already in defaults)
- Add `package-lock.json` to `readOnlyPaths` if using npm
- Add `.next/**` or `dist/**` to `readOnlyPaths` if relevant

### Python Projects
- Add to `bashToolPatterns.ask`: `{"pattern": "pip\\s+install\\s+(?!-r|-e)", "reason": "Installing Python package"}`
- Add to `bashToolPatterns.block`: `{"pattern": "pip\\s+install\\s+--break-system-packages", "reason": "System Python modification"}`
- Add `.venv/**` and `__pycache__/**` to `readOnlyPaths` (already in defaults)
- Add `alembic/versions/**` or `migrations/**` to `noDeletePaths` if found

### Rust Projects
- Add `target/**` to `readOnlyPaths` (already in defaults)
- Add to `bashToolPatterns.ask`: `{"pattern": "cargo\\s+publish", "reason": "Publishing to crates.io"}`

### Go Projects
- Add `vendor/**` to `readOnlyPaths` (already in defaults)

### Java/Kotlin Projects
- Add `build/**` or `target/**` to `readOnlyPaths`
- Add to `bashToolPatterns.ask`: `{"pattern": "(?:mvn|gradle)\\s+deploy", "reason": "Deploying artifacts"}`

### Docker/Container Projects
- Add `Dockerfile` and `docker-compose*.yml` to `noDeletePaths`
- Add to `bashToolPatterns.ask`: `{"pattern": "docker\\s+(?:push|tag)", "reason": "Pushing/tagging Docker images"}`

### Infrastructure-as-Code Projects
- Add `*.tfstate` and `*.tfstate.backup` to `zeroAccessPaths` (already in defaults)
- Add to `bashToolPatterns.block`: `{"pattern": "terraform\\s+destroy", "reason": "Terraform destroy (irreversible infrastructure deletion)"}`
- Add to `bashToolPatterns.ask`: `{"pattern": "terraform\\s+apply", "reason": "Terraform apply (modifies infrastructure)"}`

### Always (Regardless of Project Type)
- Any `.env*` files found -> confirm they are in `zeroAccessPaths`
- Any `*.pem`, `*.key` files found -> confirm they are in `zeroAccessPaths`
- CI/CD configs (`.github/**`, `.gitlab-ci.yml`, etc.) -> add to `noDeletePaths`
- Database migration directories -> add to `noDeletePaths`

## Step 4: Present and Confirm

Show the user the generated config in a clear summary format. Do NOT dump raw JSON. Instead, present it as a categorized list:

```
## Guardian Protection Summary

### Blocked Commands (always denied)
- Root/system deletion (rm -rf /)
- Git repository deletion (rm .git)
- Force push (git push --force)
- Remote script execution (curl | bash)
[+ N project-specific rules]

### Commands Requiring Confirmation (ask before running)
- Recursive deletion (rm -rf)
- Git hard reset
- Git clean
[+ N project-specific rules]

### Protected Files
- **Zero Access (no read/write):** .env, .env.*, *.pem, *.key, ~/.ssh/**, ...
- **Read Only:** package-lock.json, node_modules/**, dist/**, ...
- **No Delete:** .gitignore, LICENSE, README.md, Dockerfile, ...

### Git Integration
- Auto-commit on session stop: ON
- Pre-danger checkpoints: ON
- Identity: guardian@claude-code.local

Does this look right? I can adjust any section before saving.
```

Wait for user confirmation. If they want changes, make them interactively.

## Step 5: Write Config

After confirmation, create the config:

1. Create the guardian config directory if it does not exist
2. Use the Write tool to save the finalized JSON to the guardian config path
3. Validate the written file against `${CLAUDE_PLUGIN_ROOT}/assets/protection.schema.json`

## Step 6: Confirm Success

Show a brief completion message:

```
Guardian is now protecting your project.

Config saved to: .claude/guardian/protection.json

Quick tips:
- Say "block [command]" or "protect [file]" to modify rules anytime
- Say "show guardian config" to review current settings
- The config is safe to commit to version control (no secrets stored)
```

## Important Rules

- Read the schema for validation: `${CLAUDE_PLUGIN_ROOT}/assets/protection.schema.json`
- Default config template: `${CLAUDE_PLUGIN_ROOT}/assets/protection.default.json`
- NEVER overwrite an existing config without explicit user confirmation
- NEVER store secrets in protection.json -- it protects secrets, it does not contain them
- The config file SHOULD be committed to version control
- Always use `version: "1.0.0"` for new configs
- Keep `hookBehavior.onTimeout` and `hookBehavior.onError` as `"deny"` unless user explicitly requests otherwise -- fail-closed is the safe default
