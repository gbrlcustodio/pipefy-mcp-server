"""Pure validation for Pipefy label ``color`` (hex ``#RGB`` or ``#RRGGBB``)."""

from __future__ import annotations

import re

_LABEL_COLOR_HEX_6_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LABEL_COLOR_HEX_3_RE = re.compile(r"^#[0-9A-Fa-f]{3}$")


def normalize_label_color(value: str) -> str:
    """Normalize label color to ``#RRGGBB`` (accepts ``#RGB`` or ``#RRGGBB``)."""
    stripped = value.strip()
    if _LABEL_COLOR_HEX_3_RE.fullmatch(stripped):
        r, g, b = stripped[1], stripped[2], stripped[3]
        return f"#{r}{r}{g}{g}{b}{b}".upper()
    if _LABEL_COLOR_HEX_6_RE.fullmatch(stripped):
        return f"#{stripped[1:].upper()}"
    raise ValueError(f"expected #RGB or #RRGGBB hex color, received {stripped!r}")
