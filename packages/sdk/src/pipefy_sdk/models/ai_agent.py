"""Pydantic models for AI Agent input validation."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipefy_sdk.models.validators import NonBlankStr

ACTION_ID_AI_BEHAVIOR = "ai_behavior"
MAX_BEHAVIORS = 5

# actionTypes that require pipeId + fieldsAttributes in metadata
_CARD_FIELD_ACTION_TYPES = frozenset(
    {"update_card", "create_card", "create_connected_card"}
)


def _validate_fields_attributes_entries(action_type: str, metadata: dict) -> None:
    """Require non-empty ``fieldsAttributes`` with ``fieldId`` and ``inputMode`` per entry."""
    fields = metadata.get("fieldsAttributes")
    if not isinstance(fields, list) or not fields:
        raise ValueError(
            f"actionType '{action_type}' requires metadata.fieldsAttributes "
            f"as a non-empty list of field entries."
        )
    for i, entry in enumerate(fields):
        if not isinstance(entry, dict):
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] must be a dict."
            )
        if not entry.get("fieldId"):
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] requires 'fieldId'."
            )
        if not entry.get("inputMode"):
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] "
                f"requires 'inputMode'."
            )


def _validate_card_field_metadata(action_type: str, metadata: dict) -> None:
    """Validate metadata for actions that operate on card fields.

    Args:
        action_type: The actionType string (used in error messages).
        metadata: The metadata dict from the action.

    Raises:
        ValueError: When required keys are missing or malformed.
    """
    if not metadata.get("pipeId"):
        raise ValueError(
            f"actionType '{action_type}' requires metadata.pipeId "
            f"(the pipe where the action executes)."
        )
    _validate_fields_attributes_entries(action_type, metadata)


def _validate_create_table_record_metadata(metadata: dict) -> None:
    """Validate metadata for create_table_record (table row, not pipe fields)."""
    if not metadata.get("tableId"):
        raise ValueError(
            "actionType 'create_table_record' requires metadata.tableId "
            "(target database table ID)."
        )
    _validate_fields_attributes_entries("create_table_record", metadata)


def _validate_send_email_template_metadata(metadata: dict) -> None:
    """Validate metadata for send_email_template actions."""
    template_id = metadata.get("emailTemplateId")
    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError(
            "actionType 'send_email_template' requires metadata.emailTemplateId "
            "(non-empty email template ID)."
        )
    if "allowTemplateModifications" in metadata:
        mod = metadata["allowTemplateModifications"]
        if not isinstance(mod, bool):
            raise ValueError(
                "actionType 'send_email_template': metadata.allowTemplateModifications "
                "must be a boolean when set."
            )


def _validate_move_card_metadata(metadata: dict) -> None:
    """Validate metadata for move_card actions.

    Raises:
        ValueError: When destinationPhaseId is missing or blank.
    """
    dest = metadata.get("destinationPhaseId")
    if not isinstance(dest, str) or not dest.strip():
        raise ValueError(
            "actionType 'move_card' requires metadata.destinationPhaseId "
            "(the target phase ID)."
        )


def _validate_action_metadata(action: AiBehaviorActionAttributes) -> None:
    """Validate metadata for a single action based on its actionType.

    Unknown actionTypes are passed through without validation.
    """
    action_type = action.action_type or ""
    metadata = action.metadata if isinstance(action.metadata, dict) else {}

    if action_type in _CARD_FIELD_ACTION_TYPES:
        _validate_card_field_metadata(action_type, metadata)
    elif action_type == "move_card":
        _validate_move_card_metadata(metadata)
    elif action_type == "create_table_record":
        _validate_create_table_record_metadata(metadata)
    elif action_type == "send_email_template":
        _validate_send_email_template_metadata(metadata)


class AiBehaviorCapabilityAttributes(BaseModel):
    """One entry in ``aiBehaviorParams.capabilitiesAttributes``.

    The typed shell only; no shape or enum validation lives here. Legacy shapes
    (e.g. ``{"type": "advanced_ocr"}``) round-trip verbatim through ``extra="allow"``.
    Capability shape/enum rules are declared on this model in a follow-up.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    capability_type: str | None = Field(default=None, alias="capabilityType")
    enabled: bool | None = None


class AiBehaviorActionAttributes(BaseModel):
    """One entry in ``aiBehaviorParams.actionsAttributes``.

    ``metadata`` stays an opaque dict: it is a typed input server-side but grows
    frequently, so keeping it a pass-through keeps GET→update round-trips faithful.
    Unknown keys (e.g. injected ``referenceId``) pass through via ``extra="allow"``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str | None = None
    name: str | None = None
    action_type: str | None = Field(default=None, alias="actionType")
    reference_id: str | None = Field(default=None, alias="referenceId")
    metadata: dict | None = None


class AiBehaviorParams(BaseModel):
    """The ``actionParams.aiBehaviorParams`` payload.

    Per-field camelCase aliases match the declared ``AiBehaviorParamsInput`` schema
    names; ``extra="allow"`` lets unknown keys pass through verbatim. No structural
    validation here beyond the nested models — the presence/shape rules live on
    :class:`BehaviorInput`.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    instruction: str | None = None
    actions_attributes: list[AiBehaviorActionAttributes] | None = Field(
        default=None, alias="actionsAttributes"
    )
    capabilities_attributes: list[AiBehaviorCapabilityAttributes] | None = Field(
        default=None, alias="capabilitiesAttributes"
    )
    data_source_ids: list[str] | None = Field(default=None, alias="dataSourceIds")
    referenced_field_ids: list[str] | None = Field(
        default=None, alias="referencedFieldIds"
    )
    provider_id: str | None = Field(default=None, alias="providerId")
    system_provider_id: str | None = Field(default=None, alias="systemProviderId")


