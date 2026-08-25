# ADR-0003: MCP tools express outcomes

Status: proposed. The contract standards are ready. The outcome-tool consolidation, the resolver migration, and the destructive-gate reshaping are deferred.
Date: 2026-07-20

## Context

The MCP surface was close to a one-to-one map of the GraphQL API. A tool per endpoint pushes orchestration into the model context, where it is slow, expensive, and unreliable. Tools also leaned on `extra_input` and `**attrs` passthroughs and returned raw GraphQL envelopes, so the model had to parse wire noise and got nothing actionable from an error.

## Decision

An MCP tool expresses one user outcome and orchestrates the underlying steps in code, not in the model context. Do not fragment one goal into atomic operations the model must chain. Expose a discovery tool only where listing is itself the user's goal, never as a mandatory input-feeder for an action tool.

Tool contracts follow four standards. Arguments are flat and explicit: typed primitives, `Literal` for a closed set, one form per field, no guess-the-shape passthroughs. Responses are shaped and bounded, carrying pagination metadata. Errors are typed and actionable. A tool declares its own effect, and it asks no human for consent.

A destructive description states that the effect is permanent, and the annotations state the kind of change. The client owns the prompt and the API owns authorization, so neither one belongs in a tool body. Where the effect reaches past the arguments the caller passed, the tool offers a dry run that reports the reach and changes nothing.

A value the caller cannot supply arrives as a resolved parameter. The tool declares the parameter with its resolver, and the resolver decides between a question to the client and a plain value. The resolver owns the fallback, so a client that answers nothing still receives a value. No tool body reads the negotiated protocol revision or the shape of its channel, and no tool returns the batched-input result itself.

## Consequences

A full tool-surface audit is its own epic, so the outcome-shaping is deferred while the contract hygiene is adopted now. Keep primitive escape hatches beside the high-level tools, so consolidation does not hide expressiveness a caller needs. MCP design is young, so treat the outcome-shaped tool as a strong heuristic, not a settled recipe.

A resolved parameter is absent from the model-facing schema, so that schema stops describing the whole tool surface. The pinned `mcp` release supplies the mechanism, so the transport choice is not ours to write, and the flat-and-explicit standard above is qualified rather than replaced.

That release fails by default: a client that declares no capability gets an error, and a decline aborts the call. The fallback is therefore deliberate work, and a caller with no human present depends on it.

A resolver runs again on each round, and an answer counts only for a question that renders identically, so a schema built at runtime needs a stable rendering. The migration is deferred: two tools ask today, and one holds state across its `await`, which makes it the honest first case.

Consent leaves the server, so the toolkit gains no way to stop a destructive call that a client approved. That is the trade rather than an oversight: a consumer who set an auto-approval list gets what they set, and no run blocks on an answer that nobody is there to give.

An annotation is fixed at registration and cannot read an argument, so a tool whose reach depends on a string declares its worst case. The raw GraphQL escape hatch is that tool. The cost is permanent, so it is a property of the function and not a gap.

The two escape hatches therefore disagree on purpose. The CLI refuses a raw mutation until the consumer passes a flag, and the MCP tool refuses nothing. A refusal in the CLI is the party in front of the human refusing, and the same refusal in the MCP server would override a policy the consumer already set.

Clients do not read the declaration the same way. Some key on the tool name alone and read no annotation, so a description that omits the permanence carries that omission to the person. The description is therefore the load-bearing half, and the annotation is the half a policy engine can act on.

The gate that ships today is the reverse of this decision, so the migration breaks the contract of every destructive tool. It is cheapest before v1.0, because a break after that owes a deprecation period first.

The current rules live in [`mcp/README.md`](../../mcp/README.md).

## Target rule

No living doc carries this rule while the migration is deferred. On adoption it joins the tool-design rules in [`mcp/README.md`](../../mcp/README.md):

- A value the caller cannot supply is a resolved parameter. Declare the parameter with its resolver, keep the fallback in the resolver, and read neither the protocol revision nor the channel in a tool body.
- A tool declares what it changes, and it asks for no consent. State permanence in a destructive description, state the kind of change in the annotations, and offer a dry run only where the caller cannot compute the reach.
