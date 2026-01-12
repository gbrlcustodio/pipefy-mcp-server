"""Tests for the CommentInput Pydantic model."""

import pytest
from pydantic import ValidationError

from pipefy_mcp.models.comment import MAX_COMMENT_TEXT_LENGTH, CommentInput


@pytest.mark.unit
@pytest.mark.parametrize("card_id", [0, -1, -999])
def test_comment_input_rejects_card_id_zero_or_negative(card_id: int):
    """CommentInput should reject card_id <= 0."""
    with pytest.raises(ValidationError):
        CommentInput(card_id=card_id, text="ok")


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "\n\t  "])
def test_comment_input_rejects_blank_or_whitespace_text(text: str):
    """CommentInput should reject blank/whitespace-only text."""
    with pytest.raises(ValidationError):
        CommentInput(card_id=1, text=text)


@pytest.mark.unit
def test_comment_input_rejects_text_over_max_length():
    """CommentInput should reject text longer than the maximum length."""
    too_long_text = "a" * (MAX_COMMENT_TEXT_LENGTH + 1)
    with pytest.raises(ValidationError):
        CommentInput(card_id=1, text=too_long_text)


@pytest.mark.unit
def test_comment_input_accepts_text_at_max_length_boundary():
    """CommentInput should accept text exactly at the max length boundary."""
    text = "a" * MAX_COMMENT_TEXT_LENGTH
    comment = CommentInput(card_id=1, text=text)
    assert comment.card_id == 1
    assert comment.text == text


@pytest.mark.unit
def test_comment_input_valid_input():
    """CommentInput should accept valid inputs."""
    comment = CommentInput(card_id=123, text="Hello world")
    assert comment.card_id == 123
    assert comment.text == "Hello world"
