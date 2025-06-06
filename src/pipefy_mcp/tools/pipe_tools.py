from mcp.server.fastmcp import FastMCP

from pipefy_mcp.services.pipefy import PipefyClient


class PipeTools:
    """Declares tools to be used in the Pipe context."""

    @staticmethod
    def register(mcp: FastMCP):
        """Register the tools in the MCP server"""

        client = PipefyClient()

        @mcp.tool()
        async def create_card(pipe_id: int, fields: dict) -> None:
            """Create a card in the pipe."""
            await client.create_card(pipe_id, fields)

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
