# Identifiers: which tool expects which id

Pipefy exposes several identifier forms, and different tools expect different ones. This is the canonical map of which form each tool and argument wants, so you don't have to learn it by trial. Per-area guides link here rather than each keeping their own partial list.

## The four forms

| Form | Looks like | What it is |
| --- | --- | --- |
| **numeric id** | `"303088927"` | The node's numeric database id, as a string. Pipes, cards, organizations, automations. GraphQL types it as `ID` — always pass a string; a JSON integer is coerced to the same string. |
| **uuid** | `"5f66417e-5adc-4c83-908f-0b888493c847"` | The node's UUID. Pipe UUID (`repo_uuid` / `pipe_uuid`), organization UUID, portal UUID, agent UUID, data-source id, log UUID. |
| **slug** | `"document_upload"` | A field's human-readable id (GraphQL `id` on a field row). Used to address a **card** field for a one-off edit. |
| **internal_id** | `"429659034"` | A field's numeric id (GraphQL `internal_id` on a field row). Used by automations, field conditions, and AI prompt/behavior field references. |

Discover ids with `list_organizations` (org id + uuid, no input needed), `search_pipes` / `get_pipe` (pipe id + uuid), and `get_start_form_fields` / `get_phase_fields` (a field's `id` = slug **and** `internal_id`).

## The pipe has five argument names

The single biggest source of wrong-id errors: the same pipe is addressed by five different argument names across tools, in two different forms. Read the form from this table, not the name.

| Argument | Form | Where |
| --- | --- | --- |
| `pipe_id` | numeric id | pipes/cards, automations, relations, most tools |
| `repo_id` | numeric id (string) | observability automation-by-repo logs (`get_automation_logs_by_repo`) |
| `source_repo_id` | numeric id | knowledge-base data lookups (a UUID is accepted on create but breaks at index time — use the numeric id) |
| `repo_uuid` | **uuid** | AI agents (`get_ai_agents`, `create_ai_agent`, …), AI agent logs |
| `pipe_uuid` | **uuid** | knowledge-base tools |

## UUID-named arguments that also accept a numeric id

A few arguments are named `*_uuid` but the API resolves a numeric id too. Prefer the UUID; a numeric id is a documented fallback:

- `get_ai_credit_usage(organization_uuid)`
- `list_portals(organization_uuid)`, `create_portal(organization_uuid)`

Everywhere else, an argument named `*_uuid` wants a UUID and an argument named `*_id` wants a numeric id.

## Field references: slug vs internal_id

A field is addressed by **slug** for one-off card edits, and by **internal_id** everywhere a rule or prompt references it.

| Surface | Field identifier |
| --- | --- |
| `update_card_field` / `update_card` field keys | **slug** |
| `create_card` / `fill_card_phase_fields` field keys | **slug** |
| `upload_attachment_to_card` (`field_id`) | **slug** (a UUID returns `RESOURCE_NOT_FOUND`) |
| `set_table_record_field_value` / `upload_attachment_to_table_record` (`field_id`) | **slug** |
| Traditional automation `action_params.field_map[].fieldId` | **internal_id** (a slug typically yields `INTERNAL_SERVER_ERROR`) |
| Automation / AI-automation `condition.expressions[].field_address` | **internal_id** (the last dotted segment for a connected-card field) |
| Field condition `condition.expressions[].field_address` and `actions[].phaseFieldId` | **internal_id** |
| AI automation prompt / AI agent behavior `%{…}` references | **internal_id** |
| Data-lookup `output_fields` / `conditions[].field` | **slug** (plus statics like `id`, `title`, `current_phase`) |

`get_phase_fields` / `get_start_form_fields` return both the `id` (slug) and the `internal_id` for each field, so you can pick the form the target surface needs.

### Phase fields (create vs update)

`create_phase_field` returns both the `id` (slug) and the `internal_id`. To update or delete a phase field, pass its **slug** as `field_id` together with `phase_id` (or `pipe_id`), and the SDK resolves it to the internal id; a numeric `internal_id` is also accepted, and a `uuid` disambiguates when a slug is ambiguous.

## Per-area quick reference

### Pipes & cards
- `get_pipe` / `get_card` / `create_card` / `move_card_to_phase`: numeric ids (`pipe_id`, `card_id`, `destination_phase_id`).
- Field references: see [Field references](#field-references-slug-vs-internal_id) above.

### AI agents & knowledge bases
- AI agent tools scope by `repo_uuid` (pipe **UUID**); the agent itself is addressed by its own `uuid`.
- Knowledge-base tools scope by `pipe_uuid` (pipe **UUID**); items (plain text, document, data source) by their data-source **UUID**; data lookups read `source_repo_id` (numeric pipe id).
- `dataSourceIds` / `data_source_ids`: knowledge-base item **UUIDs**.

### Automations
- `create_automation` / `create_ai_automation`: `pipe_id` numeric; `automation_id` (get/update/delete) is the automation's own id, not the pipe's.
- Field references inside `field_map` and `condition`: **internal_id** (see above).

### Tables & records
- `table_id` and record ids are strings — numeric or an opaque token (e.g. `"fIVcd19N"`). Record field references use the field **slug**.

### LLM providers
- List / dependencies / create / update / delete: `organization_uuid` (**UUID**).
- Default get / set / reset: numeric `organization_id` / `owner_id`.
- `get_available_ai_models(provider_name)`: the vendor's snake_case name (e.g. `amazon_bedrock`), not the hyphenated `configuration.provider`.

### Observability
- `get_ai_agent_logs(repo_uuid)` (pipe UUID); `get_ai_agent_log_details(log_uuid)`.
- `get_automation_logs_by_repo(repo_id)` (numeric pipe id, string); `get_automation_logs(automation_id)`.
- Usage tools take `organization_uuid` (UUID); metrics/export take numeric `organization_id`; `get_ai_credit_usage(organization_uuid)` accepts UUID or numeric.

### Organization, portal, relations, reports
- `list_organizations`: no id. `get_organization(organization_id)`: numeric id.
- Portal: `organization_uuid` (UUID or numeric); `portal_uuid` (interface UUID).
- Relations: `get_pipe_relations(pipe_id)` (numeric pipe id); `get_table_relations(relation_ids)` (table-**relation** ids, not table ids); `create_card_relation(source_id)` = a pipe-relation id from `get_pipe_relations`.
- Reports: filter `field` values come from `get_pipe_report_filterable_fields`.
