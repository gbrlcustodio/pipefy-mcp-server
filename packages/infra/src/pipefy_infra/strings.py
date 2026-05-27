"""Generic string helpers shared across the workspace.

A utility bucket: nothing here is bound to a single bounded context. The
current sole inhabitant (:func:`strip_str`) was extracted to dedup the
``_strip_str`` ``field_validator`` body shared by ``AuthSettings`` and
``PipefySettings``, but the helper itself is plain ``object -> object``
and works anywhere.
"""

from __future__ import annotations


def strip_str(value: object) -> object:
    """Strip surrounding whitespace from a string value; pass-through otherwise.

    Primary use: inside a ``field_validator(..., mode="before")`` classmethod
    on a ``BaseSettings`` subclass so a stray leading / trailing space from
    copy-paste does not trip the per-field ``pattern`` constraint.
    Empty-after-strip still fails the pattern (the "empty raises" contract).
    """
    if isinstance(value, str):
        return value.strip()
    return value


__all__ = ["strip_str"]
