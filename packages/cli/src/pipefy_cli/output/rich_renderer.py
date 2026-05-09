"""Human-readable output via Rich."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table


def _console_default(console: Console | None) -> Console:
    if console is not None:
        return console
    return Console()


def _render_json_syntax(console: Console, payload: Any) -> None:
    text = json.dumps(payload, indent=2, default=str)
    console.print(Syntax(text, "json", theme="monokai", word_wrap=True))


def _render_list(console: Console, data: list[Any]) -> None:
    if not data:
        console.print("(empty list)")
        return
    if all(isinstance(item, BaseModel) for item in data):
        rows = [item.model_dump(mode="json") for item in data]
        _render_list_of_dicts(console, rows)
        return
    if all(isinstance(item, dict) for item in data):
        _render_list_of_dicts(console, data)
        return
    if all(not isinstance(item, (dict, list, BaseModel)) for item in data):
        table = Table("value", show_header=True)
        for item in data:
            table.add_row(str(item))
        console.print(table)
        return
    _render_json_syntax(console, data)


def _render_list_of_dicts(console: Console, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = sorted({k for row in rows for k in row})
    if not keys:
        _render_json_syntax(console, rows)
        return
    table = Table(*keys, show_header=True)
    for row in rows:
        table.add_row(*(str(row.get(k, "")) for k in keys))
    console.print(table)


def render(data: Any, *, console: Console | None = None) -> None:
    """Print a human-friendly representation of structured SDK payloads.

    Lists of uniform dict-like rows render as a Rich ``Table``. Other nested
    values render as syntax-highlighted JSON. Primitives print directly.

    Args:
        data: Plain values, mappings, sequences, or a Pydantic ``BaseModel``.
        console: Optional ``Console`` (e.g. ``Console(file=..., record=True)``
            in tests). Defaults to a stdout ``Console``.
    """
    c = _console_default(console)
    if isinstance(data, BaseModel):
        _render_json_syntax(c, data.model_dump(mode="json"))
        return
    if isinstance(data, list):
        _render_list(c, data)
        return
    if isinstance(data, dict):
        _render_json_syntax(c, data)
        return
    c.print(data)
