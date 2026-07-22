"""Pipe context checks for AI agent behaviors (shared by MCP tools and CLI pre-flight)."""

from __future__ import annotations

import asyncio
import copy
import logging
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from pipefy_sdk.behavior_placeholders import populate_referenced_field_ids
from pipefy_sdk.models import AiBehaviorParams, BehaviorPayload

if TYPE_CHECKING:
    from pipefy_sdk.client import PipefyClient

logger = logging.getLogger(__name__)

PHASE_FIELD_FETCH_CONCURRENCY = 8


def _behavior_payload(behavior: Any) -> BehaviorPayload | None:
    """Parse a raw behavior dict into the typed, casing-agnostic :class:`BehaviorPayload`.

    Returns ``None`` for entries that are not dicts or fail to parse, so callers can
    skip malformed behaviors instead of walking the dict with dual-alias branches.
    """
    if not isinstance(behavior, dict):
        return None
    try:
        return BehaviorPayload.model_validate(behavior)
    except ValidationError:
        return None


def _ai_behavior_params(behavior: Any) -> AiBehaviorParams | None:
    """Return the typed ``aiBehaviorParams`` of a raw behavior dict, or ``None``."""
    payload = _behavior_payload(behavior)
    if payload is None or payload.action_params is None:
        return None
    return payload.action_params.ai_behavior_params


KNOWN_AI_ACTION_TYPES = frozenset(
    {
        "create_card",
        "create_connected_card",
        "create_table_record",
        "move_card",
        "send_email_template",
        "update_card",
    }
)


def validate_behaviors_against_pipe(
    behaviors: list[dict[str, Any]],
    *,
    pipe_id: str = "",
    pipe_field_ids: set[str],
    pipe_phase_ids: set[str],
    related_pipe_ids: set[str] | None,
    cross_pipe_field_ids: dict[str, set[str]] | None = None,
    unknown_action_types: Literal["error", "warning", "ignore"] = "error",
) -> tuple[list[str], list[str]]:
    """Check behaviors against resolved pipe context and return problems and warnings.

    Pure function — no API calls. The caller is responsible for fetching
    pipe fields, phases, and relations beforehand.

    Args:
        behaviors: Raw behavior dicts (pre-validation format).
        pipe_id: Source pipe ID (used to decide whether fieldId checks apply).
        pipe_field_ids: Set of valid field identifiers for the source pipe (slug
            ``id`` and numeric ``internal_id``).
        pipe_phase_ids: Set of valid phase IDs (as strings) for the source pipe.
        related_pipe_ids: Pipe IDs related to the source pipe for
            ``create_connected_card`` validation; ``None`` skips that check
            (avoids false positives when relations were not loaded). A set
            (possibly empty) runs the relation check as before.
        cross_pipe_field_ids: Optional mapping of ``{pipe_id: field_ids}`` for
            target pipes referenced by cross-pipe actions. When provided,
            fieldIds targeting those pipes are validated against the map.
            When ``None`` (default), cross-pipe fieldIds are skipped.
        unknown_action_types: How to treat non-empty ``actionType`` values not in
            ``KNOWN_AI_ACTION_TYPES``: ``error`` adds to problems, ``warning``
            adds the same message to warnings, ``ignore`` skips.

    Returns:
        Tuple ``(problems, warnings)`` of human-readable strings. Empty lists
        mean no issues at that severity.
    """
    problems: list[str] = []
    warnings: list[str] = []

    for i, b in enumerate(behaviors):
        payload = _behavior_payload(b)
        name = (payload.name if payload else None) or f"<behavior {i}>"
        prefix = f'Behavior [{i}] "{name}"'

        abp = _ai_behavior_params(b)
        attrs = (abp.actions_attributes if abp else None) or []

        ep = payload.event_params if payload else None
        to_phase = ep.to_phase_id if ep else None
        if to_phase and str(to_phase) not in pipe_phase_ids:
            problems.append(
                f'{prefix}: eventParams.to_phase_id "{to_phase}" '
                f"not found in pipe phases."
            )

        for j, action in enumerate(attrs):
            action_type = action.action_type or ""
            metadata = action.metadata if isinstance(action.metadata, dict) else {}

            if action_type and action_type not in KNOWN_AI_ACTION_TYPES:
                msg = (
                    f"{prefix}, action [{j}]: unknown actionType "
                    f'"{action_type}". Known types: {sorted(KNOWN_AI_ACTION_TYPES)}.'
                )
                if unknown_action_types == "error":
                    problems.append(msg)
                elif unknown_action_types == "warning":
                    warnings.append(msg)

            if action_type == "move_card":
                dest = metadata.get("destinationPhaseId", "")
                if dest and str(dest) not in pipe_phase_ids:
                    problems.append(
                        f"{prefix}, action [{j}] (move_card): "
                        f'destinationPhaseId "{dest}" not found in pipe phases.'
                    )

            if action_type not in ("create_table_record", "send_email_template"):
                action_pipe = str(metadata.get("pipeId", ""))
                targets_source = not action_pipe or action_pipe == pipe_id
                if targets_source:
                    check_fields = pipe_field_ids
                elif (
                    cross_pipe_field_ids is not None
                    and action_pipe in cross_pipe_field_ids
                ):
                    check_fields = cross_pipe_field_ids[action_pipe]
                else:
                    check_fields = None

                if check_fields is not None:
                    fields_attrs = metadata.get("fieldsAttributes") or []
                    for k, fa in enumerate(fields_attrs):
                        if not isinstance(fa, dict):
                            continue
                        fid = fa.get("fieldId", "")
                        if fid and fid not in check_fields:
                            pipe_label = (
                                "pipe fields"
                                if targets_source
                                else f"target pipe {action_pipe} fields"
                            )
                            problems.append(
                                f"{prefix}, action [{j}] ({action_type}): "
                                f'fieldsAttributes[{k}].fieldId "{fid}" '
                                f"not found in {pipe_label}."
                            )

            if action_type == "create_table_record":
                warnings.append(
                    f"{prefix}, action [{j}] (create_table_record): "
                    "fieldsAttributes reference table field IDs, which cannot be validated "
                    "against this pipe. Verify IDs with get_table or get_table_record."
                )

            if action_type == "create_connected_card" and related_pipe_ids is not None:
                target_pipe = metadata.get("pipeId", "")
                if target_pipe and str(target_pipe) not in related_pipe_ids:
                    problems.append(
                        f"{prefix}, action [{j}] (create_connected_card): "
                        f'pipeId "{target_pipe}" has no relation with the '
                        f"source pipe. Create a pipe relation first "
                        f"(get_pipe_relations / create_pipe_relation)."
                    )

    return problems, warnings


