# pipefy

**Vendor API SDK** for Pipefy's GraphQL API: the shared library consumed by `pipefy-mcp-server` and `pipefy-cli` (not a generic “shared utils” layer). It owns HTTP/GraphQL transport, service classes, query constants, Pydantic models, shared settings, exceptions, and utilities.

## Status

Workspace-internal in v0.1; publishing **`pipefy`** to PyPI is gated separately from CLI/MCP (see **`RELEASE.md`** Trusted Publishing notes).

## Usage (within the monorepo)

```python
from pipefy_sdk import PipefyClient

client = PipefyClient(...)
card = await client.get_card(card_id="12345")
```

## Generated GraphQL input models

`pipefy_sdk/graphql_inputs/` mirrors the Pipefy GraphQL input objects the SDK writes to. `_generated.py` and `__init__.py` are written by `scripts/generate_graphql_inputs.py` and are not edited by hand; `_base.py` holds the parts that needed a decision rather than a mapping.

```bash
# After an API change, with Pipefy credentials (`pipefy auth login`):
uv run python scripts/generate_graphql_inputs.py snapshot   # rewrite schema/input_types.json
uv run python scripts/generate_graphql_inputs.py            # rewrite the models

# What CI runs, no credentials needed:
uv run python scripts/generate_graphql_inputs.py check
```

`check` catches a hand-edit of a generated file, or a snapshot committed without regenerating. It cannot see the API itself move, because CI has no Pipefy credentials — that is `test_input_types_snapshot_matches_live`, which is marked `integration`.

To migrate another `**attrs` method, add its input type to `ROOT_INPUT_TYPES` in the script and regenerate; the transitive closure is resolved from there.

## Development

From the **repository root**:

```bash
uv sync                               # installs all workspace members
uv run pytest packages/sdk/tests      # SDK unit tests in isolation
uv run ruff check packages/sdk/src    # lint
```

See the root [`README.md`](../../README.md), [`docs/config.md`](../../docs/config.md) for `PIPEFY_*` environment variables and `config.toml` schema, and [`docs/sdk/README.md`](../../docs/sdk/README.md) for SDK-oriented notes.
