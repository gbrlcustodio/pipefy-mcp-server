# MCP package conventions

Scoped to `packages/mcp/`. Repo-wide guidance lives in `../../AGENTS.md`. The layer model, type-ownership rule, and alternative-constructor guide are in [`../../docs/architecture.md`](../../docs/architecture.md); this package's intra-package layering is enforced by import-linter (`uv run lint-imports`).

## Distribution model

This MCP server is distributed as code that runs in the user's environment as
a subprocess of the agent runtime (Claude Code, Claude Desktop, etc.). The
trust boundary is the user; the server has the same filesystem and network
access the user already has.

Implications for tool design:

- Local filesystem inputs (`file_path`) are first-class. There is no
  path-traversal threat surface beyond what the user can already access.
- SSRF guards, redirect loops, and download size caps that defend a hosted
  server are not appropriate here. They add maintenance cost without buying
  a security boundary.

A hosted/remote distribution profile is in progress. It runs the server as a
multi-user HTTP service. Tool exposure there is **default-deny**: only tools
explicitly marked remote-safe are registered; everything else is withheld. The
marker is described below.

## Transport profiles

`pipefy-mcp-server` launches with two orthogonal flags:

- **`--profile {local|remote}`** (default `local`, env `PIPEFY_MCP_PROFILE`).
  - `local`: registers every tool and acts as the one credential resolved at
    startup. The installed-subprocess case.
  - `remote`: exposes ONLY the default-deny remote-safe tool surface and, when a
    resource-server URL is configured, validates an inbound bearer per request.
- **`--transport {stdio|http}`** (env `PIPEFY_MCP_TRANSPORT`). Left unset it follows
  the profile: `local` speaks stdio, `remote` serves over Streamable HTTP. Set it
  explicitly to run `local` over HTTP (loopback by default; see "Bind-safety
  interlock"). `remote` over stdio is rejected: a
  per-request bearer has no stdio equivalent. The pair is resolved (and validated)
  once, at startup, by `resolve_mcp_settings`.

Bind host/port come from `PIPEFY_MCP_HOST` / `PIPEFY_MCP_PORT` (defaults
`127.0.0.1:8000`), overridable with `--host` / `--port`, and matter only over HTTP.

Under `remote` the server acts on behalf of each caller: it validates the inbound
bearer per request and opens a per-request session carrying a snapshot of that
validated bearer, so concurrent callers each act as themselves rather than as a
single identity resolved at startup. All sessions share one process-scoped engine
(the GraphQL endpoints and their schema cache). `local` runs as the one credential
resolved at startup. The unauthenticated `local` profile binds loopback-only over
HTTP unless the `PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND` escape hatch is set; the
authenticated `remote` profile binds any host (see "Bind-safety interlock" below).

**Resource-server profile.** Config is split by domain. *Token validation* is an
auth concern and lives in `pipefy_auth.JwtValidationSettings` (`settings.jwt`,
env `PIPEFY_JWT_*`): `ISSUER_URL` (an override; absent it, the inbound issuer
defaults to the one this process logs into, the `OidcClient` issuer, since in a
single-realm deployment they are the same IdP), optional `AUDIENCE` /
`VERIFY_AUDIENCE` (off by default, the same-audience interim), and `JWKS_URI`.
*Resource identity* is MCP-specific and stays in `pipefy_mcp.ResourceServerSettings`
(`settings.rs`, env `PIPEFY_MCP_RS_*`): `RESOURCE_SERVER_URL` (this server's public
canonical URL, e.g. `https://host/mcp`) and `REQUIRED_SCOPES`. The shared
`PIPEFY_ALLOW_INSECURE_URLS` covers both. The profile activates when
`RESOURCE_SERVER_URL` is set (the one value that cannot default); there is no
separate enable flag, just the `remote` profile plus this URL. Set
`RESOURCE_SERVER_URL` with the stored-session login disabled and no `ISSUER_URL`
override and startup fails (no issuer to validate against).

The JWKS/RS256 validation lives in `pipefy_auth` (`JwtValidator`); the MCP adapter
`auth/resource_server.py` (`JwtTokenVerifier`) maps validated claims onto the
SDK's `AccessToken`. FastMCP serves the RFC 9728 protected-resource metadata and
the `401` + `WWW-Authenticate` challenge; `build_resource_server_auth` (same
module) pairs the verifier with `AuthSettings` from an already-resolved issuer.
The runtime (`McpRuntime.for_profile`) resolves the inbound issuer, gates on it,
and calls the builder for the `remote` profile, holding the pair as `inbound_auth`,
which `server.py` wires into the app.

**Bind-safety interlock.** The property protected is auth posture, not bind
interface: an unauthenticated profile must not be reachable by untrusted callers.
`McpSettings._enforce_bind_safety` (a `model_validator` at the settings boundary)
refuses a non-loopback HTTP bind under the unauthenticated `local` profile unless
`PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND` is set. Living at the settings boundary means
no serving path routes around it (the coverage argument, why every serving path
inherits the guarantee, lives on the `_enforce_bind_safety` docstring). The `remote` profile
validates a per-request bearer, so its bind host is irrelevant and is not checked
(a container binds `0.0.0.0` and is still private). Loopback detection is
`pipefy_infra.security.is_loopback_host`, which covers all of `127.0.0.0/8` and
`::1`. This replaced an earlier bind-interface guard (`_assert_safe_http_bind`) that
false-positived on the entire hosted profile and lived in the run path where the
ASGI-app path bypassed it. The attachment tools' local `file_path` inputs also
still assume a loopback peer that shares the client's disk (remote-safe file inputs
are separate follow-up work).

