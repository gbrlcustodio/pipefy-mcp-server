"""Shared Pydantic validators and annotated types."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

NonBlankStr = Annotated[
    str,
    BeforeValidator(str.strip),
    Field(min_length=1, description="Non-empty string after stripping whitespace"),
]


def _coerce_id_to_str(v: object) -> str:
    """Coerce numeric values to string, strip whitespace, and reject empty IDs.

    Why: mcporter CLI infers unquoted numeric values as int, but Pipefy IDs
    are always strings in the GraphQL API.  ``bool`` is excluded because
    ``isinstance(True, int)`` is ``True`` in Python and coercing ``True`` →
    ``"1"`` would silently hide a caller bug.

    Whitespace-only and empty strings are rejected with a ``ValueError`` so
    that ``PipefyId`` enforces non-emptiness at the Pydantic boundary.
    """
    if isinstance(v, bool):
        raise ValueError("Boolean is not a valid Pipefy ID")
    if isinstance(v, (int, float)):
        return str(int(v))
    if isinstance(v, str):
        s = v.strip()
        if not s:
            raise ValueError("ID must not be empty or whitespace-only")
        return s
    return v


PipefyId = Annotated[str, BeforeValidator(_coerce_id_to_str)]
"""String ID that accepts numeric input, strips whitespace, and rejects empty values.

Mitigates clients (e.g. mcporter) that send ``25901`` instead of ``"25901"``
for ID parameters.  Empty strings and whitespace-only values are rejected at
the Pydantic boundary.
"""
