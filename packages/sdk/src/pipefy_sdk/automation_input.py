"""Key normalization for traditional automation mutation inputs.

``CreateAutomationInput`` and ``UpdateAutomationInput`` mix naming styles:
most fields are snake_case (``action_params``, ``event_id``) but a few are
camelCase (``schedulerCron``, ``responseSchema``, ``searchFor``,
``clientMutationId``). Callers routinely guess the wrong spelling, so the
client accepts either and rewrites top-level keys to the API's field names
before sending. Nested payloads are passed through verbatim: their key casing
is part of each param's own contract (``action_params.taskParams`` is
legitimately camelCase inside a snake_case field).
"""

from __future__ import annotations

from typing import Any

_API_NAME_BY_ALIAS = {
    "actionId": "action_id",
    "actionParams": "action_params",
    "actionRepoId": "action_repo_id",
    "eventId": "event_id",
    "eventParams": "event_params",
    "eventRepoId": "event_repo_id",
    "schedulerFrequency": "scheduler_frequency",
    "client_mutation_id": "clientMutationId",
    "response_schema": "responseSchema",
    "scheduler_cron": "schedulerCron",
    "search_for": "searchFor",
}


def normalize_automation_input_keys(
    extra_input: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Rewrite top-level automation input keys to the API's field names.

    Keys already using the API spelling and unknown keys pass through
    unchanged. When both spellings of a field are present, the API-name key
    wins and the alias is dropped. Returns a new dict; ``None`` stays ``None``.
    """
    if extra_input is None:
        return None
    normalized: dict[str, Any] = {}
    for key, value in extra_input.items():
        api_name = _API_NAME_BY_ALIAS.get(key, key)
        if api_name != key and api_name in extra_input:
            continue
        normalized[api_name] = value
    return normalized


__all__ = ["normalize_automation_input_keys"]
