# pipefy-sdk

**Vendor API SDK** for Pipefy's GraphQL API: the shared library consumed by `pipefy-mcp-server` and `pipefy-cli` (not a generic “shared utils” layer). It owns HTTP/GraphQL transport, service classes, query constants, Pydantic models, shared settings, exceptions, and utilities.

## Status

Workspace-internal in v0.1; publishing **`pipefy-sdk`** to PyPI is gated separately from CLI/MCP (see **`RELEASE.md`** Trusted Publishing notes).

## Usage (within the monorepo)

```python
from pipefy_sdk import PipefyClient

client = PipefyClient(...)
card = await client.get_card(card_id="12345")
```

## Development

From the **repository root**:

```bash
uv sync                               # installs all workspace members
uv run pytest packages/sdk/tests      # SDK unit tests in isolation
uv run ruff check packages/sdk/src    # lint
```

See the root [`README.md`](../../README.md), [`docs/config.md`](../../docs/config.md) for `PIPEFY_*` environment variables and `config.toml` schema, and [`docs/sdk/README.md`](../../docs/sdk/README.md) for SDK-oriented notes.
