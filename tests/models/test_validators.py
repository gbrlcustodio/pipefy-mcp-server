"""Tests for shared Pydantic validators and annotated types."""

import pytest
from pydantic import BaseModel

from pipefy_mcp.models.validators import PipefyId


class _IdModel(BaseModel):
    some_id: PipefyId


@pytest.mark.unit
class TestPipefyId:
    def test_accepts_string(self):
        m = _IdModel(some_id="25901")
        assert m.some_id == "25901"

    def test_coerces_int(self):
        m = _IdModel(some_id=25901)
        assert m.some_id == "25901"

    def test_coerces_float(self):
        m = _IdModel(some_id=25901.0)
        assert m.some_id == "25901"

    def test_coerces_float_truncates_decimal(self):
        m = _IdModel(some_id=25901.9)
        assert m.some_id == "25901"

    def test_preserves_non_numeric_string(self):
        m = _IdModel(some_id="abc-def")
        assert m.some_id == "abc-def"

    def test_strips_whitespace(self):
        m = _IdModel(some_id="  25901  ")
        assert m.some_id == "25901"

    def test_rejects_empty_string(self):
        with pytest.raises(Exception):
            _IdModel(some_id="")

    def test_rejects_whitespace_only(self):
        with pytest.raises(Exception):
            _IdModel(some_id="   ")

    def test_rejects_none(self):
        with pytest.raises(Exception):
            _IdModel(some_id=None)

    def test_rejects_bool_true(self):
        with pytest.raises(Exception):
            _IdModel(some_id=True)

    def test_rejects_bool_false(self):
        with pytest.raises(Exception):
            _IdModel(some_id=False)
