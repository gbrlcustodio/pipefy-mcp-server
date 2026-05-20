"""Service for fetching identity of the authenticated Pipefy user."""

from __future__ import annotations

from httpx import Auth

from pipefy_sdk.base_client import BasePipefyClient
from pipefy_sdk.queries.me_queries import GET_ME_QUERY
from pipefy_sdk.services.types import MePayload
from pipefy_sdk.settings import PipefySettings


class UserService(BasePipefyClient):
    """GraphQL operations scoped to the authenticated user (`me`)."""

    def __init__(
        self,
        settings: PipefySettings,
        auth: Auth | None = None,
    ) -> None:
        super().__init__(settings=settings, auth=auth)

    async def get_me(self) -> MePayload | None:
        """Return the authenticated user's identity, or ``None`` when the schema permits.

        ``me`` is a nullable root field in Pipefy's schema (verified via introspection).
        Callers should treat ``None`` as "no human identity available for this bearer".
        """
        data = await self.execute_query(GET_ME_QUERY, {})
        me = data["me"]
        if me is None:
            return None
        return {"email": me["email"], "name": me.get("name")}
