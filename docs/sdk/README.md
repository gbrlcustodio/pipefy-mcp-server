# SDK documentation

This tree summarizes how to work with **`pipefy`**: the vendor GraphQL client, services, models, and queries shared by the MCP server and CLI.

## Using the library

- Import **`PipefyClient`** from `pipefy_sdk` and call facade methods; domain logic lives under `packages/sdk/src/pipefy_sdk/services/`.
- GraphQL operations are static `gql()` constants under `packages/sdk/src/pipefy_sdk/queries/` — do not build query strings dynamically.
- Pydantic input models live in `packages/sdk/src/pipefy_sdk/models/`.

For a short in-repo overview and dev commands, see **[`../../packages/sdk/README.md`](../../packages/sdk/README.md)**.

## Errors

`PipefyError` is the root of the API error types. Catch it to handle a failure
the Pipefy API reported:

```python
from pipefy_sdk import PipefyError, PipefyGraphQLError

try:
    await client.get_pipe(pipe_id)
except PipefyGraphQLError as exc:
    # exc.errors is the raw per-node error dict list, each with its own
    # message and extensions; read codes off that rather than the message text.
    codes = [(e.get("extensions") or {}).get("code") for e in exc.errors]
except PipefyError:
    # any other failure the API reported; see the carve-outs below
    ...
```

The hierarchy:

- **`PipefyError`** — root of the API error types below.
- **`PipefyAPIError`** — the API returned an error payload.
- **`PipefyGraphQLError`** — a GraphQL response carried `errors`. Subclasses `PipefyAPIError`, and carries the raw list on `.errors`. This is what most failures arrive as.

Catch the specific type before the root, since `except PipefyError` also catches
`PipefyGraphQLError` and would otherwise shadow it.

Other exported error types sit outside this root. Catch these by name:

- **`PortalPermissionError`** subclasses `ValueError`. That parentage is what
  maps a portal permission denial to CLI exit code 2 rather than 1.
- **`AttachmentUploadError`** and **`KnowledgeBaseDocumentUploadError`**
  subclass `Exception`.

Transport-level failures (connection refused, timeouts) surface as `gql`'s
`TransportError`, which the SDK does not wrap.

## Destructive operations

The SDK does not gate deletion. Every `delete_*` and `remove_*` method runs the mutation as soon as you call it. Enforcing a preview/confirm step is the caller's job, for all of them — `delete_pipe` and `delete_table` say so in their docstrings, and the same obligation applies to the rest.

`pipefy_sdk.destructive_confirmation` ships the helpers that step needs, so an in-process consumer runs the same protocol the MCP server runs:

```python
import time

from pipefy_sdk import (
    confirmation_signing_key,
    mint_confirmation_token,
    verify_confirmation_token,
)

# Derive the key from THIS caller's own credential, never a shared constant.
key = confirmation_signing_key(caller_bearer)
identity = {"pipe_id": pipe_id}

# First call: describe what would be deleted, and hand the token back.
token = mint_confirmation_token(
    tool_name="delete_pipe",
    resource_identity=identity,
    key=key,
    now=int(time.time()),
)

# Second call: the caller returns the token. Delete only when it verifies.
if verify_confirmation_token(
    token,
    tool_name="delete_pipe",
    resource_identity=identity,
    key=key,
    now=int(time.time()),
):
    await client.delete_pipe(pipe_id)
```

The token binds one operation name, one canonicalized resource identity, and one `key`. It expires after `DESTRUCTIVE_CONFIRMATION_TTL_SECONDS`. Verification is stateless HMAC, so no server-side store is needed. `tool_name` is any stable label for the operation: the MCP server passes its tool name, and a library consumer passes its own.

`confirmation_signing_key` derives the `key` from one caller's credential. Use it per caller. A single module-level key defeats the binding, because every token then verifies for every caller, and nothing in the SDK can catch that for you.

`classify_confirmation_token_failure` says **why** verification would fail (`missing`, `invalid_or_expired`, `identity_mismatch`) so you can word the rejection. It is diagnostic only. Never let it authorize the deletion — that stays behind `verify_confirmation_token`.

The token orders the two steps. It is not an authorization control: the API permission on the credential remains the boundary that allows or denies the deletion.

## Configuration

OAuth and endpoint variables are documented in **[`../config.md`](../config.md)** and **[`../../.env.example`](../../.env.example)**. Integration tests use `@pytest.mark.integration` and the same `PIPEFY_*` keys from local **`.env`** (e.g. `PIPEFY_PORTAL_ORG_UUID` for portal live tests). Unit tests use fictional ids in **[`../../packages/sdk/tests/_shared/fixture_ids.py`](../../packages/sdk/tests/_shared/fixture_ids.py)** — not production org UUIDs.

## Relationship to MCP and CLI

The SDK has **no** MCP or Typer dependencies. `pipefy-mcp-server` and `pipefy-cli` both depend on `pipefy` only. Feature parity between MCP tools and CLI commands is tracked in **[`../parity.md`](../parity.md)**.
