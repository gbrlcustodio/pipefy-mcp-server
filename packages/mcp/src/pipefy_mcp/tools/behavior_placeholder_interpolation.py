"""Re-export behavior placeholder helpers from ``pipefy-sdk`` (single source of truth)."""

from __future__ import annotations

from pipefy_sdk.behavior_placeholders import (
    expand_behavior_placeholders,
    expand_behaviors_placeholders,
    extract_referenced_field_ids,
    normalize_pipefy_ai_instruction_tokens,
    populate_referenced_field_ids,
)

__all__ = [
    "expand_behavior_placeholders",
    "expand_behaviors_placeholders",
    "extract_referenced_field_ids",
    "normalize_pipefy_ai_instruction_tokens",
    "populate_referenced_field_ids",
]
