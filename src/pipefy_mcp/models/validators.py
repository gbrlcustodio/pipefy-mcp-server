"""Shared Pydantic validators and annotated types."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

NonBlankStr = Annotated[
    str,
    BeforeValidator(str.strip),
    Field(min_length=1, description="Non-empty string after stripping whitespace"),
]


def _coerce_id_to_str(v: object) -> object:
    """Coerce numeric values to string for ID fields.

    Why: mcporter CLI infers unquoted numeric values as int, but Pipefy IDs
    are always strings in the GraphQL API.  ``bool`` is excluded because
    ``isinstance(True, int)`` is ``True`` in Python and coercing ``True`` →
    ``"1"`` would silently hide a caller bug.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return str(int(v))
    return v


PipefyId = Annotated[str, BeforeValidator(_coerce_id_to_str)]
"""String ID that accepts numeric input and coerces it to ``str``.

Mitigates clients (e.g. mcporter) that send ``25901`` instead of ``"25901"``
for ID parameters.
"""
