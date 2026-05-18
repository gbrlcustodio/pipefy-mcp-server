"""JSON lines to stdout for scripting."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from pydantic import BaseModel


def render(data: Any, *, stream: TextIO | None = None) -> None:
    """Serialize ``data`` as indented JSON on stdout (or ``stream``).

    Args:
        data: Plain values, mappings, sequences, or a Pydantic ``BaseModel``.
        stream: Text stream to write to. Defaults to ``sys.stdout``.
    """
    out = stream if stream is not None else sys.stdout
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
        print(json.dumps(payload, indent=2, default=str), file=out)
        return
    print(json.dumps(data, indent=2, default=str), file=out)
