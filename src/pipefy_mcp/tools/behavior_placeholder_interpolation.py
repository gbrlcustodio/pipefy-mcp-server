"""Optional ``{{name}}`` interpolation for AI behavior dicts; normalizes bare ``{field:…}`` / ``{action:uuid}`` to ``%{…}`` for Pipefy."""

from __future__ import annotations

import copy
import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
_PIPEFY_FIELD_REF = re.compile(r"(?<!\%)\{field:([^}]+)\}")
_PIPEFY_ACTION_UUID = re.compile(
    r"(?<!\%)\{action:([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})\}"
)
# Numeric-only aliases — callers often borrow the ``%{internal_id}`` syntax from
# ``create_ai_automation`` (where it renders correctly) without the ``field:``
# namespace that the AI Agent UI requires for chip rendering. Rewrite both the
# wrapped (``%{123}``) and bare (``{123}``) variants to ``%{field:123}``.
_PIPEFY_PREFIXED_NUMERIC_FIELD = re.compile(r"%\{(\d+)\}")
_PIPEFY_UNPREFIXED_NUMERIC_FIELD = re.compile(r"(?<!\%)\{(\d+)\}")

_TEMPLATE_PARAM_SOURCE_KEYS = (
    "template_params",
    "templateParams",
    "placeholders",
)
_INSTRUCTION_TEMPLATE_KEYS = frozenset(("instruction_template", "instructionTemplate"))


