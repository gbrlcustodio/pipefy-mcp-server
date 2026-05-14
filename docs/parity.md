# MCP tools and CLI parity

This matrix is the source of truth for **MCP tool ↔ `pipefy` CLI** coverage. It is maintained alongside the rollout in `.cursor/dev-planning/specs/pipefy-ai-sdk/tasks/tasks-pipefy-ai-sdk.md` (parent task **5.0**).

**Registry source:** `PIPEFY_TOOL_NAMES` in `packages/mcp/src/pipefy_mcp/tools/registry.py` (must stay in sync with this table: **128** tools).

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
| `create_ai_agent` | — | deferred | AI Agents domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_ai_automation` | — | deferred | AI Automations domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_automation` | — | deferred | Automations domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_card` | `pipefy card create` | shipped | Task **5.2** (`--fields` JSON, optional `--title`). |
| `create_card_relation` | `pipefy relation card create` | shipped | Task **5.10**. |
| `create_field_condition` | — | deferred | Field conditions / AI-adjacent building blocks; not in FR-5.2 launch list. |
| `create_label` | `pipefy label create` | shipped | Task **5.8**. |
| `create_organization_report` | — | deferred | Organization reports; organization-level ops out of v0.1 parity. |
| `create_phase` | `pipefy phase create` | shipped | Task **5.4**. |
| `create_phase_field` | `pipefy field create` | shipped | Task **5.5** (phase fields). |
| `create_pipe` | `pipefy pipe create` | shipped | Task **5.3** (`--org`). |
| `create_pipe_relation` | `pipefy relation pipe create` | shipped | Task **5.10**. |
| `create_pipe_report` | — | deferred | Reports domain; deferred from v0.1 CLI parity. |
| `create_send_task_automation` | — | deferred | Automations domain. |
| `create_table` | `pipefy table create` | shipped | Task **5.6**. |
| `create_table_field` | — | deferred | Table fields; not in FR-5.2 launch list (table CRUD only). |
| `create_table_record` | `pipefy record create` | shipped | Task **5.7**. |
| `create_webhook` | `pipefy webhook create` | shipped | Task **5.9**. |
| `delete_ai_agent` | — | deferred | AI Agents domain. |
| `delete_ai_automation` | — | deferred | AI Automations domain. |
| `delete_automation` | — | deferred | Automations domain. |
| `delete_card` | `pipefy card delete` | shipped | Task **5.2**; destructive: `--yes` or interactive confirm. |
| `delete_card_relation` | `pipefy relation card delete` | shipped | Task **5.10**; requires OAuth (internal API); `--yes`. |
| `delete_comment` | `pipefy card comment delete` | shipped | Task **5.2**; destructive: `--yes` or confirm. |
| `delete_field_condition` | — | deferred | Field conditions; not in launch list. |
| `delete_label` | `pipefy label delete` | shipped | Task **5.8**; destructive: `--yes`. |
| `delete_organization_report` | — | deferred | Organization reports. |
| `delete_phase` | `pipefy phase delete` | shipped | Task **5.4**; destructive: `--yes`. |
| `delete_phase_field` | `pipefy field delete` | shipped | Task **5.5**; destructive: `--yes`. |
| `delete_pipe` | `pipefy pipe delete` | shipped | Task **5.3**; `--yes` or confirm. |
| `delete_pipe_relation` | `pipefy relation pipe delete` | shipped | Task **5.10**; destructive: `--yes`. |
| `delete_pipe_report` | — | deferred | Reports domain. |
| `delete_table` | `pipefy table delete` | shipped | Task **5.6**; destructive: `--yes`. |
| `delete_table_field` | — | deferred | Table fields; not in launch list. |
| `delete_table_record` | `pipefy record delete` | shipped | Task **5.7**; destructive: `--yes`. |
| `delete_webhook` | `pipefy webhook delete` | shipped | Task **5.9**; destructive: `--yes`. |
| `execute_graphql` | — | N/A | Raw GraphQL escape hatch; MCP-oriented. |
| `export_automation_jobs` | — | deferred | Exports domain; deferred from v0.1 CLI parity. |
| `export_organization_report` | — | deferred | Exports + organization reports. |
| `export_pipe_audit_logs` | — | deferred | Exports domain. |
| `export_pipe_report` | — | deferred | Exports + reports. |
| `fill_card_phase_fields` | — | deferred | Card bulk fill; not in FR-5.2 launch command list (may follow **5.2**). |
| `find_cards` | `pipefy card find` | shipped | Task **5.2** (`--pipe`, `--field`, `--value`). |
| `find_records` | `pipefy record find` | shipped | Task **5.7** (`--filter` JSON with `field_id` + `field_value`). |
| `get_agents_usage` | — | deferred | AI Agents observability; not v0.1 CLI. |
| `get_ai_agent` | — | deferred | AI Agents domain. |
| `get_ai_agent_log_details` | — | deferred | AI Agents domain. |
| `get_ai_agent_logs` | — | deferred | AI Agents domain. |
| `get_ai_agents` | — | deferred | AI Agents domain. |
| `get_ai_automation` | — | deferred | AI Automations domain. |
| `get_ai_automations` | — | deferred | AI Automations domain. |
| `get_ai_credit_usage` | — | deferred | AI billing / usage; not v0.1 CLI. |
| `get_automation` | — | deferred | Automations domain. |
| `get_automation_actions` | — | deferred | Automations domain. |
| `get_automation_events` | — | deferred | Automations domain. |
| `get_automation_jobs_export` | — | deferred | Automations + export-shaped. |
| `get_automation_jobs_export_csv` | — | deferred | Automations + export-shaped. |
| `get_automation_logs` | — | deferred | Automations domain. |
| `get_automation_logs_by_repo` | — | deferred | Automations domain. |
| `get_automations` | — | deferred | Automations domain. |
| `get_automations_usage` | — | deferred | Automations usage. |
| `get_card` | `pipefy card get` | shipped | Task **4.6**; `--include-fields` added in **5.2**. |
| `get_card_inbox_emails` | — | deferred | Inbox/email surface; not in FR-5.2 launch list. |
| `get_card_relations` | `pipefy relation card list` | shipped | Task **5.10** (raw ``get_card_relations`` payload). |
| `get_cards` | `pipefy card list` | shipped | Task **5.2** + post-5.0 closure: ``list`` maps to ``get_cards`` (``--pipe``, ``--title``, ``--search`` JSON / ``CardSearch``, ``--include-fields``, ``--first`` / ``--after``). Use ``pipefy card find`` for ``find_cards`` (single field equality). |
| `get_email_templates` | — | deferred | Email templates; `send_email` family deferred from v0.1. |
| `get_field_condition` | — | deferred | Field conditions; not in launch list. |
| `get_field_conditions` | — | deferred | Field conditions; not in launch list. |
| `get_labels` | `pipefy label list` | shipped | Task **5.8**. |
| `get_organization` | — | deferred | Organization-level read; out of v0.1 parity per task **5.1** spec. |
| `get_organization_report` | — | deferred | Organization reports. |
| `get_organization_report_export` | — | deferred | Organization reports + export-shaped. |
| `get_organization_reports` | — | deferred | Organization reports. |
| `get_phase_fields` | `pipefy field list --phase` | shipped | Task **5.5**; ``pipefy phase get`` returns the same shape. |
| `get_pipe` | `pipefy pipe get` | shipped | Task **5.3**. |
| `get_pipe_members` | `pipefy member list` | shipped | Task **5.11**. |
| `get_pipe_relations` | `pipefy relation pipe list` | shipped | Task **5.10**. |
| `get_pipe_report` | — | deferred | Reports domain. |
| `get_pipe_report_columns` | — | deferred | Reports domain. |
| `get_pipe_report_export` | — | deferred | Reports + exports. |
| `get_pipe_report_filterable_fields` | — | deferred | Reports domain. |
| `get_pipe_reports` | — | deferred | Reports domain. |
| `get_start_form_fields` | — | deferred | Pipe configuration / building; not in FR-5.2 launch list. |
| `get_table` | `pipefy table get` | shipped | Task **5.6**. |
| `get_table_record` | `pipefy record get` | shipped | Task **5.7**. |
| `get_table_records` | `pipefy record find` | shipped | Task **5.7** (omit `field_id`/`field_value` in `--filter`; uses ``--first`` / ``--after``). |
| `get_table_relations` | — | deferred | Table relations helper; not in FR-5.2 launch list. |
| `get_tables` | `pipefy table list --ids` | shipped | Task **5.6**; name search uses the same command without ``--ids``. |
| `get_webhooks` | `pipefy webhook list` | shipped | Task **5.9**. |
| `introspect_mutation` | — | N/A | Schema introspection for MCP clients / agents. |
| `introspect_query` | — | N/A | Schema introspection for MCP clients / agents. |
| `introspect_type` | — | N/A | Schema introspection for MCP clients / agents. |
| `invite_members` | `pipefy member invite` | shipped | Task **5.11**. |
| `move_card_to_phase` | `pipefy card move` | shipped | Task **5.2** (`--phase`). |
| `remove_member_from_pipe` | `pipefy member remove` | shipped | Task **5.11**; ``PIPEFY_SERVICE_ACCOUNT_IDS`` guard like MCP. |
| `search_pipes` | `pipefy pipe list` | shipped | Task **5.3** (`--name`, `--max-per-org`). |
| `search_schema` | — | N/A | IDE/agent introspection helper. |
| `search_tables` | `pipefy table list` | shipped | Task **5.6** (without ``--ids``). |
| `send_email_with_template` | — | deferred | Email send; explicitly deferred from v0.1 parity. |
| `send_inbox_email` | — | deferred | Email send; explicitly deferred from v0.1 parity. |
| `set_role` | `pipefy member set-role` | shipped | Task **5.11**. |
| `set_table_record_field_value` | `pipefy record update` | shipped | Task **5.7** (``--field-id`` + ``--value``). |
| `simulate_automation` | — | deferred | Automation simulation; explicitly deferred from v0.1 parity. |
| `toggle_ai_agent_status` | — | deferred | AI Agents domain. |
| `update_ai_agent` | — | deferred | AI Agents domain. |
| `update_ai_automation` | — | deferred | AI Automations domain. |
| `update_automation` | — | deferred | Automations domain. |
| `update_card` | `pipefy card update` | shipped | Task **5.2** (`--field-updates` JSON, optional title/labels/assignees/due-date). |
| `update_card_field` | `pipefy card update` | shipped | Use `--field-updates` JSON array (task **5.2**). |
| `update_comment` | `pipefy card comment update` | shipped | Task **5.2**. |
| `update_field_condition` | — | deferred | Field conditions; not in launch list. |
| `update_label` | `pipefy label update` | shipped | Task **5.8**. |
| `update_organization_report` | — | deferred | Organization reports. |
| `update_phase` | `pipefy phase update` | shipped | Task **5.4**. |
| `update_phase_field` | `pipefy field update` | shipped | Task **5.5** (``--extra`` JSON). |
| `update_pipe` | `pipefy pipe update` | shipped | Task **5.3** (`--name`, `--icon`, `--color`, `--preferences` JSON). |
| `update_pipe_relation` | `pipefy relation pipe update` | shipped | Task **5.10**. |
| `update_pipe_report` | — | deferred | Reports domain. |
| `update_table` | `pipefy table update` | shipped | Task **5.6**. |
| `update_table_field` | — | deferred | Table fields; not in launch list. |
| `update_table_record` | `pipefy record update` | shipped | Task **5.7** (``--fields`` JSON). |
| `update_webhook` | `pipefy webhook update` | shipped | Task **5.9**. |
| `upload_attachment_to_card` | — | deferred | Attachments; not in FR-5.2 launch list. |
| `upload_attachment_to_table_record` | — | deferred | Attachments; not in FR-5.2 launch list. |
| `validate_ai_agent_behaviors` | — | deferred | AI Agents validation tooling. |
| `validate_ai_automation_prompt` | — | deferred | AI Automations validation tooling. |

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
