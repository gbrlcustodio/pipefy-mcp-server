# MCP tools and CLI parity

This matrix is the source of truth for **MCP tool ↔ `pipefy` CLI** coverage. Update it whenever MCP tools or CLI commands are added, renamed, or removed.

**Registry source:** `PIPEFY_TOOL_NAMES` in `packages/mcp/src/pipefy_mcp/tools/registry.py` (must stay in sync with this table: **153** tools).

**Later CLI coverage:** areas such as attachments, field conditions, email, audit export, traditional automations, exports/usage, introspection, and raw GraphQL appear as **shipped** below when the matching Typer commands exist in `packages/cli`.

## Response shape (MCP envelope vs CLI JSON)

Many read-only MCP tools return a unified envelope (`success`, `data`, optional `message` / `pagination`) when `PIPEFY_MCP_UNIFIED_ENVELOPE` is true (default). The CLI prints the **underlying SDK/GraphQL payload** with `--json` — there is no `success` wrapper. When comparing the same capability on both surfaces, diff the **core fields** (`pipe`, `card`, `organizations`, …); on MCP they usually live under **`data`**.

For **database records**, `find_records` result nodes may use **`fields`** while list/get table record responses may use **`record_fields`** — that follows Pipefy’s GraphQL shape per operation, not an MCP vs CLI inconsistency.

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
| `add_card_comment` | `pipefy card comment add` | shipped | — |
| `clone_pipe` | `pipefy pipe clone` | shipped | optional `--org`. |
| `create_ai_agent` | `pipefy agent create` | shipped | AI Agents domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_ai_automation` | `pipefy ai-automation create` | shipped | AI Automations domain; post-v0.1 CLI unless explicitly rescoped. |
| `create_automation` | `pipefy automation create` | shipped | (`--pipe`, `--name`, `--trigger-id`, `--action-id`, optional `--extra` JSON). |
| `create_card` | `pipefy card create` | shipped | (`--fields` JSON, optional `--title`, optional `--phase-id` for `CreateCardInput.phase_id`). |
| `create_card_relation` | `pipefy relation card create` | shipped | — |
| `create_field_condition` | `pipefy field-condition create` | shipped | (`--phase`, `--name`, `--condition`, `--actions` JSON). |
| `create_label` | `pipefy label create` | shipped | `color` must be hex `#RGB` or `#RRGGBB` (validated before GraphQL). |
| `create_organization_report` | `pipefy report-org create` | shipped | Organization reports; `filter` preflight validates ReportCardsFilter shape (nested `operator` + `queries`). |
| `create_phase` | `pipefy phase create` | shipped | — |
| `create_phase_field` | `pipefy field create` | shipped | (phase fields). |
| `create_pipe` | `pipefy pipe create` | shipped | (`--org`). |
| `create_pipe_relation` | `pipefy relation pipe create` | shipped | — |
| `create_pipe_report` | `pipefy report-pipe create` | shipped | Reports domain; `filter` preflight validates ReportCardsFilter shape (nested `operator` + `queries`). |
| `create_portal` | `pipefy portal create` | shipped | `--organization-uuid`; idempotent (find-or-create main portal). |
| `create_portal_page` | `pipefy portal page create` | shipped | `--portal-uuid`, `--title`; optional `--description`, `--index`. Empty main portal may bootstrap a templated page when the API omits `elements`. |
| `create_portal_element` | `pipefy portal element create` | shipped | `--page-id`, `--type`, `--metadata` JSON; optional `--data-sources` JSON array. SDK validates metadata before GraphQL. |
| `create_sub_portal` | `pipefy portal sub-portal create` | shipped | `--main-portal-uuid`; optional `--name`. Interfaces `createSubPortal`. |
| `create_send_task_automation` | `pipefy automation send-task create` | shipped | (task title + recipients; optional `--event-params` / `--condition` JSON). |
| `create_table` | `pipefy table create` | shipped | — |
| `create_table_field` | — | deferred | Table fields; not in initial launch list (table CRUD only). |
| `create_table_record` | `pipefy record create` | shipped | — |
| `create_webhook` | `pipefy webhook create` | shipped | — |
| `delete_ai_agent` | `pipefy agent delete` | shipped | AI Agents domain. |
| `delete_ai_automation` | `pipefy ai-automation delete` | shipped | AI Automations domain. |
| `delete_automation` | `pipefy automation delete` | shipped | destructive: `--yes` or confirm. |
| `delete_card` | `pipefy card delete` | shipped | destructive: `--yes` or interactive confirm. |
| `delete_card_relation` | `pipefy relation card delete` | shipped | requires OAuth (internal API); `--yes`. |
| `delete_comment` | `pipefy card comment delete` | shipped | destructive: `--yes` or confirm. |
| `delete_field_condition` | `pipefy field-condition delete` | shipped | destructive: `--yes` or confirm. |
| `delete_label` | `pipefy label delete` | shipped | destructive: `--yes`. |
| `delete_organization_report` | `pipefy report-org delete` | shipped | Organization reports. |
| `delete_phase` | `pipefy phase delete` | shipped | destructive: `--yes`. |
| `delete_phase_field` | `pipefy field delete` | shipped | destructive: `--yes`. |
| `delete_pipe` | `pipefy pipe delete` | shipped | `--yes` or confirm. |
| `delete_pipe_relation` | `pipefy relation pipe delete` | shipped | destructive: `--yes`. |
| `delete_pipe_report` | `pipefy report-pipe delete` | shipped | Reports domain. |
| `delete_portal` | `pipefy portal delete` | shipped | destructive: `--yes` or confirm. |
| `delete_portal_page` | `pipefy portal page delete` | shipped | destructive: `--yes` or confirm; positional portal + page UUIDs. |
| `delete_portal_element` | `pipefy portal element delete` | shipped | destructive: `--yes` or confirm; positional element + page UUIDs. |
| `delete_sub_portal` | `pipefy portal sub-portal delete` | shipped | destructive: `--yes` or MCP `confirm`; internal_api `deleteSubPortalInterface` (irreversible). |
| `delete_sub_portal_element` | `pipefy portal sub-portal detach` | shipped | destructive: `--yes` or MCP `confirm`; internal_api `deleteSubPortalElement` (removes element wiring). |
| `delete_table` | `pipefy table delete` | shipped | destructive: `--yes`. |
| `delete_table_field` | — | deferred | Table fields; not in launch list. |
| `delete_table_record` | `pipefy record delete` | shipped | destructive: `--yes`. |
| `delete_webhook` | `pipefy webhook delete` | shipped | destructive: `--yes`. |
| `duplicate_portal_element` | `pipefy portal element duplicate` | shipped | `--element-id`, `--portal-uuid` (portal that owns the page), `--page-id` (page containing the element). |
| `execute_graphql` | `pipefy graphql exec` | shipped | mutations require `--yes` (exit 2 without). |
| `export_automation_jobs` | `pipefy export automation-jobs` (also `pipefy automation export jobs`) | shipped | (`--organization`, `--period`). |
| `export_organization_report` | `pipefy report-org export` | shipped | Exports + organization reports. |
| `export_pipe_audit_logs` | `pipefy audit export` | shipped | (`--pipe`); API queues export (JSON payload only). |
| `export_pipe_report` | `pipefy report-pipe export` | shipped | Exports + reports; `filter` preflight validates ReportCardsFilter shape (nested `operator` + `queries`). |
| `fill_card_phase_fields` | — | deferred | Card bulk fill; not in initial launch command list (may follow card field updates). |
| `find_cards` | `pipefy card find` | shipped | (`--pipe`, `--field`, `--value`). |
| `find_records` | `pipefy record find` | shipped | (`--filter` JSON with `field_id` + `field_value`). Unified MCP envelope: top-level `pagination` uses `has_more` / `end_cursor` / `page_size` (same as `get_table_records`). |
| `get_agents_usage` | `pipefy usage agents` | shipped | (`--organization`, `--from`, `--to`, optional `--filters` / `--search` / `--sort` JSON). |
| `get_ai_agent` | `pipefy agent get` | shipped | AI Agents domain. |
| `get_ai_agent_log_details` | `pipefy agent logs get` | shipped | AI Agents domain. |
| `get_ai_agent_logs` | `pipefy agent logs list` | shipped | AI Agents domain. |
| `get_ai_agents` | `pipefy agent list` | shipped | AI Agents domain. |
| `get_ai_automation` | `pipefy ai-automation get` | shipped | AI Automations domain. |
| `get_ai_automations` | `pipefy ai-automation list` | shipped | AI Automations domain. |
| `get_ai_credit_usage` | `pipefy usage credits` | shipped | (`--organization`, `--period`). |
| `get_automation` | `pipefy automation get` | shipped | — |
| `get_automation_actions` | `pipefy automation actions list` | shipped | (`--pipe`). |
| `get_automation_event_attributes` | `pipefy automation event-attributes` | shipped | Official ``field_map`` event-attribute token catalog. |
| `get_automation_execution_metrics` | `pipefy usage execution-metrics` | shipped | (`--organization`, optional repeatable `--automation`, optional `--repo`, `--period`; filters `--action`, `--event`, `--active/--inactive`, `--search`, `--sort-by`, `--sort-order`; paging `--first`, `--after`). Omit `--automation` to fetch metrics for all automations in the org. Partial success: returns metrics for permitted automations plus `partial_errors` for denied ids. |
| `get_automation_events` | `pipefy automation events list` | shipped | (`--pipe`). |
| `get_automation_jobs_export` | `pipefy automation export status` | shipped | (export id argument). |
| `get_automation_jobs_export_csv` | `pipefy export automation-jobs-csv` (also `pipefy automation export csv`) | shipped | (export id argument). |
| `get_automation_logs` | `pipefy automation logs --automation` | shipped | (mutually exclusive with `--repo`). |
| `get_automation_logs_by_repo` | `pipefy automation logs --repo` | shipped | — |
| `get_automations` | `pipefy automation list` | shipped | (optional `--organization` / `--pipe`). |
| `get_automations_usage` | `pipefy usage automations` (also `pipefy automation usage`) | shipped | (`--organization`, `--from`, `--to` ISO range). |
| `get_card` | `pipefy card get` | shipped | Supports `--include-fields`. |
| `get_card_inbox_emails` | `pipefy email inbox list` | shipped | (`--card`). |
| `get_card_relations` | `pipefy relation card list` | shipped | (raw ``get_card_relations`` payload). |
| `get_cards` | `pipefy card list` | shipped | ``list`` maps to ``get_cards`` (``--pipe``, ``--title``, ``--search`` JSON / ``CardSearch``, ``--include-fields``, ``--first`` / ``--after``). Use ``pipefy card find`` for ``find_cards`` (single field equality). |
| `get_email_templates` | `pipefy email template list` | shipped | (`--repo`). |
| `get_field_condition` | `pipefy field-condition get` | shipped | — |
| `get_field_conditions` | `pipefy field-condition list` | shipped | (`--phase`). |
| `get_labels` | `pipefy label list` | shipped | — |
| `get_organization` | `pipefy org get` | shipped | Organization-level read; out of v0.1 parity per spec. |
| `get_organization_report` | `pipefy report-org get` | shipped | Organization reports. |
| `get_organization_report_export` | (poll via `pipefy report-org export --format json`) | shipped | Organization reports + export-shaped. |
| `get_organization_reports` | `pipefy report-org list` | shipped | Organization reports. |
| `get_phase_allowed_move_targets` | `pipefy phase targets` | shipped | Read-only; mirrors Phase -> Connections (`cards_can_be_moved_to_phases`). |
| `get_phase_cards` | `pipefy phase cards` | shipped | ``Phase.cards`` pagination (``--first`` default 50, ``--after``, ``--include-fields``). Prefer over ``get_cards`` for phase-local inventory. |
| `get_phase_cards_count` | `pipefy phase count` | shipped | Native ``Phase.cards_count`` via ``get_phase``; pair with ``get_phase_cards`` to list. |
| `get_phase_fields` | `pipefy field list --phase` | shipped | ``pipefy phase get`` returns the same shape. |
| `get_pipe` | `pipefy pipe get` | shipped | `phases[].cards_count` on workflow phases; `start_form_fields` for start-form intake (start form not in `phases[]`). |
| `get_pipe_members` | `pipefy member list` | shipped | — |
| `get_pipe_relations` | `pipefy relation pipe list` | shipped | — |
| `get_pipe_report` | `pipefy report-pipe get` | shipped | Reports domain. |
| `get_pipe_report_columns` | `pipefy report-pipe columns` | shipped | Reports domain. |
| `get_pipe_report_export` | (poll via `pipefy report-pipe export --format json`) | shipped | Reports + exports. |
| `get_pipe_report_filterable_fields` | `pipefy report-pipe filterable-fields` | shipped | Reports domain. |
| `get_pipe_reports` | `pipefy report-pipe list` | shipped | Reports domain. |
| `get_portal` | `pipefy portal get` | shipped | Interfaces schema; read-only; includes `published`. |
| `get_start_form_fields` | `pipefy pipe start-form` | shipped | optional ``--required-only``. |
| `get_table` | `pipefy table get` | shipped | — |
| `get_table_record` | `pipefy record get` | shipped | — |
| `get_table_records` | `pipefy record find` | shipped | (omit `field_id`/`field_value` in `--filter`; uses ``--first`` / ``--after``). |
| `get_table_relations` | `pipefy relation table list` | shipped | ``--ids`` CSV of table-relation IDs (not database ``table_id``). |
| `get_tables` | `pipefy table list --ids` | shipped | name search uses the same command without ``--ids``. |
| `get_webhooks` | `pipefy webhook list` | shipped | — |
| `introspect_mutation` | `pipefy introspect mutation` | shipped | (JSON default; optional `--rich`). |
| `introspect_query` | `pipefy introspect query` | shipped | — |
| `introspect_type` | `pipefy introspect type` | shipped | — |
| `invite_members` | `pipefy member invite` | shipped | — |
| `list_portals` | `pipefy portal list` | shipped | `--organization-uuid`; at most one main portal per org. |
| `move_card_to_phase` | `pipefy card move` | shipped | (`--phase`). |
| `publish_sub_portal` | `pipefy portal sub-portal publish` | shipped | internal_api `updateSubPortalElement` on a templated `forms` element; check `subPortals[].published` via `get_portal`. |
| `remove_member_from_pipe` | `pipefy member remove` | shipped | — |
| `search_pipes` | `pipefy pipe list` | shipped | (`--name`, `--max-per-org`). |
| `search_schema` | `pipefy introspect schema search` | shipped | (optional `--kind`). |
| `search_tables` | `pipefy table list` | shipped | (without ``--ids``). |
| `send_email_with_template` | `pipefy email template send` | shipped | (`--card`, `--template`). |
| `send_inbox_email` | `pipefy email inbox send` | shipped | (`--from-email`, `--to`, `--subject`, `--body`). |
| `set_role` | `pipefy member set-role` | shipped | — |
| `set_table_record_field_value` | `pipefy record update` | shipped | (``--field-id`` + ``--value``). |
| `simulate_automation` | `pipefy automation simulate` | shipped | (`--pipe`, `--action-id`, `--sample-card`, optional JSON fragments). |
| `sort_portal_pages` | `pipefy portal page sort` | shipped | `--portal-uuid` plus ordered ids via `--page-ids` or `--ids-json`. |
| `toggle_ai_agent_status` | `pipefy agent toggle` | shipped | AI Agents domain. |
| `unpublish_sub_portal` | `pipefy portal sub-portal unpublish` | shipped | internal_api `updateSubPortalElement(subPortalUuid: null)`; sets `subPortals[].published` to false. |
| `update_ai_agent` | `pipefy agent update` | shipped | AI Agents domain. |
| `update_ai_automation` | `pipefy ai-automation update` | shipped | AI Automations domain. |
| `update_automation` | `pipefy automation update` | shipped | (`--extra` JSON). |
| `update_card` | `pipefy card update` | shipped | (`--field-updates` JSON, optional title/labels/assignees/due-date). |
| `update_card_field` | `pipefy card update` | shipped | Use `--field-updates` JSON array (). |
| `update_comment` | `pipefy card comment update` | shipped | — |
| `update_field_condition` | `pipefy field-condition update` | shipped | (`--extra` JSON). |
| `update_label` | `pipefy label update` | shipped | `color` must be hex `#RGB` or `#RRGGBB` (validated before GraphQL). |
| `update_organization_report` | `pipefy report-org update` | shipped | Organization reports; `filter` preflight validates ReportCardsFilter shape (nested `operator` + `queries`). |
| `update_phase` | `pipefy phase update` | shipped | — |
| `update_phase_field` | `pipefy field update` | shipped | (``--extra`` JSON). Optional ``phase_id`` / ``pipe_id`` in ``--extra`` resolve slug ``field_id`` to ``internal_id`` when ``uuid`` is omitted. |
| `update_pipe` | `pipefy pipe update` | shipped | (`--name`, `--icon`, `--color`, `--preferences` JSON). |
| `update_pipe_relation` | `pipefy relation pipe update` | shipped | — |
| `update_pipe_report` | `pipefy report-pipe update` | shipped | Reports domain; `filter` preflight validates ReportCardsFilter shape (nested `operator` + `queries`). |
| `update_portal` | `pipefy portal update` | shipped | (`--name`, `--visibility`, optional `--color`, `--icon`, header flags). |
| `update_portal_page` | `pipefy portal page update` | shipped | positional portal + page UUIDs; at least one of `--title`, `--description`, `--index`. |
| `update_portal_page_layout` | `pipefy portal page layout update` | shipped | `--page-id` + `--layout` JSON only (no portal UUID on the wire). |
| `update_portal_element` | `pipefy portal element update` | shipped | positional element + page UUIDs; `--type` + full `--metadata` JSON (API replace-all). |
| `update_sub_portal_element` | `pipefy portal sub-portal attach` | shipped | positional portal, element, and sub-portal UUIDs; internal_api `updateSubPortalElement`. |
| `update_table` | `pipefy table update` | shipped | — |
| `update_table_field` | — | deferred | Table fields; not in launch list. |
| `update_table_record` | `pipefy record update` | shipped | (``--fields`` JSON). |
| `update_webhook` | `pipefy webhook update` | shipped | — |
| `upload_attachment_to_card` | `pipefy attachment upload --card` | shipped | (also needs `--organization`, `--field`, `--file`). |
| `upload_attachment_to_table_record` | `pipefy attachment upload --record` | shipped | (same supporting flags as card). |
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

Expect **152** tool names in `PIPEFY_TOOL_NAMES` and **152** data rows in the parity table (excluding the header rows).

When adding or removing an MCP tool, update **this file** and `PIPEFY_TOOL_NAMES` in the same change set.
