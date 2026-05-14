---
name: pipefy-observability
description: >
  Use this skill when the user wants to check AI agent logs, automation
  execution logs, org-level usage stats, AI credit consumption, or export
  automation job history. Covers 10 MCP tools.
tags: [pipefy, observability, logs, usage, credits, exports]
---

# Observability

Monitor AI agent and automation execution, usage stats, credit consumption, and export job history. **10 MCP tools.**

---

## Identifiers reference

| Concept | What tools expect | How to obtain |
|---------|-------------------|---------------|
| **Pipe for AI agent logs** | `repo_uuid` — the pipe **UUID** | `get_pipe` with numeric `pipe_id`; use `pipe.uuid`. |
| **Automation for logs** | `automation_id` — numeric | `get_automations pipe_id=...` |
| **Org for usage stats** | `organization_id` — numeric | Known from account setup or `get_organization`. |

---

## Tools

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_ai_agent_logs` | `pipefy agent logs list` | Yes | Execution history for a specific AI agent. |
| `get_automation_logs` | `pipefy automation logs <id>` | Yes | Execution history for an automation (by automation ID or pipe). |
| `get_agents_usage` | `pipefy usage agents` | Yes | Org-level AI agent execution count and trends. |
| `get_automations_usage` | `pipefy usage automations` | Yes | Org-level automation execution stats. |
| `get_ai_credit_usage` | `pipefy usage credits` | Yes | AI credit consumption and remaining balance. |
| `export_automation_jobs` | — | Yes | Trigger async export of automation job history. |
| `export_automation_jobs_csv` | — | Yes | Trigger async CSV export of automation job history. |
| `get_export_status` | — | Yes | Poll export job status. |
| `get_export_result` | — | Yes | Download the finished export. |
| `get_automation_logs_by_repo` | — | Yes | Get automation logs filtered by pipe UUID. |

---

## Steps — diagnose a failing AI agent

1. **Get the pipe UUID** (not the numeric pipe ID):

   MCP: `get_pipe pipe_id=67890`

   Capture `pipe.uuid` from the response.

2. **Fetch recent agent logs:**

   MCP: `get_ai_agent_logs repo_uuid=<UUID> page=1`

   CLI: `pipefy agent logs list --pipe-uuid <UUID>`

3. **Identify the failed execution** — look for `status: failed` entries.

4. **Check credit usage** if the agent stopped unexpectedly:

   MCP: `get_ai_credit_usage organization_id=123`

   CLI: `pipefy usage credits`

5. **Fix and re-enable** — update the agent config (see `skills/ai-agents/`) and toggle status:

   MCP: `toggle_ai_agent_status agent_id=456`

---

## Steps — export automation history as CSV

1. **Trigger the export:**

   MCP: `export_automation_jobs_csv pipe_id=67890`

2. **Poll for completion:**

   MCP: `get_export_status export_id=<EXPORT_ID>`

   Repeat until `status == "done"`.

3. **Fetch the result:**

   MCP: `get_export_result export_id=<EXPORT_ID>`

---

## Success criteria

- Agent logs show execution timestamps and statuses.
- Credit usage shows remaining balance; no unexpected drops.
- CSV export downloads successfully and contains expected automation history.

## Failure modes

- **`get_ai_agent_logs` returns empty:** use the pipe **UUID** (e.g., `abc123-...`), not the numeric pipe ID. Get UUID from `get_pipe`.
- **`get_export_status` stays "pending" indefinitely:** large exports take time. Wait at least 60 seconds between polls. If still pending after 5 minutes, retry the export trigger.
- **Credit usage shows 0 remaining:** alert the user — AI features will stop working until credits are replenished. Escalate to the Pipefy admin.

## See also

- `skills/ai-agents/` — create and configure AI agents.
- `skills/automations/` — create and debug automation rules.
