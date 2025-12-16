from mcp.server.fastmcp import FastMCP

from pipefy_mcp.services.pipefy import PipefyClient


class PipeTools:
    """Declares tools to be used in the Pipe context."""

    @staticmethod
    def register(mcp: FastMCP):
        """Register the tools in the MCP server"""

        client = PipefyClient()

        @mcp.tool()
        async def create_card(pipe_id: int, fields: dict) -> dict:
            """Create a card in the pipe.

            Args:
                pipe_id: The ID of the pipe where the card will be created
                fields: A dict with field_id as keys and values
                       Example: {"title": "Card Title"}
            """
            return await client.create_card(pipe_id, fields)

        @mcp.tool()
        async def get_card(card_id: int) -> dict:
            """Get a card by its ID."""

            return await client.get_card(card_id)

        @mcp.tool()
        async def get_cards(pipe_id: int, search: dict) -> dict:
            """Get all cards in the pipe."""

            return await client.get_cards(pipe_id, search)

        @mcp.tool()
        async def get_pipe(pipe_id: int) -> dict:
            """Get a pipe by its ID."""

            return await client.get_pipe(pipe_id)

        @mcp.tool()
        async def move_card_to_phase(card_id: int, destination_phase_id: int) -> dict:
            """Move a card to a specific phase."""

            return await client.move_card_to_phase(card_id, destination_phase_id)

        @mcp.tool()
        async def update_card_field(card_id: int, field_id: str, new_value) -> dict:
            """Update a single field of a card.

            Use this tool for simple, single-field updates. The entire field value
            will be replaced with the new value provided.

            Args:
                card_id: The ID of the card containing the field to update
                field_id: The ID (slug) of the field to update
                new_value: The new value for the field (replaces existing value)

            Returns:
                dict: GraphQL response with success status and updated card information
                      including the card's id, title, fields, and updated_at timestamp
            """
            return await client.update_card_field(card_id, field_id, new_value)

        @mcp.tool()
        async def update_card(
            card_id: int,
            title: str | None = None,
            assignee_ids: list[int] | None = None,
            label_ids: list[int] | None = None,
            due_date: str | None = None,
            fields: dict | None = None,
            values: list[dict] | None = None,
        ) -> dict:
            """Update a card's fields and attributes with intelligent mutation selection.

            This tool automatically chooses between replacement and incremental update
            modes based on the parameters provided.

            **Replacement Mode** (default):
            Updates fields/attributes by replacing existing values. Use for:
            - Changing the card title
            - Replacing all assignees or labels
            - Updating custom fields

            **Incremental Mode** (when using `values` with ADD/REMOVE):
            Updates multi-value fields incrementally without replacing the entire list.
            Use for adding/removing specific assignees or labels.

            Args:
                card_id: The ID of the card to update (required)
                title: New title for the card (replacement mode)
                assignee_ids: List of user IDs to assign - replaces existing (replacement mode)
                label_ids: List of label IDs to associate - replaces existing (replacement mode)
                due_date: New due date in ISO 8601 format (replacement mode)
                fields: Dict of custom field updates with field_id as keys (replacement mode)
                        Example: {"field_1": "Value 1", "field_2": "Value 2"}
                values: List of field update objects for incremental operations:
                        - field_id (str): The field ID to update
                        - value (any): The value(s) to add/remove/replace
                        - operation (str): "ADD", "REMOVE", or "REPLACE" (default)
                        Example: [
                            {"field_id": "assignees", "value": [123], "operation": "ADD"},
                            {"field_id": "labels", "value": [456], "operation": "REMOVE"}
                        ]

            **Mutation Selection:**
            - If `values` contains ADD/REMOVE operations → uses incremental mode
            - Otherwise → uses replacement mode
            - If both provided, incremental mode takes precedence

            Returns:
                dict: GraphQL response with updated card information including
                      phase, assignees, labels, fields, and timestamps
            """
            return await client.update_card(
                card_id=card_id,
                title=title,
                assignee_ids=assignee_ids,
                label_ids=label_ids,
                due_date=due_date,
                fields=fields,
                values=values,
            )

        @mcp.tool()
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
