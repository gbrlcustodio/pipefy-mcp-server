# Decision records

These are immutable records of the architecturally significant decisions behind the toolkit design: how the SDK, MCP server, and CLI are layered, how their contracts are shaped, and how the code is structured. Each record holds one decision with its context and reasoning.

There are four records, one per principle. The rule each decision produced lives in a living doc, and that is what a contributor follows day to day. The record keeps the why. To change a decision, add a new record that supersedes the old one. Do not edit an adopted record. See [`authoring.md`](../authoring.md).

| ADR | Decision | Status | Current rule |
|---|---|---|---|
| [0001](0001-layered-responsibility.md) | Layered responsibility | adopted | [`architecture.md`](../architecture.md) |
| [0002](0002-typed-single-form-contract.md) | Typed, single-form contract | adopted; typed-output rollout in progress | [`conventions.md`](../conventions.md) |
| [0003](0003-mcp-tools-express-outcomes.md) | MCP tools express outcomes | partially adopted; consolidation deferred | [`mcp/README.md`](../../mcp/README.md) |
| [0004](0004-vertical-slice-structure.md) | Vertical-slice structure and naming | accepted, deferred | [`architecture.md`](../architecture.md) |

The governance rule that a self-imposed constraint is a refactor candidate lives in [`conventions.md`](../conventions.md), not as a separate record.

## Rollout epics

Three decisions carry deferred work, tracked as epics rather than in these records:

- Outcome-tool audit and consolidation (0003).
- Vertical-slice refactor and the `Pipefy` root rename (0004).
- Typed-output rollout, resource by resource with Card first (0002).

The step-by-step exploration behind these decisions is in the repository history.
