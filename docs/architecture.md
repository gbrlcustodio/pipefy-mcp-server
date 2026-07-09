# Architecture guidelines

This document describes how code is layered inside a package and how types cross a boundary. It fills the gap between two things that are already written down:

- `docs/dependencies.md` and the root `AGENTS.md` cover the direction between packages (`pipefy-infra` is the leaf; `pipefy` and `pipefy-auth` sit above it; `pipefy-mcp-server` and `pipefy-cli` sit on top). That direction is enforced per package by ruff `TID251` banned-api and the CI "banned upward imports" steps.
- `AGENTS.md` ("type validation at boundaries", "parse, don't validate", "parsed types are self-guaranteeing", "composition: the per-app runtime") and the coding principles cover how data is parsed at the edge and where effects live.

What was missing is the layer model *within* a package: which module is domain, which is an adapter, which is the composition root, and what each is allowed to import. This document states that model, the type-ownership rule at boundaries, the port and inversion seam, the per-app composition root, and a decision guide for alternative constructors. It reinforces the existing rules rather than replacing them; the reconciliation section at the end lists where the two meet.

## Layer model

We follow a hexagonal shape with a deliberately thin core. Most of this codebase is an adapter: `pipefy-mcp-server` wraps the MCP SDK and the Pipefy GraphQL API, `pipefy-cli` wraps Typer over the same SDK. The business logic that is genuinely ours is small, so the domain tier is small, and most modules legitimately touch a framework or the vendor SDK. That is the point of an adapter, not a leak.

Three roles:

- **Domain (core).** Pure types and logic. Owns the interfaces (ports) it needs from the outside. Imports no framework and no vendor SDK.
- **Adapter.** Translates an outside type into a domain type, or registers domain behavior with a framework. Framework and SDK imports live here. A driving adapter is entered from the outside (an MCP tool call, a CLI command); a driven adapter is called by the core to reach the outside (Pipefy data access).
- **Composition root.** The per-app wiring built once at startup. It is the only place that constructs concrete adapters and framework objects and hands them to everything else.

### How the roles map onto `pipefy_mcp` today

- Composition root: `server.py` (`build_pipefy_mcp_server`), `main.py`, and `core/runtime.py` (`McpRuntime.for_profile`).
- Driving adapter: `tools/` (MCP tool registration and the GraphQL calls behind each tool) and `core/fastmcp_tool_lifecycle.py` (FastMCP lifecycle).
- Auth adapter: `auth/` (inbound bearer validation; `JwtTokenVerifier` maps validated claims onto the SDK `AccessToken`).
- Driven side: Pipefy data access through the `pipefy` SDK (`PipefyClient` / `PipefyEngine`), which is a separate package, consumed concretely.
- Config boundary: `settings.py` (pydantic-settings parses `PIPEFY_*` into typed settings).
- Domain: currently thin and scattered as helper functions under `tools/` (payload builders, `tool_error_envelope.py`, `tool_context.py`). It has no dedicated framework-free module yet. Consolidating it is the incremental target that unlocks the framework-free check described under Enforcement.

## Dependency rule

Imports point inward: an outer role may import an inner one, never the reverse. Between packages this is already enforced by `TID251`. Within `pipefy_mcp` it is enforced by import-linter (see Enforcement).

The enforced spine is the actual acyclic import chain that holds today, from outer to inner: `server` above `tools` above `core` above `auth` above `settings`. This is a conservative encoding of "inward only": it reflects the direction imports run in the code, not the conceptual role names. The two do not line up one-to-one yet (the runtime is the composition root but lives under `core/`, which the spine places below `tools/` because tools import the runtime to get their dependencies). Converging the physical layering with the conceptual roles is part of the incremental work, not a precondition for the check.

The two ports of this package:

- Driving port: tool invocation. The MCP SDK enters here; `tools/` is the adapter.
- Driven port: Pipefy data access. Consumed today as the concrete `pipefy` SDK. Introducing an owned interface for it is the inversion described under Ports.

## Type ownership at boundaries

A domain type must not carry a framework or SDK type as a field, and must not take one in a public signature. If it does, every consumer of that type transitively depends on the framework, and the domain stops being swappable.

This binds domain types, not adapters. An adapter mapping an outside value onto a currency type is correct: `JwtTokenVerifier._to_access_token` maps validated JWT claims onto the SDK `AccessToken`, and `AccessToken` is the adapter's currency, so holding it there is fine. The rule bites when a type meant to be domain fields, say, a raw request or a raw SDK result and forces that dependency on everyone downstream.

This is the ownership half of the boundary rules in `AGENTS.md`: "type validation at boundaries" says where to check, "parsed types are self-guaranteeing" says the check hands back a type that enforces its own invariants, and this rule says that type is expressed in terms the domain owns, not the framework's.

## Ports and dependency inversion

Coding principle 3 ("depend on abstractions you own") holds without exception: business logic depends on an interface shaped by what it needs, and the adapter implements it. This document only names where that seam sits so "invert" does not get read as "invert everything".

