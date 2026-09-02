# SDK documentation

This tree summarizes how to work with **`pipefy`**: the vendor GraphQL client, services, models, and queries shared by the MCP server and CLI.

## Using the library

- Import **`PipefyClient`** from `pipefy_sdk` and call facade methods; domain logic lives under `packages/sdk/src/pipefy_sdk/services/`.
- GraphQL operations are static `gql()` constants under `packages/sdk/src/pipefy_sdk/queries/` — do not build query strings dynamically.
- Pydantic input models live in `packages/sdk/src/pipefy_sdk/models/`.

For a short in-repo overview and dev commands, see **[`../../packages/sdk/README.md`](../../packages/sdk/README.md)**.

## Typed mutation inputs

Write methods take one typed input model that mirrors the GraphQL input object, field for field:

```python
from pipefy_sdk.graphql_inputs import UpdatePipeInput

await client.update_pipe(UpdatePipeInput(id=pipe_id, name="Onboarding", color="blue"))
```

The model carries the `id`, because `UpdatePipeInput.id` is `ID!` in the schema. Fields you leave unset are not sent, so a partial update stays partial. The consequence is that no field can be sent as an explicit `null`.

A misspelled field is rejected by name, before the request:

```python
UpdatePipeInput(id=pipe_id, nmae="Onboarding")
# pydantic_core.ValidationError: nmae — Extra inputs are not permitted
```

This adds no rule of its own. Pipefy answers the same call with `InputObject 'UpdatePipeInput' doesn't accept argument 'nmae'`; the model only moves the rejection to before the round trip. `pipefy_sdk.graphql_inputs.describe_input_rejection` turns that `ValidationError` into one line naming the field, which is how the MCP tools and the CLI word their own message.

Three details are worth knowing:

- **`ID` is not coerced.** A GraphQL `ID` accepts a string or an integer and the models pass through whichever you gave. `createFieldCondition` needs integers in `expressions_structure` and answers strings with an opaque 500, so coercing either way would break one caller to serve another.
- **Enums are soft.** A GraphQL enum is typed `str`, and the documented values are exported as a tuple (`COLORS_VALUES`). Any value is sent and the API validates it, so a value added server-side works without an SDK release.
- **A resolution hint is a parameter, not a field.** `update_phase_field` takes `phase_id` / `pipe_id` keyword arguments, which the mutation has no fields for. They let the SDK resolve a slug `id` to the field's `uuid` before it calls the API.
- **A field condition needs its shape repaired first.** GraphQL coerces a bare value into a single-item list, so `expressions_structure: [0]` is a legal way to write `[[0]]` on the wire. A model mirroring `[[ID]]` refuses it, so run `normalize_field_condition_fields` on the raw mapping before constructing `CreateFieldConditionInput` or `UpdateFieldConditionInput`. It is idempotent, and the service runs the same repair on the serialized payload for callers who skip it.

The models are generated from a snapshot of the live schema by `scripts/generate_graphql_inputs.py`; see [`../../packages/sdk/README.md`](../../packages/sdk/README.md) for regenerating them. Methods that still take `**attrs` are migrating one batch at a time.

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

## Configuration

OAuth and endpoint variables are documented in **[`../config.md`](../config.md)** and **[`../../.env.example`](../../.env.example)**. Integration tests use `@pytest.mark.integration` and the same `PIPEFY_*` keys from local **`.env`** (e.g. `PIPEFY_PORTAL_ORG_UUID` for portal live tests). Unit tests use fictional ids in **[`../../packages/sdk/tests/_shared/fixture_ids.py`](../../packages/sdk/tests/_shared/fixture_ids.py)** — not production org UUIDs.

## Relationship to MCP and CLI

The SDK has **no** MCP or Typer dependencies. `pipefy-mcp-server` and `pipefy-cli` both depend on `pipefy` only. Feature parity between MCP tools and CLI commands is tracked in **[`../parity.md`](../parity.md)**.
