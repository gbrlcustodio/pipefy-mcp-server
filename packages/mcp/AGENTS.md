# MCP package conventions

Scoped to `packages/mcp/`. Repo-wide guidance lives in `../../AGENTS.md`.

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
  explicitly to run `local` over loopback HTTP. `remote` over stdio is rejected: a
  per-request bearer has no stdio equivalent. The pair is resolved (and validated)
  once, at startup, by `resolve_mcp_settings`.

Bind host/port come from `PIPEFY_MCP_HOST` / `PIPEFY_MCP_PORT` (defaults
`127.0.0.1:8000`), overridable with `--host` / `--port`, and matter only over HTTP.

Under `remote` the server acts on behalf of each caller: it validates the inbound
bearer per request and opens a per-request session carrying a snapshot of that
validated bearer, so concurrent callers each act as themselves rather than as a
single identity resolved at startup. All sessions share one process-scoped engine
(the GraphQL endpoints and their schema cache). `local` runs as the one credential
resolved at startup. The transport still binds loopback-only until the
DNS-rebinding host/Origin allowlist lands.

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
module) resolves the inbound issuer and pairs the verifier with `AuthSettings`.
The runtime (`McpRuntime.for_profile`) calls it for the `remote` profile and holds
the pair as `inbound_auth`, which `server.py` wires into the app.

**Loopback bind.** `_assert_safe_http_bind` restricts the HTTP transport to a
loopback bind, unconditionally for now. Per-request on-behalf-of identity (each
call runs as the validated caller, not a single startup identity) means inbound
identity is not the constraint; the constraint is DNS-rebinding protection, the
configurable host / Origin allowlist for a proxied deployment. Off-loopback binding
stays off until that lands (see `experiments/hosted-obo/RFC-OUTLINE.md`). The
attachment tools' local `file_path` inputs also still assume a loopback peer that
shares the client's disk (remote-safe file inputs are separate follow-up work).

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
(`tools/tool_context.py`), which calls
`ctx.request_context.lifespan_context.session_for_request()`. Because a session is
opened per call rather than captured at registration, tools act as whoever is
calling without re-registering; under the hosted profile each session carries a
snapshot of that request's validated bearer, so identity is per-request. That is
why there is no repeat-visit bookkeeping: registration never repeats.

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
inputs (for example the attachment tools, which would accept a `file_url` rather
than a local `file_path`), enforce that in the tool body gated on
`settings.mcp.profile == "remote"` at call time, not via the marker. A tool whose
exclusion deserves a reason gets a plain code comment stating why; the exclusion
itself needs no annotation.
