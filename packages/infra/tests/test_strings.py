"""Tests for ``pipefy_infra.strings.strip_str``."""

import pytest

from pipefy_infra.strings import strip_str


@pytest.mark.unit
def test_strip_str_strips_surrounding_whitespace() -> None:
    assert strip_str("  hello  ") == "hello"
    assert strip_str("\thttps://app.pipefy.com\n") == "https://app.pipefy.com"


@pytest.mark.unit
def test_strip_str_returns_empty_for_whitespace_only() -> None:
    assert strip_str("   ") == ""


@pytest.mark.unit
@pytest.mark.parametrize("value", [None, 42, True, ["a"], {"k": "v"}])
def test_strip_str_passthrough_for_non_strings(value: object) -> None:
    assert strip_str(value) is value
