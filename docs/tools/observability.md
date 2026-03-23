# Observability

Monitor AI agent and automation execution, usage stats, credit consumption, and export job history. **8 tools.**

All read tools use `readOnlyHint=True`; the export mutation does not.

---

## AI Agent log tools

| Tool | Read-only | Role |
|------|-----------|------|
| `get_ai_agent_logs` | Yes | Lists AI agent execution logs for a pipe (`repo_uuid`). Filter by `status` (`processing`, `failed`, `success`) and `search_term`. Paginated with `first` / `after`. |
| `get_ai_agent_log_details` | Yes | Detailed log by UUID: execution time, finish timestamp, and `tracingNodes` — step-by-step trace with per-node status (`success`, `failed`, `skipped`, `conditions_not_met`). |

## Automation log tools

| Tool | Read-only | Role |
|------|-----------|------|
| `get_automation_logs` | Yes | Lists execution logs for a specific automation (`automation_id`). Filter by `status` and `search_term`; paginated. |
| `get_automation_logs_by_repo` | Yes | Lists automation logs for all automations in a pipe (`repo_id`). Same filters and pagination. |

## Usage & credits tools

| Tool | Read-only | Role |
|------|-----------|------|
| `get_agents_usage` | Yes | AI agent usage stats for an org within a date range. `filter_date_from` / `filter_date_to` (ISO8601). Optional `filters`, `search`, `sort`. Returns total AI credits consumed and per-agent breakdown. |
| `get_automations_usage` | Yes | Automation usage stats for an org. Same date-range and filter inputs as `get_agents_usage`. Returns total execution count and per-automation breakdown. |
| `get_ai_credit_usage` | Yes | AI credit dashboard for an org: credit limit, total consumption, per-resource breakdown (AI Agents vs Assistants), addon status. `period`: `current_month`, `last_month`, or `last_3_months`. |

## Automation export tools

| Tool | Read-only | Role |
|------|-----------|------|
| `export_automation_jobs` | No | Triggers async export of automation job history for an org. `period`: `current_month`, `last_month`, or `last_3_months`. The export file is delivered to the requesting user. |
