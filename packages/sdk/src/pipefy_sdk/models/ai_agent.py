"""Pydantic models for AI Agent input validation."""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from pipefy_sdk.models.ai_automation import (
    AutomationEventParamsInput,
    FieldMapInput,
)
from pipefy_sdk.models.validators import NonBlankStr

ACTION_ID_AI_BEHAVIOR = "ai_behavior"
MAX_BEHAVIORS = 5

# actionTypes that require pipeId + fieldsAttributes in metadata
_CARD_FIELD_ACTION_TYPES = frozenset(
    {"update_card", "create_card", "create_connected_card"}
)


def _validate_fields_attributes_entries(
    action_type: str, fields: list[FieldMapInput] | None
) -> None:
    """Require non-empty ``fieldsAttributes`` with ``fieldId`` and ``inputMode`` per entry."""
    if not fields:
        raise ValueError(
            f"actionType '{action_type}' requires metadata.fieldsAttributes "
            f"as a non-empty list of field entries."
        )
    for i, entry in enumerate(fields):
        if not entry.field_id:
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] requires 'fieldId'."
            )
        if not entry.input_mode:
            raise ValueError(
                f"actionType '{action_type}': fieldsAttributes[{i}] "
                f"requires 'inputMode'."
            )


def _validate_card_field_metadata(
    action_type: str, metadata: AiBehaviorMetadataInput
) -> None:
    """Validate metadata for actions that operate on card fields.

    Args:
        action_type: The actionType string (used in error messages).
        metadata: The typed metadata from the action.

    Raises:
        ValueError: When required keys are missing or malformed.
    """
    if not metadata.pipe_id:
        raise ValueError(
            f"actionType '{action_type}' requires metadata.pipeId "
            f"(the pipe where the action executes)."
        )
    _validate_fields_attributes_entries(action_type, metadata.fields_attributes)


def _validate_create_table_record_metadata(metadata: AiBehaviorMetadataInput) -> None:
    """Validate metadata for create_table_record (table row, not pipe fields)."""
    if not metadata.table_id:
        raise ValueError(
            "actionType 'create_table_record' requires metadata.tableId "
            "(target database table ID)."
        )
    _validate_fields_attributes_entries(
        "create_table_record", metadata.fields_attributes
    )


def _validate_send_email_template_metadata(metadata: AiBehaviorMetadataInput) -> None:
    """Validate metadata for send_email_template actions."""
    template_id = metadata.email_template_id
    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError(
            "actionType 'send_email_template' requires metadata.emailTemplateId "
            "(non-empty email template ID)."
        )
    mod = metadata.allow_template_modifications
    if mod is not None and not isinstance(mod, bool):
        raise ValueError(
            "actionType 'send_email_template': metadata.allowTemplateModifications "
            "must be a boolean when set."
        )


def _validate_move_card_metadata(metadata: AiBehaviorMetadataInput) -> None:
    """Validate metadata for move_card actions.

    Raises:
        ValueError: When destinationPhaseId is missing or blank.
    """
    dest = metadata.destination_phase_id
    if not isinstance(dest, str) or not dest.strip():
        raise ValueError(
            "actionType 'move_card' requires metadata.destinationPhaseId "
            "(the target phase ID)."
        )


_CAPABILITY_CANONICAL_SHAPE = '{"capabilityType": "<type>", "enabled": true|false}'


