"""Service for advanced-automations (iPaaS) access tokens."""

from __future__ import annotations

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.queries.advanced_automations_queries import (
    GET_ADVANCED_AUTOMATIONS_TOKEN_QUERY,
)


class AdvancedAutomationsService:
    """Internal-API operations for the advanced-automations (iPaaS) feature."""

    def __init__(self, *, internal_executor: GraphQLExecutor) -> None:
        self._internal_executor = internal_executor

    async def get_token(self, pipe_id: str | int) -> str:
        """Mint a short-lived advanced-automations access token for a pipe.

        The token grants access to the pipe's iPaaS workspace. Minting it
        requires the caller to be allowed to create automations on the pipe
        and the organization to have iPaaS enabled; the API rejects the
        request otherwise.

        Args:
            pipe_id: Numeric pipe ID.
        """
        data = await self._internal_executor.execute_query(
            GET_ADVANCED_AUTOMATIONS_TOKEN_QUERY, {"repoId": str(pipe_id)}
        )
        token = (data.get("advancedAutomationsToken") or {}).get("token")
        if not token:
            msg = f"No advanced-automations token returned for pipe '{pipe_id}'."
            raise ValueError(msg)
        return token
