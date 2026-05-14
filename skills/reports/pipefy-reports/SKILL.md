---
name: pipefy-reports
description: >
  Use this skill when the user wants to create, read, update, delete, or
  export pipe reports or organization reports. Covers the async export
  workflow (trigger, poll, download). 17 MCP tools.
tags: [pipefy, reports, exports, pipe-reports, organization-reports]
---

# Reports

Pipe reports and organization reports: discovery, CRUD, and async exports. **17 MCP tools.**

---

## Cross-cutting patterns

- Build `ReportCardsFilter` using `get_pipe_report_columns` and `get_pipe_report_filterable_fields`; use `introspect_type` for uncommon inputs.
- `get_pipe_reports` omits `cardCount` in the query (Pipefy can error when resolving it).
- `debug=true` on writes like other mutation tools.

---

## Pipe report tools

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_pipe_reports` | `pipefy report-pipe list --pipe <id>` | Yes | List all reports for a pipe. |
| `get_pipe_report` | `pipefy report-pipe get <id>` | Yes | Single report data. |
| `get_pipe_report_columns` | — | Yes | Discover available columns for a report filter. |
| `get_pipe_report_filterable_fields` | — | Yes | Discover filterable fields for a report. |
| `create_pipe_report` | `pipefy report-pipe create` | No | Create a new pipe report. |
| `update_pipe_report` | `pipefy report-pipe update <id>` | No | Update report name or filters. |
| `delete_pipe_report` | `pipefy report-pipe delete <id>` | No | **Two-step destructive.** |
| `export_pipe_report` | `pipefy report-pipe export <id>` | No | Trigger async export. |

## Organization report tools

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_organization_reports` | `pipefy report-org list` | Yes | List all org-level reports. |
| `get_organization_report` | `pipefy report-org get <id>` | Yes | Single org report data. |
| `create_organization_report` | `pipefy report-org create` | No | Create an org-wide report. |
| `update_organization_report` | `pipefy report-org update <id>` | No | Update report config. |
| `delete_organization_report` | `pipefy report-org delete <id>` | No | **Two-step destructive.** |
| `export_organization_report` | `pipefy report-org export <id>` | No | Trigger async export. |

## Export status & download

| Tool (MCP) | CLI | Purpose |
|------------|-----|---------|
| `get_export_status` | — | Poll export job status. |
| `get_export_result` | — | Download finished export data. |

---

## Steps — export a pipe report

1. **List available reports:**

   MCP: `get_pipe_reports pipe_id=67890`

   CLI: `pipefy report-pipe list --pipe 67890`

2. **Trigger the export:**

   MCP: `export_pipe_report report_id=123`

   CLI: `pipefy report-pipe export 123`

3. **Poll until done:**

   MCP: `get_export_status export_id=<EXPORT_ID>`

   Repeat every 5–10 seconds until `status == "done"`.

4. **Download the result:**

   MCP: `get_export_result export_id=<EXPORT_ID>`

---

## Steps — create a filtered pipe report

1. **Discover filterable fields:**

   MCP: `get_pipe_report_filterable_fields pipe_id=67890`

2. **Create the report with a filter:**

   MCP: `create_pipe_report pipe_id=67890 name="Overdue Cards" filter='{"status":["overdue"]}'`

   CLI: `pipefy report-pipe create --pipe 67890 --name "Overdue Cards" --filter '{"status":["overdue"]}'`

---

## Success criteria

- `get_export_status` returns `status: done`.
- Downloaded export contains the expected card/report data.

## Failure modes

- **Export stuck at "pending":** large pipes with many cards can take minutes. Wait at least 60 seconds per poll. Retry export trigger if still pending after 5 minutes.
- **`get_pipe_reports` returns `null` for `cardCount`:** known Pipefy API behavior; the tool omits that field automatically.
- **Filter not working:** use `get_pipe_report_filterable_fields` to confirm the exact filter key and value format.

## See also

- `skills/observability/` — export automation job history (different from pipe reports).
- `skills/introspection/` — discover `ReportCardsFilter` input shape for complex filters.