**Transport allowlist.** DNS-rebinding protection is a separate axis from the
bind-safety interlock: it checks the inbound request's `Host` / `Origin`, not the
bind interface. FastMCP auto-enables a loopback-only allowlist on the `127.0.0.1`
construction host, so behind a proxy that forwards the public `Host` it answers
`421 Misdirected Request`. `core/transport_security.py:build_transport_security`
widens it by deriving the allowed host from `resource_server_url` (the public origin
the `remote` profile already declares) plus loopback, and `build_pipefy_mcp_server`
passes the result to FastMCP. `PIPEFY_MCP_ALLOWED_HOSTS` / `PIPEFY_MCP_ALLOWED_ORIGINS`
(JSON) extend it for extra hostnames or a stricter Origin posture. Unset (no
resource-server URL and no override) leaves FastMCP's loopback-only default in force,
so the local subprocess case is unaffected. Being configuration derived at
composition (mirroring `build_resource_server_auth`), it lives in the composition
tier, not in `settings.py`, which keeps the mcp SDK out of the config boundary.

## Hosted structured logging

The HTTP transport emits allowlisted JSON lines on stderr for hosted **debugging**
(`pipefy_mcp/observability/`): one `http_request` line per request and one
`tool_call` line per tool invocation (via `tool_log_middleware`). Fields are
privacy-bounded (no bearer, no argument values, no query string, no exception
messages). Stdio does **not** install the structured emitter: under stdio,
stdout is the JSON-RPC wire, and local installs should not arm that
process-global handler.

Wiring lives in `wire_hosted_observability` (`observability/wiring.py`): it calls
`streamable_http_app()` once, attaches request middleware, and returns the Starlette app.
`run_server` serves that app with uvicorn directly (`access_log=False`) so the
structured request line replaces uvicorn's text access log.
`configure_observability_logging` pins the dedicated structured logger at `INFO`
independently of `PIPEFY_MCP_LOG_LEVEL` (which only governs FastMCP/root text
logs), so quieting noisy text does not drop request/tool lines.

The request logger is **pure-ASGI middleware** (`RequestLogMiddleware`), never
Starlette `BaseHTTPMiddleware`: `BaseHTTPMiddleware` buffers the response body,
which breaks long-lived Streamable HTTP / SSE streams. The pure-ASGI middleware
only inspects `http.response.start` (status + headers) and passes the body through.
`request_id` prefers inbound `x-request-id`, then `x-correlation-id`, and mints a
UUID only when both are absent (or blank), so an upstream proxy can keep one id
across service boundaries. Tool lines go through the same emitter builders as
HTTP lines (`build_tool_call_event` / `emit_structured_event`).

## Tool registration

