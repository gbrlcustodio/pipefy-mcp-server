"""Pure validation for Pipefy label ``color`` (hex ``#RRGGBB`` only)."""

from __future__ import annotations

import re

_LABEL_COLOR_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_label_color(value: str) -> str:
    """Return a normalized ``#RRGGBB`` color string for Pipefy label mutations.

    Args:
        value: Raw color from MCP/CLI (stripped before validation).

    Raises:
        ValueError: When ``value`` is not exactly ``#`` plus six hex digits.
    """
    stripped = value.strip()
    if not _LABEL_COLOR_HEX_RE.fullmatch(stripped):
        raise ValueError(f"expected #RRGGBB, received {stripped!r}")
    return f"#{stripped[1:].upper()}"
