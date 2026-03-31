"""Minimal valid AI agent behavior dicts for unit tests (matches Pipefy API constraints)."""


def minimal_behavior_dict(name="Test Behavior", event_id="card_created"):
    """One behavior with actionParams.aiBehaviorParams.actionsAttributes (required by live API)."""
    return {
        "name": name,
        "event_id": event_id,
        "actionParams": {
            "aiBehaviorParams": {
                "instruction": "Test behavior instruction.",
                "actionsAttributes": [
                    {
                        "name": "Move card",
                        "actionType": "move_card",
                        "metadata": {},
                    },
                ],
            }
        },
    }
