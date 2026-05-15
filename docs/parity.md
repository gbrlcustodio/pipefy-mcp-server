# MCP tools and CLI parity

This matrix is the source of truth for **MCP tool ↔ `pipefy` CLI** coverage. It is maintained alongside the rollout in `.cursor/dev-planning/specs/pipefy-labs/tasks/tasks-pipefy-labs.md` (parent task **5.0**).

**Registry source:** `PIPEFY_TOOL_NAMES` in `packages/mcp/src/pipefy_mcp/tools/registry.py` (must stay in sync with this table: **128** tools).

**v0.2 / v0.3 CLI:** Tasks **8.0** (attachments, field conditions, email, audit export) and **9.0** (traditional automations + exports/usage, introspection, raw GraphQL exec) are reflected as **shipped** below where Typer commands exist in `packages/cli`.

## Status legend

| Status | Meaning |
| --- | --- |
| **shipped** | CLI command exists in `packages/cli` today. |
| **pending** | Planned CLI coverage not shipped yet (see matrix). |
| **deferred** | Not targeted for the initial CLI parity wave; see **Notes**. |
| **N/A** | MCP- or IDE-oriented surface with no first-class CLI twin planned. |

## Parity matrix

| MCP tool name | CLI command (or target) | Status | Notes |
| --- | --- | --- | --- |
| `add_card_comment` | `pipefy card comment add` | shipped | Task **5.2**. |
| `clone_pipe` | `pipefy pipe clone` | shipped | Task **5.3**; optional `--org`. |
| `create_ai_agent` | `pipefy agent create` | shipped | AI Agents domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_ai_automation` | `pipefy ai-automation create` | shipped | AI Automations domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_automation` | `pipefy automation create` | shipped | Task **9.1** (`--pipe`, `--name`, `--trigger-id`, `--action-id`, optional `--extra` JSON). |
| `create_card` | `pipefy card create` | shipped | Task **5.2** (`--fields` JSON, optional `--title`). |
| `create_card_relation` | `pipefy relation card create` | shipped | Task **5.10**. |
| `create_field_condition` | `pipefy field-condition create` | shipped | Task **8.2** (`--phase`, `--name`, `--condition`, `--actions` JSON). |
| `create_label` | `pipefy label create` | shipped | Task **5.8**. |
| `create_organization_report` | `pipefy report-org create` | shipped | Organization reports; organization-level ops out of v0.1 parity. |
| `create_phase` | `pipefy phase create` | shipped | Task **5.4**. |
| `create_phase_field` | `pipefy field create` | shipped | Task **5.5** (phase fields). |
| `create_pipe` | `pipefy pipe create` | shipped | Task **5.3** (`--org`). |
| `create_pipe_relation` | `pipefy relation pipe create` | shipped | Task **5.10**. |
| `create_pipe_report` | `pipefy report-pipe create` | shipped | Reports domain; deferred from v0.1 CLI parity. |
| `create_send_task_automation` | `pipefy automation send-task create` | shipped | Task **9.1** (task title + recipients; optional `--event-params` / `--condition` JSON). |
| `create_table` | `pipefy table create` | shipped | Task **5.6**. |
| `create_table_field` | — | deferred | Table fields; not in FR-5.2 launch list (table CRUD only). |
| `create_table_record` | `pipefy record create` | shipped | Task **5.7**. |
| `create_webhook` | `pipefy webhook create` | shipped | Task **5.9**. |
| `delete_ai_agent` | `pipefy agent delete` | shipped | AI Agents domain. |
| `delete_ai_automation` | `pipefy ai-automation delete` | shipped | AI Automations domain. |
| `delete_automation` | `pipefy automation delete` | shipped | Task **9.1**; destructive: `--yes` or confirm. |
| `delete_card` | `pipefy card delete` | shipped | Task **5.2**; destructive: `--yes` or interactive confirm. |
| `delete_card_relation` | `pipefy relation card delete` | shipped | Task **5.10**; requires OAuth (internal API); `--yes`. |
| `delete_comment` | `pipefy card comment delete` | shipped | Task **5.2**; destructive: `--yes` or confirm. |
| `delete_field_condition` | `pipefy field-condition delete` | shipped | Task **8.2**; destructive: `--yes` or confirm. |
| `delete_label` | `pipefy label delete` | shipped | Task **5.8**; destructive: `--yes`. |
| `delete_organization_report` | `pipefy report-org delete` | shipped | Organization reports. |
| `delete_phase` | `pipefy phase delete` | shipped | Task **5.4**; destructive: `--yes`. |
| `delete_phase_field` | `pipefy field delete` | shipped | Task **5.5**; destructive: `--yes`. |
| `delete_pipe` | `pipefy pipe delete` | shipped | Task **5.3**; `--yes` or confirm. |
| `delete_pipe_relation` | `pipefy relation pipe delete` | shipped | Task **5.10**; destructive: `--yes`. |
| `delete_pipe_report` | `pipefy report-pipe delete` | shipped | Reports domain. |
| `delete_table` | `pipefy table delete` | shipped | Task **5.6**; destructive: `--yes`. |
| `delete_table_field` | — | deferred | Table fields; not in launch list. |
| `delete_table_record` | `pipefy record delete` | shipped | Task **5.7**; destructive: `--yes`. |
| `delete_webhook` | `pipefy webhook delete` | shipped | Task **5.9**; destructive: `--yes`. |
| `execute_graphql` | `pipefy graphql exec` | shipped | Task **9.3**; mutations require `--yes` (exit 2 without). |
| `export_automation_jobs` | `pipefy export automation-jobs` (also `pipefy automation export jobs`) | shipped | Task **9.1** / **11.3** (`--organization`, `--period`). |
| `export_organization_report` | `pipefy report-org export` | shipped | Exports + organization reports. |
| `export_pipe_audit_logs` | `pipefy audit export` | shipped | Task **8.4** (`--pipe`); API queues export (JSON payload only). |
| `export_pipe_report` | `pipefy report-pipe export` | shipped | Exports + reports. |
| `fill_card_phase_fields` | — | deferred | Card bulk fill; not in FR-5.2 launch command list (may follow **5.2**). |
| `find_cards` | `pipefy card find` | shipped | Task **5.2** (`--pipe`, `--field`, `--value`). |
| `find_records` | `pipefy record find` | shipped | Task **5.7** (`--filter` JSON with `field_id` + `field_value`). Unified MCP envelope: top-level `pagination` uses `has_more` / `end_cursor` / `page_size` (same as `get_table_records`). |
| `get_agents_usage` | `pipefy usage agents` | shipped | Task **10.3** (`--organization`, `--from`, `--to`, optional `--filters` / `--search` / `--sort` JSON). |
| `get_ai_agent` | `pipefy agent get` | shipped | AI Agents domain. |
| `get_ai_agent_log_details` | `pipefy agent logs get` | shipped | AI Agents domain. |
| `get_ai_agent_logs` | `pipefy agent logs list` | shipped | AI Agents domain. |
| `get_ai_agents` | `pipefy agent list` | shipped | AI Agents domain. |
| `get_ai_automation` | `pipefy ai-automation get` | shipped | AI Automations domain. |
| `get_ai_automations` | `pipefy ai-automation list` | shipped | AI Automations domain. |
| `get_ai_credit_usage` | `pipefy usage credits` | shipped | Task **10.3** (`--organization`, `--period`). |
| `get_automation` | `pipefy automation get` | shipped | Task **9.1**. |
| `get_automation_actions` | `pipefy automation actions list` | shipped | Task **9.1** (`--pipe`). |
| `get_automation_events` | `pipefy automation events list` | shipped | Task **9.1** (`--pipe`). |
| `get_automation_jobs_export` | `pipefy automation export status` | shipped | Task **9.1** (export id argument). |
| `get_automation_jobs_export_csv` | `pipefy export automation-jobs-csv` (also `pipefy automation export csv`) | shipped | Task **9.1** / **11.3** (export id argument). |
| `get_automation_logs` | `pipefy automation logs --automation` | shipped | Task **9.1** (mutually exclusive with `--repo`). |
| `get_automation_logs_by_repo` | `pipefy automation logs --repo` | shipped | Task **9.1**. |
| `get_automations` | `pipefy automation list` | shipped | Task **9.1** (optional `--organization` / `--pipe`). |
| `get_automations_usage` | `pipefy usage automations` (also `pipefy automation usage`) | shipped | Task **9.1** / **10.3** (`--organization`, `--from`, `--to` ISO range). |
| `get_card` | `pipefy card get` | shipped | Task **4.6**; `--include-fields` added in **5.2**. |
| `get_card_inbox_emails` | `pipefy email inbox list` | shipped | Task **8.3** (`--card`). |
| `get_card_relations` | `pipefy relation card list` | shipped | Task **5.10** (raw ``get_card_relations`` payload). |
| `get_cards` | `pipefy card list` | shipped | Task **5.2** + post-5.0 closure: ``list`` maps to ``get_cards`` (``--pipe``, ``--title``, ``--search`` JSON / ``CardSearch``, ``--include-fields``, ``--first`` / ``--after``). Use ``pipefy card find`` for ``find_cards`` (single field equality). |
| `get_email_templates` | `pipefy email template list` | shipped | Task **8.3** (`--repo`). |
| `get_field_condition` | `pipefy field-condition get` | shipped | Task **8.2**. |
| `get_field_conditions` | `pipefy field-condition list` | shipped | Task **8.2** (`--phase`). |
| `get_labels` | `pipefy label list` | shipped | Task **5.8**. |
| `get_organization` | `pipefy org get` | shipped | Organization-level read; out of v0.1 parity per task **5.1** spec. |
| `get_organization_report` | `pipefy report-org get` | shipped | Organization reports. |
| `get_organization_report_export` | (poll via `pipefy report-org export --format json`) | shipped | Organization reports + export-shaped. |
| `get_organization_reports` | `pipefy report-org list` | shipped | Organization reports. |
| `get_phase_fields` | `pipefy field list --phase` | shipped | Task **5.5**; ``pipefy phase get`` returns the same shape. |
| `get_pipe` | `pipefy pipe get` | shipped | Task **5.3**. |
| `get_pipe_members` | `pipefy member list` | shipped | Task **5.11**. |
| `get_pipe_relations` | `pipefy relation pipe list` | shipped | Task **5.10**. |
| `get_pipe_report` | `pipefy report-pipe get` | shipped | Reports domain. |
| `get_pipe_report_columns` | `pipefy report-pipe columns` | shipped | Reports domain. |
| `get_pipe_report_export` | (poll via `pipefy report-pipe export --format json`) | shipped | Reports + exports. |
| `get_pipe_report_filterable_fields` | `pipefy report-pipe filterable-fields` | shipped | Reports domain. |
| `get_pipe_reports` | `pipefy report-pipe list` | shipped | Reports domain. |
| `get_start_form_fields` | — | deferred | Pipe configuration / building; not in FR-5.2 launch list. |
| `get_table` | `pipefy table get` | shipped | Task **5.6**. |
| `get_table_record` | `pipefy record get` | shipped | Task **5.7**. |
| `get_table_records` | `pipefy record find` | shipped | Task **5.7** (omit `field_id`/`field_value` in `--filter`; uses ``--first`` / ``--after``). |
| `get_table_relations` | — | deferred | Table relations helper; not in FR-5.2 launch list. |
| `get_tables` | `pipefy table list --ids` | shipped | Task **5.6**; name search uses the same command without ``--ids``. |
| `get_webhooks` | `pipefy webhook list` | shipped | Task **5.9**. |
| `introspect_mutation` | `pipefy introspect mutation` | shipped | Task **9.2** (JSON default; optional `--rich`). |
| `introspect_query` | `pipefy introspect query` | shipped | Task **9.2**. |
| `introspect_type` | `pipefy introspect type` | shipped | Task **9.2**. |
| `invite_members` | `pipefy member invite` | shipped | Task **5.11**. |
| `move_card_to_phase` | `pipefy card move` | shipped | Task **5.2** (`--phase`). |
| `remove_member_from_pipe` | `pipefy member remove` | shipped | Task **5.11**; ``PIPEFY_SERVICE_ACCOUNT_IDS`` guard like MCP. |
| `search_pipes` | `pipefy pipe list` | shipped | Task **5.3** (`--name`, `--max-per-org`). |
| `search_schema` | `pipefy introspect schema search` | shipped | Task **9.2** (optional `--kind`). |
| `search_tables` | `pipefy table list` | shipped | Task **5.6** (without ``--ids``). |
| `send_email_with_template` | `pipefy email template send` | shipped | Task **8.3** (`--card`, `--template`). |
| `send_inbox_email` | `pipefy email inbox send` | shipped | Task **8.3** (`--from-email`, `--to`, `--subject`, `--body`). |
| `set_role` | `pipefy member set-role` | shipped | Task **5.11**. |
| `set_table_record_field_value` | `pipefy record update` | shipped | Task **5.7** (``--field-id`` + ``--value``). |
| `simulate_automation` | `pipefy automation simulate` | shipped | Task **9.1** (`--pipe`, `--action-id`, `--sample-card`, optional JSON fragments). |
| `toggle_ai_agent_status` | `pipefy agent toggle` | shipped | AI Agents domain. |
| `update_ai_agent` | `pipefy agent update` | shipped | AI Agents domain. |
| `update_ai_automation` | `pipefy ai-automation update` | shipped | AI Automations domain. |
| `update_automation` | `pipefy automation update` | shipped | Task **9.1** (`--extra` JSON). |
| `update_card` | `pipefy card update` | shipped | Task **5.2** (`--field-updates` JSON, optional title/labels/assignees/due-date). |
| `update_card_field` | `pipefy card update` | shipped | Use `--field-updates` JSON array (task **5.2**). |
| `update_comment` | `pipefy card comment update` | shipped | Task **5.2**. |
| `update_field_condition` | `pipefy field-condition update` | shipped | Task **8.2** (`--extra` JSON). |
| `update_label` | `pipefy label update` | shipped | Task **5.8**. |
| `update_organization_report` | `pipefy report-org update` | shipped | Organization reports. |
| `update_phase` | `pipefy phase update` | shipped | Task **5.4**. |
| `update_phase_field` | `pipefy field update` | shipped | Task **5.5** (``--extra`` JSON). Optional ``phase_id`` / ``pipe_id`` in ``--extra`` resolve slug ``field_id`` to ``internal_id`` when ``uuid`` is omitted. |
| `update_pipe` | `pipefy pipe update` | shipped | Task **5.3** (`--name`, `--icon`, `--color`, `--preferences` JSON). |
| `update_pipe_relation` | `pipefy relation pipe update` | shipped | Task **5.10**. |
| `update_pipe_report` | `pipefy report-pipe update` | shipped | Reports domain. |
| `update_table` | `pipefy table update` | shipped | Task **5.6**. |
| `update_table_field` | — | deferred | Table fields; not in launch list. |
| `update_table_record` | `pipefy record update` | shipped | Task **5.7** (``--fields`` JSON). |
| `update_webhook` | `pipefy webhook update` | shipped | Task **5.9**. |
| `upload_attachment_to_card` | `pipefy attachment upload --card` | shipped | Task **8.1** (also needs `--organization`, `--field`, `--file`). |
| `upload_attachment_to_table_record` | `pipefy attachment upload --record` | shipped | Task **8.1** (same supporting flags as card). |
| `validate_ai_agent_behaviors` | `pipefy agent validate-behaviors` | shipped | AI Agents validation tooling. |
| `validate_ai_automation_prompt` | `pipefy ai-automation validate-prompt` | shipped | AI Automations validation tooling. |

## Row count check

```bash
uv run python -c "import ast, pathlib; p=pathlib.Path('packages/mcp/src/pipefy_mcp/tools/registry.py'); m=ast.parse(p.read_text());
for n in m.body:
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='PIPEFY_TOOL_NAMES' for t in n.targets):
        v=n.value
        if isinstance(v, ast.Call) and getattr(v.func,'id',None)=='frozenset':
            print(len(v.args[0].elts))"
```

Expect **128** tool names in `PIPEFY_TOOL_NAMES` and **128** data rows in the parity table (excluding the header rows).

When adding or removing an MCP tool, update **this file** and `PIPEFY_TOOL_NAMES` in the same change set.
