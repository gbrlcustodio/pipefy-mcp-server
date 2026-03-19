"""Shared Pydantic validators and annotated types."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

NonBlankStr = Annotated[
    str,
    BeforeValidator(str.strip),
    Field(min_length=1, description="Non-empty string after stripping whitespace"),
]
