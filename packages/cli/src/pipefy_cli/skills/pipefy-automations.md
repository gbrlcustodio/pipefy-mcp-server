---
name: pipefy-automations
description: >
  Use this skill when the user wants to create, read, update, or delete
  traditional automations (if/then rules) or AI automations (prompt-driven).
  Covers 15 MCP tools. For AI agents (conversational), see skills/ai-agents/.
tags: [pipefy, automations, ai-automations, rules]
---

# Automations

Traditional automations (if/then rules), AI automations (prompt-driven), task automations, and simulation. **15 MCP tools.**

For AI agents (conversational agents with behaviors), see `skills/ai-agents/pipefy-ai-agents/SKILL.md`.

**CLI status:** traditional automation commands ship as `pipefy automation …` (task **9.1**). AI automation tools remain MCP-first until task **10.2** (CLI `ai-automation`).

---

## Traditional automations (rules engine)

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_automations` | `pipefy automation list` | Yes | List all automations for a pipe. |
| `get_automation` | `pipefy automation get <id>` | Yes | Single automation with full rule config. |
| `create_automation` | `pipefy automation create` | No | Create an if/then rule. |
| `update_automation` | `pipefy automation update <id>` | No | Change trigger, conditions, or actions. |
| `delete_automation` | `pipefy automation delete <id>` | No | **Destructive:** `--yes` or confirm. |
| `simulate_automation` | `pipefy automation simulate` | No | Dry-run against a specific card. |
| `get_automation_logs` | `pipefy automation logs --automation <id>` | Yes | Execution history and errors. |
| `get_automation_logs_by_repo` | `pipefy automation logs --repo <pipe_id>` | Yes | Logs across automations in a pipe. |
| `get_automation_events` | `pipefy automation events list --pipe <id>` | Yes | Available trigger events. |
| `get_automation_actions` | `pipefy automation actions list --pipe <id>` | Yes | Available action types. |
| `create_send_task_automation` | `pipefy automation send-task create` | No | Shortcut for send-a-task rules. |
| `get_automations_usage` | `pipefy automation usage` | Yes | Org usage stats (date range + org id). |
| `export_automation_jobs` | `pipefy automation export jobs` | No | Start async jobs export. |
| `get_automation_jobs_export` | `pipefy automation export status <export_id>` | Yes | Poll export status / URL. |
| `get_automation_jobs_export_csv` | `pipefy automation export csv <export_id>` | Yes | Fetch CSV text when export is finished. |

---

## AI automations (prompt-driven)

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_ai_automations` | — (CLI v0.3+) | Yes | List AI automations for a pipe. |
| `get_ai_automation` | — (CLI v0.3+) | Yes | Single AI automation config. |
| `create_ai_automation` | — (CLI v0.3+) | No | Create a prompt-driven automation. |
| `update_ai_automation` | — (CLI v0.3+) | No | Change trigger or prompt. |
| `delete_ai_automation` | — (CLI v0.3+) | No | **Two-step destructive.** |
| `validate_ai_automation_prompt` | — (CLI v0.3+) | Yes | **Always call before create/update.** Pre-flight check. |

---

## Steps — create an AI automation

1. **Validate the prompt first** (avoids silent failures):

   MCP: `validate_ai_automation_prompt pipe_id=67890 trigger_event="card_created" prompt="Summarize the card fields and post a comment."`

2. **Create the automation** (only if validation returns `valid: true`):

   MCP: `create_ai_automation pipe_id=67890 trigger_event="card_created" prompt="Summarize the card fields and post a comment."`

---

## Steps — simulate a traditional automation

1. **Get automation ID:**

   MCP: `get_automations pipe_id=67890`

2. **Simulate against a card:**

   MCP: `simulate_automation pipe_id=67890 action_id=generate_with_ai sample_card_id=456`

   CLI: `pipefy automation simulate --pipe 67890 --action-id generate_with_ai --sample-card 456`

3. **Check logs for result:**

   MCP: `get_automation_logs automation_id=123`

---

## Success criteria

- `get_automation` returns the new automation with correct trigger and actions.
- `simulate_automation` returns a successful dry-run result.
- AI automation `validate_ai_automation_prompt` returns `valid: true` before creation.

## Failure modes

- **`validate_ai_automation_prompt` returns `valid: false`:** check the returned error message for which field or prompt element failed. Fix the prompt, then retry validation.
- **`create_automation` fails with unknown event:** call `get_automation_events` to list valid trigger event names.
- **Simulation shows no actions fired:** check the automation conditions against the card's field values.

## See also

- `skills/ai-agents/` — conversational agents with behaviors (different from AI automations).
- `skills/observability/` — monitoring automation execution logs at scale.
- `skills/introspection/` — discover available trigger and action types.
