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