The seam is domain to infrastructure: a vendor SDK, the network, a database. You define a narrow interface in the domain (`find_by_email`, not `Database.query`), scoped to one need, and let an adapter satisfy it. You do not invert stdlib calls, and you do not invert calls that stay inside the domain; wrapping `dict` or a pure helper behind an interface buys nothing.

Today this package owns almost no such interface: the Pipefy engine is consumed as the concrete `pipefy` SDK. Introducing an owned port is incremental and starts where there is payoff, a test seam or a second implementation. The clearest first candidate is a narrow protocol over the Pipefy engine so tool logic can be exercised against a fake without the real client.

## Composition root

Effects are built once, in a per-app runtime, at startup. There is one composition root per app package, not one for the repo: `pipefy-mcp-server` and `pipefy-cli` each have their own. `McpRuntime.for_profile` is the MCP server's build step; the runtime turns raw settings into domain types and wired resources, and everything downstream depends on the runtime or the types it holds, never on raw settings or an ad-hoc resolve.

Only the composition root constructs concrete adapters and framework objects. A tool module does not reach for a concrete client; it receives what it needs from the runtime.

## Alternative constructors

When you build a domain type from another type, where the constructor lives is decided by what it must import.

| Source type | Constructor form | Where it lives |
| --- | --- | --- |
| stdlib, primitive, or another domain type | `@classmethod` `from_x` on the type | the domain module (adds no import) |
| a framework, web, ORM, or vendor SDK type | free factory function | the adapter that owns that outside concept |
| a value that only exists at one boundary | free factory, co-located with the frozen value | the adapter module for that boundary |

Tie-breaker: if the constructor would force the type's own module to import something it otherwise would not, it does not belong on the type. A `Caller.from_request(request)` classmethod drags the web framework into the domain module; a free `caller_from_request(request)` in the web adapter does not.

The free factory maps or assembles, it does not become the invariant-enforcer. The domain type's own constructor still rejects invalid construction, so holding an instance is proof it is valid (`AGENTS.md`, "parsed types are self-guaranteeing"). A factory that skipped that and left the type constructible in an invalid state would move the guarantee out of the type, which is the thing that rule forbids.

Precedents in the tree:

- Classmethod on a domain type, source is an internal parsed type: `StartupIdentity.from_configured_credential(settings)` and `McpRuntime.for_profile(settings)` build from `Settings`.
- Free factory in an adapter, source is a framework type: `require_request_bearer(request)` reads a Starlette `Request` in `auth/`, rather than a `from_request` classmethod on a domain type.
- Free factory over a sum type at the app layer: `resolve_pipefy_auth` returns a `ResolvedAuth` and `build_httpx_auth` is total over it; `build_pipefy_mcp_server` assembles the server.

## Testing at boundaries

A port defines a contract, and the same contract test suite runs against the real adapter and against any fake that implements the port. The fake exists to isolate the driving side (drive a tool without the live Pipefy API); it does not replace the real adapter's own tests. The preference in coding principle 4 stands: exercise real infrastructure over mocks, because a mock only tests your understanding of a dependency. The port contract is what keeps a fake honest, since the real adapter must pass the identical suite.

Drive a package through its driving port, not through internals. A test that constructs the app and invokes the tool handler exercises the same path a client does.

## Enforcement

Between packages: ruff `TID251` banned-api per package, run in CI ("banned upward imports").

Within `pipefy_mcp`: import-linter. The contract lives in `packages/mcp/pyproject.toml` under `[tool.importlinter]` and runs in CI (`cd packages/mcp && uv run lint-imports`), alongside the ruff banned-import steps. It encodes the inward-only spine that holds today.

The next ratchet is disabled until the domain has a home. Once the scattered domain helpers move into a dedicated framework-free module, a forbidden contract locks it so it cannot import the MCP SDK, Starlette, or the vendor SDK. It cannot target `pipefy_mcp.core` today, because that package holds the runtime (the composition root), which must import those. The disabled contract and the switch to turn it on are recorded in `packages/mcp/pyproject.toml`.

This is a pilot on `pipefy_mcp`. The other packages keep their `TID251` inter-package guards; extending intra-package contracts to them is a later step.

## Reconciliation with the existing rules

This document reinforces the rules already in `AGENTS.md` and the coding principles; four points are worth stating so they are not misread:

- The composition root is per app, not one for the repo, and keeps the name `AGENTS.md` already uses (the per-app runtime).
- "Invert only where there is payoff" is a statement about where the seam sits (domain to infrastructure), not a relaxation of coding principle 3. Direct concrete imports in the domain remain an inversion violation.
- "Contract tests at ports" is not a preference for mocks. The real-infrastructure preference stands; the port contract is the shared spec a fake and the real adapter must both satisfy.
- A free factory maps or assembles; it does not take over invariant enforcement. The domain type's constructor still self-guarantees.
