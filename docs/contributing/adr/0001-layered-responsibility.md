# ADR-0001: Layered responsibility

Status: proposed
Date: 2026-07-20

## Context

The SDK, the MCP server, and the CLI all touch the same domain. Without a stated rule, multi-step logic and product decisions drifted into whichever layer was open. A hidden `get_pipe` inside an SDK method is the symptom: orchestration the caller cannot see, living below the layer that owns the intent. A second question was left open: when can identifier resolution live in the SDK at all?

## Decision

The SDK is the deterministic execution layer. The application layer, which is the MCP tools and the CLI, owns intent, orchestration, and product policy. The SDK executes a named operation predictably. The application layer decides which operations to run to satisfy an intent.

Place a behavior by its determinism. Deterministic resolution, where the scoping id makes exactly one answer correct, lives in the SDK. The technique is to require the scoping id that makes the key unique, for example resolving `(repo_id, slug)` rather than a bare slug. Genuine ambiguity, where choosing an answer is a judgment call, lives in the application layer.

This split covers the three applications (SDK, CLI, MCP server) and the shared support libraries (`auth`, `infra`). A shared library is not an application. It owns no driving port. It adds a driven port only where there is payoff, so a pure-utility library holds none.

## Consequences

A reader locates any behavior by one question: is it how to execute an operation (SDK) or what the user wants (application layer). This is the mainstream hexagonal split, so the model is recognizable to any contributor. Resolution placement is the sharpest rule and the least standardized, so it carries the highest teaching burden. A newcomer will not arrive knowing it, and mis-classifying an ambiguous resolution as deterministic puts a judgment call in the wrong layer.

The current rule lives in [`architecture.md`](../architecture.md).
