# Target architecture

## Status

North-star for the whole monorepo: the invariants the packages converge on and the directory structure they take. It describes the end-state, not the current code. `architecture.md` holds the rules enforced today and the machinery that enforces them; each invariant here moves into `architecture.md` as the code comes to obey it. The path from today's code to this end-state is incremental and lands through the enforcement machinery in `architecture.md`; it does not belong in this document.

## Decisions

- The app packages (`pipefy-mcp-server`, `pipefy-cli`) are thin delivery adapters over the `pipefy` SDK. They own no domain tier: one operation per tool or command, and no Pipefy entity modeled in an app package. An app exposes Pipefy surfaces but owns none of them. Anything that composes multiple operations is a shared workflow and lives in the SDK.
- The `pipefy` SDK is the Pipefy gateway and the only place the Pipefy domain is modeled. It is grouped by Pipefy bounded context (not by the GraphQL API shape), is internally hexagonal (transport behind a port, query building and response mapping as adapters), and returns typed models: typed collections carrying pagination and a typed error taxonomy, not only typed entities.
- The owned logic in the app packages is a cross-cutting policy layer (safety, exposure, telemetry, response shaping), not a domain. It has no entities, and its seams run perpendicular to Pipefy's.
- The MCP server exposes a fixed meta-tool surface (discover, describe, dispatch, categorize) over a hidden, validated tool catalog: only the meta-tools and a raw-GraphQL escape hatch (`search_schema`, `introspect_*`, `execute_graphql`) appear in `tools/list`, and the real tool bodies are reached by name through `execute_tool`. This keeps the exposed tool-list small (a context-budget concern) and makes the catalog a runtime artifact rather than a protocol dump. The CLI has no such surface: a CLI is discovered by `--help`, so it exposes its commands directly.

## The rules

Two questions, a short list of rules each.

### Where a file lives

1. A concern is a folder named by concern, and a concern is a file until a second role earns the folder: a thin concern stays a single module named by concern, becoming a folder only when a second role has real content to hold. Inside a concern folder, one module per role, named by its content, never by `port`/`adapter`/`utils`/`middleware`/`common`, and no name is overloaded toward a wrong dominant meaning. Where a concern owns a port, the port and its adapter are separate modules and the port is framework-free.
2. An app owns its delivery concerns but only carries Pipefy surfaces, and the two are not peers. Owned concerns (`auth`, `telemetry`, `response`, `wiring`, and the server's meta-tool surface `dispatch/`) are folders at the package root. The Pipefy surface groups under one delivery-role folder (`tools/` on the server, `commands/` on the CLI) because the app holds no Pipefy domain: a `cards/` folder at the root would be a hollow domain slot that invites SDK domain logic to leak upward, and it would mirror the SDK's context taxonomy as app structure. Inside that folder, one module per surface area named by the canonical Pipefy toolset (`pipes`, `cards`, `database`, `connections`, `reports`, `portal`, `automation`, `ai`, `access`, `integrations`, `introspection`), each a file until a second role earns it a folder. On the server that folder is a hidden catalog reached only through the meta-tool surface; the CLI exposes it directly.
3. Only two positions are not concerns: the center and the composition root `wiring/`. The center holds stdlib-pure vocabulary that no single concern owns, and may be empty when every type has a concern that owns it. `wiring/` wires every concern and is imported only by `main`. `main.py` is the entry; `settings.py` is the config boundary.
4. A type lives with the concern that owns its behavior and is published as that concern's contract; a type no concern owns lives at the center. Cross-cutting code lives in its concern, never a pattern bucket (no `middlewares/`, no `utils/`).

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
  wiring/            composition root: factory.py  runtime.py  catalog.py   (imported by none but main; builds the tool catalog once, owns the process-scoped SDK engine, hands the surface a per-request client provider)
  dispatch/          the exposed meta-tool surface: meta_tools.py (search/describe/execute/categories)  parse.py (arguments against the catalog schema)   (the only Pipefy tools in tools/list; reads the wiring-built catalog; remote default-deny enforced here)
  graphql.py         the raw-GraphQL escape hatch (search_schema, introspect_*, execute_graphql): thin over SDK operations, exposure-gated
  mcp_extensions/    MCP-SDK integration: tool_middleware.py  lifespan.py  capabilities.py
  auth/              identity: identity.py  verifier.py  resolve.py  credentials.py   (identity.py published as contract)
  telemetry/         emission (a sink): emitter.py  log_middleware.py   (observes each dispatched body, not the meta-tool boundary)
  response/          response shaping: envelope.py  shaper.py
  tools/             the hidden tool catalog, dispatched into by name (one module per toolset, each a file until a role earns a folder):
                     pipes.py  cards.py  database.py  connections.py  reports.py  portal.py  automation.py  ai.py  access.py  integrations.py  introspection.py
                     (each defines a schema + validated body into the catalog, not an @mcp.tool; a thickened surface becomes tools/pipes/ with parse.py)
```

The CLI takes the same shape with delivery-specific concerns swapped: its delivery-role surface folder is `commands/` in place of `tools/` (same rule, one module per toolset), `output/` replaces `response/` (rendering, not enveloping), there is no `mcp_extensions/`, `dispatch/`, or `graphql.py` (a CLI is discovered by `--help`, so it exposes its commands directly with no meta-tool surface), and its composition root is `main.py` plus `runtime.py`.

## Relationship to other artifacts

- `architecture.md` holds the rules enforced today and the machinery that enforces them (the import-linter contract set, ruff `TID251`). The migration toward this end-state happens as incremental PRs, not as a plan recorded here.
- `tools/toolsets.py` (server) is the static grouping (the `power`, `all`, `default` keywords) that seeds the catalog's categories, which `get_tool_categories` and `search_tools` serve at runtime; its area names align with the catalog modules under `tools/`.
- The separately-maintained Pipefy domain model is the input to the SDK's context grouping only. It does not shape the app packages.
