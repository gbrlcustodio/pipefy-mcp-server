"""Pydantic models for comment-related entities."""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from pipefy_mcp.models.validators import PipefyId

MAX_COMMENT_TEXT_LENGTH = 1000

# Strip first so blank/whitespace-only fails min_length.
_CommentText = Annotated[
    str,
    BeforeValidator(str.strip),
    Field(
        min_length=1,
        max_length=MAX_COMMENT_TEXT_LENGTH,
        description="Comment text (1-1000 characters)",
    ),
]


class CommentInput(BaseModel):
    """Validated input for creating a comment on a Pipefy card.

    Attributes:
        card_id: The ID of the card to comment on (must be positive).
        text: The comment text (1-1000 characters, cannot be blank).
    """

    card_id: PipefyId = Field(description="Card ID")
    text: _CommentText


class UpdateCommentInput(BaseModel):
    """Validated input for updating an existing comment.

    Attributes:
        comment_id: The ID of the comment to update (must be positive).
        text: The new comment text (1-1000 characters, cannot be blank).
    """

    comment_id: PipefyId = Field(description="Comment ID")
    text: _CommentText


class DeleteCommentInput(BaseModel):
    """Validated input for deleting a comment.

    Attributes:
        comment_id: The ID of the comment to delete (must be positive).
    """

    comment_id: PipefyId = Field(description="Comment ID")
