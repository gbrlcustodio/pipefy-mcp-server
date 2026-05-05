"""Tests for shared Pydantic validators and annotated types."""

import pytest
from pydantic import BaseModel, ValidationError

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

    def test_rejects_float_integral(self):
        with pytest.raises(ValidationError) as exc_info:
            _IdModel(some_id=25901.0)
        assert "Float is not a valid Pipefy ID" in str(exc_info.value)

    def test_rejects_float_fractional(self):
        with pytest.raises(ValidationError) as exc_info:
            _IdModel(some_id=25901.9)
        assert "Float is not a valid Pipefy ID" in str(exc_info.value)

    def test_rejects_list(self):
        with pytest.raises(ValidationError) as exc_info:
            _IdModel(some_id=["25901"])
        assert "Pipefy ID must be int or str, got list" in str(exc_info.value)

    def test_rejects_dict(self):
        with pytest.raises(ValidationError) as exc_info:
            _IdModel(some_id={"id": "25901"})
        assert "Pipefy ID must be int or str, got dict" in str(exc_info.value)

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
        with pytest.raises(ValidationError) as exc_info:
            _IdModel(some_id=None)
        assert "Pipefy ID must be int or str, got NoneType" in str(exc_info.value)

    def test_rejects_bool_true(self):
        with pytest.raises(Exception):
            _IdModel(some_id=True)

    def test_rejects_bool_false(self):
        with pytest.raises(Exception):
            _IdModel(some_id=False)
