# Conventions

This document holds the rules for writing code at a boundary: how data is validated, parsed, typed, and shaped as it crosses an edge. It is contributor explanation. For the shape of the code and the three surfaces, see [`architecture.md`](architecture.md).

## Type validation at boundaries, not inside

Static typing is the contract for internal code. Do not re-check it at runtime. A parameter annotated `value: str` is trusted by every internal caller, and a type checker, not a hand-written `isinstance` guard, is the right place to enforce it. Runtime type guards inside internal functions reinvent dynamic typing by hand and set the wrong norm. Do it once and it becomes the expectation everywhere.

Runtime type checks belong only at a trust boundary, where untyped or external data crosses into typed code and static analysis cannot follow.

- The MCP tool signature is the boundary. `MCPServer` builds a pydantic model per tool from the signature, so a scalar arg declared `color: str` is coerced and rejected there. SDK planners called behind it trust the type and must not guard it again.
- The CLI command signature is the same kind of boundary. Typer parses and coerces options against their annotations, and the same SDK planners run behind it.
- A `dict`-typed tool arg validates the container but not its nested values. Validating that nested, un-schema'd structure is legitimate boundary work, not defensive noise.

When a type-related failure looks plausible, the fix is a type checker in CI, not a per-function guard.

## Parse, don't validate

The boundary check should return a type that carries its result, not a bool or a bare raise that the interior re-derives. Validation that only raises throws away what it learned. The value flows on with its original loose type, so every downstream caller re-checks or re-normalizes it. Parsing turns loose input into a precise type once, and that type carries the proof, so the interior is total.

- pydantic-settings models are the parse step for env vars: raw strings in, a typed settings object out, illegal values rejected at construction. Normalize there, so no consumer re-normalizes the same field later.
- Prefer a closed sum type over a bag of optionals when inputs are mutually exclusive or co-dependent. `resolve_pipefy_auth` returns a `ResolvedAuth`, so the winning credential tier is kept in the type, and the consumer is total over it with no `None` branch.
- Make illegal states unrepresentable instead of checking for them downstream. A cross-field rule such as "verify_audience requires audience" is a sum type wearing two fields.

A function that accepts the parsed type may assume the guarantee and must not re-check it. This pairs with the boundary rule above. That one says where to validate. This one says what the check should hand back.

## Parsed types are self-guaranteeing

A parsed type rejects invalid construction itself. It does not rely on the pipeline that usually builds it. Its constructor enforces every invariant it claims, so holding an instance is proof it is valid, and a hand-written instance cannot be invalid.

- A recurring value-plus-invariant pair earns a dedicated leaf type rather than a bare `str`, so every field holding one inherits the guarantee. A one-off invariant stays with its owner.
- When validity depends on a policy, carry the policy as part of the value, so the constructor has the context to judge it.
- A runtime-erased alias does not qualify. It disappears at runtime, so an invalid value still constructs. Reach for a type whose constructor actually runs.
- Settings models stay pure data readers. A cross-field rule fails fast at construction, not through a projection method a consumer must remember to call.

## Type ownership at boundaries

A domain type must not carry a framework or SDK type as a field, and must not take one in a public signature. If it does, every consumer of that type transitively depends on the framework, and the domain stops being swappable.

This binds domain types, not adapters. An adapter mapping an outside value onto a currency type is correct. A JWT verifier that maps validated claims onto the SDK `AccessToken` holds `AccessToken` as the adapter's currency, which is fine. The rule bites when a type meant to be domain holds a raw request or a raw SDK result, and forces that dependency on everyone downstream.

## Response typing at the boundary

The rules above type data flowing in. Data flowing back out follows the same idea, parse once at the boundary, but the shape depends on who consumes it. There are two response boundaries, with two defaults.

