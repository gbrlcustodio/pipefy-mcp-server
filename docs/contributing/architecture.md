# Architecture

This document describes the shape of the code: the layers inside a package, what each layer can import, and the three surfaces the repository ships. It is explanation for contributors. For the rules about writing code at a boundary (validation, parsing, typing, arguments), see [`conventions.md`](conventions.md).

## Layer model

We follow a hexagonal shape with a thin core. Most of this codebase is an adapter. `pipefy-mcp-server` wraps the MCP SDK and the Pipefy GraphQL API. `pipefy-cli` wraps Typer over the same SDK. The logic that is genuinely ours is small, so the core is small. Most modules touch a framework or the vendor SDK. That is the point of an adapter, not a leak.

Three roles:

- Domain (core). Pure types and logic. It owns the ports that it needs from the outside. It imports no framework and no vendor SDK.
- Adapter. It translates an outside type into a domain type, or it registers domain behavior with a framework. Framework and SDK imports live here. A driving adapter is entered from the outside, for example an MCP tool call or a CLI command. A driven adapter is called by the core to reach the outside, for example Pipefy data access.
- Composition root. The per-app wiring, built once at startup. It is the only place that constructs concrete adapters and framework objects.

The mapping of these roles onto module paths lives with the code. See `packages/mcp` and its `pyproject.toml` import-linter contract. That contract is the source of truth for the layering that holds today. This document states the model, not the snapshot, so it does not go stale as modules move.

The framework-free core is a target, not a fact today. The `core` layer still imports `settings` and Starlette in places. The import-linter contract that would lock it is written but disabled, because the pure domain has no single home module yet.

## Dependency rule

Imports point inward. An outer role can import an inner one, never the reverse.

Between packages, ruff `TID251` bans the inward-breaking imports. Each package lists the modules it must not import. Within the MCP package, import-linter holds the layer order `server > tools > core > auth > settings`. A second contract bans any `pipefy_mcp.settings` import from the `tools` layer. The enforced spine is the acyclic import chain that holds today. It is recorded in each package's `pyproject.toml`, not restated here.

An app package is entered through a driving surface, for example an MCP tool call or a CLI command. A shared support library is not entered this way. It is called as a library.

## Ports and dependency inversion

Business logic depends on an interface shaped by what it needs, and the adapter implements it. This names where the seam sits, so "invert" is not read as "invert everything". The seam is domain to infrastructure: a vendor SDK, the network, a database. Define a narrow interface in the domain (`find_by_email`, not `Database.query`), scoped to one need. Let an adapter satisfy it. Do not invert stdlib calls. Do not invert calls that stay inside the domain. A port over `dict` or a pure helper buys nothing.

Add an owned port only where there is payoff: a test seam or a second implementation. Ports are not universal. Today they live in the SDK. `GraphQLExecutor` is a driven port over the GraphQL client. The attachment service owns `S3Uploader` and `UrlDownloader`. A test injects a fake against each. The clearest next candidate is a narrow protocol over the Pipefy engine, so tool logic can run against a fake without the real client.

### Shared support libraries

Not every package is a surface. `auth` and `infra` are shared support libraries. A shared library holds its own domain and adapters, and the ports rule applies to it by payoff.

- `infra` is pure or thin utility (`coerce`, `security`, `filesystem`, `telemetry`). A port over it buys nothing, so it stays port-free.
- `auth` does real driven I/O: OIDC and JWKS network calls, keychain storage, and a loopback redirect server. It also holds domain logic such as PKCE and token resolution. So `auth` is the one shared library with real port candidates: a credential-store seam over `storage.py` and an HTTP seam over `_http.py`. Neither is built yet.

The CLI is a driving adapter, not a shared library. It owns no driven port, because it composes the SDK and `auth` for outbound work.

## Composition root

Effects are built once, in a per-app composition root, at startup. Parsed types are decisions and cost no I/O to build, so they are constructed freely. Effects such as keychain reads, network calls, and client construction live in the composition root. That is the single place where raw settings become domain types and wired resources.

There is one composition root per app, not one for the repo. The MCP app centralizes it in `core/runtime.py` (`McpRuntime.for_profile`). The CLI composes at its entry point instead of a single runtime module. A tool module does not reach for a concrete client. It receives what it needs from the composition root. A shared package exports parsed types and resolvers, not app wiring or effects. An app can wire eagerly and fail fast at boot, or it can keep effectful members lazy. That is a per-app choice.

## The three surfaces

One domain is exposed through three surfaces, and each surface is matched to its user.

- The SDK is for a programmer. It executes a named operation deterministically and returns a domain value. It is the deterministic execution layer.
- The CLI is for a human or a script in a shell. It is thin over the SDK. Discovery is a separate command, which is idiomatic in a shell.
- The MCP server is for an LLM that acts on intent. It takes a human intent and keeps ids internal to the tool.

The layer split follows from this. The SDK executes. The application layer, which is the CLI and the MCP server, owns intent, orchestration, and outcomes. Place a behavior by its determinism. Deterministic resolution, such as a friendly id to a uuid, lives in the SDK. Ambiguous resolution lives in the application layer, where a human or an LLM can decide.

The identifier form is a per-surface decision, not one global choice. The SDK takes numeric ids first. The CLI takes deterministic ids. If the CLI resolves a name, it does so behind an explicit flag that fails closed under automation. The MCP server takes the human intent as the primary input. It resolves ambiguity by elicitation when the client declares that capability. Interactive behavior versus ambient behavior follows from the surface's declared capability, so a headless caller stays deterministic.

### Earn the surface

Default to the smaller surface. Add a field, a method, a tool, or a flag only when a user need earns it. This is why the MCP layer prefers a tool that expresses an outcome over one tool per API endpoint. The tool count tracks user intent, not the wire. The per-tool outcome design lives in the MCP docs.

## Planned: vertical slices

A larger restructure would organize each package by domain vertical slice rather than technical layer. An import-linter contract inside each slice would hold the four roles: models, client, use cases, facade. This work is deferred to its own initiative. It includes the `PipefyClient` to `Pipefy` rename. The full reasoning is preserved in the branch history of this change.
