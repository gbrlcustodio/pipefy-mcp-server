"""Tests for the CommentInput, UpdateCommentInput, and DeleteCommentInput Pydantic models."""

import pytest
from pydantic import ValidationError

from pipefy_mcp.models.comment import (
    MAX_COMMENT_TEXT_LENGTH,
    CommentInput,
    DeleteCommentInput,
    UpdateCommentInput,
)


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


@pytest.mark.unit
@pytest.mark.parametrize("comment_id", [0, -1, -999])
def test_update_comment_input_rejects_comment_id_zero_or_negative(comment_id: int):
    """UpdateCommentInput should reject comment_id <= 0."""
    with pytest.raises(ValidationError):
        UpdateCommentInput(comment_id=comment_id, text="ok")


@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "\n\t  "])
def test_update_comment_input_rejects_blank_or_whitespace_text(text: str):
    """UpdateCommentInput should reject blank/whitespace-only text."""
    with pytest.raises(ValidationError):
        UpdateCommentInput(comment_id=1, text=text)


@pytest.mark.unit
def test_update_comment_input_rejects_text_over_max_length():
    """UpdateCommentInput should reject text longer than the maximum length."""
    too_long_text = "a" * (MAX_COMMENT_TEXT_LENGTH + 1)
    with pytest.raises(ValidationError):
        UpdateCommentInput(comment_id=1, text=too_long_text)


@pytest.mark.unit
def test_update_comment_input_accepts_text_at_max_length_boundary():
    """UpdateCommentInput should accept text exactly at the max length boundary."""
    text = "a" * MAX_COMMENT_TEXT_LENGTH
    comment = UpdateCommentInput(comment_id=1, text=text)
    assert comment.comment_id == 1
    assert comment.text == text


@pytest.mark.unit
def test_update_comment_input_valid_input():
    """UpdateCommentInput should accept valid inputs."""
    comment = UpdateCommentInput(comment_id=456, text="Updated message")
    assert comment.comment_id == 456
    assert comment.text == "Updated message"


@pytest.mark.unit
@pytest.mark.parametrize("comment_id", [0, -1, -999])
def test_delete_comment_input_rejects_comment_id_zero_or_negative(comment_id: int):
    """DeleteCommentInput should reject comment_id <= 0."""
    with pytest.raises(ValidationError):
        DeleteCommentInput(comment_id=comment_id)


@pytest.mark.unit
def test_delete_comment_input_valid_input():
    """DeleteCommentInput should accept valid comment_id > 0."""
    comment = DeleteCommentInput(comment_id=789)
    assert comment.comment_id == 789
