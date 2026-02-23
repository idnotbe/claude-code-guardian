# Team 2 Context: Config Onboarding Research

## Objective
Research and recommend the best way for new users to easily set up their Guardian config when installing the plugin. Output a comprehensive research report to `/home/idnotbe/projects/claude-code-guardian/research/config-onboarding-research.md`.

## Key Questions to Answer
1. **What mechanisms does Claude Code provide for plugin initialization?**
   - Commands (like `/guardian:init` which already exists)
   - Skills (like the existing `config-guide` skill)
   - Agents (like the existing `config-assistant` agent)
   - SessionStart hooks
   - Automatic file copying on install

2. **Can we auto-install a default config when the plugin is installed?**
   - What happens when a user runs `claude plugins install`?
   - Can a SessionStart hook detect "first run" and offer to create config?
   - What are the UX implications of each approach?

3. **Can we create an interactive config wizard?**
   - The `/guardian:init` command already exists - how good is it?
   - Could we improve it with a "quick start" mode?
   - Could the config-assistant agent guide users through customization?

4. **How do other Claude Code plugins handle initial config?**
   - Research patterns from other plugins

5. **What's the optimal onboarding flow?**
   - First install -> what happens?
   - First run -> what should happen?
   - User asks "how do I configure this?" -> what experience?

## Existing Plugin Assets to Analyze
- `/home/idnotbe/projects/claude-code-guardian/commands/init.md` - Init wizard command
- `/home/idnotbe/projects/claude-code-guardian/skills/config-guide/SKILL.md` - Config guide skill
- `/home/idnotbe/projects/claude-code-guardian/agents/config-assistant.md` - Config assistant agent
- `/home/idnotbe/projects/claude-code-guardian/.claude-plugin/plugin.json` - Plugin manifest
- `/home/idnotbe/projects/claude-code-guardian/assets/guardian.default.json` - Default config
- `/home/idnotbe/projects/claude-code-guardian/assets/guardian.schema.json` - Config schema

## Deliverables
1. Main research report: `/home/idnotbe/projects/claude-code-guardian/research/config-onboarding-research.md`
2. Working notes/drafts: `/home/idnotbe/projects/claude-code-guardian/temp/` (multiple files OK)

## Analysis Framework
For each alternative approach, evaluate:
- **Ease of use** (1-5): How easy is it for a brand new user?
- **Flexibility** (1-5): Can power users customize it?
- **Discoverability** (1-5): Will users know this exists?
- **Implementation effort** (1-5): How much work to implement?
- **Maintenance cost** (1-5): How much ongoing effort?