Tools are registered **once, at construction** (via `_register_pipefy_tools` in
`server.py`, reached through `build_pipefy_mcp_server`, which both transports use),
not inside the FastMCP `lifespan`. The lifespan owns resources only: it yields
the already-wired app-scoped runtime as the request `lifespan_context`. This
follows the FastMCP contract, where the lifespan can run per session (per request
under Streamable HTTP) and so must not mutate the tool table.

Tools take no client at registration. Each tool function declares a
`ctx: Context` parameter (FastMCP injects it and keeps it out of the tool's
input schema) and resolves its client per request with `get_pipefy_client(ctx)`
(`tools/tool_context.py`), which reads the runtime off
`ctx.request_context.lifespan_context` and opens a session via
`session_for_request(ctx.request_context.request)`. Because a session is opened per
call rather than captured at registration, tools act as whoever is calling without
re-registering; under the hosted profile each session snapshots the bearer off that
request (the message's own validated request, not a session-wide contextvar frozen
at `initialize`), so identity is per-request. That is why there is no repeat-visit
bookkeeping: registration never repeats.

When adding a tool, give it a `ctx: Context` parameter and start its body with
`client = get_pipefy_client(ctx)`; do not pass a client through `register`.

Both transports launch through the single `run_server` entry point, which resolves
the profile/transport once (via `resolve_mcp_settings`) and builds the same app
through `build_pipefy_mcp_server` (same runtime-bound lifespan, same
`_register_pipefy_tools`), differing only in the transport `run` and HTTP's bind
concerns. `build_pipefy_mcp_server` constructs one app-scoped `McpRuntime` via
`McpRuntime.for_profile` (`core/runtime.py`) and binds the lifespan to it.
`for_profile` is the composition root's one build step: the `remote` profile picks
a per-request identity and builds the inbound resource-server `(verifier, auth)`
pair (failing fast when that profile has no resource server); every other profile
resolves the one startup credential and fails fast when none is configured
(`StartupIdentity.from_configured_credential`). So a missing credential (or, under
`remote`, a missing resource server) surfaces when the server is built at startup,
not on the first tool call. The runtime exposes the inbound pair as `inbound_auth`,
which `build_pipefy_mcp_server` reads into FastMCP. (This also means
`build_pipefy_mcp_server` resolves the credential, so the live integration tests
that build the app at import skip themselves when no creds are configured.)
Building the engine at construction is safe off the event loop: `PipefyEngine`
construction does no network I/O and binds nothing to a running loop, because its
endpoints open a fresh per-request transport at call time; the engine built at
startup serves whatever loop later handles requests. Streamable HTTP re-entering
the lifespan per session just yields the same already-wired runtime, so there is
nothing to rebuild. The runtime holds no per-request state: it opens a cheap
session per request via `session_for_request`, binding the identity's resolved
`httpx.Auth` to the shared endpoints. `StartupIdentity` resolves to the one
credential resolved at startup (stdio/local), while `RequestScopedIdentity`
snapshots each caller's validated bearer from the request context, so every session
acts as its own caller.

## Remote-profile tool marker

Under the `remote` profile (`--profile remote` / `PIPEFY_MCP_PROFILE=remote`), the
server exposes ONLY tools whose registration carries `meta=REMOTE`. Any unmarked
tool is implicitly withheld (default-deny). Under `local` (the default), all tools
register and the marker is inert.

The marker is a single co-located source of truth on the `@mcp.tool` decorator:

```python
from pipefy_mcp.tools.remote_profile import REMOTE

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), meta=REMOTE)
async def get_organization(...): ...
```

`ToolRegistry.apply_remote_profile()` reads it back via `is_remote_tool` and
removes every unmarked Pipefy tool at registration time (before the server
serves anything). The marker is greppable (`rg "meta=REMOTE" packages/mcp`) and
machine-enforced, unlike the comment-only `GATED:` convention it replaces.

Inclusion criteria for marking a tool remote-safe: it reaches the API with the
request-scoped bearer and is fully governed by API permissions; it does NOT read
the local filesystem; it does NOT read process-global settings for a per-user
decision. Opting a tool in is a deliberate, reviewed change (it shifts the
`REMOTE_SEED` drift guard in `tests/tools/test_remote_profile.py`).

### Exposure vs input restriction