def _validate_capability_entries(
    capabilities: list[AiBehaviorCapabilityAttributes] | None,
) -> None:
    """Enforce the canonical capability wire shape on each entry.

    Every entry must carry a non-empty ``capabilityType`` string, a boolean
    ``enabled``, and no other keys (the GraphQL input type is closed — an unknown
    key fails the whole mutation with an opaque coercion error, so it is rejected
    here with a clear one). Legacy shapes (bare string lists, ``{"type": ...}``)
    are rejected: a string list fails Pydantic list coercion before this runs, and
    ``{"type": ...}`` lands here with ``capability_type`` unset. Enum membership is
    intentionally *not* checked — any ``capabilityType`` value passes through,
    because the capability set grows over time and the API validates the enum
    server-side on write.
    """
    if not capabilities:
        return
    for i, cap in enumerate(capabilities):
        ctype = cap.capability_type
        if not ctype or not ctype.strip():
            raise ValueError(
                f"capabilitiesAttributes[{i}] requires a non-empty 'capabilityType'. "
                f"Use the canonical shape {_CAPABILITY_CANONICAL_SHAPE}; legacy shapes "
                f'(string lists, {{"type": ...}}) are not accepted.'
            )
        if cap.enabled is None:
            raise ValueError(
                f"capabilitiesAttributes[{i}] (capabilityType '{ctype}') requires a "
                f"boolean 'enabled'. Use the canonical shape "
                f"{_CAPABILITY_CANONICAL_SHAPE}."
            )
        if cap.model_extra:
            unknown = ", ".join(sorted(cap.model_extra))
            raise ValueError(
                f"capabilitiesAttributes[{i}] (capabilityType '{ctype}') has unknown "
                f"key(s): {unknown}. The API accepts exactly 'capabilityType' and "
                f"'enabled'; unknown keys make the whole mutation fail."
            )


def _reject_non_mapping_capability_entries(value: object) -> object:
    """Give bare-string / non-object capability entries the canonical-shape error.

    A legacy string list fails ``AiBehaviorCapabilityAttributes`` coercion with an
    opaque ``model_type`` error before :func:`_validate_capability_entries` can run,
    so the caller never sees the canonical-shape guidance. Catch non-object entries
    here to surface the same actionable message as the other legacy shapes; object
    entries (including the legacy ``{"type": ...}`` shape) pass through untouched to
    normal coercion and the after-validator.
    """
    if not isinstance(value, list):
        return value
    for i, entry in enumerate(value):
        if not isinstance(entry, (dict, AiBehaviorCapabilityAttributes)):
            raise ValueError(
                f"capabilitiesAttributes[{i}] must be an object, not "
                f"{type(entry).__name__}. Use the canonical shape "
                f"{_CAPABILITY_CANONICAL_SHAPE}; legacy shapes (string lists, "
                f'{{"type": ...}}) are not accepted.'
            )
    return value


def _validate_action_metadata(action: AiBehaviorActionAttributes) -> None:
    """Validate metadata for a single action based on its actionType.

    Unknown actionTypes are passed through without validation.
    """
    action_type = action.action_type or ""
    metadata = action.metadata or AiBehaviorMetadataInput()

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

    A lenient typed shell: it parses any dict (``extra="allow"`` keeps unknown keys),
    so read/normalization paths (:class:`BehaviorPayload`) accept whatever the API
    stores — reads always return ``{capabilityType, enabled}``, both non-null. The
    canonical-shape rules (``capabilityType`` + boolean ``enabled`` required, no
    unknown keys) are enforced at the input boundary by :class:`BehaviorInput`, not
    here; enum membership is not checked client-side (the API validates it on write).
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    capability_type: str | None = Field(default=None, alias="capabilityType")
    enabled: bool | None = None


class AiBehaviorMetadataInput(BaseModel):
    """Behavior action ``metadata`` (``AiBehaviorMetadataInput``).

    Types the fields the per-actionType validators read; ``extra="allow"`` carries
    the growing tail (``mcpServerId``, ``toolName``, ``toolInputs``, ``emails``,
    ``title``, …) verbatim so GET→update round-trips stay byte-identical. All declared
    names are camelCase. ``allowTemplateModifications`` is typed ``Any`` on purpose:
    Pydantic's lax bool coercion would silently turn ``"yes"`` into ``True``, so the
    boolean contract is enforced by :func:`_validate_send_email_template_metadata`
    with an actionable message instead.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    pipe_id: str | None = Field(default=None, alias="pipeId")
    table_id: str | None = Field(default=None, alias="tableId")
    destination_phase_id: str | None = Field(default=None, alias="destinationPhaseId")
    email_template_id: str | None = Field(default=None, alias="emailTemplateId")
    allow_template_modifications: Any = Field(
        default=None, alias="allowTemplateModifications"
    )
    fields_attributes: list[FieldMapInput] | None = Field(
        default=None, alias="fieldsAttributes"
    )


class AiBehaviorActionAttributes(BaseModel):
    """One entry in ``aiBehaviorParams.actionsAttributes``.

    ``metadata`` is a typed :class:`AiBehaviorMetadataInput` shell: the validators read
    typed fields, while ``extra="allow"`` on that model keeps the growing tail (and
    injected keys like ``referenceId``) so GET→update round-trips serialize identically.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str | None = None
    name: str | None = None
    action_type: str | None = Field(default=None, alias="actionType")
    reference_id: str | None = Field(default=None, alias="referenceId")
    metadata: AiBehaviorMetadataInput | None = None


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
    capabilities_attributes: Annotated[
        list[AiBehaviorCapabilityAttributes] | None,
        BeforeValidator(_reject_non_mapping_capability_entries),
    ] = Field(default=None, alias="capabilitiesAttributes")
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
    event_params: AutomationEventParamsInput | None = Field(
        default=None, alias="eventParams"
    )
    action_params: AiBehaviorActionParams | None = Field(
        default=None, alias="actionParams"
    )


