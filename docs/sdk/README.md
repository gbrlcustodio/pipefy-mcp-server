# SDK documentation

This tree summarizes how to work with **`pipefy-sdk`**: the vendor GraphQL client, services, models, and queries shared by the MCP server and CLI.

## Using the library

- Import **`PipefyClient`** from `pipefy_sdk` and call facade methods; domain logic lives under `packages/sdk/src/pipefy_sdk/services/`.
- GraphQL operations are static `gql()` constants under `packages/sdk/src/pipefy_sdk/queries/` — do not build query strings dynamically.
- Pydantic input models live in `packages/sdk/src/pipefy_sdk/models/`.

For a short in-repo overview and dev commands, see **[`../../packages/sdk/README.md`](../../packages/sdk/README.md)**.

## Configuration

OAuth and endpoint variables are documented in **[`../setup.md`](../setup.md)** and **[`../../.env.example`](../../.env.example)**. Integration tests use `@pytest.mark.integration` and the same `PIPEFY_*` keys from local **`.env`** (e.g. `PIPEFY_PORTAL_ORG_UUID` for portal live tests). Unit tests use fictional ids in **[`../../packages/sdk/tests/_shared/fixture_ids.py`](../../packages/sdk/tests/_shared/fixture_ids.py)** — not production org UUIDs.

## Relationship to MCP and CLI

The SDK has **no** MCP or Typer dependencies. `pipefy-mcp-server` and `pipefy-cli` both depend on `pipefy-sdk` only. Feature parity between MCP tools and CLI commands is tracked in **[`../parity.md`](../parity.md)**.