The `meta` marker expresses **exposure** only: whether a tool is available in the
remote profile. The retired `GATED:` convention could also express *input*
restriction within an exposed tool. Where a remotely-exposed tool needs restricted
inputs, enforce that in the tool body at call time via
`is_remote_profile(ctx)` (`tools/tool_context.py`), not via the marker — and not
via the module-global settings singleton, which can disagree with the profile the
runtime was actually built from (embedders and tests construct runtimes from
explicit settings). The shipped instance is `create_ipaas_connection`, which
rejects `{"$env": ...}` credential references on the remote profile because they
resolve from the deployment's own environment; the attachment tools (a `file_url`
rather than a local `file_path`) would follow the same shape. A tool whose
exclusion deserves a reason gets a plain code comment stating why; the exclusion
itself needs no annotation.

## Tool-call middleware

Cross-cutting concerns that wrap a tool invocation (logging, per-user quotas,
rate limiting, cost weighting, downstream 429/circuit-breaking) register as
ordered middleware, not by overwriting the server's internal handler. The MCP SDK
dispatches every tool call through one `request_handlers[CallToolRequest]` slot;
`core/tool_middleware.py` wraps that slot once, at build time, and composes the
registered middleware around it. The middleware chain is the extension surface;
the private slot is wrapped, not written to directly.

A middleware is a plain async callable. A built-in middleware joins the per-profile
defaults (`default_tool_middlewares` in `server.py`); a consumer of
`build_pipefy_mcp_server` passes its own through `extra_tool_middlewares`, which the
builder folds into the single install after the built-ins (so the default
observability layer stays outermost). Neither path touches FastMCP internals:

```python
from pipefy_mcp.core.tool_middleware import ToolCallContext, CallNext, short_circuit_error

async def quota(ctx: ToolCallContext, call_next: CallNext):
    if over_quota(ctx.identity.client_id):
        return short_circuit_error("quota exceeded", code="RATE_LIMITED")
    return await call_next(ctx)

# a serving layer registers its own middleware through the public builder:
#   app = build_pipefy_mcp_server(settings, extra_tool_middlewares=[quota])
```

- **Order**: list order runs outer to inner around the tool. `[A, B]` runs A,
  then B, then the tool, and unwinds in reverse.
- **Short-circuit**: a middleware that returns without awaiting `call_next` skips
  the inner chain and the tool. Use `short_circuit_error`, which carries the
  canonical `tool_error` envelope but sets `isError=True` deliberately: a
  governance stop means the tool never ran, distinct from a tool that ran and
  reported a business error (`isError=False`).
- **Identity** (`ctx.identity`): the validated caller's `client_id` and `scopes`,
  read off the request's bearer, never re-decoded. Empty under stdio/local (no
  inbound bearer). The end-user `subject` is intentionally absent until its
  consumer (per-user quotas) exists.
- **`request_id`**: correlates a call to its HTTP request when available, else the
  JSON-RPC message id, which is client-chosen and only unique within a session.
- **Raw arguments**: FastMCP registers the terminal with `validate_input=False`
  and coerces arguments downstream, so middleware sees the un-coerced, client-sent
  arguments. `ctx.argument_keys` is bounded (count and length caps) and values-free
  for privacy-sensitive consumers; `ctx.arguments` values are passed unbounded to
  any consumer that opts to read them. Never log a bearer or argument values.

The chain installs on every profile (a no-op when the list is empty); the
built-in structured logger (`observability/tool_log_middleware.py`) is seeded
by default only under the `remote` profile. That is a default, not a capability
boundary: per-call concerns like observability and downstream protection apply to
any deployment (only per-user concerns are hosted-specific), so a local deployment
can register its own middleware. Tool lines use the same stderr JSON emitter as
HTTP request lines (`emit_structured_event`), never stdout.

The wrap targets a FastMCP internal and is tested against `mcp==1.25.0`; the
install is idempotent per app (the sentinel is per handler, not a global). This is
a separate seam from the argument-validation envelope
(`tools/validation_envelope.py`), which patches `Tool.run` to reshape a pydantic
`ValidationError` inside FastMCP's executor: that error's structured detail exists
only there, below this chain, so the two are complementary, not interchangeable.