class BehaviorInput(BaseModel):
    """One AI agent behavior; accepts snake_case or camelCase, dumps with camelCase aliases.

    The Pipefy API requires ``actionParams.aiBehaviorParams.actionsAttributes`` with at least
    one action; otherwise ``updateAiAgent`` fails (e.g. "The instructions must contain at least 1 action").

    Optional ``eventParams`` configures the trigger.

    Optional ``actionParams.aiBehaviorParams.capabilitiesAttributes`` is a list of capability
    entries in the canonical shape ``{"capabilityType": "<type>", "enabled": true|false}``.
    Both keys are required per entry; legacy shapes (bare string lists, ``{"type": ...}``)
    are rejected. ``capabilityType`` values are not checked against a known-enum set
    (any value passes through; the API validates the enum on write).

    Optional ``providerId`` / ``systemProviderId`` select the behavior's LLM provider; at
    most one may be set (reads resolve a single active provider, so co-presence is
    unverifiable).

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
    event_params: AutomationEventParamsInput | None = Field(
        default=None, alias="eventParams"
    )
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
        _validate_capability_entries(abp.capabilities_attributes)
        for wire_name, value in (
            ("providerId", abp.provider_id),
            ("systemProviderId", abp.system_provider_id),
        ):
            # Blank strings would dodge the co-presence check below (falsy) yet
            # still be serialized to the API (exclude_none keeps them).
            if value is not None and not value.strip():
                raise ValueError(
                    f"aiBehaviorParams.{wire_name} must be a non-empty string when "
                    f"set; omit the field to leave the provider unset."
                )
        if abp.provider_id and abp.system_provider_id:
            raise ValueError(
                "A behavior may set at most one of providerId / systemProviderId. "
                "Reads resolve a single active provider per behavior, so co-presence "
                "is unverifiable — send only the one that applies."
            )
        return self


class CreateAiAgentInput(BaseModel):
    """Validated input for create-and-configure: name/repo_uuid plus optional disabled_at for inactive create."""

    name: NonBlankStr
    repo_uuid: NonBlankStr
    instruction: NonBlankStr
    behaviors: list[BehaviorInput] = Field(
        min_length=1,
        max_length=MAX_BEHAVIORS,
        description="List of behaviors (1 to MAX_BEHAVIORS)",
    )
    data_source_ids: list[str] = Field(default_factory=list)
    disabled_at: str | None = None


class UpdateAiAgentInput(BaseModel):
    """Validated input for updating an AI Agent.

    Prefer passing ``disabled_at`` from a prior ``get_ai_agent`` read (pass-through;
    skips the preserve re-read). When ``preserve_disabled_at`` is True (default) and
    ``disabled_at`` is None, the adapter fetches the current agent and re-sends
    ``disabledAt`` if set (routine update must not clear a disabled agent). When
    False and ``disabled_at`` is None, ``disabledAt`` is omitted from the payload so
    the API can clear a default disabled shell (create-active configure chain).
    """

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
    disabled_at: str | None = None
    preserve_disabled_at: bool = True
