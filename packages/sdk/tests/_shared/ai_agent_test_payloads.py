"""Minimal valid AI agent behavior dicts for unit tests (matches Pipefy API constraints)."""

from __future__ import annotations

from uuid import uuid4

from _shared.fixture_ids import make_field_id, make_pipe_id


def minimal_behavior_dict(
    name: str = "Test Behavior",
    event_id: str = "card_created",
    *,
    pipe_id: str | None = None,
    field_id: str | None = None,
):
    """One behavior with actionParams.aiBehaviorParams.actionsAttributes (required by live API).

    Uses ``update_card`` with realistic metadata matching Pipefy's golden payload shape.
    The API rejects empty ``metadata: {}`` — it must include at least the required keys.

    Args:
        pipe_id: Pipe repo id in action metadata; defaults to a unique fictional id per call.
        field_id: Field internal id in fieldsAttributes; defaults to a unique fictional id per call.
    """
    resolved_pipe_id = pipe_id if pipe_id is not None else make_pipe_id()
    resolved_field_id = field_id if field_id is not None else make_field_id()
    return {
        "name": name,
        "event_id": event_id,
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Test behavior instruction.",
                "actionsAttributes": [
                    {
                        "name": "Update card fields",
                        "actionType": "update_card",
                        "metadata": {
                            "destinationPhaseId": "",
                            "pipeId": resolved_pipe_id,
                            "fieldsAttributes": [
                                {
                                    "fieldId": resolved_field_id,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                },
                            ],
                        },
                    },
                ],
            }
        },
    }


def behavior_with_action(
    action_type, metadata, *, name="Test Behavior", event_id="card_created"
):
    """Build a behavior dict with a single action of the given type and metadata."""
    return {
        "name": name,
        "event_id": event_id,
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Test instruction.",
                "actionsAttributes": [
                    {
                        "name": f"{action_type} action",
                        "actionType": action_type,
                        "metadata": metadata,
                    },
                ],
            }
        },
    }


def mock_api_behavior_response(
    *,
    pipe_id: str | None = None,
    field_id: str | None = None,
    reference_id: str | None = None,
):
    """Behavior dict as returned by GET_AI_AGENT_QUERY (aliased field names).

    Mirrors the exact GraphQL response shape including aliases
    (``eventId``, ``eventParams``, ``actionId``, ``actionParams``).
    """
    resolved_pipe_id = pipe_id if pipe_id is not None else make_pipe_id()
    resolved_field_id = field_id if field_id is not None else make_field_id()
    resolved_reference_id = reference_id if reference_id is not None else str(uuid4())
    return {
        "id": "123",
        "name": "When card created — update fields",
        "active": True,
        "eventId": "card_created",
        "eventParams": {
            "fromPhaseId": None,
            "inPhaseId": None,
            "to_phase_id": None,
            "triggerFieldIds": None,
            "triggerAutomationId": None,
        },
        "actionId": "ai_behavior",
        "condition": None,
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Analyze the card and fill summary.",
                "dataSourceIds": [],
                "referencedFieldIds": [],
                "providerId": None,
                "systemProviderId": None,
                "capabilitiesAttributes": [
                    {"capabilityType": "advanced_ocr", "enabled": True},
                ],
                "actionsAttributes": [
                    {
                        "id": "456",
                        "name": "Update card fields",
                        "actionType": "update_card",
                        "referenceId": resolved_reference_id,
                        "metadata": {
                            "destinationPhaseId": None,
                            "pipeId": resolved_pipe_id,
                            "tableId": None,
                            "emailTemplateId": None,
                            "allowTemplateModifications": None,
                            "fieldsAttributes": [
                                {
                                    "fieldId": resolved_field_id,
                                    "inputMode": "fill_with_ai",
                                    "value": "",
                                },
                            ],
                        },
                    }
                ],
            }
        },
    }


def mock_api_behavior_response_send_email_template():
    """One behavior node as returned by GET_AI_AGENT_QUERY for ``send_email_template``.

    Use for round-trip tests (get → update) so ``emailTemplateId`` / ``allowTemplateModifications``
    are present under ``metadata`` like the expanded query selection.
    """
    base = mock_api_behavior_response()
    base["name"] = "When card created — send email"
    attrs = base["actionParams"]["aiBehaviorParams"]["actionsAttributes"][0]
    attrs["name"] = "Send notification email"
    attrs["actionType"] = "send_email_template"
    attrs["referenceId"] = str(uuid4())
    attrs["metadata"] = {
        "destinationPhaseId": None,
        "pipeId": None,
        "tableId": None,
        "emailTemplateId": "tmpl-12345",
        "allowTemplateModifications": True,
        "fieldsAttributes": None,
    }
    return base


def mock_agent_with_behaviors():
    """Full ``aiAgent`` API response including behaviors — matches GET_AI_AGENT_QUERY shape."""
    return {
        "uuid": "agent-with-behaviors",
        "name": "Production Assistant",
        "instruction": "Help users with card triage.",
        "repoUuid": "repo-uuid-123",
        "dataSourceIds": ["ds-1"],
        "disabledAt": None,
        "needReview": False,
        "behaviors": [mock_api_behavior_response()],
    }
