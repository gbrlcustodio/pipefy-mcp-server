# Automations & AI

Traditional automations (if/then rules) and AI-powered automations and agents. **15 tools.**

---

## Traditional automations (rules engine)

Seven tools manage Pipefy traditional automations: if/then rules bound to a pipe via the standard GraphQL API.

**Tip:** Call `get_automation_events` (global event catalog) and `get_automation_actions` with the target pipe (`repoId`) before `create_automation` to pick valid `trigger_id` / `action_id` values. Writes accept optional `extra_input` (camelCase API keys) and `debug=true` on errors.

| Tool | Read-only | Role |
|------|-----------|------|
| `get_automation` | Yes | Loads one rule by ID (trigger, actions, `active`). |
| `get_automations` | Yes | Lists rules; optional `organization_id` and/or `pipe_id`. |
| `get_automation_actions` | Yes | Catalog of action types for a pipe (IDs and field metadata). |
| `get_automation_events` | Yes | Catalog of trigger event definitions (global list; tool still takes `pipe_id` for context). |
| `create_automation` | No | Creates a rule: `pipe_id`, `name`, `trigger_id`, `action_id`; `active` defaults to true. Set `active: false` to create disabled. |
| `update_automation` | No | Patches a rule via `extra_input` (`UpdateAutomationInput` fields). |
| `delete_automation` | No | Permanently deletes a rule (`destructiveHint=True` — confirm with the user first). |

---

## AI automations & agents

AI automations are separate from traditional rules above. They are prompt-driven and use the internal API.

| Tool | Role |
|------|------|
| `create_ai_automation` | Prompt-driven automation writing to one or more card fields (AI must be enabled on the pipe). |
| `update_ai_automation` | Change name, `active`, prompt, `field_ids`, or `condition`. |
| `create_ai_agent` | Create an agent on a pipe; `repo_uuid` is the pipe UUID from `get_pipe`. |
| `update_ai_agent` | Replaces full agent config; send the complete `behaviors` list (1-5). |
| `toggle_ai_agent_status` | Enable/disable without resending configuration. |

### AI Agent read & delete

Use `get_ai_agents` with the pipe's `uuid` (same as `repo_uuid`) before `create_ai_agent` to avoid duplicates.

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ai_agent` | Yes | Loads one agent by UUID: name, instruction, behaviors. |
| `get_ai_agents` | Yes | Lists agents for a pipe (`repo_uuid` = pipe UUID). |
| `delete_ai_agent` | No | Permanently deletes an agent (`destructiveHint=True` — confirm with the user first). |
