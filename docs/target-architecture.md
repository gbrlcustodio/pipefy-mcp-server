# Target architecture

## Status

North-star for the whole monorepo: the invariants the packages converge on and the directory structure they take. It describes the end-state, not the current code. `architecture.md` holds the rules enforced today and the machinery that enforces them; each invariant here moves into `architecture.md` as the code comes to obey it. The path from today's code to this end-state is incremental and lands through the enforcement machinery in `architecture.md`; it does not belong in this document.

## Architectural style

This is an integration and capability-provider system, not a business-domain application. It owns no domain: Pipefy owns the domain, the persistence, the invariants, and its own use cases. System-scale domain/application/infrastructure layering therefore leaves empty boxes (a hollow domain core, an application layer with no code), and the fitting patterns are integration and client-library ones, each at its own scale:

- Strategic DDD, not tactical: Pipefy is an upstream bounded context and the SDK is an anti-corruption layer conforming to its published language. Tactical DDD applies only inside the SDK (see "SDK-internal roles").
- The SDK is a client library over that gateway; ports-and-adapters is accurate at that small scale.
- The MCP server is a microkernel: the meta-tool surface is the kernel, the tool catalog is plug-in capabilities. The CLI is the same capabilities behind a thinner dispatcher.
- Code is packaged by feature and concern, never by layer: the SDK by Pipefy bounded context, each app by concern with capabilities under one delivery-role folder.

The use-case layer is externalized to the caller, the model over MCP and the human over CLI; its absence from the codebase is the signature of a capability provider, not a missing tier.

## Decisions

- The app packages (`pipefy-mcp-server`, `pipefy-cli`) are thin delivery adapters over the `pipefy` SDK. They own no domain of their own: one operation per tool or command, and no Pipefy entity modeled in an app package. An app exposes Pipefy surfaces but owns none of them. The thinness is a consequence, not a rule imposed for its own sake: the use-case layer is the caller's, the model orchestrating tools over the MCP surface and the human orchestrating commands over the CLI, so there is no use-case code left for an app to hold.
- The `pipefy` SDK is the Pipefy gateway and the only place the Pipefy domain is modeled, as a projection of a domain Pipefy owns: an anti-corruption layer, not a domain-owning core, so Pipefy stays the authority for the invariants the SDK mirrors. It is grouped by Pipefy bounded context (not by the GraphQL API shape), is internally hexagonal (transport behind a port, query building and response mapping as adapters), and returns typed models (typed collections carrying pagination and a typed error taxonomy, not only typed entities). What it exposes are Pipefy's own use cases seen from outside: a gateway operation is one Pipefy use case, a single atomic unit of work Pipefy runs server-side. The SDK exposes Pipefy's use cases, never the consumer's.
- The boundary is whose use case. A single Pipefy use case, a read whose multi-step shape Pipefy's own structure forces (pagination, connection resolution), and decoration or preflight validation wrapped one-to-one around a Pipefy use case all belong in the SDK; preflight is a fail-fast mirror of a Pipefy-owned invariant, so it can drift and is never the authority. Composing several Pipefy use cases toward a goal is the consumer's use case and stays with whoever forms the intent: the SDK cannot own the cross-operation coordination (ordering, partial failure, idempotency) it turns on, because Pipefy gives no transaction across operations. The lone exception that becomes code is orchestration mixing Pipefy with a non-Pipefy system, outside the Pipefy-scoped SDK: it lives in the app that needs it, or in a shared first-party package once a second app needs it, and none exists today.
- A Pipefy use case reaches an app in two hops, and neither hop authors a use case: the SDK exposes it as a typed, transport-agnostic operation, each app re-exposes that operation through its own delivery surface (a `tools/` catalog entry reached by the meta-tools, or a `commands/` Typer command), and the caller composes the exposed operations. The operation is re-exposed once per app because it is shared (it lives in the SDK) while the delivery binding is not (a catalog entry and a Typer command are different mechanisms). So the apps share a substrate (the SDK, plus the `auth` and `infra` primitives), never a use case, and there is no shared use-case or exposure package.
- The owned logic in the app packages is a cross-cutting policy layer (safety, exposure, telemetry, response shaping), not a domain. It has no entities, and its seams run perpendicular to Pipefy's.
- The MCP server exposes a fixed meta-tool surface (discover, describe, dispatch, categorize) over a hidden, validated tool catalog: only the meta-tools and a raw-GraphQL escape hatch (`search_schema`, `introspect_*`, `execute_graphql`) appear in `tools/list`, and the real tool bodies are reached by name through `execute_tool`. This keeps the exposed tool-list small (a context-budget concern) and makes the catalog a runtime artifact rather than a protocol dump. The CLI has no such surface: a CLI is discovered by `--help`, so it exposes its commands directly.