def _extract_slug_field_ids_by_pipe(
    behaviors: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Scan behaviors and collect non-numeric fieldIds grouped by their target pipeId.

    Args:
        behaviors: Raw behavior dicts (supports both camelCase and snake_case keys).

    Returns:
        Dict mapping pipeId → set of slug fieldIds found in that pipe's actions.
        Empty dict when no slugs are present.
    """
    slugs_by_pipe: dict[str, set[str]] = {}
    for b in behaviors:
        abp = _ai_behavior_params(b)
        if abp is None:
            continue
        for a in abp.actions_attributes or []:
            metadata = a.metadata if isinstance(a.metadata, dict) else {}
            pipe_id = str(metadata.get("pipeId", ""))
            if not pipe_id:
                continue
            for fa in metadata.get("fieldsAttributes") or []:
                if not isinstance(fa, dict):
                    continue
                fid = str(fa.get("fieldId", ""))
                if fid and not fid.isdigit():
                    slugs_by_pipe.setdefault(pipe_id, set()).add(fid)
    return slugs_by_pipe


_INSTRUCTION_FIELD_TOKEN_RE = re.compile(r"%\{field:([^}]+)\}")


def _instruction_has_non_numeric_field_tokens(instruction: str) -> bool:
    for m in _INSTRUCTION_FIELD_TOKEN_RE.finditer(instruction):
        if m.group(1) and not m.group(1).strip().isdigit():
            return True
    return False


def pipe_ids_from_behavior(behavior: dict[str, Any]) -> set[str]:
    """Extract target pipe IDs from a single behavior's action metadata.

    Args:
        behavior: Raw behavior dict (supports both camelCase and snake_case keys).

    Returns:
        Set of pipe ID strings found in ``metadata.pipeId`` across all actions.
    """
    pids: set[str] = set()
    abp = _ai_behavior_params(behavior)
    if abp is None:
        return pids
    for a in abp.actions_attributes or []:
        metadata = a.metadata if isinstance(a.metadata, dict) else {}
        pid = str(metadata.get("pipeId", ""))
        if pid:
            pids.add(pid)
    return pids


def collect_pipe_ids_from_behaviors(behaviors: list[dict[str, Any]]) -> list[str]:
    """Collect all unique pipe IDs referenced in behavior metadata.

    Args:
        behaviors: List of raw behavior dicts.

    Returns:
        Deduplicated list of pipe ID strings.
    """
    ids: set[str] = set()
    for b in behaviors:
        if isinstance(b, dict):
            ids.update(pipe_ids_from_behavior(b))
    return list(ids)


def _rewrite_instruction_field_tokens(
    instruction: str, slug_to_numeric: dict[str, str]
) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        if key.isdigit():
            return m.group(0)
        if key in slug_to_numeric:
            return f"%{{field:{slug_to_numeric[key]}}}"
        return m.group(0)

    return _INSTRUCTION_FIELD_TOKEN_RE.sub(repl, instruction)


def add_slug_from_field(slug_map: dict[str, str], field: Any) -> None:
    """Map a non-numeric field slug to its numeric ``internal_id`` when both exist."""
    if not isinstance(field, dict):
        return
    slug = str(field.get("id", ""))
    internal = str(field.get("internal_id", ""))
    if slug and internal and not slug.isdigit():
        slug_map[slug] = internal


async def _fetch_phase_slug_map(
    client: PipefyClient,
    phase_id: str,
    *,
    semaphore: asyncio.Semaphore,
) -> dict[str, str]:
    async with semaphore:
        try:
            phase_data = await client.get_phase_fields(phase_id)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to fetch fields for phase %s", phase_id, exc_info=True)
            return {}
    partial: dict[str, str] = {}
    for field in phase_data.get("fields") or []:
        add_slug_from_field(partial, field)
    return partial


async def build_field_slug_map(
    client: PipefyClient,
    pipe_id: str | int,
) -> dict[str, str]:
    """Build a slug → numeric internal_id map for all fields in a pipe.

    Uses start-form fields and embedded ``phases[].fields`` from ``get_pipe`` when
    present; otherwise calls ``get_phase_fields`` per phase (in parallel).

    Args:
        client: PipefyClient instance.
        pipe_id: Numeric pipe ID.

    Returns:
        Dict mapping field slug to its numeric ``internal_id`` string.
        Only includes entries where the slug is non-numeric.
    """
    slug_map: dict[str, str] = {}

    pipe_data = await client.get_pipe(pipe_id)
    pipe_info = pipe_data.get("pipe") or {}

    for field in pipe_info.get("start_form_fields") or []:
        add_slug_from_field(slug_map, field)

    phases_to_fetch: list[str] = []
    for phase in pipe_info.get("phases") or []:
        embedded_fields = phase.get("fields")
        if embedded_fields:
            for field in embedded_fields:
                add_slug_from_field(slug_map, field)
        phase_id = phase.get("id")
        if phase_id and not embedded_fields:
            phases_to_fetch.append(str(phase_id))

    if phases_to_fetch:
        semaphore = asyncio.Semaphore(PHASE_FIELD_FETCH_CONCURRENCY)
        partial_maps = await asyncio.gather(
            *(
                _fetch_phase_slug_map(client, phase_id, semaphore=semaphore)
                for phase_id in phases_to_fetch
            )
        )
        for partial in partial_maps:
            slug_map.update(partial)

    return slug_map


async def resolve_field_slugs_to_numeric(
    client: PipefyClient,
    behaviors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve slug ``fieldId`` values and ``%{field:<slug>}`` tokens to numeric internal ids.

    Args:
        client: PipefyClient for fetching pipe field data.
        behaviors: Behavior dicts (same shape as ``create_ai_agent`` / ``update_ai_agent``).

    Returns:
        New list when any pipe fetch ran; otherwise the original list. Unresolved slugs unchanged.
    """
    slugs_by_pipe = _extract_slug_field_ids_by_pipe(behaviors)
    pipes_needed: set[str] = set(slugs_by_pipe.keys())

    for b in behaviors:
        abp = _ai_behavior_params(b)
        if abp is None:
            continue
        instr = abp.instruction
        if isinstance(instr, str) and _instruction_has_non_numeric_field_tokens(instr):
            pipes_needed.update(pipe_ids_from_behavior(b))

    if not pipes_needed:
        return behaviors

    slug_to_numeric: dict[str, str] = {}
    for pipe_id_str in pipes_needed:
        try:
            field_map = await build_field_slug_map(client, pipe_id_str)
            slug_to_numeric.update(field_map)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to fetch field map for pipe %s; slugs left as-is",
                pipe_id_str,
                exc_info=True,
            )

    if not slug_to_numeric:
        return behaviors

    resolved: list[dict[str, Any]] = []
    for b in behaviors:
        # Deep-copy before parsing: pydantic keeps a reference to the input
        # ``metadata`` dict, so mutating it in place would corrupt the caller's
        # behavior. Parsing a copy keeps the original untouched.
        b_copy = copy.deepcopy(b)
        payload = _behavior_payload(b_copy)
        abp = (
            payload.action_params.ai_behavior_params
            if payload and payload.action_params
            else None
        )
        if abp is None:
            resolved.append(b_copy)
            continue
        for a in abp.actions_attributes or []:
            metadata = a.metadata if isinstance(a.metadata, dict) else None
            if metadata is None:
                continue
            for fa in metadata.get("fieldsAttributes") or []:
                if not isinstance(fa, dict):
                    continue
                fid = str(fa.get("fieldId", ""))
                if fid in slug_to_numeric:
                    fa["fieldId"] = slug_to_numeric[fid]
        if isinstance(abp.instruction, str):
            abp.instruction = _rewrite_instruction_field_tokens(
                abp.instruction, slug_to_numeric
            )
        resolved.append(payload.model_dump(by_alias=True, exclude_none=True))

    return resolved


