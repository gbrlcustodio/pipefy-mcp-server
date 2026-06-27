"""Permissive coercion helpers for values of uncertain shape.

When a value crosses a boundary (deserialization, user input, third-party
payload) it may arrive as a string, int, float, or wrong shape entirely.
These helpers normalize the common cases without raising, and explicitly
reject misshapen types (booleans, bytes) that Python's built-in conversions
would silently accept:

- :func:`optional_int` / :func:`optional_str` / :func:`optional_float` collapse
  ``None`` and any unparseable or wrong-shape value to ``None``. Use when
  absence and malformed-input are handled identically by the caller.
- :func:`try_int` returns the input unchanged if it can't be parsed as int.
  Use when a non-numeric input is itself a meaningful value to preserve.

Booleans are rejected (or passed through, for ``try_int``) despite ``bool``
being a subclass of ``int``: a bool in a numeric- or string-shaped slot is
a shape signal, not the value ``1`` / ``0`` / ``"True"``. Bytes are likewise
rejected because ``str(b"x") == "b'x'"`` (the repr) is almost never what a
caller wants.
"""

from __future__ import annotations

import math
from typing import TypeVar

T = TypeVar("T")


def optional_int(value: object) -> int | None:
    """Return ``int(value)``, or ``None`` for None/bool/bytes/unparseable input.

    Floats truncate (``42.7 -> 42``); non-finite floats and overflowing values
    return ``None``. Numeric strings (including signed and PEP 515 underscored
    forms) parse via Python's built-in ``int()``.
    """
    if value is None or isinstance(value, (bool, bytes, bytearray)):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None


def optional_str(value: object) -> str | None:
    """Return ``str(value).strip()``, or ``None`` for None/bool/bytes/empty input.

    Booleans return ``None`` (a bool in a string-shaped slot is a shape error,
    not the literal ``'True'`` / ``'False'``). Bytes return ``None`` to avoid
    producing the bytes-repr form. Numeric inputs are stringified
    (``optional_str(42) == '42'``) for the case where a numeric id needs
    comparing against a string token.
    """
    if value is None or isinstance(value, (bool, bytes, bytearray)):
        return None
    text = str(value).strip()
    return text or None


def optional_float(value: object) -> float | None:
    """Return ``float(value)``, or ``None`` for None/bool/bytes/unparseable input.

    Non-finite floats (``inf``, ``-inf``, ``nan``) return ``None`` so callers
    can treat them like missing data rather than threading edge-case checks
    through every comparison.
    """
    if value is None or isinstance(value, (bool, bytes, bytearray)):
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def strip_if_str(value: object) -> object:
    """Return ``value.strip()`` if ``value`` is a ``str``, else ``value`` unchanged.

    A ``mode="before"`` field-validator helper for settings whose env / TOML
    source may carry surrounding whitespace. Non-string inputs (already-typed
    bools, ints, ``None``) pass through so each field's own validation still
    sees them in their native shape.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def try_int(value: T) -> T | int:
    """Return ``int(value)``, or ``value`` unchanged if conversion fails.

    Distinct from :func:`optional_int` in that a non-numeric input is preserved
    rather than collapsed to ``None``. Use when the caller wants to upgrade a
    numeric form to an int but leave non-numeric values alone. Booleans and
    bytes pass through unchanged (the misshapen-type rejection that
    :func:`optional_int` uses ``None`` for).
    """
    if isinstance(value, (bool, bytes, bytearray)):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return value


__all__ = ["optional_float", "optional_int", "optional_str", "strip_if_str", "try_int"]
