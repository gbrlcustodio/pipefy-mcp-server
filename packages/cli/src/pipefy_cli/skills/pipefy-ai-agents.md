---
name: pipefy-ai-agents
description: >
  Use this skill when the user wants to create, read, update, delete,
  or troubleshoot AI agents (conversational agents with behaviors).
  Covers 7 MCP tools including pre-flight validation.
  For traditional automations and AI automations, see skills/automations/.
tags: [pipefy, ai-agents, behaviors, conversational]
---

# AI Agents

Conversational AI agents attached to pipes. Each agent has an agent-level instruction and 1–5 behaviors, each with its own trigger event, prompt, and actions. **7 MCP tools.**

For traditional automations and AI automations (prompt-driven), see `skills/automations/pipefy-automations/SKILL.md`.

---

## Tools

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_pipe_ai_agents` | `pipefy agent list --pipe <id>` | Yes | List all AI agents for a pipe. |
| `get_ai_agent` | `pipefy agent get <id>` | Yes | Full agent config including behaviors. |
| `create_ai_agent` | `pipefy agent create` | No | Create a new conversational agent. |
| `update_ai_agent` | `pipefy agent update <id>` | No | Update instruction or name. |
| `delete_ai_agent` | `pipefy agent delete <id>` | No | **Two-step destructive.** |
| `toggle_ai_agent_status` | `pipefy agent toggle <id>` | No | Enable or disable the agent. |
| `validate_ai_agent_behaviors` | `pipefy agent validate-behaviors` | Yes | **Pre-flight check before create/update.** |

---

## Steps — create an AI agent

1. **Validate behaviors before creating** (avoids silent failures):

   MCP: `validate_ai_agent_behaviors pipe_id=67890 behaviors='[{"trigger_event":"card_created","prompt":"Welcome the customer by name."}]'`

   CLI: `pipefy agent validate-behaviors --pipe 67890 --behaviors '[{"trigger_event":"card_created","prompt":"Welcome..."}]'`

2. **Create the agent** (only if validation succeeds):

   MCP: `create_ai_agent pipe_id=67890 name="Customer Support Agent" instruction="You are a helpful Pipefy assistant." behaviors='[{"trigger_event":"card_created","prompt":"Welcome the customer."}]'`

   CLI: `pipefy agent create --pipe 67890 --name "Customer Support Agent" --instruction "..." --behaviors '[...]'`

3. **Verify the agent is active:**

   MCP: `get_pipe_ai_agents pipe_id=67890`

---

## Steps — update an existing agent behavior

1. **Get current config:**

   MCP: `get_ai_agent agent_id=123`

2. **Validate the updated behaviors:**

   MCP: `validate_ai_agent_behaviors pipe_id=67890 behaviors='[{"trigger_event":"card_updated","prompt":"Notify the team of changes."}]'`

3. **Update the agent:**

   MCP: `update_ai_agent agent_id=123 behaviors='[{"trigger_event":"card_updated","prompt":"Notify the team of changes."}]'`

---

## Success criteria

- `get_ai_agent` returns the agent with `status: active`.
- `validate_ai_agent_behaviors` returns no errors before creation.
- Agent appears in the Pipefy UI under the pipe's AI settings.

## Failure modes

- **`validate_ai_agent_behaviors` returns validation errors:** check the `errors` field for which behavior field is invalid. Common issues: invalid `trigger_event`, prompt too long, or missing required action config.
- **Agent created but not responding:** check `toggle_ai_agent_status` — it may be disabled. Also verify the service account has the correct permissions for the pipe.
- **`delete_ai_agent` fails on first call:** expected — call without `confirm=true`, show preview to user, then call with `confirm=true`.

## See also

- `skills/automations/` — traditional automations and AI automations (different from AI agents).
- `skills/observability/` — check agent execution logs and credit usage.
