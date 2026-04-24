"""MCP tools for pipes, cards, comments, and related operations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from pipefy_mcp.models.comment import (
    CommentInput,
    DeleteCommentInput,
    UpdateCommentInput,
)
from pipefy_mcp.models.form import create_form_model
from pipefy_mcp.models.validators import PipefyId
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.services.pipefy.types import CardSearch, copy_card_search
from pipefy_mcp.settings import settings
from pipefy_mcp.tools.destructive_tool_guard import check_destructive_confirmation
from pipefy_mcp.tools.graphql_error_helpers import (
    enrich_permission_denied_error,
    extract_graphql_correlation_id,
    extract_graphql_error_codes,
    handle_tool_graphql_error,
    with_debug_suffix,
)
from pipefy_mcp.tools.mcp_capabilities import supports_elicitation
from pipefy_mcp.tools.pagination_helpers import (
    build_pagination_info,
    validate_page_size,
)
from pipefy_mcp.tools.phase_transition_helpers import (
    try_enrich_move_card_to_phase_failure,
)
from pipefy_mcp.tools.pipe_tool_helpers import (
    FIND_CARDS_EMPTY_MESSAGE,
    AddCardCommentPayload,
    DeleteCardPayload,
    DeleteCommentPayload,
    UpdateCommentErrorPayload,
    UpdateCommentSuccessPayload,
    UserCancelledError,
    _filter_editable_field_definitions,
    _filter_fields_by_definitions,
    build_add_card_comment_error_payload,
    build_add_card_comment_success_payload,
    build_delete_card_error_payload,
    build_delete_card_success_payload,
    build_delete_comment_error_payload,
    build_delete_comment_success_payload,
    build_update_comment_error_payload,
    build_update_comment_success_payload,
    map_add_card_comment_error_to_message,
    map_delete_card_error_to_message,
    map_delete_comment_error_to_message,
    map_update_comment_error_to_message,
)
from pipefy_mcp.tools.relation_tool_helpers import (
    build_relation_error_payload,
    build_relation_mutation_success_payload,
    handle_relation_tool_graphql_error,
)
from pipefy_mcp.tools.tool_error_envelope import (
    tool_error,
    tool_error_message,
    tool_success,
)
from pipefy_mcp.tools.validation_helpers import validate_tool_id

# Key for findCards response; used when reading edges and adding empty message.
FIND_CARDS_RESPONSE_KEY = "findCards"


class PipeTools:
    """Declares tools to be used in the Pipe context."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register the tools in the MCP server"""

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def create_card(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            title: str | None = None,
            fields: dict[str, Any] | None = None,
            required_fields_only: bool = False,
            skip_elicitation: bool = False,
        ) -> dict:
            """Create a card in the pipe.

            When ``skip_elicitation`` is True, field values from ``fields`` are
            filtered to editable start-form field IDs and sent directly to the
            API — no interactive form is shown. AI agents should set this to
            True when they already know the field values.

            When ``skip_elicitation`` is False (default) and the client supports
            elicitation, an interactive form is presented even if ``fields``
            carries pre-filled values — the human can review and adjust them.

            Discover fields first via ``get_start_form_fields`` and pass all
            required values.

            The Pipefy ``createCard`` mutation does not accept a title directly.
            If ``title`` is provided, the card is created first and then updated
            via ``updateCard`` to set the title — this is especially useful when the
            pipe has no start-form fields, which would otherwise leave the card
            titled "Draft".

            Args:
                pipe_id: The ID of the pipe where the card will be created.
                title: Optional card title. Applied via updateCard after creation.
                fields: A dictionary of fields that can be pre-filled on the card.
                    When ``skip_elicitation`` is False, these pre-fill the interactive
                    form. When True, they are sent directly to the API.
                required_fields_only: If True, only elicit required fields. Default: False.
                skip_elicitation: When True, bypass interactive elicitation and send
                    ``fields`` directly to the API. Recommended for AI agent workflows.
            """
            form_fields = await client.get_start_form_fields(
                pipe_id, required_fields_only
            )

            expected_fields = _filter_editable_field_definitions(
                form_fields.get("start_form_fields", [])
            )

            await ctx.debug(f"Expected fields for pipe {pipe_id}: {expected_fields}")
            await ctx.debug(f"Provided fields: {fields}")

            card_data = fields or {}
            can_elicit = supports_elicitation(ctx)

            if can_elicit and not skip_elicitation:
                try:
                    card_data = await PipeTools._elicit_field_details(
                        message=f"Creating a card in pipe {pipe_id}",
                        prefilled_fields=fields,
                        expected_fields=expected_fields,
                        ctx=ctx,
                    )
                except UserCancelledError:
                    return tool_error("Card creation cancelled by user.")
            elif expected_fields:
                card_data = _filter_fields_by_definitions(card_data, expected_fields)

            try:
                result = await client.create_card(pipe_id, card_data)
            except Exception as exc:  # noqa: BLE001
                perm_msg = await enrich_permission_denied_error(
                    exc, [str(pipe_id)], client
                )
                error_text = str(exc)
                if perm_msg:
                    error_text = f"{perm_msg}\n{error_text}"
                return tool_error(error_text)
            card_id = result.get("createCard", {}).get("card", {}).get("id")
            if card_id:
                if title:
                    try:
                        await client.update_card(card_id, title=title)
                    except Exception as exc:  # noqa: BLE001
                        result["title_warning"] = (
                            f"Card created but title update failed: {exc}"
                        )
                    else:
                        card_data_node = result.get("createCard", {}).get("card")
                        if card_data_node is not None:
                            card_data_node["title"] = title
                card_url = f"https://app.pipefy.com/open-cards/{card_id}"
                result["card_link"] = f"[{card_url}]({card_url})"
            return result

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_card(
            ctx: Context[ServerSession, None],
            card_id: PipefyId,
            include_fields: bool = False,
            debug: bool = False,
        ) -> dict:
            """Load one card by ID for title, phase, assignees, labels, and optional field values.

            Use this to inspect a card before updates, after ``find_cards`` / ``get_cards``,
            or when the user references a card by ID. Set ``include_fields`` when you need
            custom field ``name``/``value`` pairs for forms or automation.

            Args:
                card_id: Pipefy card ID (string or positive integer).
                    Discover via: ``find_cards`` or ``get_cards(pipe_id)``.
                include_fields: If True, include each custom field's name and value on the card node.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                dict: GraphQL ``card`` query payload (typically ``card`` with ``id``, ``title``,
                ``phase``, ``assignees``, ``labels``, and—when requested—``fields``).
            """
            await ctx.debug(f"get_card: card_id={card_id}")
            card_id_str, err = validate_tool_id(card_id, "card_id")
            if err is not None:
                return err
            try:
                return await client.get_card(card_id_str, include_fields=include_fields)
            except Exception as exc:  # noqa: BLE001
                return handle_tool_graphql_error(
                    exc,
                    "Failed to load card.",
                    debug=debug,
                    resource_kind="card",
                    resource_id=card_id_str,
                )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_card_relations(
            ctx: Context[ServerSession, None],
            card_id: PipefyId,
            debug: bool = False,
        ) -> dict:
            """List parent and child card relations for a card (full lists; no pagination).

            Use after ``get_card`` or ``find_cards`` when you need linked cards in other pipes.
            ``child_relations`` and ``parent_relations`` mirror Pipefy's relation groups (name,
            pipe, linked cards).

            Args:
                card_id: Card whose relations to load.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                On success: ``success``, ``message``, ``child_relations``, and ``parent_relations``
                (API fields ``child_relations`` / ``parent_relations`` on ``Card``). On failure:
                ``success: False`` and ``error``.
            """
            await ctx.debug(f"get_card_relations: card_id={card_id}")
            card_id_str, err = validate_tool_id(card_id, "card_id")
            if err is not None:
                return err

            try:
                raw = await client.get_card_relations(card_id_str)
            except Exception as exc:  # noqa: BLE001
                return handle_relation_tool_graphql_error(
                    exc,
                    "Get card relations failed.",
                    debug=debug,
                    resource_kind="card",
                    resource_id=card_id_str,
                )

            card_node = raw.get("card")
            if card_node is None:
                return tool_error("Card not found or access denied.")

            # Public GraphQL returns snake_case (``child_relations``); accept camelCase too.
            child = (
                card_node.get("child_relations")
                or card_node.get("childRelations")
                or []
            )
            parent = (
                card_node.get("parent_relations")
                or card_node.get("parentRelations")
                or []
            )
            return {
                "success": True,
                "message": "Card relations loaded.",
                "child_relations": child,
                "parent_relations": parent,
            }

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
            structured_output=False,
        )
        async def add_card_comment(
            card_id: PipefyId, text: str
        ) -> AddCardCommentPayload:
            """Add a text comment to a Pipefy card.

            Args:
                card_id: The ID of the card to comment on
                text: The comment text to post (1-1000 characters)
            """
            # Privacy: never log the full comment text (it may contain sensitive data).
            try:
                comment_input = CommentInput(card_id=card_id, text=text)
            except ValidationError:
                return build_add_card_comment_error_payload(
                    message="Invalid input. Please provide a valid 'card_id' and non-empty 'text'."
                )

            try:
                response = await client.add_card_comment(
                    card_id=comment_input.card_id, text=comment_input.text
                )
                comment_id = response["createComment"]["comment"]["id"]
            except Exception as exc:  # noqa: BLE001
                return build_add_card_comment_error_payload(
                    message=map_add_card_comment_error_to_message(exc)
                )

            return build_add_card_comment_success_payload(comment_id=comment_id)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
            structured_output=False,
        )
        async def update_comment(
            comment_id: PipefyId, text: str
        ) -> UpdateCommentSuccessPayload | UpdateCommentErrorPayload:
            """Update an existing comment by its ID.

            Args:
                comment_id: The ID of the comment to update.
                text: The new comment text (1-1000 characters).
            """
            # Privacy: do not log full comment text.
            try:
                update_input = UpdateCommentInput(comment_id=comment_id, text=text)
            except ValidationError:
                return build_update_comment_error_payload(
                    message="Invalid input. Please provide a valid 'comment_id' and non-empty 'text'."
                )

            try:
                response = await client.update_comment(
                    update_input.comment_id, update_input.text
                )
                comment_id_out = response["updateComment"]["comment"]["id"]
            except Exception as exc:  # noqa: BLE001
                return build_update_comment_error_payload(
                    message=map_update_comment_error_to_message(exc)
                )

            return build_update_comment_success_payload(comment_id=comment_id_out)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
            structured_output=False,
        )
        async def delete_comment(
            ctx: Context[ServerSession, None],
            comment_id: PipefyId,
            confirm: bool = False,
        ) -> DeleteCommentPayload:
            """Delete a comment from Pipefy.

            Two-step operation:

            1. **Preview** — call with ``confirm=False`` (default). Returns a preview payload;
               nothing is deleted. Elicitation is **not** used to authorize deletion.
            2. **Execute** — call again with ``confirm=True`` after explicit human approval.

            Args:
                comment_id: The ID of the comment to delete.
                confirm: Must be ``True`` to run the delete mutation.
            """
            try:
                delete_input = DeleteCommentInput(comment_id=comment_id)
            except ValidationError:
                return build_delete_comment_error_payload(
                    message="Invalid input. Please provide a valid 'comment_id'."
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=f"comment (ID: {delete_input.comment_id})",
            )
            if guard is not None:
                return guard

            try:
                await client.delete_comment(delete_input.comment_id)
            except Exception as exc:  # noqa: BLE001
                return build_delete_comment_error_payload(
                    message=map_delete_comment_error_to_message(exc)
                )

            return build_delete_comment_success_payload()

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
        )
        async def delete_card_relation(
            ctx: Context[ServerSession, None],
            child_id: PipefyId,
            parent_id: PipefyId,
            source_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> dict:
            """Remove a link between two related cards (requires OAuth credentials).

            ``source_id`` is the **pipe relation** id from ``get_pipe_relations`` (same as
            ``create_card_relation``). Two-step flow: preview with ``confirm=False`` (default),
            then execute with ``confirm=True`` after explicit approval.

            Requires OAuth credentials (PIPEFY_OAUTH_CLIENT, PIPEFY_OAUTH_SECRET,
            PIPEFY_OAUTH_URL) because the ``deleteCardRelation`` mutation is only available
            on the internal API, not the public GraphQL schema.

            Args:
                child_id: Child card ID in the relation.
                parent_id: Parent card ID in the relation.
                source_id: Pipe relation ID defining the pipe-to-pipe link.
                confirm: Must be ``True`` to run the delete mutation.
                debug: When True, append GraphQL codes and correlation_id to errors.

            Returns:
                Success payload with mutation result, or ``success: False`` with ``error``.
            """
            await ctx.debug(
                f"delete_card_relation: child_id={child_id}, parent_id={parent_id}, "
                f"source_id={source_id}, confirm={confirm}"
            )

            if not client.internal_api_available:
                return build_relation_error_payload(
                    message=(
                        "delete_card_relation requires OAuth credentials "
                        "(PIPEFY_OAUTH_CLIENT, PIPEFY_OAUTH_SECRET, PIPEFY_OAUTH_URL). "
                        "The deleteCardRelation mutation is only available on the "
                        "internal API. Check .env.example for the required variables."
                    ),
                )

            cid, err = validate_tool_id(child_id, "child_id")
            if err is not None:
                return err
            pid, err = validate_tool_id(parent_id, "parent_id")
            if err is not None:
                return err
            sid, err = validate_tool_id(source_id, "source_id")
            if err is not None:
                return err

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=(
                    f"card relation (child: {cid}, parent: {pid}, source: {sid})"
                ),
            )
            if guard is not None:
                return guard

            try:
                raw = await client.delete_card_relation(cid, pid, sid)
            except Exception as exc:  # noqa: BLE001
                return handle_relation_tool_graphql_error(
                    exc,
                    "Delete card relation failed.",
                    debug=debug,
                    resource_kind="card",
                    resource_id=str(cid),
                )

            node = raw.get("deleteCardRelation") or {}
            if node.get("success"):
                return build_relation_mutation_success_payload(
                    message="Card relation removed.",
                    data=raw,
                )
            return build_relation_error_payload(
                message="Delete card relation did not succeed.",
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_cards(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            title: str | None = None,
            search: CardSearch | None = None,
            include_fields: bool = False,
            first: int | None = None,
            after: str | None = None,
        ) -> dict:
            """Get cards in the pipe with optional search and pagination.

            Supports searching by card **title** (use the ``title`` shortcut) as well
            as by assignees, labels, and other attributes via ``search``.

            Use ``first`` and ``after`` (from ``pageInfo.endCursor``) to paginate
            through large result sets. Without pagination params, returns the API
            default page.

            Args:
                pipe_id: The ID of the pipe.
                title: Filter cards whose title contains this text. Convenience
                    shortcut — merged into ``search`` automatically.
                search: Optional search filters (title, assignee_ids, label_ids,
                    include_done, etc.). See ``CardSearch`` for all supported keys.
                include_fields: If True, include each card's custom fields (name, value) in the response.
                first: Max cards to return per page (1-500).
                after: Cursor for fetching the next page (from ``pageInfo.endCursor`` of a previous call).
            """
            # Only validate when the caller supplied a value; ``None`` means
            # "use the API default page" and is left unchanged.
            if first is not None:
                validated_first, err = validate_page_size(first)
                if err is not None:
                    return err
                first = validated_first

            merged_search: CardSearch = copy_card_search(search) if search else {}
            if title:
                merged_search["title"] = title

            effective_search: CardSearch | None = (
                merged_search if merged_search else None
            )

            await ctx.debug(
                f"Getting cards for pipe {pipe_id} (include_fields={include_fields}, search={effective_search})"
            )
            raw = await client.get_cards(
                pipe_id,
                effective_search,
                include_fields=include_fields,
                first=first,
                after=after,
            )
            if settings.pipefy.mcp_unified_envelope:
                # When the caller omits ``first`` the tool falls through to the
                # Pipefy API default page; there is no requested page size to
                # report back, so omit the pagination block rather than publish
                # ``page_size=0`` (which our own validator would reject).
                pagination = None
                if first is not None:
                    page_info = (
                        (raw.get("cards") or {}).get("pageInfo")
                        if isinstance(raw, dict)
                        else None
                    )
                    pagination = build_pagination_info(
                        page_info=page_info, page_size=first
                    )
                return tool_success(
                    data=raw, message="Cards retrieved.", pagination=pagination
                )
            return raw

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def find_cards(
            pipe_id: PipefyId,
            field_id: str,
            field_value: str,
            include_fields: bool = False,
            first: int | None = None,
            after: str | None = None,
        ) -> dict:
            """Find cards in the pipe where a specific custom field equals a given value.

            Use this when you need to filter cards by a **custom field** value
            (e.g. Status = "In Progress"). This tool does **not** support
            searching by card title — use ``get_cards(title=...)`` for that.

            Do **not** use column ``name`` values from ``get_pipe_report_columns`` or
            ``get_pipe_report_filterable_fields`` (e.g. ``field_2_string``) as ``field_id``:
            those keys are for pipe **reports**, not for the ``findCards`` GraphQL field.
            Always take ``field_id`` from ``get_phase_fields`` or ``get_start_form_fields``
            (the field's ``id`` / slug).

            Args:
                pipe_id: The ID of the pipe to search in.
                field_id: Pipefy field slug (e.g. "status", "campaign_name") — the ``id``
                    value returned by get_start_form_fields or get_phase_fields, NOT the
                    human-readable label and NOT pipe-report column names. Call
                    get_phase_fields (per phase) or get_start_form_fields to discover valid slugs.
                field_value: Value to match for that field (string; use the format expected by the field type).
                include_fields: If True, include each card's custom fields (name, value) in the response.
                first: Max cards per page (optional).
                after: Cursor from ``pageInfo.endCursor`` for the next page (optional).
            """
            response = await client.find_cards(
                pipe_id,
                field_id,
                field_value,
                include_fields=include_fields,
                first=first,
                after=after,
            )
            edges = response.get(FIND_CARDS_RESPONSE_KEY, {}).get("edges")
            if not edges:
                response = dict(response)
                response["message"] = FIND_CARDS_EMPTY_MESSAGE
            return response

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_pipe(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            debug: bool = False,
        ) -> dict:
            """Load a pipe by ID: name, phases, labels, and start-form field definitions.

            Use this after resolving ``pipe_id`` (e.g. from ``search_pipes``) to inspect workflow
            structure, obtain phase IDs for ``move_card_to_phase``, or read start-form fields
            before ``create_card``.

            Args:
                pipe_id: Pipe identifier (string or positive integer).
                    Discover via: ``search_pipes`` or ``get_organization``.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                dict: GraphQL response containing a ``pipe`` object with ``id``, ``name``,
                ``phases``, ``labels``, ``start_form_fields``, and related metadata from the API.
            """
            await ctx.debug(f"get_pipe: pipe_id={pipe_id}")
            pipe_id_str, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            try:
                return await client.get_pipe(pipe_id_str)
            except Exception as exc:  # noqa: BLE001
                return handle_tool_graphql_error(
                    exc,
                    "Failed to load pipe.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=pipe_id_str,
                )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_labels(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            debug: bool = False,
        ) -> dict:
            """List labels defined on a pipe (id and name).

            Uses the same underlying data as ``get_pipe`` (``labels { id name }``) but returns
            only the label list—lighter for agents that only need valid label IDs for cards or filters.

            Args:
                pipe_id: Pipe whose labels to load.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                On success: ``success``, ``message``, and ``labels`` (list of ``{id, name}``).
                On failure: ``success: False`` and ``error``.
            """
            await ctx.debug(f"get_labels: pipe_id={pipe_id}")
            pipe_id_str, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err

            try:
                raw = await client.get_pipe(pipe_id_str)
            except Exception as exc:  # noqa: BLE001
                return handle_tool_graphql_error(
                    exc,
                    "Get labels failed.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=pipe_id_str,
                )

            pipe_node = raw.get("pipe")
            if pipe_node is None:
                return tool_error("Pipe not found or access denied.")

            labels = pipe_node.get("labels")
            if labels is None:
                labels = []
            return {
                "success": True,
                "message": "Labels loaded.",
                "labels": labels,
            }

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_pipe_members(
            ctx: Context[ServerSession, None],
            pipe_id: PipefyId,
            debug: bool = False,
        ) -> dict:
            """List members of a pipe with roles and basic user profile fields.

            Use this to audit who has access, resolve user IDs for assignments, or before
            changing membership with invite/remove/role tools.

            Args:
                pipe_id: Pipe identifier (string or positive integer).
                    Discover via: ``search_pipes`` or ``get_organization``.
                debug: When True, append GraphQL codes and correlation_id on errors.

            Returns:
                dict: GraphQL payload whose ``pipe.members`` entries include ``user``
                (``id``, ``uuid``, ``name``, ``email``) and ``role_name`` per member.
            """
            await ctx.debug(f"get_pipe_members: pipe_id={pipe_id}")
            pipe_id_str, err = validate_tool_id(pipe_id, "pipe_id")
            if err is not None:
                return err
            try:
                return await client.get_pipe_members(pipe_id_str)
            except Exception as exc:  # noqa: BLE001
                return handle_tool_graphql_error(
                    exc,
                    "Failed to load pipe members.",
                    debug=debug,
                    resource_kind="pipe",
                    resource_id=pipe_id_str,
                )

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
        )
        async def move_card_to_phase(
            card_id: PipefyId, destination_phase_id: PipefyId
        ) -> dict:
            """Move a card to a target phase (Kanban column) within the same pipe.

            Use this when the workflow should advance or regress a card; pair with ``get_pipe``
            or ``get_card`` to resolve valid phase IDs. On failure, if the destination is not
            among ``cards_can_be_moved_to_phases`` for the card's current phase, the tool may
            return ``success: false`` with ``valid_destinations`` instead of only the raw API error.

            Args:
                card_id: The card to move.
                    Discover via: ``find_cards`` or ``get_cards(pipe_id)``.
                destination_phase_id: Target phase ID (must be allowed for the current phase).
                    Discover via: ``get_pipe(pipe_id).phases[].id``.

            Returns:
                dict: Pipefy move mutation response on success. On some validation failures,
                a structured payload with ``success: false`` and ``valid_destinations`` when the
                destination phase is not allowed from the current phase.
            """

            try:
                return await client.move_card_to_phase(card_id, destination_phase_id)
            except Exception as exc:  # noqa: BLE001
                enriched = await try_enrich_move_card_to_phase_failure(
                    client,
                    card_id,
                    destination_phase_id,
                )
                if enriched is not None:
                    return enriched
                raise exc

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_card_field(
            card_id: PipefyId, field_id: str, new_value: Any
        ) -> dict:
            """Update a single field of a card.

            Use this tool for simple, single-field updates. The entire field value
            will be replaced with the new value provided.

            Args:
                card_id: The ID of the card containing the field to update.
                    Discover via: ``find_cards`` or ``get_cards(pipe_id)``.
                field_id: The ID (slug) of the field to update.
                    Discover via: ``get_phase_fields(phase_id)[].id`` (or ``internal_id`` for numeric forms).
                new_value: The new value for the field (string, number, list, etc.)

            Returns:
                dict: GraphQL response with success status and updated card information
                      including the card's id, title, fields, and updated_at timestamp
            """
            return await client.update_card_field(card_id, field_id, new_value)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def update_card(
            card_id: PipefyId,
            title: str | None = None,
            assignee_ids: list[PipefyId] | None = None,
            label_ids: list[PipefyId] | None = None,
            due_date: str | None = None,
            field_updates: list[dict] | None = None,
        ) -> dict:
            """Update a card's fields and attributes with intelligent mutation selection.

            This tool automatically chooses between two modes based on parameters:

            **Attribute Mode** (uses `updateCard` mutation):
            For updating card attributes like title, assignees, labels, due_date.

            **Field Mode** (uses `updateFieldsValues` mutation):
            For updating custom fields via field_updates list.

            If field_updates is empty or omitted, only card attributes will be updated.

            Args:
                card_id: The ID of the card to update (required)
                title: New title for the card
                assignee_ids: List of user IDs to assign (replaces existing)
                label_ids: List of label IDs to associate (replaces existing)
                due_date: New due date in ISO 8601 format
                field_updates: List of field update objects:
                        - field_id (str): The field ID to update
                        - value (any): The value(s) to set
                        - operation (str, optional): "ADD", "REMOVE", or "REPLACE" (default)

            Returns:
                dict: GraphQL response with updated card information including
                      phase, assignees, labels, fields, and timestamps

            Examples:
                update_card(card_id=123, title="New Title")
                update_card(card_id=123, field_updates=[
                    {"field_id": "status", "value": "In Progress"},
                    {"field_id": "priority", "value": "High"},
                ])
                update_card(card_id=123, field_updates=[
                    {"field_id": "tags", "value": "urgent", "operation": "ADD"},
                ])
            """
            return await client.update_card(
                card_id=card_id,
                title=title,
                assignee_ids=assignee_ids,
                label_ids=label_ids,
                due_date=due_date,
                field_updates=field_updates,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_start_form_fields(
            pipe_id: PipefyId, required_only: bool = False
        ) -> dict:
            """Get the start form fields of a pipe.

            Use this tool to understand which fields need to be filled when creating
            a card in a pipe. Returns field definitions including type, options,
            and whether they are required.

            Args:
                pipe_id: The ID of the pipe to get start form fields from
                required_only: If True, returns only required fields. Default: False
                              Use this to see the minimum fields needed to create a card.

            Returns:
                dict: Contains 'start_form_fields' array with field properties:
                      - id: Field identifier (slug) used when creating cards
                      - label: Display name of the field
                      - type: Field type (short_text, select, date, etc.)
                      - required: Whether the field is mandatory
                      - editable: Whether the field can be edited after card creation
                      - options: Available options for select/radio/checklist fields
                      - description: Field description text
                      - help: Help text for the field
            """
            return await client.get_start_form_fields(pipe_id, required_only)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_phase_fields(
            phase_id: PipefyId, required_only: bool = False
        ) -> dict:
            """Get the fields available in a specific phase.

            Use this tool to understand which fields need to be filled on a specific phase.
            Returns field definitions including type, options, description
            and whether they are required.

            Args:
                phase_id: The ID of the phase to get fields from.
                          You can find phase IDs by calling get_pipe first.
                required_only: If True, returns only required fields. Default: False.
                               Use this to see the minimum fields needed in the phase.

            Returns:
                dict: Contains phase info and 'fields' array with field properties:
                      - id: Field identifier (slug) used when updating cards
                      - internal_id: Stable numeric-style ID (use for mutations such as field conditions)
                      - uuid: Field UUID
                      - label: Display name of the field
                      - type: Field type (short_text, select, date, etc.)
                      - required: Whether the field is mandatory
                      - editable: Whether the field can be edited
                      - options: Available options for select/radio/checklist fields
                      - description: Field description text
                      - help: Help text for the field
            """
            return await client.get_phase_fields(phase_id, required_only)

        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=False),
        )
        async def fill_card_phase_fields(
            ctx: Context[ServerSession, None],
            card_id: PipefyId,
            phase_id: PipefyId,
            fields: dict[str, Any] | None = None,
            required_fields_only: bool = False,
            skip_elicitation: bool = False,
        ) -> dict:
            """Fill in the phase fields for a card.

            When ``skip_elicitation`` is True, field values from ``fields`` are
            filtered to editable phase field IDs and sent directly to the API.
            AI agents should set this to True when they already know the values.

            When ``skip_elicitation`` is False (default) and the client supports
            elicitation, an interactive form is presented — ``fields`` pre-fills
            it so the human can review and adjust.

            Args:
                card_id: The ID of the card to update.
                    Discover via: ``find_cards`` or ``get_cards(pipe_id)``.
                phase_id: The ID of the phase whose fields should be filled.
                    Discover via: ``get_pipe(pipe_id).phases[].id``.
                fields: A dictionary of fields that can be pre-filled.
                        When ``skip_elicitation`` is False, these pre-fill the
                        interactive form. When True, they are sent directly.
                        Discover via: ``get_phase_fields(phase_id)[].id`` for valid keys.
                required_fields_only: If True, only elicit required fields. Default: False.
                skip_elicitation: When True, bypass interactive elicitation and send
                    ``fields`` directly to the API. Recommended for AI agent workflows.

            Returns:
                dict: GraphQL response with success status and updated card information.
            """
            phase_fields_result = await client.get_phase_fields(
                phase_id, required_fields_only
            )
            expected_fields = _filter_editable_field_definitions(
                phase_fields_result.get("fields", [])
            )
            phase_name = phase_fields_result.get("phase_name", f"Phase {phase_id}")

            await ctx.debug(f"Expected fields for phase {phase_id}: {expected_fields}")
            await ctx.debug(f"Provided fields: {fields}")

            field_data = fields or {}
            can_elicit = supports_elicitation(ctx)

            if can_elicit and expected_fields and not skip_elicitation:
                try:
                    field_data = await PipeTools._elicit_field_details(
                        message=f"Filling fields for phase '{phase_name}' (ID: {phase_id})",
                        prefilled_fields=fields,
                        expected_fields=expected_fields,
                        ctx=ctx,
                    )
                except UserCancelledError:
                    return tool_error("Phase field update cancelled by user.")
            elif expected_fields:
                field_data = _filter_fields_by_definitions(field_data, expected_fields)

            if not field_data:
                return {
                    "success": True,
                    "message": "No fields to update.",
                    "phase_id": phase_id,
                    "phase_name": phase_name,
                }

            field_updates = [
                {"field_id": field_id, "value": value}
                for field_id, value in field_data.items()
            ]

            return await client.update_card(
                card_id=card_id,
                field_updates=field_updates,
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def search_pipes(
            pipe_name: str | None = None,
            max_pipes_per_org: int = 500,
        ) -> dict:
            """Search for all accessible pipes across all organizations.

            Use this tool to find a pipe's ID when you only know its name.
            Returns pipes from all organizations, optionally filtered by name.

            When filtering by name, uses fuzzy matching with a 70% similarity threshold.
            Only pipes with a match score of 70 or higher are included in the results.
            Results are sorted by match score (best matches first).

            Without a name filter, each organization returns at most ``max_pipes_per_org``
            pipes (capped 1--500) to avoid huge responses. With a name filter, the API
            receives a server-side ``name_search`` hint; results are still capped per org
            after scoring. Check ``search_limits`` and per-org ``pipes_truncated`` when present.

            Args:
                pipe_name: Optional pipe name to search for (case-insensitive partial match).
                           If not provided, returns up to ``max_pipes_per_org`` pipes per org.
                max_pipes_per_org: Maximum pipes per organization (1--500, default 500).

            Returns:
                dict: Contains 'organizations' array, each with:
                      - id: Organization ID
                      - name: Organization name
                      - pipes: Array of pipes in the organization, each with:
                          - id: Pipe ID (use this for other pipe operations)
                          - name: Pipe name
                          - description: Pipe description
                          - match_score: Fuzzy match score (0-100) when pipe_name is provided.
                      And ``search_limits`` with applied caps.
            """
            mpc = max(1, min(500, int(max_pipes_per_org)))
            return await client.search_pipes(pipe_name, max_pipes_per_org=mpc)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
            ),
            structured_output=False,
        )
        async def delete_card(
            ctx: Context[ServerSession, None],
            card_id: PipefyId,
            confirm: bool = False,
            debug: bool = False,
        ) -> DeleteCardPayload:
            """Delete a card from Pipefy.

            Two-step operation:

            1. **Preview** — call with ``confirm=False`` (default). Returns a preview payload;
               nothing is deleted. Elicitation is **not** used to authorize deletion (automated
               clients may auto-accept prompts).
            2. **Execute** — call again with ``confirm=True`` after explicit human approval.

            Args:
                card_id: The ID of the card to delete.
                confirm: Must be ``True`` to run the delete mutation.
                debug: When true, appends GraphQL error codes and correlation_id to the error message.

            Returns:
                Success/error status of the deletion.
            """
            card_id_str, err = validate_tool_id(card_id, "card_id")
            if err is not None:
                return build_delete_card_error_payload(message=tool_error_message(err))

            try:
                card_response = await client.get_card(card_id_str)
                card_data = card_response["card"]
                card_title = card_data["title"]
                pipe_name = card_data.get("pipe", {}).get("name", "Unknown Pipe")
            except Exception as exc:  # noqa: BLE001
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_card_error_to_message(
                    card_id=card_id_str, card_title="Unknown", codes=codes
                )
                return build_delete_card_error_payload(
                    message=with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    )
                )

            guard = await check_destructive_confirmation(
                ctx,
                confirm=confirm,
                resource_descriptor=(
                    f"card '{card_title}' (ID: {card_id_str}) from pipe '{pipe_name}'"
                ),
            )
            if guard is not None:
                return guard

            try:
                delete_response = await client.delete_card(card_id_str)

                delete_data = delete_response.get("deleteCard", {})

                if delete_data.get("success"):
                    return build_delete_card_success_payload(
                        card_id=card_id_str,
                        card_title=card_title,
                        pipe_name=pipe_name,
                    )
                else:
                    return build_delete_card_error_payload(
                        message=(
                            f"Failed to delete card '{card_title}' (ID: {card_id_str}). "
                            "Please try again or contact support."
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                codes = extract_graphql_error_codes(exc)
                correlation_id = extract_graphql_correlation_id(exc)
                base = map_delete_card_error_to_message(
                    card_id=card_id_str, card_title=card_title, codes=codes
                )
                return build_delete_card_error_payload(
                    message=with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    )
                )

    @staticmethod
    async def _elicit_field_details(
        message: str,
        prefilled_fields: dict[str, Any] | None,
        expected_fields: list,
        ctx: Context[ServerSession, None],
    ) -> dict:
        """Handle interactive field elicitation."""
        DynamicFormModel = create_form_model(expected_fields, prefilled_fields)
        await ctx.debug(
            f"Created DynamicFormModel: {DynamicFormModel.model_json_schema()}"
        )

        result = await ctx.elicit(
            message=message,
            schema=DynamicFormModel,
        )
        await ctx.debug(f"Elicited result: {result}")

        if result.action != "accept":
            raise UserCancelledError()

        return result.data.model_dump()
