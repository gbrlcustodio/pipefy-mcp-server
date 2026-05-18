# CLI self-healing: introspect then execute

See also the **[CLI docs index](README.md)** for other CLI-oriented guides.

This flow is the canonical **Tier 2** fallback when no dedicated MCP tool or Typer command exists for an operation: discover the GraphQL shape from the schema, then run the operation with explicit confirmation for mutations.

## 1. Search the schema

```bash
uv run pipefy introspect schema search label
```

Use keywords that match type or field names (case-insensitive).

## 2. Inspect the operation

For a mutation root field:

```bash
uv run pipefy introspect mutation createLabel
```

For a query root field:

```bash
uv run pipefy introspect query pipe
```

For an input or object type:

```bash
uv run pipefy introspect type CreateLabelInput
```

Default output is **JSON**. Add `--rich` for a syntax-highlighted view in the terminal.

## 3. Run GraphQL

Read-only query (variables default to `{}`):

```bash
uv run pipefy graphql exec --query 'query Q($id: ID!) { pipe(id: $id) { id name } }' --vars '{"id":"123"}' --json
```

Mutations require **`--yes`** or the CLI exits with code **2**:

```bash
uv run pipefy graphql exec --query 'mutation M($input: CreateLabelInput!) { createLabel(input: $input) { label { id } } }' --vars '{"input":{"pipeId":1,"name":"X","color":"#000000"}}' --yes --json
```

Malformed `--vars` JSON also exits with code **2**.

## Security notes

- There is no server-side blocklist: scope is limited by the **token** (service account or user) used for `pipefy`.
- Prefer dedicated tools when they exist; they validate inputs and normalize errors.

## Related docs

- Parity matrix: `docs/parity.md`
- MCP introspection tools map 1:1 to `pipefy introspect` subcommands (task **9.2**).
