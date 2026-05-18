"""Pipe member invite input."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class MemberInvite(BaseModel):
    """One pipe member invite row (email + role)."""

    email: EmailStr
    role_name: str = Field(min_length=1)

    model_config = {"extra": "forbid"}

    @field_validator("email", mode="after")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        """Normalize casing so invites match Pipefy's typical mailbox identity."""
        return value.lower()


__all__ = ["MemberInvite"]
