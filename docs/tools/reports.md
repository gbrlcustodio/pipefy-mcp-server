# Reports

Pipe reports and organization reports: discovery, CRUD, and async exports. **16 tools.**

## Cross-cutting patterns

- Build `ReportCardsFilter` using `get_pipe_report_columns` and `get_pipe_report_filterable_fields`; use `introspect_type` for uncommon inputs.
- `get_pipe_reports` omits `cardCount` in the query (Pipefy can error when resolving it).
- `debug=true` on writes like other mutation tools.
- **Async export pattern:** trigger export -> poll the matching `get_*_report_export` until `state` is done -> use `fileURL`. `export_pipe_audit_logs` only returns `success` (no export ID to poll — the file is delivered to the requesting user).

---

## Report read tools

| Tool | Role |
|------|------|
| `get_pipe_reports` | Lists pipe reports with pagination and optional search. |
| `get_pipe_report_columns` | Returns columns (`name`, `label`, `type`, ...) for building `fields` on create/update. |
| `get_pipe_report_filterable_fields` | Returns filterable fields grouped by section/phase for `filter`. |
| `get_organization_report` | Loads one organization report by ID. |
| `get_organization_reports` | Lists organization reports with pagination. |
| `get_pipe_report_export` | Poll export status after `export_pipe_report`; includes `fileURL` when `state` is done. |
| `get_organization_report_export` | Poll export status after `export_organization_report`. |

## Report management tools

| Tool | Role |
|------|------|
| `create_pipe_report` | Creates a pipe report (name, optional `fields`, `filter`, `formulas`). |
| `update_pipe_report` | Updates a pipe report; only provided arguments are applied. |
| `delete_pipe_report` | Deletes a pipe report (`destructiveHint=True` — confirm with the user first). |
| `create_organization_report` | Creates an org-wide report spanning multiple pipes. |
| `update_organization_report` | Updates an organization report. |
| `delete_organization_report` | Deletes an organization report (`destructiveHint=True` — confirm first). |

## Report export tools

| Tool | Role |
|------|------|
| `export_pipe_report` | Starts a pipe report export; returns export id and `processing` state. |
| `export_organization_report` | Starts an organization report export; poll with `get_organization_report_export`. |
| `export_pipe_audit_logs` | Queues a pipe audit log export; `success` only (no polling id). |
