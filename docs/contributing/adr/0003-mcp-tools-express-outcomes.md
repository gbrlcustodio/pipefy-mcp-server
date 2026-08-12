# ADR-0003: MCP tools express outcomes

Status: proposed. The contract standards are ready. The outcome-tool consolidation is deferred.
Date: 2026-07-20

## Context

The MCP surface was close to a one-to-one map of the GraphQL API. A tool per endpoint pushes orchestration into the model context, where it is slow, expensive, and unreliable. Tools also leaned on `extra_input` and `**attrs` passthroughs and returned raw GraphQL envelopes, so the model had to parse wire noise and got nothing actionable from an error.

## Decision

An MCP tool expresses one user outcome and orchestrates the underlying steps in code, not in the model context. Do not fragment one goal into atomic operations the model must chain. Expose a discovery tool only where listing is itself the user's goal, never as a mandatory input-feeder for an action tool.

Tool contracts follow four standards. Arguments are flat and explicit: typed primitives, `Literal` for a closed set, one form per field, no guess-the-shape passthroughs. Responses are shaped and bounded, carrying pagination metadata. Errors are typed and actionable. Write gates use protocol-native elicitation, which fires when the client declares support and otherwise fails closed, so a headless client never waits on a prompt nobody can answer.

## Consequences

A full tool-surface audit is its own epic, so the outcome-shaping is deferred while the contract hygiene is adopted now. Keep primitive escape hatches beside the high-level tools, so consolidation does not hide expressiveness a caller needs. MCP design is young, so treat the outcome-shaped tool as a strong heuristic, not a settled recipe.

The current rules live in [`mcp/README.md`](../../mcp/README.md).
