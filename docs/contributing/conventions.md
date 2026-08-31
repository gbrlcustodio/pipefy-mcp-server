# Conventions

This document settles the decisions that recur when we write code, so a review applies a rule instead of reopening the argument. A rule belongs here when a reviewer applies it by judgment to one unit of code. For the decomposition, the dependency rule, and the split by application, see [`architecture.md`](architecture.md). That document is the map of the architecture, and CI enforces the import bans that its dependency rule produces. The role order inside a package is checked in one package alone, which its `Known gaps` section records.

How to read it. Each rule has a permanent ID, so a review comment cites `PARSE-3` rather than quoting a paragraph. A retired rule keeps its ID. Every code block is illustrative and names no shipped symbol. This document states what we commit to, and it names no gap in the current code.

## Type validation at boundaries, not inside

**VALID-1. Static typing is the contract inside the code.**

Do

- Trust an annotated parameter, and let the type checker in CI enforce it.
- If a type failure looks plausible, tighten the check in CI rather than guard the function.

Do not

- Write an `isinstance` guard in an internal function.

Why: a runtime type guard reinvents dynamic typing by hand. Do it once and it becomes the expectation everywhere.

**VALID-2. A runtime type check belongs at a trust boundary.**

Do

- Check where untyped or external data crosses into typed code.
- Treat the MCP tool signature and the CLI command signature as that boundary. Each framework builds a model from the signature and coerces there.

Do not

- Check again behind the boundary. A planner called from a tool trusts its arguments.

Why: static analysis cannot follow data that arrives from the wire. It follows everything after the boundary parsed it.

**VALID-3. A payload with a knowable shape gets a model, not a `dict`.**

Do

- Declare a model for the payload, and let the boundary build it.
- Validate nested values by hand only when the payload is genuinely arbitrary.

Do not

- Take a `dict` argument for a shape we already know.

Why: a `dict` annotation validates the container and nothing inside it. The nested check then lives in the function body, where no schema describes it to the caller.

## Parse at the boundary

**PARSE-1. A boundary hands inward a named type.**

Do

- Accept a loose shape, because the wire expresses only so much.
- Return a model, a sum type, or a `TypedDict`.

Do not

- Return a bool, a bare raise, or a bare `dict`.

Why: validation that only raises throws away what it learned, so every caller re-checks the value. Parsing produces a precise type once, and the interior is then total. This is the "parse, don't validate" rule.

**PARSE-2. A parsed type enforces itself in its own constructor.**

Do

- Reject invalid construction inside the type.
- Carry the policy in the value when validity depends on a policy, so the constructor can judge it.

Do not

- Rely on the pipeline that usually builds the value.

Why: the instance is the proof, so a hand-written instance cannot be invalid.

**PARSE-3. Keep an `Annotated` alias inside the model.**

Do

- Declare the alias on a model field.

Do not

- Put the alias in a plain function signature.

Why: the model is what travels, so its constructor is the proof. An alias carries a validator that runs where a framework reads the annotation, and it marks no value. In a plain signature the value travels as a `str` that any caller can fabricate.

Weighed: a frozen value object is stronger, because a type checker separates it and its constructor always runs. We reject it at a tool parameter, because the wrapper becomes a nested object in the generated schema. A model fills a flat string more reliably.

```python
CardId = Annotated[str, BeforeValidator(coerce_id)]

class Comment(BaseModel):
    card_id: CardId                     # the alias validates here

def notify(card_id: CardId) -> None:    # nothing validates here
    ...
```

**PARSE-4. A recurring invariant earns a named type.**

Do

- Declare a named type when the same invariant applies to the same kind of value in many places.
- Leave a one-off invariant on the model that owns it.

Why: every field that names the type inherits the invariant, so the rule has one home.

**PARSE-5. Pick the named type by the boundary.**

The direction of the data does not change the rule, so an outbound response is parsed on the same terms as an inbound argument.

| Boundary | Named type |
| --- | --- |
| env vars and config files | a settings model, normalized once at construction |
| inputs that are mutually exclusive or co-dependent | a closed sum type the caller constructs |
| the published SDK facade (`pipefy`) | a domain model, with the raw wire reachable as `raw` |
| an internal boundary we own both ends of | a `TypedDict` |

Do

- Match a sum type exhaustively, so illegal states are unrepresentable.
- Express a cross-field rule as a sum type that wears both fields.
- Give a facade model one casing, drop the `edges` and `node` envelope, and validate the response once.
- Roll a facade model out one resource at a time.
- Give even a pure pass-through a named shape.
- Upgrade an internal `TypedDict` to a model when a consumer re-derives an invariant the payload already holds.

