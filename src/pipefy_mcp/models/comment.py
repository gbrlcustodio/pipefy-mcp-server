"""Pydantic models for comment-related entities."""

from pydantic import BaseModel, Field, field_validator

MAX_COMMENT_TEXT_LENGTH = 1000


class CommentInput(BaseModel):
    """Validated input for creating a comment on a Pipefy card.

    Attributes:
        card_id: The ID of the card to comment on (must be positive).
        text: The comment text (1-1000 characters, cannot be blank).
    """

    card_id: int = Field(gt=0, description="Card ID must be a positive integer")
    text: str = Field(
        min_length=1,
        max_length=MAX_COMMENT_TEXT_LENGTH,
        description="Comment text (1-1000 characters)",
    )

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        """Ensure text is not blank or whitespace-only."""
        if v.strip() == "":
            raise ValueError("text must not be blank")
        return v


class UpdateCommentInput(BaseModel):
    comment_id: int = Field(gt=0, description="Comment ID must be a positive integer")
    text: str = Field(
        min_length=1,
        max_length=MAX_COMMENT_TEXT_LENGTH,
        description="Comment text (1-1000 characters)",
    )

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        if v.strip() == "":
            raise ValueError("text must not be blank")
        return v


class DeleteCommentInput(BaseModel):
    comment_id: int = Field(gt=0, description="Comment ID must be a positive integer")
