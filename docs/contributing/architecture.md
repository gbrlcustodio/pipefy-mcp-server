# Architecture

This document describes the shape of the code: the layers inside a package, what each layer may import, and the three surfaces the repository ships. It is contributor explanation. For the rules about writing code at a boundary (validation, parsing, typing, arguments), see [`conventions.md`](conventions.md).

## Layer model

We follow a hexagonal shape with a deliberately thin core. Most of this codebase is an adapter. `pipefy-mcp-server` wraps the MCP SDK and the Pipefy GraphQL API, and `pipefy-cli` wraps Typer over the same SDK. The business logic that is genuinely ours is small, so the domain tier is small, and most modules legitimately touch a framework or the vendor SDK. That is the point of an adapter, not a leak.

Three roles:

- Domain (core). Pure types and logic. Owns the interfaces (ports) it needs from the outside. Imports no framework and no vendor SDK.
- Adapter. Translates an outside type into a domain type, or registers domain behavior with a framework. Framework and SDK imports live here. A driving adapter is entered from the outside (an MCP tool call, a CLI command). A driven adapter is called by the core to reach the outside (Pipefy data access).
- Composition root. The per-app wiring built once at startup. It is the only place that constructs concrete adapters and framework objects and hands them to everything else.

The current mapping of these roles onto module paths lives with the code. See `packages/mcp` and its `pyproject.toml` import-linter contract, which is the source of truth for the layering that holds today. This document states the model, not the snapshot, so it does not go stale as modules move.

## Dependency rule

Imports point inward. An outer role may import an inner one, never the reverse. Between packages this is enforced by ruff `TID251`. Within a package it is enforced by import-linter. The enforced spine is the acyclic import chain that holds today, and it is recorded in the package's `pyproject.toml` rather than restated here.

Every package has at least one driving port, which is how it is entered, and, if it reaches outside, a driven port, which is how it reaches out.

## Ports and dependency inversion

Business logic depends on an interface shaped by what it needs, and the adapter implements it. This names where that seam sits, so "invert" is not read as "invert everything". The seam is domain to infrastructure: a vendor SDK, the network, a database. You define a narrow interface in the domain (`find_by_email`, not `Database.query`), scoped to one need, and let an adapter satisfy it. You do not invert stdlib calls, and you do not invert calls that stay inside the domain. Wrapping `dict` or a pure helper behind an interface buys nothing.

Introduce an owned port where there is payoff, a test seam or a second implementation. The clearest first candidate is a narrow protocol over the Pipefy engine, so tool logic can be exercised against a fake without the real client.

## Composition root

Effects are built once, in a per-app runtime, at startup. Parsed types are decisions and cost no I/O to build, so they are constructed freely. Effects such as keychain reads, network calls, and building clients or verifiers live in the runtime, the single place where raw settings become domain types and wired resources. There is one composition root per app package, not one for the repo. Only the composition root constructs concrete adapters and framework objects. A tool module does not reach for a concrete client. It receives what it needs from the runtime. A shared package exports parsed types and resolvers, not app wiring or effects. Whether an app wires eagerly and fails fast at boot, or keeps effectful members lazy, is a per-app choice.

## The three surfaces

One domain is exposed through three surfaces, and each surface is matched to its user.

- The SDK is for a programmer. It executes a named operation deterministically and returns a domain value. It is the deterministic execution layer.
- The CLI is for a human or a script in a shell. It is thin over the SDK, and discovery is a separate command, which is idiomatic where composition is the point.
- The MCP server is for an LLM acting on intent. It takes a human intent and keeps ids internal to the tool.

The layer split follows from this. The SDK executes. The application layer, which is the CLI and the MCP server, owns intent, orchestration, and outcomes. Place a behavior by its determinism. Deterministic resolution, such as a friendly id to a uuid, lives in the SDK. Ambiguous resolution lives in the application layer, where a human or an LLM can decide.

The identifier form is a per-surface decision, not one global choice. The SDK defaults to numeric-first ids. The CLI takes deterministic ids and gates any name resolution behind an explicit flag that fails closed under automation. The MCP server takes the human intent as the primary input and resolves ambiguity by elicitation when the client supports it. Interactive behavior versus ambient behavior follows from the surface's declared capability, so a headless caller stays deterministic.

### Earn the surface

Default to the smaller surface. Add a field, a method, a tool, or a flag only when a user need earns it. This is why the MCP layer prefers a tool that expresses an outcome over one tool per API endpoint. The tool count tracks user intent, not the wire. The per-tool outcome design lives in the MCP docs.

## Planned: vertical slices

A larger restructure organizes each package by domain vertical slice rather than technical layer, with the four roles (models, client, use cases, facade) held by an import-linter contract inside each slice. It is deferred to its own initiative, including the `PipefyClient` to `Pipefy` rename. The full reasoning is preserved in the branch history of this change.
