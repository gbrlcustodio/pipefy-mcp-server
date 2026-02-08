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
from pipefy_mcp.services.pipefy import PipefyClient
from pipefy_mcp.services.pipefy.types import CardSearch
from pipefy_mcp.tools.pipe_tool_helpers import (
    FIND_CARDS_EMPTY_MESSAGE,
    AddCardCommentPayload,
    DeleteCardConfirmation,
    DeleteCardPayload,
    DeleteCommentPayload,
    UpdateCommentPayload,
    UserCancelledError,
    _extract_graphql_correlation_id,
    _extract_graphql_error_codes,
    _filter_editable_field_definitions,
    _filter_fields_by_definitions,
    _with_debug_suffix,
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

FIND_CARDS_RESPONSE_KEY = "findCards"


class PipeTools:
    """Declares tools to be used in the Pipe context."""

    @staticmethod
    def register(mcp: FastMCP, client: PipefyClient) -> None:
        """Register the tools in the MCP server"""

        @mcp.tool(
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def create_card(
            ctx: Context[ServerSession, None],
            pipe_id: int,
            fields: dict[str, Any] | None = None,
            required_fields_only: bool = False,
        ) -> dict:
            """
            Create a card in the pipe.

            The fields can be interactively elicited, but, if the LLM is aware of the intended values for certain fields,
            they can be provided in the `fields` argument.

            Importantly, if elicitation is not supported, the provided fields will be used as-is and must be provided.

            Args:
                pipe_id: The ID of the pipe where the card will be created
                fields: A dictionary of fields that can be pre-filled on the card.
                        This argument should be provided when the LLM is aware of the intended values for certain fields.
                required_fields_only: If True, only elicit required fields. Default: False
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
            can_elicit = ctx.session.client_params.capabilities.elicitation

            if can_elicit:
                try:
                    card_data = await PipeTools._elicit_field_details(
                        message=f"Creating a card in pipe {pipe_id}",
                        prefilled_fields=fields,
                        expected_fields=expected_fields,
                        ctx=ctx,
                    )
                except UserCancelledError:
                    return {"error": "Card creation cancelled by user."}
            elif expected_fields:
                card_data = _filter_fields_by_definitions(card_data, expected_fields)

            result = await client.create_card(pipe_id, card_data)
            card_id = result.get("createCard", {}).get("card", {}).get("id")
            if card_id:
                card_url = f"https://app.pipefy.com/open-cards/{card_id}"
                result["card_link"] = f"[{card_url}]({card_url})"
            return result

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_card(
            card_id: int,
            include_fields: bool = False,
        ) -> dict:
            """Get a card by its ID.

            Args:
                card_id: The ID of the card.
                include_fields: If True, include the card's custom fields (name, value) in the response.
            """
            return await client.get_card(card_id, include_fields=include_fields)

        @mcp.tool(
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def add_card_comment(card_id: int, text: str) -> AddCardCommentPayload:
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
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def update_comment(comment_id: int, text: str) -> UpdateCommentPayload:
            """Change the text of an existing comment by its ID.

            Args:
                comment_id: The ID of the comment to update
                text: The new comment text (1-1000 characters)
            """
            try:
                comment_input = UpdateCommentInput(comment_id=comment_id, text=text)
            except ValidationError:
                return build_update_comment_error_payload(
                    message="Invalid input. Please provide a valid 'comment_id' and non-empty 'text'."
                )

            try:
                response = await client.update_comment(
                    comment_id=comment_input.comment_id,
                    text=comment_input.text,
                )
            except Exception as exc:  # noqa: BLE001
                return build_update_comment_error_payload(
                    message=map_update_comment_error_to_message(exc)
                )

            comment_data = (response.get("updateComment", {}) or {}).get(
                "comment"
            ) or {}
            comment_id_res = comment_data.get("id")
            if not comment_id_res:
                return build_update_comment_error_payload(
                    message="Unexpected response from Pipefy. Comment may not have been updated."
                )

            return build_update_comment_success_payload(comment_id=comment_id_res)

        @mcp.tool(
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def delete_comment(comment_id: int) -> DeleteCommentPayload:
            """Remove a comment by its ID.

            Args:
                comment_id: The ID of the comment to delete
            """
            try:
                comment_input = DeleteCommentInput(comment_id=comment_id)
            except ValidationError:
                return build_delete_comment_error_payload(
                    message="Invalid input. Please provide a valid 'comment_id'."
                )

            try:
                response = await client.delete_comment(
                    comment_id=comment_input.comment_id
                )
            except Exception as exc:  # noqa: BLE001
                return build_delete_comment_error_payload(
                    message=map_delete_comment_error_to_message(exc)
                )

            delete_data = response.get("deleteComment", {})
            if delete_data.get("success"):
                return build_delete_comment_success_payload()
            return build_delete_comment_error_payload(
                message="Failed to delete comment. Please try again or verify the comment exists."
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_cards(
            ctx: Context[ServerSession, None],
            pipe_id: int,
            search: CardSearch | None = None,
            include_fields: bool = False,
        ) -> dict:
            """Get all cards in the pipe.

            Args:
                pipe_id: The ID of the pipe.
                search: Optional search filters.
                include_fields: If True, include each card's custom fields (name, value) in the response.
            """
            await ctx.debug(
                f"Getting cards for pipe {pipe_id} (include_fields={include_fields}, search={search})"
            )
            return await client.get_cards(
                pipe_id, search, include_fields=include_fields
            )

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def find_cards(
            pipe_id: int,
            field_id: str,
            field_value: str,
            include_fields: bool = False,
        ) -> dict:
            """Find cards in the pipe where a specific field equals a given value.

            Use this when you need to filter cards by a custom field (e.g. Status = In Progress)
            rather than by title or assignees. The field_id can be obtained from
            get_start_form_fields or get_phase_fields.

            Args:
                pipe_id: The ID of the pipe to search in.
                field_id: Pipefy field identifier (e.g. from get_start_form_fields or get_phase_fields).
                field_value: Value to match for that field (string; use the format expected by the field type).
                include_fields: If True, include each card's custom fields (name, value) in the response.
            """
            response = await client.find_cards(
                pipe_id, field_id, field_value, include_fields=include_fields
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
        async def get_pipe(pipe_id: int) -> dict:
            """Get a pipe by its ID."""

            return await client.get_pipe(pipe_id)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_pipe_members(pipe_id: int) -> dict:
            """Get the members of a pipe."""

            return await client.get_pipe_members(pipe_id)

        @mcp.tool(
            annotations=ToolAnnotations(
                destructiveHint=False,
                idempotentHint=True,
            ),
        )
        async def move_card_to_phase(card_id: int, destination_phase_id: int) -> dict:
            """Move a card to a specific phase."""

            return await client.move_card_to_phase(card_id, destination_phase_id)

        @mcp.tool(
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def update_card_field(
            card_id: int, field_id: str, new_value: Any
        ) -> dict:
            """Update a single field of a card.

            Use this tool for simple, single-field updates. The entire field value
            will be replaced with the new value provided.

            Args:
                card_id: The ID of the card containing the field to update
                field_id: The ID (slug) of the field to update
                new_value: The new value for the field (string, number, list, etc.)

            Returns:
                dict: GraphQL response with success status and updated card information
                      including the card's id, title, fields, and updated_at timestamp
            """
            return await client.update_card_field(card_id, field_id, new_value)

        @mcp.tool(
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def update_card(
            card_id: int,
            title: str | None = None,
            assignee_ids: list[int] | None = None,
            label_ids: list[int] | None = None,
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
                # Update only card attributes
                update_card(card_id=123, title="New Title")

                # Update custom fields with REPLACE operation (default)
                update_card(card_id=123, field_updates=[
                    {"field_id": "status", "value": "In Progress"},
                    {"field_id": "priority", "value": "High"}
                ])

                # Update custom fields with ADD operation
                update_card(card_id=123, field_updates=[
                    {"field_id": "tags", "value": "urgent", "operation": "ADD"}
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
            pipe_id: int, required_only: bool = False
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
        async def get_phase_fields(phase_id: int, required_only: bool = False) -> dict:
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
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def fill_card_phase_fields(
            ctx: Context[ServerSession, None],
            card_id: int,
            phase_id: int,
            fields: dict[str, Any] | None = None,
            required_fields_only: bool = False,
        ) -> dict:
            """Fill in the phase fields for a card using interactive elicitation.

            This tool helps fill in the fields that are specific to a phase.
            When elicitation is supported, it will prompt the user for field values.

            Args:
                card_id: The ID of the card to update
                phase_id: The ID of the phase whose fields should be filled
                fields: A dictionary of fields that can be pre-filled.
                        This argument should be provided when the LLM is aware
                        of the intended values for certain fields.
                required_fields_only: If True, only elicit required fields. Default: False

            Returns:
                dict: GraphQL response with success status and updated card information
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
            can_elicit = ctx.session.client_params.capabilities.elicitation

            if can_elicit and expected_fields:
                try:
                    field_data = await PipeTools._elicit_field_details(
                        message=f"Filling fields for phase '{phase_name}' (ID: {phase_id})",
                        prefilled_fields=fields,
                        expected_fields=expected_fields,
                        ctx=ctx,
                    )
                except UserCancelledError:
                    return {
                        "success": False,
                        "error": "Phase field update cancelled by user.",
                    }
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
        async def search_pipes(pipe_name: str | None = None) -> dict:
            """Search for all accessible pipes across all organizations.

            Use this tool to find a pipe's ID when you only know its name.
            Returns all pipes from all organizations, optionally filtered by name.

            When filtering by name, uses fuzzy matching with a 70% similarity threshold.
            Only pipes with a match score of 70 or higher are included in the results.
            Results are sorted by match score (best matches first).

            Args:
                pipe_name: Optional pipe name to search for (case-insensitive partial match).
                           If not provided, returns all available pipes.

            Returns:
                dict: Contains 'organizations' array, each with:
                      - id: Organization ID
                      - name: Organization name
                      - pipes: Array of pipes in the organization, each with:
                          - id: Pipe ID (use this for other pipe operations)
                          - name: Pipe name
                          - description: Pipe description
                          - match_score: Fuzzy match score (0-100) when pipe_name is provided.
            """
            return await client.search_pipes(pipe_name)

        @mcp.tool(
            annotations=ToolAnnotations(
                destructiveHint=True,
            ),
        )
        async def delete_card(
            ctx: Context[ServerSession, None], card_id: int, debug: bool = False
        ) -> DeleteCardPayload:
            """Delete a card from Pipefy.

            This is a destructive operation that permanently removes a card.
            Use with caution.

            Args:
                card_id: The ID of the card to delete
                debug: When true, appends GraphQL error codes and correlation_id to the error message.

            Returns:
                Success/error status of the deletion.
            """
            # Input validation
            if not isinstance(card_id, int):
                return build_delete_card_error_payload(
                    message=f"Invalid 'card_id'. Expected an integer, got {type(card_id).__name__}."
                )
            if card_id <= 0:
                return build_delete_card_error_payload(
                    message="Invalid 'card_id'. Please provide a positive integer."
                )

            # Fetch card details for preview/confirmation
            try:
                card_response = await client.get_card(card_id)
                card_data = card_response["card"]
                card_title = card_data["title"]
                pipe_name = card_data.get("pipe", {}).get("name", "Unknown Pipe")
            except Exception as exc:
                codes = _extract_graphql_error_codes(exc)
                correlation_id = _extract_graphql_correlation_id(exc)
                base = map_delete_card_error_to_message(
                    card_id=card_id, card_title="Unknown", codes=codes
                )
                return build_delete_card_error_payload(
                    message=_with_debug_suffix(
                        base,
                        debug=debug,
                        codes=codes,
                        correlation_id=correlation_id,
                    )
                )

            # Sampling/Elicitation for confirmation
            can_elicit = ctx.session.client_params.capabilities.elicitation
            if can_elicit:
                confirmation_message = (
                    f"⚠️ You are about to permanently delete card '{card_title}' (ID: {card_id}) from pipe '{pipe_name}'. "
                    "This action is irreversible. Are you sure you want to proceed?"
                )

                try:
                    result = await ctx.elicit(
                        message=confirmation_message,
                        schema=DeleteCardConfirmation,
                    )

                    if result.action != "accept":
                        # User manually cancelled via UI
                        return build_delete_card_error_payload(
                            message="Card deletion cancelled by user."
                        )

                    confirmation_data = result.data.model_dump()
                    if not confirmation_data.get("confirm"):
                        return build_delete_card_error_payload(
                            message="Card deletion cancelled by user."
                        )

                except Exception as e:
                    return build_delete_card_error_payload(
                        message=f"Failed to request confirmation: {str(e)}"
                    )

            try:
                delete_response = await client.delete_card(card_id)

                delete_data = delete_response.get("deleteCard", {})

                if delete_data.get("success"):
                    return build_delete_card_success_payload(
                        card_id=card_id,
                        card_title=card_title,
                        pipe_name=pipe_name,
                    )
                else:
                    return build_delete_card_error_payload(
                        message=f"Failed to delete card '{card_title}' (ID: {card_id}). Please try again or contact support."
                    )
            except Exception as exc:
                codes = _extract_graphql_error_codes(exc)
                correlation_id = _extract_graphql_correlation_id(exc)
                base = map_delete_card_error_to_message(
                    card_id=card_id, card_title=card_title, codes=codes
                )
                return build_delete_card_error_payload(
                    message=_with_debug_suffix(
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