The published SDK facade (`pipefy`) is a public contract. Its callers are not only the MCP server and the CLI in this repo. The distribution ships under a bare name, so a consumer we do not control can hold any return value. The return type is therefore the API, and it is a domain model, not a bare `dict`. The model settles casing to one form, drops the `edges`/`node` envelope, and validates the wire response once at this seam, so a malformed shape fails here and not deep in a caller. It keeps the raw wire reachable as `raw` for a caller who wants it. Build the model with a `from_x` classmethod on the type (see the alternative-constructor rule below). Roll the models out one resource at a time, not in a single sweep.

An internal boundary we own both ends of stays a `TypedDict`. The MCP tool-output envelopes are the case: each stores the raw `data` verbatim and hands it to a serializer, so a validating model there guards nothing and only adds cost. Upgrade one to a model only when a consumer re-derives an invariant the payload already holds, for example a duplicated `isinstance` ladder or a casing hedge across two products.

A bare `dict` return is wrong at both boundaries. Even a pure pass-through gets a named shape. The choice is `TypedDict` versus domain model, never an untyped dict.

## Alternative constructors

When you build a domain type from another type, where the constructor lives is decided by what it must import.

| Source type | Constructor form | Where it lives |
| --- | --- | --- |
| stdlib, primitive, or another domain type | `@classmethod` `from_x` on the type | the domain module (adds no import) |
| a framework, web, ORM, or vendor SDK type | free factory function | the adapter that owns that outside concept |
| a value that only exists at one boundary | free factory, co-located with the frozen value | the adapter module for that boundary |

Tie-breaker: if the constructor would force the type's own module to import something it otherwise would not, it does not belong on the type. A `Caller.from_request(request)` classmethod drags the web framework into the domain module. A free `caller_from_request(request)` in the web adapter does not.

The free factory maps or assembles. It does not become the invariant-enforcer. The domain type's own constructor still rejects invalid construction, so holding an instance is proof it is valid. The wire-to-domain mapping named in the response-typing rule above is the classmethod form, `Model.from_wire` on the domain model, because its source is a wire dict and it adds no framework import.

## Single-form arguments

Every identifier and argument is an explicit single-form field. A second form is a separate named field, a `_by_*` sibling, or a sum type the caller constructs, never one argument that inspects a value to guess which form it received. The caller declares the form by the field it fills, so a resource literally named like an id is handled by field choice, not by a guess.

When one method must accept exactly one of two forms and is not split into a `_by_*` sibling, encode the argument as a sum type the caller constructs (`PipeRef = ById | ByUuid`) and match it exhaustively, rather than two optional parameters that make both-set and neither-set representable. At the CLI and MCP boundary the separate scalar fields still stand, and the boundary parses whichever field was set into the variant. Prefer the two-method split for small signatures and the sum-type argument for large or repeated ones.

## Testing at boundaries

A port defines a contract, and the same contract test suite runs against the real adapter and against any fake that implements the port. The fake isolates the driving side, so a tool runs without the live Pipefy API. It does not replace the real adapter's own tests. Exercise real infrastructure over mocks, because a mock only tests your understanding of a dependency. The port contract is what keeps a fake honest, since the real adapter must pass the identical suite.

A client test binds to the typed SDK surface, a fake resource over the spec'd executor, not to a wire-shaped mock of a flat method. Drive a package through its driving port, not through its internals. A test that constructs the app and invokes the tool handler exercises the same path a client does.

## A constraint is a refactor candidate

A constraint we imposed on ourselves is a refactor candidate, not a fixed boundary. When an in-house rule blocks a better name or a cleaner structure, the default is to remove the rule, not to accept the worse option. For example, name the low-level layer on merits even though the good name is currently held by another type: free the name by renaming, rather than settle for a second-best term.

This applies only to constraints we own. A constraint set by the vendor API or the runtime is not ours to lift. Weigh the churn. The guard against endless renames is that the constraint must actually block something, not merely feel imperfect.

Record a concrete candidate as a GitHub issue, not in a docs file. An issue closes when the work ships, so the tracker stays true. A list of candidates in docs has no forcing function, so it goes stale once the work lands and nobody deletes the entry. Docs hold the durable rule. The tracker holds the closeable task.