Do not

- Take a bag of optionals where a sum type belongs.
- Put a cross-field rule in a projection method a consumer must remember to call.
- Add a validating model at an internal boundary that only stores a payload and forwards it.

Why: the facade ships under a bare name, so its return type is the API and a malformed shape must fail at the boundary. `resolve_pipefy_auth` returns `ResolvedAuth`, which keeps the winning credential tier in the type and leaves the consumer no `None` branch. A duplicated `isinstance` ladder or a casing hedge across two products is the signal to upgrade.

**PARSE-6. Inside the boundary, trust the parsed type.**

Do

- Assume the guarantee that the type carries.

Do not

- Re-check an invariant the constructor already enforced.

Why: the type already carries the guarantee. A second check invites a third, and the interior stops being total.

## Module placement

**MODULE-1. Place a module by the role it takes, not by the kind of file it is.**

Do

- Decide the role before the file name: a domain type, a driven adapter, a use case, or a facade.
- Treat a module that takes a client and orchestrates calls against it as a use case.
- Treat a module with no client and no I/O as a domain type.

Do not

- Group by file kind, such as a `validators` or a `helpers` module.

Why: `QR-14` demands that a merged change never breaks the layer order, and a misplaced module breaks it in silence. [`architecture.md`](architecture.md) states the direction between the roles, and [ADR-0004](adr/0004-vertical-slice-structure.md) holds the reasoning.

**MODULE-2. A use case lives with its package's use cases, never at the package root.**

Do

- Put SDK orchestration under `services/`.
- Put an MCP tool's orchestration in that tool's helpers module.

Do not

- Let a module at the package root take a facade and call it.

Why: `QR-14` again. A root use case sits in no layer, so no contract can hold it, and it reaches back to the facade that imports it.

## Type ownership

**OWN-1. A domain type carries no framework or third-party SDK type.**

Do

- Keep a raw request, a raw ORM row, and a raw third-party result out of a domain type.

Do not

- Hold one as a field.
- Take one in a public signature.

Why: every consumer of that type then depends on the framework transitively, and the domain stops being swappable. `MODULE-1` classifies the module, and this rule binds what a domain type inside it can hold.

**OWN-2. An adapter can hold an outside type as its own currency.**

Do

- Map an outside value onto the adapter's own currency type.

Why: the rule above binds domain types, not adapters. A JWT verifier that maps validated claims onto the MCP SDK `AccessToken` holds that type as adapter currency, which is correct.

## Ports

**PORT-1. A port is a narrow interface, scoped to one need.**

Do

- Name the port after what the caller needs (`find_by_email`, not `Database.query`).
- Let an adapter satisfy it.

Do not

- Invert a stdlib call, or a call that stays inside the domain.
- Put a port over a `dict` or a pure helper.

Why: the boundary is domain to infrastructure, so a port buys nothing inside the domain. A wide port copies the shape of the thing it hides, and the domain then depends on that shape.

**PORT-2. An owned port earns its place only where there is payoff.**

Do

- Add the port when a test injects a fake, or when a second implementation exists.

Do not

- Add a port for purity.

Why: `GraphQLExecutor` and the attachment service ports each have a fake in a test, which is the payoff. A port with one implementation and no fake is indirection.

**PORT-3. The module that performs the I/O owns the port question.**

Do

- Decide per module, by whether that module performs the I/O itself.
- Ask the question of a shared support library and of a driving adapter alike.
- Read a patched module attribute in a test as a candidate.

Do not

- Decide by the package label.

Why: a monkeypatch is the symptom of an unbuilt port. A test that rebinds an imported name works around I/O that a caller cannot hand the module. The fix is injection, and the port is what makes injection possible.

## Alternative constructors

**CTOR-1. Where a constructor lives is decided by what it must import.**

| Source type | Constructor form | Where it lives |
| --- | --- | --- |
| stdlib, primitive, or another domain type | a `from_x` classmethod on the type | the domain module, which gains no import |
| a framework, web, ORM, or third-party SDK type | a free factory function | the adapter that owns that outside concept |
| a value that exists at one boundary only | a free factory beside the frozen value | the adapter module for that boundary |

Do

- Apply the tie-breaker. A constructor that forces the type's own module to import something new does not belong on the type.
- Keep a wire-to-domain mapping as a classmethod, because a wire dict adds no framework import.

```python
# domain module
class Card(BaseModel):
    @classmethod
    def from_wire(cls, payload: dict) -> "Card": ...

# web adapter, never the domain module
def card_from_request(request: Request) -> Card: ...
```

