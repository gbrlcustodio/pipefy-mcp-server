---
name: pipefy-database-tables
description: >
  Use this skill when the user wants to work with Pipefy Database Tables —
  creating/reading/updating/deleting tables, records (rows), or table fields
  (schema columns). Covers 17 MCP tools.
tags: [pipefy, database, tables, records, fields]
---

# Database Tables

Tables, records (rows), schema columns (table fields), and attachments for Pipefy Database Tables. **17 MCP tools.**

**CLI status (v0.1):** table, record, and field commands ship today; table-record attachment upload on the CLI is planned for v0.3+.

---

## Cross-cutting patterns

- Same conventions as pipe building: `introspect_type` on inputs such as `CreateTableFieldInput` / `UpdateTableFieldInput`, `debug=true` on mutations.
- **Pagination:** `get_table_records` and `find_records` support `first` / `after`. With the unified MCP envelope, read top-level `pagination.has_more` and `pagination.end_cursor` (and `pagination.page_size`) and pass `after=end_cursor` for the next page (default page size is 50).
- **Destructive deletes** (`delete_table`, `delete_table_record`, `delete_table_field`) use a **mandatory two-step flow**: call without `confirm=true` first (preview), then with `confirm=true` after user approves.

---

## Table operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_tables` | `pipefy table list` | Yes | List database tables by org. |
| `search_tables` | `pipefy table list --search` | Yes | Search tables by name. |
| `get_table` | `pipefy table get <id>` | Yes | Table metadata and field schema. |
| `create_table` | `pipefy table create` | No | Create a new database table. |
| `update_table` | `pipefy table update <id>` | No | Rename or change settings. |
| `delete_table` | `pipefy table delete <id>` | No | **Two-step destructive.** |

---

## Table field (schema column) operations

| Tool (MCP) | CLI | Purpose |
|------------|-----|---------|
| `create_table_field` | `pipefy field create --table <id>` | Add a column to a table schema. |
| `update_table_field` | `pipefy field update <id>` | Rename or reorder a column. |
| `delete_table_field` | `pipefy field delete <id>` | **Two-step destructive.** |

---

## Record operations

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_table_records` | `pipefy record find --table <id>` | Yes | Paginated list of all records in a table. |
| `find_records` | `pipefy record find --filter` | Yes | Filter records by field value (JSON filter). |
| `get_table_record` | `pipefy record get <id>` | Yes | Single record with all field values. |
| `create_table_record` | `pipefy record create` | No | Add a row to a table. |
| `update_table_record` | `pipefy record update <id>` | No | Update one or more field values on a row. |
| `delete_table_record` | `pipefy record delete <id>` | No | **Two-step destructive.** |

---

## Steps — find and update a record

1. **Get table ID** (if not known):

   MCP: `get_tables organization_id=123`

   CLI: `pipefy table list`

2. **Find the record:**

   MCP: `find_records table_id=456 filter='{"column_id":"email","search_value":"user@example.com"}'`

   CLI: `pipefy record find --table 456 --filter '{"column_id":"email","search_value":"user@example.com"}'`

3. **Update the record:**

   MCP: `update_table_record record_id=789 node_fields='[{"field_id":"status","field_value":"Active"}]'`

   CLI: `pipefy record update 789 --fields '{"status":"Active"}'`

---

## Attachment uploads

| Tool (MCP) | CLI | Purpose |
|------------|-----|---------|
| `upload_attachment_to_table_record` | — (CLI v0.3+) | Attach a file to a table record. |

---

## Success criteria

- `get_table_records` returns the created/updated records with correct field values.
- Schema changes reflect immediately in `get_table`.

## Failure modes

- **`create_table_field` rejects type:** call `introspect_type type_name="CreateTableFieldInput"` for valid field types.
- **`find_records` returns empty:** check that `column_id` matches a field's ID (not label) from `get_table`.
- **Pagination cursor expired:** re-fetch from the beginning; cursors are short-lived.

## See also

- `skills/relations/` — connect tables to pipes.
- `skills/introspection/` — discover field input schemas.
