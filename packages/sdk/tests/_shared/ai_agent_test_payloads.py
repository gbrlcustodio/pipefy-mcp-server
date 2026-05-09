"""Minimal valid AI agent behavior dicts for unit tests (matches Pipefy API constraints)."""


def minimal_behavior_dict(name="Test Behavior", event_id="card_created"):
    """One behavior with actionParams.aiBehaviorParams.actionsAttributes (required by live API).

    Uses ``update_card`` with realistic metadata matching Pipefy's golden payload shape.
    The API rejects empty ``metadata: {}`` — it must include at least the required keys.
    """
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
                            "pipeId": "306996636",
                            "fieldsAttributes": [
                                {
                                    "fieldId": "425829426",
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


def mock_api_behavior_response():
    """Behavior dict as returned by GET_AI_AGENT_QUERY (aliased field names).

    Mirrors the exact GraphQL response shape including aliases
    (``eventId``, ``eventParams``, ``actionId``, ``actionParams``).
    """
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
                "actionsAttributes": [
                    {
                        "id": "456",
                        "name": "Update card fields",
                        "actionType": "update_card",
                        "referenceId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "metadata": {
                            "destinationPhaseId": None,
                            "pipeId": "306996636",
                            "tableId": None,
                            "emailTemplateId": None,
                            "allowTemplateModifications": None,
                            "fieldsAttributes": [
                                {
                                    "fieldId": "425829426",
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
    attrs["referenceId"] = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
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
