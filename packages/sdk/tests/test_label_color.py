"""Tests for label color hex validation planner."""

from __future__ import annotations

import pytest

from pipefy_sdk.label_color import normalize_label_color


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("#FF0000", "#FF0000"),
        ("#ff0000", "#FF0000"),
        ("  #E50000  ", "#E50000"),
        ("#F00", "#FF0000"),
        ("#fff", "#FFFFFF"),
    ],
)
def test_normalize_label_color_accepts_rrggbb(raw: str, expected: str) -> None:
    assert normalize_label_color(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "red",
        "blue",
        "#FF00000",
        "FF0000",
        "#GGGGGG",
        "",
        "   ",
    ],
)
def test_normalize_label_color_rejects_non_hex(raw: str) -> None:
    with pytest.raises(ValueError, match=r"expected #RGB or #RRGGBB"):
        normalize_label_color(raw)
