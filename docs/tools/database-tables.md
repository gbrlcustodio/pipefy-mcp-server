# Database Tables

Tables, records (rows), and schema columns (table fields) for org Database Tables. **17 tools.**

## Cross-cutting patterns

- Same conventions as pipe building: `introspect_type` on inputs such as `CreateTableFieldInput` / `UpdateTableFieldInput`, `debug=true` on mutations, `extra_input` where the tool exposes it.
- **Pagination:** `get_table_records` and `find_records` support `first` / `after`. Read `pageInfo.hasNextPage` and `pageInfo.endCursor` from the response and pass `after=endCursor` for the next page (default page size for listing records is 50; caps apply — see tool docstrings).

---

| Domain | Tools | Notes |
|--------|-------|-------|
| **Read** | `get_table`, `get_tables`, `get_table_records`, `get_table_record`, `find_records` | |
| **Table CRUD** | `create_table`, `update_table`, `delete_table` | `delete_table` uses preview + `confirm=true` (like `delete_pipe`). |
| **Record CRUD** | `create_table_record`, `update_table_record`, `delete_table_record`, `set_table_record_field_value` | |
| **Field CRUD** | `create_table_field`, `update_table_field`, `delete_table_field` | Schema columns; `delete_table_field` is destructive (confirm with the user). |
