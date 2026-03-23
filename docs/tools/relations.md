# Connections & Relations

Link processes and cards across workflows. **6 tools.**

## Key concepts

- **Pipe relations** define parent/child structure between pipes (who connects to whom, constraints, auto-fill). Use `get_pipe_relations` on a pipe to list relation IDs and metadata.
- **Card relations** connect individual cards through an existing pipe relation: pass `source_id` = that pipe relation's ID (from `get_pipe_relations`). Default `sourceType` is `PipeRelation`; use `extra_input` (e.g. `sourceType: Field`) when the API requires a field-based link — see `introspect_type` on `CreateCardRelationInput`.
- **Table relations** in GraphQL are loaded by table-relation ID, not by database table ID: `get_table_relations` takes a non-empty list of those IDs (root `table_relations` query).

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_pipe_relations` | Yes | Lists parent/child pipe relations for a pipe. |
| `get_table_relations` | Yes | Batch-loads table relations by relation ID list. |
| `create_pipe_relation` | No | Creates a parent-child relation between two pipes; optional `extra_input` (camelCase) for `CreatePipeRelationInput`. |
| `update_pipe_relation` | No | Updates relation config; `name` required; optional `extra_input` for other `UpdatePipeRelationInput` keys. |
| `delete_pipe_relation` | No | Permanently deletes a pipe relation (`destructiveHint=True` — confirm with the user first). |
| `create_card_relation` | No | Links a child card to a parent card via `source_id` (pipe relation ID); optional `extra_input` for `CreateCardRelationInput`. Mutations support `debug=true` on errors. |
