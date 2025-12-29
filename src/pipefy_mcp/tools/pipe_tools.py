from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from pipefy_mcp.core.container import ServicesContainer
from pipefy_mcp.models.form import create_form_model


class PipeTools:
    """Declares tools to be used in the Pipe context."""

    @staticmethod
    def register(mcp: FastMCP):
        """Register the tools in the MCP server"""

        container = ServicesContainer.get_instance()
        client = container.pipefy_client

        @mcp.tool(
            annotations=ToolAnnotations(
                idempotentHint=False,
            ),
        )
        async def create_card(pipe_id: int, ctx: Context[ServerSession, None]) -> dict:
            """Create a card in the pipe.

            Args:
                pipe_id: The ID of the pipe where the card will be created
            """

            expected_fields = await client.get_start_form_fields(pipe_id, False)
            await ctx.debug(f"Expected fields for pipe {pipe_id}: {expected_fields}")

            # Convert field definitions to a pydantic form model
            expected_fields = expected_fields.get("start_form_fields", [])
            DynamicFormModel = create_form_model(expected_fields)

            await ctx.debug(
                f"Created DynamicFormModel: {DynamicFormModel.model_json_schema()}"
            )

            result = await ctx.elicit(
                message=(f"Creating a card in pipe {pipe_id}"),
                schema=DynamicFormModel,
            )

            await ctx.debug(f"Elicited result: {result}")

            if result.action == "accept":
                return await client.create_card(pipe_id, result.data.model_dump())

            return {"error": "Card creation cancelled by user."}

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_card(card_id: int) -> dict:
            """Get a card by its ID."""

            return await client.get_card(card_id)

        @mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
            ),
        )
        async def get_cards(pipe_id: int, search: dict) -> dict:
            """Get all cards in the pipe."""

            return await client.get_cards(pipe_id, search)

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
