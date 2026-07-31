# MCP package conventions

Scoped to `packages/mcp/`. Repo-wide guidance lives in `../../AGENTS.md`. The layer model, type-ownership rule, and alternative-constructor guide are in [`../../docs/architecture.md`](../../docs/architecture.md); this package's intra-package layering is enforced by import-linter (`uv run lint-imports`).

## Distribution model

This MCP server is distributed as code that runs in the user's environment as
a subprocess of the agent runtime (Claude Code, Claude Desktop, etc.). The
trust boundary is the user; the server has the same filesystem and network
access the user already has.

Implications for tool design:

- Local filesystem inputs (`file_path`) are first-class. There is no
  path-traversal threat surface beyond what the user can already access, and a
  local `file_path` needs no SSRF guard, redirect cap, or download size limit —
  the user already has that filesystem and network reach.
- A **server-side URL fetch is different**: when the server (not the user) makes
  the request, those defenses apply. The `file_url` attachment source carries
  them in the SDK (`HttpxUrlDownloader`: HTTPS + public-IP gate, 80/443 ports,
  connect-time re-validation, redirect cap, size cap), and any future URL
  ingestion should do the same.

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
SDK's `AccessToken`. The SDK serves the RFC 9728 protected-resource metadata and
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
ASGI-app path bypassed it. The attachment tools' local `file_path` input assumes a
loopback peer that shares the client's disk, so it is rejected under the remote
profile; the hosted-safe path is their `file_url` input, which the SDK downloads
under an SSRF guard (see "Exposure vs input restriction").

**Transport allowlist.** DNS-rebinding protection is a separate axis from the
bind-safety interlock: it checks the inbound request's `Host` / `Origin`, not the
bind interface. The SDK auto-enables a loopback-only allowlist on the `127.0.0.1`
construction host, so behind a proxy that forwards the public `Host` it answers
`421 Misdirected Request`. `core/transport_security.py:build_transport_security`
widens it by deriving the allowed host from `resource_server_url` (the public origin
the `remote` profile already declares) plus loopback. `transport_security_for` resolves it and the
serving path hands it to `streamable_http_app()`, because 2.0 takes the allowlist
per transport rather than on the constructor. `PIPEFY_MCP_ALLOWED_HOSTS` / `PIPEFY_MCP_ALLOWED_ORIGINS`
(JSON) extend it for extra hostnames or a stricter Origin posture. Unset (no
resource-server URL and no override) leaves the SDK's loopback-only default in force,
so the local subprocess case is unaffected. Being configuration derived at
composition (mirroring `build_resource_server_auth`), it lives in the composition
tier, not in `settings.py`, which keeps the mcp SDK out of the config boundary.

## Hosted structured logging

The HTTP transport emits allowlisted JSON lines on stderr for hosted **debugging**
(`pipefy_mcp/observability/`): one `http_request` line per request and one
`tool_call` line per tool invocation (via `tool_log_middleware`). Fields are
privacy-bounded: **excluded** are bearer tokens, argument values, query strings,
and exception messages; **included** on `http_request` lines are the caller's
`sub` and `client_id` when an authenticated bearer is present (attribution for
hosted debugging). `tool_call` lines deliberately omit `sub` until a consumer
needs it (see Tool-call middleware); they still carry `client_id` when available.
Stdio does **not** install the structured emitter: under stdio, stdout is the
JSON-RPC wire, and local installs should not arm that process-global handler.

Wiring lives in `wire_hosted_observability` (`observability/wiring.py`): it calls
`streamable_http_app()` once, attaches request middleware, and returns the Starlette app.
`run_server` serves that app with uvicorn directly (`access_log=False`) so the
structured request line replaces uvicorn's text access log.
`configure_observability_logging` pins the dedicated structured logger at `INFO`
independently of `PIPEFY_MCP_LOG_LEVEL` (which only governs SDK/root text
logs), so quieting noisy text does not drop request/tool lines.

**Mounting the returned app.** The app carries its own lifespan, and that lifespan
is what enters `session_manager.run()`. Serving it directly (what `run_server`
does) needs nothing extra, because uvicorn runs it. Mounting it under a host
Starlette or FastAPI app does: Starlette does not run a mounted app's lifespan, so
the host's own lifespan has to enter `app.session_manager.run()` (the property is
only available once `wire_hosted_observability` has built the HTTP app). Without
it the session manager never starts and every request fails.

