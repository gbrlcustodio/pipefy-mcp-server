import logging

from pipefy_mcp.server import run_server

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the pipefy-mcp-server script defined in pyproject.toml"""

    logger.info("Starting Pipefy MCP server")

    run_server()


if __name__ == "__main__":
    main()
