# Connections & Relations

Link processes and cards across workflows. **8 tools.**

## Key concepts

- **Pipe relations** define parent/child structure between pipes (who connects to whom, constraints, auto-fill). Use `get_pipe_relations` on a pipe to list relation IDs and metadata.
- **Card relations** connect individual cards through an existing pipe relation: pass `source_id` = that pipe relation's ID (from `get_pipe_relations`). Default `sourceType` is `PipeRelation`; use `extra_input` (e.g. `sourceType: Field`) when the API requires a field-based link — see `introspect_type` on `CreateCardRelationInput`. The GraphQL `Card` type exposes **`child_relations`** and **`parent_relations`** (snake_case); the MCP maps them to tool output keys of the same shape.
- **Table relations** in GraphQL are loaded by table-relation ID, not by database table ID: `get_table_relations` takes a non-empty list of those IDs (root `table_relations` query).

## Common mistakes (agents)

- **`get_table_relations` + `table_id`:** The tool argument is `relation_ids` (table **relation** IDs). The database table id from `search_tables` / `get_table` is the wrong kind of id — the MCP client may reject the call or GraphQL will not find what you expect.
- **`create_card_relation` + wrong `source_id`:** `source_id` must be a **pipe relation** id from `get_pipe_relations`. It is not a table-relation id, not a `table_id`, and not a pipe/card id.
- **Symmetry trap:** `get_pipe_relations(pipe_id)` takes a pipe id, but `get_table_relations(relation_ids)` does **not** take a table id — the APIs differ by design.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_pipe_relations` | Yes | Lists parent/child pipe relations for a pipe. |
| `get_table_relations` | Yes | Batch-loads table relations by relation ID list. |
| `create_pipe_relation` | No | Creates a parent-child relation between two pipes; optional `extra_input` (camelCase) for `CreatePipeRelationInput`. |
| `update_pipe_relation` | No | Updates relation config; `name` required; optional `extra_input` for other `UpdatePipeRelationInput` keys. |
| `delete_pipe_relation` | No | Permanently deletes a pipe relation (`destructiveHint=True` — confirm with the user first). |
| `create_card_relation` | No | Links a child card to a parent card via `source_id` (pipe relation ID); optional `extra_input` for `CreateCardRelationInput`. Mutations support `debug=true` on errors. |
| `get_card_relations` | Yes | Lists `child_relations` and `parent_relations` for a card (linked cards and pipes). |
| `delete_card_relation` | No | Removes a card link (`destructiveHint=True`). Public GraphQL may not expose the underlying delete mutation on all tenants. |
