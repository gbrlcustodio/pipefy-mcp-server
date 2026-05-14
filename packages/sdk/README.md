# pipefy-sdk

**Vendor API SDK** for Pipefy's GraphQL API. This is the shared library consumed by `pipefy-mcp-server` and `pipefy-cli` — neither package is useful without it.

The SDK owns all Pipefy API semantics: HTTP/GraphQL transport, service classes, query constants, Pydantic models, shared settings, exceptions, and utilities.

See [ADR 0003](.cursor/dev-planning/specs/pipefy-labs/decisions/0003-monorepo-package-taxonomy.md) for the full taxonomy rationale (why "Vendor API SDK" and not "shared" / "common" / "core").

## Status

Workspace-internal in v0.1; not published to PyPI yet (tracked in task 12.3 / `0002-sdk-pypi-promotion.md`).

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

See the root [`README.md`](../../README.md) and [`docs/setup.md`](../../docs/setup.md) for `PIPEFY_*` environment variables.