Why: a classmethod that takes a web request drags the web framework into the domain module. The free factory keeps that import in the adapter that already owns it.

**CTOR-2. A free factory maps or assembles, and the type still enforces itself.**

Do

- Let the domain type's own constructor reject invalid construction.

Do not

- Make the factory the invariant-enforcer.

Why: the instance is the proof, so the guarantee cannot depend on which factory built it.

**CTOR-3. An intermediate type carries the same invariants as the type it mirrors.**

Do

- Give the intermediate the same declared types as the model it mirrors.
- If the intermediate feeds several domain types, shape it like the wire, as a `TypedDict` that claims no invariant.

Do not

- Reach a service through the intermediate while another surface reaches it through the model.

Why: two doors into one service means the weaker door decides. A surface that builds the intermediate by hand rewrites the checks the model already owns, and skips the ones it forgets.

## Single-form arguments

**ARG-1. Every identifier and argument is one explicit form.**

Do

- Let the caller declare the form by the field it fills.

Do not

- Inspect a value to guess which form it received.

Why: a resource named like an id is then handled by field choice, not by a guess.

**ARG-2. A second form is a separate field, a `_by_*` sibling, or a sum type.**

Do

- Encode one of two forms as a sum type the caller constructs, and match it exhaustively.

Do not

- Take two optional parameters, which makes both-set and neither-set representable.

Why: `AttachmentTarget` is the shipped form of this, a closed union of two destinations that the service matches. A caller cannot express a third state.

**ARG-3. Split small signatures into two methods, and give large or repeated ones a sum type.**

Do

- Keep the separate scalar fields at the CLI and MCP boundary, and parse whichever field was set into the variant.

Why: the boundary speaks the wire's vocabulary, and the interior speaks the sum type's.

## Earn the surface

**SURF-1. A field, a method, a tool, or a flag arrives only when a user need earns it.**

Do

- Default to the smaller surface.

Do not

- Add a parameter because the wire carries one.

Why: the tool count tracks user intent, not the wire. A surface member that no user need earns still costs every reader and every caller.

## Tool contracts

**TOOL-1. An MCP tool expresses one user outcome, and it orchestrates the steps in code.**

Do

- Put the sequence in the tool body, so one call finishes the goal.
- Expose a discovery tool only where the listing is itself what the user wants.

Do not

- Split one goal into atomic tools that the model has to chain.
- Ship a discovery tool whose only job is to feed an action tool its arguments.

Why: a chain in the model context is slow and unreliable, and the caller pays a round trip per link. A surface that mirrors the API pushes that chain onto every caller.

**TOOL-2. An MCP tool declares its own effect, and it asks for no consent.**

Do

- Declare read-only on a tool that changes nothing, which settles its kind on its own.
- Declare a write destructive unless every change it makes is additive.
- Say in a destructive description that the effect is permanent.

Do not

- Withhold execution until a second call approves it.
- Read a declaration as authorization, which is the API's alone.

Why: the protocol defaults a tool to a destructive write, so a tool that declares nothing misinforms every client that reads the hint. The client owns the policy its consumer set, so a stop inside the server overrides that policy and asks the model rather than the person.

Weighed: elicitation, rejected because a client can auto-accept it, so the prompt proves nothing about a person.

## Testing at boundaries

**TEST-1. A port's contract suite runs against the real adapter and every fake.**

Do

- Run one suite against both.
- Keep the real adapter's own tests as well.

Why: the shared contract is what keeps a fake honest, because the real adapter must pass the identical suite. A fake isolates the driving side, so a tool runs without the live Pipefy API.

**TEST-2. Exercise real infrastructure over mocks.**

Why: a mock only tests your understanding of a dependency.

**TEST-3. Drive a package through its driving port, not its internals.**

Do

- Bind a client test to the typed SDK surface, with a fake resource over the specified executor.

Do not

- Mock a flat method with a wire-shaped return.

Why: a test that constructs the app and invokes the tool handler walks the same path a client walks.

## A constraint is a refactor candidate

**CONS-1. A constraint we own is a refactor candidate.**

Do

- Remove the rule when it blocks a better name or a cleaner structure.
- Free a held name by renaming, rather than settle for a second-best term.

Do not

- Rename because a constraint feels imperfect. It must actually block something.

Why: the default is to fix the rule, not to accept the worse option. Weigh the churn before a wide rename.

**CONS-2. A constraint set by a vendor or the runtime is not ours to lift.**

Why: the rule above applies only to constraints we imposed on ourselves.
