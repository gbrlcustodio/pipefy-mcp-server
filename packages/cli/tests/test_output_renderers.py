"""Snapshot-style tests for CLI output renderers."""

from __future__ import annotations

from io import StringIO

from pydantic import BaseModel
from rich.console import Console

from pipefy_cli.output import json_renderer, rich_renderer


class _SampleModel(BaseModel):
    id: str
    title: str


def _test_console() -> Console:
    return Console(
        file=StringIO(),
        width=80,
        force_terminal=False,
        color_system=None,
        legacy_windows=False,
    )


def test_json_renderer_dict_snapshot() -> None:
    buf = StringIO()
    json_renderer.render({"a": 1, "b": "x"}, stream=buf)
    assert buf.getvalue() == ('{\n  "a": 1,\n  "b": "x"\n}\n')


def test_json_renderer_list_snapshot() -> None:
    buf = StringIO()
    json_renderer.render([{"id": "1"}, {"id": "2"}], stream=buf)
    assert buf.getvalue() == (
        '[\n  {\n    "id": "1"\n  },\n  {\n    "id": "2"\n  }\n]\n'
    )


def test_json_renderer_pydantic_uses_model_dump_snapshot() -> None:
    buf = StringIO()
    json_renderer.render(_SampleModel(id="c1", title="Hello"), stream=buf)
    assert buf.getvalue() == ('{\n  "id": "c1",\n  "title": "Hello"\n}\n')


def test_rich_renderer_dict_syntax_snapshot() -> None:
    console = _test_console()
    rich_renderer.render({"pipe": "p1", "count": 3}, console=console)
    out = console.file.getvalue()
    assert '"pipe"' in out
    assert '"p1"' in out
    assert "count" in out


def test_rich_renderer_list_of_dicts_table_snapshot() -> None:
    console = _test_console()
    rich_renderer.render(
        [
            {"id": "1", "name": "Alpha"},
            {"id": "2", "name": "Bravo"},
        ],
        console=console,
    )
    out = console.file.getvalue()
    assert "id" in out
    assert "name" in out
    assert "Alpha" in out
    assert "Bravo" in out


def test_rich_renderer_list_of_models_table_snapshot() -> None:
    console = _test_console()
    rich_renderer.render(
        [_SampleModel(id="a", title="One"), _SampleModel(id="b", title="Two")],
        console=console,
    )
    out = console.file.getvalue()
    assert "id" in out
    assert "title" in out
    assert "One" in out
    assert "Two" in out


def test_rich_renderer_list_of_primitives_table_snapshot() -> None:
    console = _test_console()
    rich_renderer.render(["x", "y", "z"], console=console)
    out = console.file.getvalue()
    assert "value" in out
    assert "x" in out
    assert "y" in out
    assert "z" in out


def test_rich_renderer_empty_list_snapshot() -> None:
    console = _test_console()
    rich_renderer.render([], console=console)
    assert "(empty list)" in console.file.getvalue()


def test_rich_renderer_nested_list_json_fallback_snapshot() -> None:
    console = _test_console()
    rich_renderer.render([{"a": 1}, ["nested"]], console=console)
    out = console.file.getvalue()
    assert "nested" in out


def test_rich_renderer_pydantic_syntax_snapshot() -> None:
    console = _test_console()
    rich_renderer.render(_SampleModel(id="c99", title="Card"), console=console)
    out = console.file.getvalue()
    assert "c99" in out
    assert "Card" in out


def test_rich_renderer_primitive_snapshot() -> None:
    console = _test_console()
    rich_renderer.render("plain", console=console)
    assert console.file.getvalue().strip() == "plain"
