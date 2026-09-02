"""Hand-written runtime the generated GraphQL input models are built on.

`_generated.py` next to this file is written by
`scripts/generate_graphql_inputs.py` and must not be edited. Everything that
needs a human decision — the scalar mapping, the serialization rule, the base
class config — lives here instead, so a regeneration never overwrites it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

PipefyGraphQLId = str | int
"""A GraphQL ``ID``, passed through in whatever form the caller supplied.

``ID`` serializes as a string or an integer, and Pipefy needs both. ``updatePipe``
takes either for ``id``, but ``createFieldCondition`` returns an opaque 500 when
``expressions_structure`` entries arrive as strings instead of integers. A mapping
that coerced in either direction would break one of those two, so this one does
not coerce at all.
"""

GraphQLJson = Any
"""A GraphQL ``JSON`` / ``Json`` / ``UndefinedInput`` scalar: an arbitrary value."""


class GraphQLInput(BaseModel):
    """Base class for a model that mirrors one Pipefy GraphQL input object.

    ``extra="forbid"`` mirrors the API rather than adding a rule on top of it.
    Pipefy answers an unknown input field with
    ``InputObject 'UpdatePipeInput' doesn't accept argument 'nmae'``, so
    forbidding extras only moves that rejection to before the request, where it
    names the field without spending a round trip.

    A field left unset is omitted from the payload, so a partial update stays
    partial. The consequence is that no field can be sent as an explicit
    ``null``, which is also true of the ``**attrs`` handling these models
    replace.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def to_graphql_input(self) -> dict[str, Any]:
        """Render this model as the ``input`` variable of its mutation."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def describe_input_rejection(error: ValidationError) -> str:
    """Name the first rejected field, without echoing the value it carried.

    Both the MCP tool layer and the CLI wrap this in their own error shape. The
    field is reported by its dotted path, so a nested one reads
    ``preferences.findabl`` rather than being attributed to the outer input.
    The value is deliberately left out: a caller who puts a secret in the wrong
    field should not see it repeated back in a transcript or a shell log.
    """
    first = error.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "input"
    match first["type"]:
        case "extra_forbidden":
            return f"'{field}' is not an accepted field"
        case "missing":
            return f"'{field}' is required"
        case _:
            message = first["msg"]
            return f"'{field}' {message[:1].lower()}{message[1:]}"


__all__ = [
    "GraphQLInput",
    "GraphQLJson",
    "PipefyGraphQLId",
    "describe_input_rejection",
]