def _string_params(params: dict[Any, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in params.items() if v is not None}


def _merge_template_param_sources(working_copy: dict[str, Any]) -> dict[str, str]:
    """Extract template param maps; **mutates** ``working_copy`` in place (pops source keys)."""
    merged: dict[str, str] = {}
    for key in _TEMPLATE_PARAM_SOURCE_KEYS:
        raw = working_copy.pop(key, None)
        if isinstance(raw, dict):
            merged.update(_string_params(raw))
    return merged


def _substitute_in_string(text: str, params: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            msg = (
                f"Missing template parameter '{name}' for {{{{{name}}}}} "
                "(set template_params / placeholders on this behavior)."
            )
            raise ValueError(msg)
        return params[name]

    return _PLACEHOLDER_RE.sub(repl, text)


def _deep_interpolate(obj: Any, params: dict[str, str]) -> Any:
    if isinstance(obj, str):
        if "{{" in obj and not params:
            raise ValueError(
                "Behavior strings contain {{placeholders}} but no template_params "
                "(or placeholders) dict was provided on this behavior."
            )
        return _substitute_in_string(obj, params) if params else obj
    if isinstance(obj, list):
        return [_deep_interpolate(item, params) for item in obj]
    if isinstance(obj, dict):
        return {k: _deep_interpolate(v, params) for k, v in obj.items()}
    return obj


def normalize_pipefy_ai_instruction_tokens(text: str) -> str:
    """Normalize AI Agent instruction tokens to the canonical ``%{field:…}`` / ``%{action:…}`` syntax.

    The Pipefy AI Agent UI only renders chip tokens for the ``field:`` / ``action:``
    namespaces. Callers often pass the AI Automation-style ``%{<internal_id>}``
    (bare numeric) which the API stores verbatim but the UI displays as plain
    text. This function rewrites the common variants to the chip-friendly form:

      * ``{field:X}``          → ``%{field:X}``   (missing ``%`` prefix)
      * ``{action:<uuid>}``    → ``%{action:<uuid>}``
      * ``%{<digits>}``        → ``%{field:<digits>}`` (missing ``field:`` namespace)
      * ``{<digits>}``         → ``%{field:<digits>}`` (missing both prefix and namespace)

    Already-canonical tokens (``%{field:X}``, ``%{action:<uuid>}``) are left
    untouched. Non-numeric bare tokens without a namespace (e.g. ``{foo}``) are
    also left alone — they may be template placeholders for
    :func:`expand_behavior_placeholders`.

    Args:
        text: ``aiBehaviorParams.instruction`` value (or fragment).
    """
    if not text:
        return text
    out = _PIPEFY_FIELD_REF.sub(r"%{field:\1}", text)
    out = _PIPEFY_ACTION_UUID.sub(r"%{action:\1}", out)
    out = _PIPEFY_PREFIXED_NUMERIC_FIELD.sub(r"%{field:\1}", out)
    return _PIPEFY_UNPREFIXED_NUMERIC_FIELD.sub(r"%{field:\1}", out)


def _normalize_instruction_in_behavior(behavior: dict[str, Any]) -> None:
    ap = behavior.get("actionParams") or behavior.get("action_params")
    if not isinstance(ap, dict):
        return
    abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params")
    if not isinstance(abp, dict):
        return
    instr = abp.get("instruction")
    if isinstance(instr, str) and instr:
        abp["instruction"] = normalize_pipefy_ai_instruction_tokens(instr)


def _ensure_ai_behavior_instruction(behavior: dict[str, Any], instruction: str) -> None:
    ap = behavior.get("actionParams") or behavior.get("action_params")
    if not isinstance(ap, dict):
        ap = {}
        behavior["actionParams"] = ap
    abp = ap.get("aiBehaviorParams") or ap.get("ai_behavior_params")
    if not isinstance(abp, dict):
        abp = {}
        ap["aiBehaviorParams"] = abp
    abp["instruction"] = instruction


def expand_behavior_placeholders(behavior: dict[str, Any]) -> dict[str, Any]:
    """Copy one behavior, merge ``instruction_template`` into ``actionParams``, strip template keys, interpolate ``{{name}}`` in all string leaves.

    Args:
        behavior: Raw MCP tool behavior dict. Optional keys (removed before validation):
            ``template_params`` / ``templateParams`` / ``placeholders`` — flat ``str -> str``
            map for replacements; ``instruction_template`` / ``instructionTemplate`` —
            text written to ``actionParams.aiBehaviorParams.instruction`` before interpolation.

    Returns:
        New dict with the same shape expected by ``BehaviorInput``, without template-only keys.
    """
    # ``deepcopy`` first so the input ``behavior`` is never aliased; later steps
    # intentionally mutate this tree in place (pops, nested instruction updates).
    result: dict[str, Any] = copy.deepcopy(behavior)
    params = _merge_template_param_sources(result)

    instruction_tmpl = None
    for k in _INSTRUCTION_TEMPLATE_KEYS:
        if k in result:
            instruction_tmpl = result.pop(k)
            break
    if instruction_tmpl is not None:
        _ensure_ai_behavior_instruction(result, str(instruction_tmpl))

    if not params:
        if isinstance(result, dict):
            _walk_check_orphan_placeholders(result)
        _normalize_instruction_in_behavior(result)
        return result

    out = _deep_interpolate(result, params)
    _normalize_instruction_in_behavior(out)
    return out


def _walk_check_orphan_placeholders(obj: Any) -> None:
    if isinstance(obj, str) and "{{" in obj and _PLACEHOLDER_RE.search(obj):
        raise ValueError(
            "Behavior contains {{placeholders}} but no template_params "
            "(or placeholders) dict was provided on this behavior."
        )
    if isinstance(obj, list):
        for item in obj:
            _walk_check_orphan_placeholders(item)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_check_orphan_placeholders(v)


def expand_behaviors_placeholders(
    behaviors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply :func:`expand_behavior_placeholders` to each behavior dict.

    Args:
        behaviors: List of raw behavior dicts from tool arguments.

    Returns:
        Expanded list safe for Pydantic ``BehaviorInput`` validation.
    """
    return [expand_behavior_placeholders(b) for b in behaviors]


__all__ = [
    "expand_behavior_placeholders",
    "expand_behaviors_placeholders",
    "normalize_pipefy_ai_instruction_tokens",
]
