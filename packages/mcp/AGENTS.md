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

The identity the server acts as is still the single credential resolved at startup,
for both profiles: `remote` validates the inbound bearer but does not yet act on
behalf of the caller. Per-request on-behalf-of identity is separate, in-progress
work; until it lands, treat `remote` as a validation-only HTTP profile and keep the
bind on loopback.

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
module, the composition root) resolves the inbound issuer and pairs the verifier
with `AuthSettings`, which `server.py` wires into the app.

**Loopback bind.** `_assert_safe_http_bind` restricts the HTTP transport to a
loopback bind, unconditionally for now. Even with the resource-server profile
validating an inbound bearer, there is no per-request on-behalf-of identity yet,
so every call runs as the single startup identity; a network-reachable port would
hand that identity to anyone who can reach it. Off-loopback binding stays off until
the hosted on-behalf-of profile lands (see `experiments/hosted-obo/RFC-OUTLINE.md`),
which brings per-request identity and the configurable host / Origin allowlist for a
proxied deployment (DNS-rebinding protection). The attachment tools' local
`file_path` inputs also still assume a loopback peer that shares the client's disk
(remote-safe file inputs are separate follow-up work).

## Tool registration

Tools are registered **once, at construction** (via `_register_pipefy_tools` in
`server.py`, reached through `build_pipefy_mcp_server`, which both transports use),
not inside the FastMCP `lifespan`. The lifespan owns resources only: it
initializes services and yields the container as the request `lifespan_context`.
This follows the FastMCP contract, where the lifespan can run per session (per
request under Streamable HTTP) and so must not mutate the tool table.

Tools take no client at registration. Each tool function declares a
`ctx: Context` parameter (FastMCP injects it and keeps it out of the tool's
input schema) and resolves the live client per request with
`get_pipefy_client(ctx)` (`tools/tool_context.py`), which reads
`ctx.request_context.lifespan_context.pipefy_client`. Because the client is
looked up per call rather than captured at registration, what the lifespan yields
can change (a future per-request identity can vary the client) without touching
any tool or re-registering. That is why there is no repeat-visit bookkeeping:
registration never repeats.

When adding a tool, give it a `ctx: Context` parameter and start its body with
`client = get_pipefy_client(ctx)`; do not pass a client through `register`.

Both transports launch through the single `run_server` entry point, which resolves
the profile/transport once and builds the same app through
`build_pipefy_mcp_server` (same `lifespan`, same `_register_pipefy_tools`), differing
only in the transport `run` and HTTP's bind concerns. Initialization runs in the
lifespan, in the serving event loop, for both: the per-request HTTP clients bind to
the loop that is running when they are first used, so creating them off in a
separate startup loop would leave them bound to a closed loop. The lifespan builds a
fresh `ServicesContainer` per entry (no singleton); Streamable HTTP re-enters it per
session, so each session gets its own initialized container. The per-session
re-resolution is cheap (the stored-session warm-up only hits the network when the
token is stale, serialized by the auth layer) and a future per-request identity will
build the client from the request here anyway.

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
