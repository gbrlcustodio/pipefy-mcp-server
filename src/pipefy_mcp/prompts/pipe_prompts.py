import textwrap

from mcp.server.fastmcp import FastMCP


class PipePrompts:
    """Declares prompts for Pipefy workflows."""

    @staticmethod
    def register(mcp: FastMCP):
        """Register prompts with the MCP server."""

        @mcp.prompt()
        def complete_task(pipe_name: str, card_title: str) -> str:
            """Mark a task as complete by moving it to the done phase."""
            return textwrap.dedent(f"""
                Find the pipe named "{pipe_name}", then search for a card matching "{card_title}".

                1. First, use search_pipes to find the pipe by name
                2. Use get_pipe to get the pipe structure and identify the final/done phase, when in doubt, prompt the user with the pipe structure and ask them to identify the final/done phase.
                3. Use get_cards to find the card that matches the title "{card_title}"
                4. Use move_card_to_phase to move the card to the final phase
                5. Confirm the card has been moved successfully
            """).strip()