async def resolve_and_populate_field_refs(
    client: PipefyClient,
    behaviors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve slug fieldIds to numeric and populate ``referencedFieldIds``.

    Args:
        client: PipefyClient for fetching field-slug maps.
        behaviors: Behavior dicts (same shape as ``create_ai_agent``).

    Returns:
        Resolved-and-populated behavior dicts.
    """
    resolved = await resolve_field_slugs_to_numeric(client, behaviors)
    for b in resolved:
        populate_referenced_field_ids(b)
    return resolved


def add_field_identifiers(field_ids: set[str], field: Any) -> None:
    """Add slug ``id`` and numeric ``internal_id`` when present on a field dict."""
    if not isinstance(field, dict):
        return
    for key in ("id", "internal_id"):
        fid = field.get(key)
        if fid:
            field_ids.add(str(fid))


async def _fetch_phase_field_ids(
    client: PipefyClient,
    phase_id: str,
    *,
    timeout: float,
    semaphore: asyncio.Semaphore,
) -> tuple[set[str], str | None]:
    async with semaphore:
        try:
            phase_data = await asyncio.wait_for(
                client.get_phase_fields(phase_id),
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to fetch fields for phase %s during validation context",
                phase_id,
                exc_info=True,
            )
            return set(), phase_id
    field_ids: set[str] = set()
    for field in phase_data.get("fields") or []:
        add_field_identifiers(field_ids, field)
    return field_ids, None


async def collect_field_ids_for_pipe(
    client: PipefyClient,
    pipe_info: dict[str, Any],
    *,
    timeout: float,
) -> tuple[set[str], list[str]]:
    """Collect slug and internal_id values for start-form and phase fields.

    Matches the field universe used by ``build_field_slug_map`` (start form plus
    ``get_phase_fields`` per phase when ``phases[].fields`` is absent). Embedded
    ``phases[].fields`` from ``GET_PIPE_QUERY`` are used without extra round-trips.

    Returns:
        Tuple of ``(field_ids, failed_phase_ids)``. ``failed_phase_ids`` lists
        phases whose ``get_phase_fields`` call failed (timeouts, 5xx, etc.).
    """
    field_ids: set[str] = set()
    phases_to_fetch: list[str] = []

    for field in pipe_info.get("start_form_fields") or []:
        add_field_identifiers(field_ids, field)

    for phase in pipe_info.get("phases") or []:
        embedded_fields = phase.get("fields")
        if embedded_fields:
            for field in embedded_fields:
                add_field_identifiers(field_ids, field)
        phase_id = phase.get("id")
        if phase_id and not embedded_fields:
            phases_to_fetch.append(str(phase_id))

    failed_phase_ids: list[str] = []
    if phases_to_fetch:
        semaphore = asyncio.Semaphore(PHASE_FIELD_FETCH_CONCURRENCY)
        results = await asyncio.gather(
            *(
                _fetch_phase_field_ids(
                    client, phase_id, timeout=timeout, semaphore=semaphore
                )
                for phase_id in phases_to_fetch
            )
        )
        for phase_field_ids, failed_id in results:
            field_ids.update(phase_field_ids)
            if failed_id is not None:
                failed_phase_ids.append(failed_id)

    return field_ids, failed_phase_ids


def phase_field_fetch_warning(failed_phase_ids: list[str], *, pipe_id: str) -> str:
    """Build a user-facing warning when phase field fetches were incomplete."""
    phases = ", ".join(sorted(failed_phase_ids))
    return (
        f"Could not load fields for phase(s) {phases} in pipe {pipe_id}; "
        "fieldId checks may be incomplete."
    )


async def fetch_pipe_validation_context(
    client: PipefyClient,
    pipe_id: str,
    *,
    timeout: float = 30,
) -> tuple[set[str], set[str], set[str] | None, list[str]]:
    """Fetch pipe phases, fields, and relations for behavior validation.

    Exceptions from ``get_pipe`` propagate to the caller (e.g. TimeoutError,
    RuntimeError). Exceptions from ``get_pipe_relations`` are caught internally
    and result in ``related_pipe_ids=None``.

    Args:
        client: PipefyClient instance.
        pipe_id: Numeric pipe ID as string.
        timeout: Timeout in seconds for each API call.

    Returns:
        Tuple of ``(field_ids, phase_ids, related_pipe_ids, fetch_warnings)``.
        ``related_pipe_ids`` is None when relations could not be loaded.
        ``fetch_warnings`` lists incomplete phase field loads for the source pipe.
    """
    pipe_data = await asyncio.wait_for(
        client.get_pipe(pipe_id),
        timeout=timeout,
    )
    pipe_info = pipe_data.get("pipe") or {}

    phase_ids: set[str] = set()
    for phase in pipe_info.get("phases") or []:
        pid = phase.get("id")
        if pid:
            phase_ids.add(str(pid))

    field_ids, failed_phase_ids = await collect_field_ids_for_pipe(
        client, pipe_info, timeout=timeout
    )
    fetch_warnings: list[str] = []
    if failed_phase_ids:
        fetch_warnings.append(
            phase_field_fetch_warning(failed_phase_ids, pipe_id=pipe_id)
        )

    related_pipe_ids: set[str] | None
    try:
        relations = await asyncio.wait_for(
            client.get_pipe_relations(pipe_id),
            timeout=timeout,
        )
        related_pipe_ids = set()
        for rel in relations.get("children") or []:
            cid = rel.get("child", {}).get("id")
            if cid:
                related_pipe_ids.add(str(cid))
        for rel in relations.get("parents") or []:
            pid = rel.get("parent", {}).get("id")
            if pid:
                related_pipe_ids.add(str(pid))
    except Exception:  # noqa: BLE001
        related_pipe_ids = None

    return field_ids, phase_ids, related_pipe_ids, fetch_warnings


__all__ = [
    "KNOWN_AI_ACTION_TYPES",
    "add_field_identifiers",
    "add_slug_from_field",
    "build_field_slug_map",
    "collect_field_ids_for_pipe",
    "collect_pipe_ids_from_behaviors",
    "fetch_pipe_validation_context",
    "phase_field_fetch_warning",
    "pipe_ids_from_behavior",
    "resolve_and_populate_field_refs",
    "resolve_field_slugs_to_numeric",
    "validate_behaviors_against_pipe",
]
