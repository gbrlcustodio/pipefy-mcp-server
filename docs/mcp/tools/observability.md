# Observability

Monitor AI agent and automation execution, usage stats, credit consumption, and export job history. **10 tools.**

Read-only observability tools use `readOnlyHint=True`. The async export mutation (`export_automation_jobs`) does not.

---

## Identifiers (avoid mixing pipe vs automation vs org)

| Concept | What observability tools expect | How to obtain it |
|--------|--------------------------------|------------------|
| **Pipe for AI agent logs** | `repo_uuid` — the pipe **UUID** | `get_pipe` with numeric `pipe_id`; use `pipe.uuid` as `repo_uuid`. |
| **Pipe for automation logs (all rules)** | `repo_id` — pipe id as **string** (numeric id is fine) | Same id you see in the Pipefy URL / `get_pipe` → `pipe.id`. |
| **Single automation logs** | `automation_id` — **not** the pipe id | `get_automations` with `pipe_id` lists rules and their `id` values. |
| **Organization for usage queries** | `organization_uuid` — org **UUID** | `get_organization(organization_id)` returns the `uuid` directly. Alternatively: `execute_graphql` with `pipe(id: $id) { organization { uuid } }`. |
| **Organization for credit dashboard** | `organization_uuid` in the tool | **UUID** or **numeric org id** (string); numeric ids are resolved server-side before calling the API. |
| **Organization for export** | `organization_id` on `export_automation_jobs` | Numeric org id (as used in URLs / exports); differs from the usage tools’ UUID parameter name. |

Empty lists (`totalCount: 0`) are valid: the pipe or automation may have no recent executions in what the API returns.

---

## Recommended workflows

**AI agent logs (you know the pipe id)**  
1. `get_pipe(pipe_id)` → read `uuid`.  
2. `get_ai_agent_logs(repo_uuid=that uuid, first=…)` → list entries.  
3. `get_ai_agent_log_details(log_uuid=…)` for trace / `tracingNodes` (use `uuid` from step 2).

**Automation logs (you know the pipe id, not which rule ran)**  
1. Prefer `get_automation_logs_by_repo(repo_id=str(pipe_id), …)` to see logs across every automation in the pipe.  
2. Each node includes `automationId` — use that value with `get_automation_logs(automation_id=…)` when you only care about one rule.  

`get_automation_logs` **cannot** be called with a pipe id alone. If you guess an `automation_id` from `get_automations`, that rule may have **zero** log rows while another rule on the same pipe has rows — use `get_automation_logs_by_repo` first when exploring.

**Org usage and credits**  
1. `get_agents_usage` and `get_automations_usage` need the org **UUID** and ISO8601 `filter_date_from` / `filter_date_to` values.  
2. `get_ai_credit_usage` accepts org UUID **or** numeric org id; `period` is `current_month`, `last_month`, or `last_3_months`.  
3. **`get_automations_usage` `usage`** is an **execution count** (runs), not AI credits. **`get_agents_usage` `usage`** aligns with AI credit consumption for agents — compare with `get_ai_credit_usage` for the dashboard view, not with automation run totals.

**Automation jobs export (async file)**  
1. `export_automation_jobs(organization_id, period)` → read `result.createAutomationJobsExport.automationJobsExport.id`.  
2. Poll `get_automation_jobs_export(export_id=that id)` until `status` is `finished` or `failed`. `ExportStatus`: `created`, `processing`, `finished`, `failed`.  
3. When `finished`, use **`get_automation_jobs_export_csv`** with the same `export_id` to download the `.xlsx` from Pipefy’s signed URL (https hosts ending in `.pipefy.com` only), convert the **first worksheet** to **CSV** text, and return it in the tool payload for LLM use. Cap output with `max_output_chars` (default 400_000) and download size with `max_download_bytes` (default 50 MiB).  
4. Alternatively, read `fileUrl` from `get_automation_jobs_export` and download outside the MCP if you need the raw xlsx.

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
| `get_agents_usage` | Yes | AI agent usage stats for an org within a date range. `filter_date_from` / `filter_date_to` (ISO8601). Optional `filters`, `search`, `sort`. Returns total **AI credits** consumed and per-agent breakdown. Requires org **UUID** (see Identifiers). |
| `get_automations_usage` | Yes | Automation usage stats for an org. Same date-range and filter inputs as `get_agents_usage`. Returns total **execution count** and per-automation breakdown (not the same unit as AI credits). Requires org **UUID**. |
| `get_ai_credit_usage` | Yes | AI credit dashboard for an org: credit limit, total consumption, per-resource breakdown (AI Agents vs Assistants), addon status. `organization_uuid` may be the org UUID or the **numeric organization id** (string). `period`: `current_month`, `last_month`, or `last_3_months`. |

## Automation export tools

| Tool | Read-only | Role |
|------|-----------|------|
| `export_automation_jobs` | No | Triggers async export of automation job history for an org. `period`: `current_month`, `last_month`, or `last_3_months`. Uses `organization_id` (numeric id). Also delivers the file to the requesting user in the Pipefy UI when processing completes. |
| `get_automation_jobs_export` | Yes | Poll by `export_id` (from `export_automation_jobs`). Returns `status` and `fileUrl` when the API exposes a signed download link. Does not download the spreadsheet body. |
| `get_automation_jobs_export_csv` | Yes | When status is `finished`, downloads the xlsx from the API’s signed URL (Pipefy https hosts only), converts the **first sheet** to CSV, returns `csv` plus metadata. Limits: `max_output_chars` (256–2_000_000), `max_download_bytes` (4 KiB–80 MiB). |

---

## See also

- [Automations & AI](automations-and-ai.md) — `get_automations` / `get_pipe` when resolving ids before calling observability tools.
- [Organization](organization.md) — `get_organization` for org UUID, plan, and member count (replaces `execute_graphql` workarounds for org discovery).
- [Introspection](introspection.md) — `execute_graphql` for ad-hoc queries; `introspect_query` / `introspect_mutation` to discover query shapes before calling `execute_graphql`.