## The rules

Two questions, a short list of rules each.

### Where a file lives

1. A concern is a folder named by concern, and a concern is a file until a second role earns the folder: a thin concern stays a single module named by concern, becoming a folder only when a second role has real content to hold. Inside a concern folder, one module per role, named by its content, never by `port`/`adapter`/`utils`/`middleware`/`common`, and no name is overloaded toward a wrong dominant meaning. Where a concern owns a port, the port and its adapter are separate modules and the port is framework-free.
2. An app owns its delivery concerns but only carries Pipefy surfaces, and the two are not peers. Owned concerns (`auth`, `telemetry`, `response`, `wiring`, and the server's meta-tool surface `dispatch/`) are folders at the package root. The Pipefy surface groups under one delivery-role folder (`tools/` on the server, `commands/` on the CLI) because the app holds no Pipefy domain: a `cards/` folder at the root would be a hollow domain slot that invites SDK domain logic to leak upward, and it would mirror the SDK's context taxonomy as app structure. Inside that folder, one module per surface area named by the canonical Pipefy toolset (`pipes`, `cards`, `database`, `connections`, `reports`, `portal`, `automation`, `ai`, `access`, `integrations`, `introspection`), each a file until a second role earns it a folder. On the server that folder is a hidden catalog reached only through the meta-tool surface; the CLI exposes it directly.
3. Only two positions are not concerns: the center and the composition root `wiring/`. The center holds stdlib-pure vocabulary that no single concern owns, and may be empty when every type has a concern that owns it. `wiring/` wires every concern and is imported only by `main`. `main.py` is the entry; `settings.py` is the config boundary.
4. A type lives with the concern that owns its behavior and is published as that concern's contract; a type no concern owns lives at the center. Cross-cutting code lives in its concern, never a pattern bucket (no `middlewares/`, no `utils/`).
5. Reaching into a third-party's private or undocumented surface (a monkeypatch, a private attribute, an internal slot) is its own concern and lives only in `vendor/`, one module or folder per vendor named for that vendor. Every other concern calls a `vendor/` shim, never the private symbol directly, so an unstable dependency has one owner and an SDK upgrade has one place to change. This is an owned anti-corruption layer rather than a technical bucket: it groups by the external surface it isolates, and a `TID251` ban keeps each vendor's private symbols out of every folder but this one.

### How it behaves

1. Validate only at the boundary, and parse rather than validate: the boundary returns a carrier type, and the interior is total and never re-checks. The boundaries are config (`settings.py`), identity (`auth/`), call arguments, and gateway responses (the SDK). Call arguments are parsed against the tool's schema, which is derived from the body's typed signature, so the signature still defines the parse; on the server the dispatcher runs it against the catalog schema for the named tool, rather than the framework. The raw-GraphQL escape hatch is a deliberate unparsed passthrough, allowed only where exposure policy permits it.
2. Effects are built once, in `wiring/`, the only place that constructs concrete adapters and framework objects. Everything downstream receives them; the surface never constructs a client, but takes a per-request provider from `wiring/` that mints one bound to the caller's identity (the process-scoped SDK engine is the effect, and identity is the sole per-request input). Decisions are carried as sum types, and the root fails fast.
3. Concerns integrate only through published contracts (each concern's `__init__` exposes its contract types, never its adapters), and the import graph is acyclic. Vocabulary flows down (a concern imports a value type from the concern that owns it); behavior inverts (a concern never calls a concern above it, only through a center abstraction). Telemetry is a sink: it observes concerns, and nothing imports it but `wiring/`.
4. A tool returns a typed result or raises; one seam shapes every response into the envelope, at the dispatch boundary, using the SDK's typed models. The gateway port is the SDK client, which we own, so nothing wraps it in a second abstraction.

## Target structure

Monorepo:

```
packages/     (directory names; distribution names in parentheses)
  pipefy/  the Pipefy gateway and domain home (dist pipefy; directory renamed from sdk/ on migration); internal hex; grouped by Pipefy context; typed models
  auth/    shared identity (dist pipefy-auth): credential resolution and token verification, consumed by both apps
  infra/   generic transport, security, and config primitives (dist pipefy-infra); no domain of its own
  mcp/     the MCP delivery adapter over pipefy (dist pipefy-mcp-server)
  cli/     the Typer delivery adapter over pipefy (dist pipefy-cli)
```

App package (the server shown; the CLI takes the same shape, below):

```
pipefy_mcp/
  main.py            entry; imports wiring only
  settings.py        config boundary
  wiring/            composition root: factory.py  runtime.py  catalog.py  lifespan.py   (imported by none but main; builds the tool catalog once, owns the process-scoped SDK engine, binds the SDK lifespan hook to that runtime, hands the surface a per-request client provider)
  dispatch/          the exposed meta-tool surface: meta_tools.py (search/describe/execute/categories)  parse.py (arguments against the catalog schema)   (the only Pipefy tools in tools/list; reads the wiring-built catalog; remote default-deny enforced here)
  graphql.py         the raw-GraphQL escape hatch (search_schema, introspect_*, execute_graphql): thin over SDK operations, exposure-gated
  vendor/            anti-corruption shims over third-party private surfaces, one module or folder per vendor named for that vendor: fastmcp.py (installs the tool-call middleware into the private request_handlers slot; removes and lists catalog tools through the private _tool_manager)   (the only code that may touch a vendor private symbol; every concern calls a shim here, never the attribute)
  auth/              identity: identity.py  verifier.py  resolve.py  credentials.py   (identity.py published as contract)
  telemetry/         emission (a sink): emitter.py  log_middleware.py   (observes each dispatched body, not the meta-tool boundary)
  response/          response shaping: envelope.py  shaper.py
  tools/             the hidden tool catalog, dispatched into by name (one module per toolset, each a file until a role earns a folder):
                     pipes.py  cards.py  database.py  connections.py  reports.py  portal.py  automation.py  ai.py  access.py  integrations.py  introspection.py
                     (each defines a schema + validated body into the catalog, not an @mcp.tool; a thickened surface becomes tools/pipes/ with parse.py)
```

The CLI takes the same shape with delivery-specific concerns swapped: its delivery-role surface folder is `commands/` in place of `tools/` (same rule, one module per toolset), `output/` replaces `response/` (rendering, not enveloping), there is no `dispatch/` or `graphql.py` (a CLI is discovered by `--help`, so it exposes its commands directly with no meta-tool surface), it carries a `vendor/` folder only if it reaches into a Typer or Click internal, and its composition root is `main.py` plus `runtime.py`.

## SDK-internal roles

Within the SDK, code plays tactical DDD roles, model, repository, and service, which no other package does (the apps and shared packages split by concern). It is the worked example of that split. One caveat throughout: Pipefy owns the domain, so anything logic-like the SDK holds is an advisory mirror, never the authority.

- Domain model: the mirrored entities and value objects, a conformist projection of Pipefy's published language, optionally carrying eager fail-fast validation.
- Domain service: sparse, and not the GraphQL calls. Only genuinely replicated domain computations that no single entity owns (a derived `is_overdue(card)`, "which fields this phase requires"), advisory like the rest.
- Repository / gateway: the 1:1 GraphQL operations and their decorated forms alike. This is access, not logic. Decoration (richer types, better errors, a preflight guard) is ergonomics on the repository and does not promote it to a domain or application service.
- Application layer: absent inside the SDK. Each GraphQL operation is a gateway to one of Pipefy's use cases, so Pipefy's application layer is upstream and the consumer's is the caller.

## Relationship to other artifacts

- `architecture.md` holds the rules enforced today and the machinery that enforces them (the import-linter contract set, ruff `TID251`, including the ban on each vendor's private symbols outside `vendor/`). The migration toward this end-state happens as incremental PRs, not as a plan recorded here.
- `tools/toolsets.py` (server) is the static grouping (the `power`, `all`, `default` keywords) that seeds the catalog's categories, which `get_tool_categories` and `search_tools` serve at runtime; its area names align with the catalog modules under `tools/`.
- The separately-maintained Pipefy domain model is the input to the SDK's context grouping only. It does not shape the app packages.
