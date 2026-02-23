# Research: UX Patterns for Developer Tool Onboarding

## How Popular Developer Tools Handle Initial Configuration

### ESLint
- **Pattern**: Explicit init command (`npx @eslint/init`)
- **Wizard style**: Interactive Q&A (framework, style guide, format preference)
- **Output**: Generates `eslint.config.js` with smart defaults
- **First-run behavior**: If no config file found, ESLint warns and suggests running init
- **Key insight**: Shifted from `.eslintrc` to flat config (eslint.config.js) for simplicity

### Prettier
- **Pattern**: Zero-config defaults + optional config file
- **First-run behavior**: Works immediately with sensible defaults, no config needed
- **Customization**: Drop a `.prettierrc` when you want to override defaults
- **Key insight**: "It just works" approach -- opinionated defaults reduce config friction

### Husky (Git Hooks)
- **Pattern**: `npx husky init` creates `.husky/` directory with a pre-commit hook
- **Install step**: `npm pkg set scripts.prepare="husky"` in package.json
- **Key insight**: Minimal setup, single command, hooks to npm lifecycle

### Rust's Clippy
- **Pattern**: Zero-config, works out of the box
- **Customization**: `clippy.toml` or `#[allow]` attributes for overrides
- **Key insight**: Opinionated defaults that work for 95% of cases

### Docker
- **Pattern**: `docker init` scaffolds Dockerfile, docker-compose.yml, .dockerignore
- **Detection**: Scans project for language/framework indicators
- **Key insight**: Smart project detection + templated output

### GitHub Actions
- **Pattern**: Template marketplace + starter workflows
- **First-run**: Suggests workflows based on repo language
- **Key insight**: Template selection, not blank-slate configuration

## Patterns Specific to Security Tools

### Dependabot
- **Pattern**: Config file in `.github/dependabot.yml`
- **First-run**: GitHub UI suggests enabling with a default config
- **Key insight**: Platform-level suggestion + one-click enable

### CodeQL
- **Pattern**: Config in `.github/workflows/codeql.yml`
- **First-run**: GitHub suggests adding after repo creation
- **Key insight**: Progressive disclosure -- basic setup first, advanced later

### Snyk
- **Pattern**: `snyk wizard` for interactive setup
- **Progressive**: Basic scan with no config, then `snyk wizard` for policy creation
- **Key insight**: Works without config, config adds customization

### OWASP ZAP
- **Pattern**: Default scan profiles (Baseline, API, Full)
- **Progressive**: Predefined profiles for different risk appetites
- **Key insight**: Tiered profiles mapped to user expertise/risk tolerance

## Patterns from Other Claude Code Plugins

### explanatory-output-style
- **Pattern**: SessionStart hook injects context
- **No config needed**: Just a prompt that gets added to session context
- **Key insight**: Simplest possible onboarding -- install and forget

### learning-output-style
- **Pattern**: SessionStart hook encourages specific behavior
- **No config needed**: Self-contained in the hook
- **Key insight**: SessionStart hooks as "ambient configuration"

### hookify
- **Pattern**: Multiple commands for different aspects (`/hookify`, `/hookify:list`, `/hookify:configure`)
- **Agent**: `conversation-analyzer` for detecting problematic patterns
- **Key insight**: Multiple entry points for different user needs

### plugin-dev
- **Pattern**: `/plugin-dev:create-plugin` with 8-phase guided workflow
- **Agents**: Specialized agents for validation and review
- **Key insight**: Comprehensive wizard for complex tasks

### security-guidance
- **Pattern**: PreToolUse hook monitors security patterns
- **No config needed**: Works immediately after install
- **Key insight**: Security tools benefit most from zero-config defaults

## Key UX Principles Identified

### 1. Progressive Disclosure
- Start with opinionated defaults that work for most users
- Reveal complexity only when users ask for it
- Example: Prettier works with zero config, ESLint starts with a simple wizard

### 2. Smart Detection
- Automatically detect project type, framework, and patterns
- Reduce questions by inferring answers
- Example: Docker init scans for language indicators

### 3. Tiered Complexity
- Offer predefined profiles for different user types
- "Starter", "Recommended", "Paranoid" tiers
- Example: OWASP ZAP's scan profiles, CodeQL's default vs. advanced configs

### 4. Zero-Config Defaults
- The tool should work immediately after installation
- Config is for customization, not basic operation
- Example: Prettier, Clippy, security-guidance plugin

### 5. Guided Wizards for Complex Config
- When config IS needed, guide users through it
- Detect and suggest, don't interrogate
- Example: ESLint init, Docker init, guardian:init

### 6. Multiple Entry Points
- Different users discover features differently
- Command for intentional setup, agent for organic discovery, skill for contextual help
- Example: hookify's multiple commands and analyzer agent

### 7. Platform-Level Suggestions
- The system itself should suggest setup at the right moment
- Example: GitHub suggesting Dependabot, Claude seeing SessionStart context

## Mapping to Guardian's Situation

Guardian is a **security tool** with a **complex config** (regex patterns, path globs, git settings). This maps most closely to:

| Pattern | Applicability to Guardian |
|---------|--------------------------|
| Zero-config defaults | HIGH -- Guardian already has a hardcoded minimal fallback |
| Smart detection | HIGH -- guardian:init already does project detection |
| Tiered profiles | HIGH -- different users want different security levels |
| SessionStart suggestion | HIGH -- perfect for first-run prompting |
| Progressive disclosure | HIGH -- start simple, customize later |
| Multiple entry points | ALREADY EXISTS -- init + skill + agent |

## Anti-Patterns to Avoid

1. **Mandatory config before use** -- blocks adoption, especially for "just trying it out" users
2. **20-question wizards** -- init.md already warns against this
3. **Silent failure** -- if no config, clearly communicate what defaults are in effect
4. **Config sprawl** -- too many config files confuse users
5. **Breaking changes on config format changes** -- version field and migration path needed
