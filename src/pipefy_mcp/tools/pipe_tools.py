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
        async def get_start_form_fields(pipe_id: int, required_only: bool = False) -> dict:
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
