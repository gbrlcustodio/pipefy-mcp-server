"""Pydantic models for Pipefy portal input validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PortalVisibility = Literal["internal", "private", "public"]


class CreatePortalInput(BaseModel):
    """Input for creating or fetching the org's main portal via template flow."""

    organization_uuid: str | int = Field(
        description="Organization UUID or numeric organization id."
    )

    model_config = ConfigDict(extra="forbid")


class UpdatePortalInput(BaseModel):
    """Partial update payload for ``updateInterface`` (Interfaces schema)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    interface_uuid: str = Field(min_length=1)
    name: str | None = None
    visibility: PortalVisibility | None = None
    color: str | None = None
    icon: str | None = None
    display_pipefy_header: bool | None = Field(default=None, alias="displayPipefyHeader")


__all__ = [
    "CreatePortalInput",
    "PortalVisibility",
    "UpdatePortalInput",
]
