"""Unit tests for ``pipefy_infra.coerce`` type-coercion helpers."""

from __future__ import annotations

import pytest

from pipefy_infra.coerce import optional_float, optional_int, optional_str, try_int


class TestOptionalInt:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            (0, 0),
            (42, 42),
            ("42", 42),
            ("  42  ", 42),
            ("-5", -5),
            ("1_000", 1000),
            (42.7, 42),
            (-0.9, 0),
            ("", None),
            ("abc", None),
            ([], None),
            ({}, None),
            (float("inf"), None),
            (float("nan"), None),
            (True, None),
            (False, None),
            (b"42", None),
            (bytearray(b"42"), None),
        ],
    )
    def test_cases(self, value: object, expected: int | None) -> None:
        assert optional_int(value) == expected


class TestOptionalStr:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            ("", None),
            ("   ", None),
            ("hello", "hello"),
            ("  hello  ", "hello"),
            (42, "42"),
            (-5, "-5"),
            (3.14, "3.14"),
            (True, None),
            (False, None),
            (b"hello", None),
            (bytearray(b"hello"), None),
        ],
    )
    def test_cases(self, value: object, expected: str | None) -> None:
        assert optional_str(value) == expected


class TestOptionalFloat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            (0, 0.0),
            (42, 42.0),
            (42.7, 42.7),
            ("42", 42.0),
            ("3.14", 3.14),
            ("  3.14  ", 3.14),
            ("", None),
            ("abc", None),
            (float("inf"), None),
            (float("-inf"), None),
            (float("nan"), None),
            (True, None),
            (False, None),
            (b"3.14", None),
        ],
    )
    def test_cases(self, value: object, expected: float | None) -> None:
        assert optional_float(value) == expected


class TestTryInt:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("42", 42),
            ("-5", -5),
            ("1_000", 1000),
            ("abc", "abc"),
            ("", ""),
            (7, 7),
            (3.9, 3),
            (None, None),
            (True, True),
            (False, False),
            (b"42", b"42"),
        ],
    )
    def test_cases(self, value: object, expected: object) -> None:
        assert try_int(value) == expected

    def test_inf_preserved(self) -> None:
        value = float("inf")
        assert try_int(value) is value