**Request body limit.** The SDK caps a Streamable HTTP POST body at 4 MiB and
answers `413` above it. The wiring does not pass `max_request_body_size`, so that
default stands. Attachments do not go through the JSON-RPC body (no tool takes
bytes or base64; uploads use `file_path`, `file_url`, or a presigned URL), so the
reachable case is a large free-text argument: knowledge-base `content`,
`send_inbox_email.body`, `execute_graphql`. A hosted deployment that needs more
raises it on the `streamable_http_app()` call.

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
not inside the SDK `lifespan`. The lifespan owns resources only: it yields
the already-wired app-scoped runtime as the request `lifespan_context`. This
follows the SDK contract: the lifespan owns resources, not registration. Streamable
HTTP enters the lifespan once, at session-manager startup. Registering at
construction keeps the tool table off the lifespan entirely, so no lifespan entry can
mutate it.

Tools take no client at registration. Each tool function declares a
`ctx: Context` parameter (the SDK injects it and keeps it out of the tool's
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
which `build_pipefy_mcp_server` reads into the SDK. (This also means
`build_pipefy_mcp_server` resolves the credential, so the live integration tests
that build the app at import skip themselves when no creds are configured.)
Building the engine at construction is safe off the event loop: `PipefyEngine`
construction does no network I/O and binds nothing to a running loop, because its
endpoints open a fresh per-request transport at call time; the engine built at
startup serves whatever loop later handles requests. Streamable HTTP re-entering
the lifespan (once, at session-manager startup) just yields the same already-wired
runtime, so there is nothing to rebuild. The runtime holds no per-request state: it opens a cheap
session per request via `session_for_request`, binding the identity's resolved
`httpx.Auth` to the shared endpoints. `StartupIdentity` resolves to the one
credential resolved at startup (stdio/local), while `RequestScopedIdentity`
snapshots each caller's validated bearer from the request context, so every session
acts as its own caller.

## Subject-domain taxonomy

The tool surface is classified along two orthogonal axes. A **domain** is the single subject a tool is *about* — domains form a disjoint partition where every registered tool has exactly one, answering "what subject is this tool fundamentally about?". A **profile** is an overlapping, journey-sized selection where the same tool may appear in many, answering "who reaches for this tool, and when?". Domains back the tool-catalog map and the drift-guard; profiles carry the small-working-set job for named `--toolsets` selection. The two are complementary: a tool like `set_default_llm_provider` is *about* AI (domain `intelligence`) yet an IT/governance persona also reaches for it — so the subject fixes the one domain and the cross-persona pull is expressed as a profile overlap, never by splitting the domain or duplicating the tool.

The eight domains and the subject each owns:

- **workflow** — running a process: pipes, phases, fields, labels, field conditions, cards, comments, card attachments, inbox email, and pipe/card relations.
- **database** — Pipefy database tables: tables, table fields, table relations, records, and record attachments.
- **interfaces** — no-code page building: portals, pages, elements, and sub-portals.
- **automation** — Pipefy-native rule (if/then) and AI automations, plus their execution logs, metrics, usage, and job exports.
- **intelligence** — AI capability: agents, LLM providers, knowledge bases, available models, and AI usage and credits.
- **analytics** — reporting: pipe and organization reports and their exports.
- **governance** — org administration: organization, members, roles, service accounts, and audit-log export.
- **integration** — connecting to the outside: webhooks, iPaaS, and the raw GraphQL API (introspection and arbitrary execution). iPaaS lives here (external-app connectivity), not in `automation`.

Subject domains are deliberately chosen over the `docs/mcp/tools/*.md` doc-areas: doc-areas group by API object (cards, pipes, tables), which is redundant with tool names — if a caller says "cards", the names (`create_card`) already lead the model there. The value a taxonomy adds is at the job/business-subject layer, which subject domains capture and doc-areas do not.

The partition lives as central data in `tools/toolsets.py` (`DOMAINS`), not co-located in each tool's `meta` dict — a partition's correctness is a whole-set property (complete, disjoint) best reviewed and asserted in one place, unlike a per-tool security marker like remote-safety, which is reviewed tool-by-tool and so stays on the decorator. The drift-guard (`tests/tools/test_toolsets.py`) keys completeness to `PIPEFY_TOOL_NAMES` with no hardcoded count: a newly registered tool with no domain fails the build. Re-homing or renaming a domain later churns the guard, the docs, and the `--toolsets` vocabulary callers type, so the boundary choices above are deliberate.

**Selecting toolsets at startup.** `--toolsets` / `PIPEFY_MCP_TOOLSETS` takes a comma-separated list of domain names (case-insensitive), plus the `all` / `default` keywords that mean no curation. `resolve_selection` (`tools/toolsets.py`) maps the spec to a set of tool names — the union of the named domains, or `None` for no curation — and `ToolRegistry.apply_toolset_selection` applies it via `retain_only`, run **after** `apply_remote_profile` (floor then selection). Because `retain_only` only ever removes from the live surface, selection narrows within the floored set and can never widen past it — on the remote profile the survivors are the remote-safe floor intersected with the selection. The default (unset) is no curation, so the surface is backward-compatible. An unknown name is a usage error, checked in `main.py` for the flag (the composition root can import the domain map; the settings layer, which sits below the tool layer, cannot) and surfaced at build for a bad `PIPEFY_MCP_TOOLSETS`. Overlapping persona *profiles* (`PROFILES` in `tools/toolsets.py`) extend the same selection vocabulary: `--toolsets operator` or `--toolsets database,admin` resolve profile names the same way as domains and union them. Profiles are curated, journey-sized, and — unlike domains — overlapping (a tool may appear in many), so their guard is a subset check (each ⊆ `PIPEFY_TOOL_NAMES`, names disjoint from the domains and keywords), not a partition. Each is grounded in a Pipefy role scope:

- **requester** — an external guest: submit a request and track your own cards.
- **operator** — a pipe member: run existing cards day to day (reads plus the card lifecycle); no pipe configuration.
- **manager** — a pipe admin, oversight slant: the operator surface plus reports, execution logs, and audit-log export. A superset of `operator`.
- **builder** — a pipe admin: configure pipes, phases, fields, conditions, automations, AI agents, and relations.
- **admin** — an org super admin: members, roles, service accounts, LLM providers, webhooks, and organization reports.
- **auditor** — read-only: every read tool plus audit-log export, to reconstruct history.

The role boundaries are deliberate: "run a case" (pipe member) and "configure a pipe" (pipe admin) are the real capability split, and org-wide governance (members, roles, LLM providers) is a super-admin concern distinct from pipe building. `power` remains a distinct branch, not a profile.

**The `power` discovery profile.** `--toolsets power` (alias `architect`) is a distinct branch: instead of narrowing by domain, `ToolRegistry.apply_power_profile` snapshots the curated tools that survived the floor, removes them from `tools/list`, and registers four catalog meta-tools (`tools/meta_tools.py`) over that snapshot — `get_tool_categories` (the domain map), `search_tools` (a keyword ranker), `describe_tool` (a hidden tool's schema), and `execute_tool` (invoke one). The raw-GraphQL tools (`POWER_GRAPHQL_TOOLS`: `search_schema`, `introspect_*`, `execute_graphql`) stay visible by name alongside them, so the working set is nine tools regardless of catalog size. `execute_tool` dispatches through the hidden tool's own `PipefyValidationTool.run`, so argument validation and the error envelope apply exactly as a direct call; and because the snapshot is taken after the floor, it can never reach a tool the floor withholds. `wants_power` (checked in `server.py`) routes to this branch before the domain path, so `power` and a domain list are not combined. The meta-tools are registered post-floor and are not in `PIPEFY_TOOL_NAMES`, so the partition drift-guard and the remote seed do not count them; their safety on the remote profile comes from the catalog being post-floor, not from a marker.

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
explicit settings). Two shipped instances: `create_ipaas_connection` rejects
`{"$env": ...}` credential references on the remote profile because they resolve
from the deployment's own environment; and the attachment tools reject their local
`file_path` input on the remote profile, exposing only the `file_url` source (which
the SDK downloads under an SSRF guard, so it reads no local disk). A tool whose
exclusion deserves a reason gets a plain code comment stating why; the exclusion
itself needs no annotation.

### Write tools on the remote profile

A write — create, update, delete, or an action-style mutation — must pass the same inclusion criteria as a read (above) plus three write-specific ones before it earns `meta=REMOTE`:

- **Authorization is the API's, and only the API's.** A remote-safe write carries no client-side permission check; it relies entirely on the backend rejecting a caller who lacks the permission (org-admin to create or delete a service account, pipe-admin to add a member). Mark a write remote-safe only once its permission is enforced downstream for the request-scoped bearer — never infer authorization from the tool merely being reachable.
- **A returned secret must never reach a log.** A write that returns a credential (`create_service_account` returns an OAuth2 client secret shown only once) is safe to expose because the hosted logging layers record neither argument values nor response bodies: `tool_log_middleware` logs bounded argument key names only, and `RequestLogMiddleware` logs request metadata without buffering the response body. The secret goes to the authenticated caller and nowhere else. A write that would need its secret logged, echoed in an error, or persisted server-side is not remote-safe.
- **`confirm` is a UX guard, not an authorization boundary.** The two-step `check_destructive_confirmation` flow (preview on `confirm=False`, execute on `confirm=True`) makes a destructive call deliberate, and deliberately avoids elicitation because some clients auto-accept it. A programmatic caller can still pass `confirm=True` on the first call, so `confirm` protects against accident, not intent — the guard against an *unauthorized* delete is the API permission above. A destructive write is remote-safe when its authorization is downstream and its effect is stated plainly to the caller, not because `confirm` gates it.

Input restriction (via `is_remote_profile(ctx)`, per "Exposure vs input restriction" above) is required for a write only when an input resolves from the deployment's own environment or disk — the `create_ipaas_connection` `$env` case — not merely because the tool mutates. A write whose every input is a per-request value (an id, a name, a role) needs none.

The organization service-account tools (`create_service_account`, `delete_service_account`, `add_service_account_to_pipe`) are the first **public-GraphQL** writes on the remote seed (the iPaaS meta-tools `call_ipaas_tool` / `create_ipaas_connection` are also writes, but reach the iPaaS host rather than the public API) and the worked example of the test above: public-GraphQL mutations, API-permission-governed, per-request inputs only, a returned-once secret kept out of logs, and a `confirm`-gated delete.

**Raw GraphQL on the remote profile.** `execute_graphql` is remote-safe (#308), unlike the dedicated destructive tools it can stand in for. It runs an arbitrary query or mutation as the request-scoped bearer, so its write reach is whatever that caller's API permissions already allow — the same trust boundary as its remote-safe introspection siblings (`search_schema`, `introspect_*`), just write-capable. It qualifies on the same three write criteria: authorization is the API's alone (no client-side permission check), no returned value is logged (hosted logging records neither argument values nor response bodies), and it takes only per-request inputs (a query string and variables — no `file_path`, no `$env` reference, no iPaaS host). Two properties are worth stating plainly: it deliberately has **no `confirm` gate** and bypasses the client-side input restrictions of dedicated tools — acceptable because, per the criteria above, `confirm` and input scrubs are UX guards, not authorization boundaries, and the authorization boundary (the API permission on the bearer) still holds. Its reach is the public GraphQL API only (the SDK runs it on the public executor); it cannot read local disk, reach the iPaaS host, or use the Internal API, so the tools withheld for *those* reasons stay unreachable through it — though public-GraphQL equivalents of tools withheld for other reasons remain callable.

**Governance is deferred, on purpose.** Per-user quotas, rate limiting, and cost weighting for remote writes are not a precondition of exposure: the tool-call middleware seam (`core/tool_middleware.py`) is where they attach, but the only middleware shipped is structured logging, and remote writes rely on API-side rate limits plus per-user identity. Per-user write governance is tracked under the "Scaling and abuse protection" milestone; until it lands, expose new write categories conservatively and prefer ones whose blast radius is bounded by API permissions.

### Process-global configuration and the single-backend assumption

When the server runs in hosted (`remote`) mode, one process serves many users at the same time. Settings loaded from the environment are **shared by everyone** — there is one copy for the whole process, not one per user.

That's fine when a setting answers a question about the *deployment* ("which Pipefy backend do we talk to?", "how long before a lookup times out?"). It's a problem if a setting ever answers a question about a *user* ("who is this call acting as?", "which org does this caller belong to?") — because then one shared value would silently apply to every user. The one truly per-user thing, identity, never comes from settings: in hosted mode each request carries its own validated token (`RequestScopedIdentity`). `settings.auth` is read in both modes, but always for a per-deployment purpose: local mode resolves the one outbound startup credential from it, and remote mode reads it once at startup to derive the default inbound issuer URL (see "Resource-server profile" above) — safe under the same single-realm assumption.

Everything else that reads shared settings is safe because of one assumption, stated here on purpose so it isn't forgotten: **one hosted deployment serves a single integrator against a single backend.** In other words, every user of a deployment shares the same config because they genuinely share the same setup. The full list of shared-settings reads a tool call can hit, audited for #306:

- `PIPEFY_BASE_URL` — which backend the server talks to. Everyone hits the same one; this is the assumption itself.
- The GraphQL schema cache (`gql_reuse_fetched_graphql_schema`) — shared across users, which is fine because one backend means one schema.
- `permission_denied_enrichment_timeout_seconds` (`tools/graphql_error_helpers.py`) — a timeout knob. Same for everyone by design.
- `unified_envelope` (`core/tool_error_envelope.py`) — a flag that changes the shape of tool responses. Applies identically to every caller.
- The bind host and transport allowlist (`core/transport_security.py`, from `McpSettings`) — DNS-rebinding / bind-safety config resolved once at startup. A property of the deployment's front door, not of any caller.
- `default_webhook_name` and `allow_insecure_urls` (SDK webhook service, on create/update) — a cosmetic default name and an insecure-URL escape hatch. `create_webhook` / `update_webhook` are remote-safe (#478), and both settings are per-deployment, not per-user: every caller shares the one deployment's fallback webhook name and its HTTPS-enforcement posture, exactly as they share `PIPEFY_BASE_URL`. Neither answers a question about the caller, so reading them on the hosted path is safe under the same single-backend assumption.

A related note: tools that call Pipefy's Internal API (like `delete_card_relation`) carry no special credential requirement. The SDK binds the session's one credential to all three API endpoints (public, Interfaces, Internal), so the Internal API simply receives whatever credential the caller already has — nothing in the client is service-account-specific. That is why an Internal-API write is remote-safe on the same terms as a public-API one: `delete_card_relation` is on the seed (#472), governed by the request-scoped bearer and the API's permissions like every other remote write.

**When this breaks (the rework trigger).** If one hosted server ever needs to serve *multiple* backends, or integrators with different config, the assumption is gone: "same for everyone" stops being true, and each of the reads above becomes a per-user question. The fix is the same one identity already went through in #302 — stop reading the value from shared settings and resolve it from the incoming request instead.

**How this is enforced.** An import-linter rule in `pyproject.toml` forbids tool code from *importing* `pipefy_mcp.settings`, even indirectly through a helper (that indirect path is how `unified_envelope` was caught). Every existing import is an explicitly listed, commented exception. If someone adds a new settings import to tool-reachable code, `uv run lint-imports` fails, and it only gets an exception after review confirms it reads a per-deployment value — never a per-user one. The rule sees import edges, not value reads off an object that already holds a `Settings`; that gap is closed by construction rather than review, because the one object a tool can reach through its request context — the `McpRuntime` on the lifespan context — holds no `Settings` tree. It resolves only narrow per-deployment booleans at startup (`is_remote`, `unified_envelope`; see `core/runtime.py`), so there is no settings tree to read off it at call time. Per-user values must come from the request.

## Tool-call middleware

Cross-cutting concerns that wrap a tool invocation (logging, per-user quotas,
rate limiting, cost weighting, downstream 429/circuit-breaking) register as
ordered middleware. The SDK supplies the outer seam: `MCPServer(middleware=[...])`
takes a list of `ServerMiddleware`, each an async `(ctx, call_next)` around every
inbound message. `core/tool_middleware.py` adapts that one message-level slot into
the tool-level chain the package registers against, and the composition root passes
the single adapter to the constructor.

The adapter layer exists for two reasons. The SDK marks its `middleware` list
provisional, so keeping `ToolCallContext` and `ToolCallMiddleware` as the
registration surface confines any churn there to one module. And a `ServerMiddleware`
sees every method (`initialize`, `tools/list`, notifications) while every consumer
here wants tool calls only, so the `ctx.method` filter belongs in one place.

A middleware is a plain async callable. A built-in middleware joins the per-profile
defaults (`default_tool_middlewares` in `server.py`); a consumer of
`build_pipefy_mcp_server` passes its own through `extra_tool_middlewares`, which the
builder folds in after the built-ins (so the default observability layer stays
outermost). Neither path touches SDK internals:

```python
from pipefy_mcp.core.tool_middleware import ToolCallContext, CallNext, short_circuit_error

async def quota(ctx: ToolCallContext, call_next: CallNext):
    if over_quota(ctx.identity.client_id):
        return short_circuit_error(ctx, "quota exceeded", code="RATE_LIMITED")
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
  reported a business error (`isError=False`). It takes `ctx` because a
  short-circuiting middleware owns its response envelope: the SDK shapes a result
  per negotiated revision inside `call_next`, so a result returned without awaiting
  it is never shaped, and `short_circuit_error` runs the SDK's own
  `serialize_server_result` against `ctx.protocol_version` instead. That is why it
  returns the wire dict, not a `CallToolResult`: the model would dump its 2026-era
  `resultType` default onto a legacy connection, and nothing downstream (including
  the client's own surface validation, which ignores extras) would object.
- **Identity** (`ctx.identity`): the validated caller's `client_id` and `scopes`,
  read off the request's bearer, never re-decoded. Empty under stdio/local (no
  inbound bearer). The end-user `subject` is intentionally absent until its
  consumer (per-user quotas) exists.
- **`request_id`**: correlates a call to its HTTP request when available, else the
  JSON-RPC message id, which is client-chosen and only unique within a session.
- **Raw arguments**: middleware reads `tool_name` and `arguments` off the inbound
  params before the SDK validates or coerces them, so it sees exactly what the client
  sent. A malformed `tools/call` therefore still reaches middleware, which a
  governance layer counting calls needs. `arguments` is the same mapping object the
  dispatcher holds, so mutating it in place rewrites the call; rewrite deliberately
  through the SDK's `replace(ctx, params=...)` instead.
- **Reading the result**: what `call_next` returns is polymorphic, so use
  `result_is_error(result)` rather than an attribute read. A real tool call comes back
  as the serialized wire dict keyed `isError` (the SDK shapes the result for the wire
  inside the chain), success and failure alike, and so does `short_circuit_error`; a
  `CallToolResult` model with snake_case `is_error` only arrives from an inner
  middleware that built its result by hand. `result.is_error` reads `False` on the
  dict, so every real failure would look like a success. A middleware test fixture
  must use the dict shape for anything standing in for a real call, or it exercises a
  branch production never takes.
- **Privacy**: `ctx.argument_keys` is bounded (count and length caps) and values-free
  for privacy-sensitive consumers; `ctx.arguments` values are passed unbounded to
  any consumer that opts to read them. Never log a bearer or argument values.

The chain installs on every profile (a no-op when the list is empty); the
built-in structured logger (`observability/tool_log_middleware.py`) is seeded
by default only under the `remote` profile. That is a default, not a capability
boundary: per-call concerns like observability and downstream protection apply to
any deployment (only per-user concerns are hosted-specific), so a local deployment
can register its own middleware. Tool lines use the same stderr JSON emitter as
HTTP request lines (`emit_structured_event`), never stdout.

`build_tool_call_middleware` returns `None` for an empty list, so a deployment with
no middleware registers nothing and every inbound message skips the adapter. This is
a separate seam from the argument-validation envelope
(`tools/validation_envelope.py`), which patches `Tool.run` to reshape a pydantic
`ValidationError` inside the SDK's tool executor: that error's structured detail
exists only there, below this chain, so the two are complementary, not
interchangeable. The `Tool.run` patch is the one SDK internal this package still
reaches for, tested against `mcp==2.0.0`.

That patch and the provisional `middleware` list are why the dependency is pinned to
`mcp[cli]==2.0.*` rather than opened to `<3`. Neither surface is covered by SemVer,
and no CI job resolves past `uv.lock`, so a minor release could move either one with
nothing to catch it before a release. Widening to a new minor means re-testing both.
