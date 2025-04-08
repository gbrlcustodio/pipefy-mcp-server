from typing import Self

from pipefy_mcp.settings import Settings


class ServicesContainer:
    """Container for all services"""

    _instance: Self | None = None

    @classmethod
    def get_instance(cls) -> Self:
        """Get the singleton instance of the container"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the container"""
        pass

    def initialize_services(self, settings: Settings) -> None:
        pass