class AiBehaviorActionParams(BaseModel):
    """The ``actionParams`` payload for an AI behavior.

    Only ``aiBehaviorParams`` is modeled. Sibling automation-action params
    (e.g. ``card_id``, ``to_phase_id``, ``field_map`` — genuinely snake_case wire
    names in ``AutomationActionParamsInput``) are never touched: ``extra="allow"``
    passes them through byte-for-byte. Aliasing is strictly per declared field, so
    no blanket snake→camel conversion can corrupt those siblings.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    ai_behavior_params: AiBehaviorParams | None = Field(
        default=None, alias="aiBehaviorParams"
    )


class BehaviorPayload(BaseModel):
    """Lenient, casing-agnostic view of a behavior for reads and normalization.

    ``populate_by_name`` accepts snake_case or camelCase for every field (via the
    same per-field aliases as :class:`BehaviorInput`); ``extra="allow"`` preserves
    tool-boundary sugar (``instruction_template``, ``template_params``) and any
    other keys. Unlike :class:`BehaviorInput` it runs no structural validation, so
    consumers can parse once and read typed attributes instead of walking the dict
    with dual-alias branches. Dumping with ``by_alias=True`` emits the declared
    wire names.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str | None = None
    event_id: str | None = Field(default=None, alias="eventId")
    action_id: str | None = Field(default=None, alias="actionId")
    active: bool | None = None
    condition: dict | None = None
    event_params: dict | None = Field(default=None, alias="eventParams")
    action_params: AiBehaviorActionParams | None = Field(
        default=None, alias="actionParams"
    )


class BehaviorInput(BaseModel):
    """One AI agent behavior; accepts snake_case or camelCase, dumps with camelCase aliases.

    The Pipefy API requires ``actionParams.aiBehaviorParams.actionsAttributes`` with at least
    one action; otherwise ``updateAiAgent`` fails (e.g. "The instructions must contain at least 1 action").

    Optional ``eventParams`` configures the trigger.

    Optional ``actionParams.aiBehaviorParams.capabilitiesAttributes`` is a list of capability
    entries the API accepts (e.g. ``advanced_ocr``, ``web_search``). No extra structural
    validation here — the API enforces capability shapes.

    For each action dict, known ``actionType`` values get ``metadata`` checks:
    ``update_card`` / ``create_card`` / ``create_connected_card`` need ``pipeId`` and non-empty
    ``fieldsAttributes`` (each entry needs ``fieldId`` and ``inputMode``); ``move_card`` needs
    ``destinationPhaseId``; ``create_table_record`` needs ``tableId`` and non-empty
    ``fieldsAttributes`` (same entry shape as card actions; ``pipeId`` not required);
    ``send_email_template`` needs ``emailTemplateId`` and optional ``allowTemplateModifications``
    (boolean). Other types are not validated here.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: NonBlankStr
    event_id: NonBlankStr = Field(alias="eventId")
    action_id: str = Field(default=ACTION_ID_AI_BEHAVIOR, alias="actionId")
    active: bool = True
    condition: dict | None = None
    event_params: dict | None = Field(default=None, alias="eventParams")
    action_params: AiBehaviorActionParams | None = Field(
        default=None, alias="actionParams"
    )

    @model_validator(mode="after")
    def ai_behavior_must_include_at_least_one_action(self) -> Self:
        """Reject behaviors that would fail updateAiAgent in production."""
        params = self.action_params
        if params is None:
            raise ValueError(
                "Each behavior must include actionParams with aiBehaviorParams.actionsAttributes "
                'containing at least one action (e.g. actionType "move_card" with metadata).'
            )
        abp = params.ai_behavior_params
        if abp is None:
            raise ValueError(
                "Each behavior must include actionParams.aiBehaviorParams with "
                "a non-empty actionsAttributes list."
            )
        actions = abp.actions_attributes
        if not actions:
            raise ValueError(
                "Each behavior must set actionParams.aiBehaviorParams.actionsAttributes with "
                'at least one action (Pipefy: "The instructions must contain at least 1 action").'
            )
        for action in actions:
            _validate_action_metadata(action)
        return self


class CreateAiAgentInput(BaseModel):
    """Validated input for create-and-configure flow: create mutation uses name and repo_uuid only."""

    name: NonBlankStr
    repo_uuid: NonBlankStr
    instruction: NonBlankStr
    behaviors: list[BehaviorInput] = Field(
        min_length=1,
        max_length=MAX_BEHAVIORS,
        description="List of behaviors (1 to MAX_BEHAVIORS)",
    )
    data_source_ids: list[str] = Field(default_factory=list)


class UpdateAiAgentInput(BaseModel):
    """Validated input for updating an AI Agent."""

    uuid: NonBlankStr
    name: NonBlankStr
    repo_uuid: NonBlankStr
    behaviors: list[BehaviorInput] = Field(
        min_length=1,
        max_length=MAX_BEHAVIORS,
        description="List of behaviors (1 to MAX_BEHAVIORS)",
    )
    instruction: str | None = None
    data_source_ids: list[str] = Field(default_factory=list)
