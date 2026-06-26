"""Service for fetching identity of the authenticated Pipefy user."""

from __future__ import annotations

from pipefy_sdk.graphql_executor import GraphQLExecutor
from pipefy_sdk.queries.me_queries import GET_ME_QUERY
from pipefy_sdk.services.types import MePayload


class UserService:
    """GraphQL operations scoped to the authenticated user (`me`)."""

    def __init__(self, *, executor: GraphQLExecutor) -> None:
        self._executor = executor

    async def get_me(self) -> MePayload | None:
        """Return the authenticated user's identity, or ``None`` when the schema permits.

        ``me`` is a nullable root field in Pipefy's schema (verified via introspection).
        Callers should treat ``None`` as "no human identity available for this bearer".
        """
        data = await self._executor.execute_query(GET_ME_QUERY, {})
        me = data["me"]
        if me is None:
            return None
        return {"id": me["id"], "email": me["email"], "name": me.get("name")}
