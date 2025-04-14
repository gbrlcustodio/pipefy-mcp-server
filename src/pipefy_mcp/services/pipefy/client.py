from gql import Client, gql
from gql.transport.httpx import HTTPXAsyncTransport
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.types import CardSearch
from pipefy_mcp.settings import settings


class PipefyClient:
    """Client for encapsulating queries and mutations using the Pipefy API"""

    def __init__(self):
        self.transport = HTTPXAsyncTransport(
            url=settings.pipefy_graphql_url,
            auth=OAuth2ClientCredentials(
                token_url=settings.pipefy_oauth_url,
                client_id=settings.pipefy_oauth_client,
                client_secret=settings.pipefy_oauth_secret,
            ),
        )

    async def create_card(self, pipe_id: int, fields: dict) -> dict:
        """Create a card in the specified pipe with the given fields."""
        query = gql(
            """
            mutation ($pipe_id: ID!, $fields: [FieldValueInput!]!) {
                createCard(input: {pipe_id: $pipe_id, fields_attributes: $fields}) {
                    card {
                        id
                    }
                }
            }
            """
        )

        async with Client(transport=self.transport, fetch_schema_from_transport=True) as session:
            variables = {"pipe_id": pipe_id, "fields": fields}
            result = await session.execute(query, variable_values=variables)

        return result

    async def get_card(self, card_id: int) -> dict:
        """Get a card by its ID."""
        query = gql(
            """
            query ($card_id: ID!) {
                card(id: $card_id) {
                    id
                    title
                }
            }
            """
        )
        async with Client(transport=self.transport, fetch_schema_from_transport=True) as session:
            variables = {"card_id": card_id}
            result = await session.execute(query, variable_values=variables)

        return result

    async def get_cards(self, pipe_id: int, search: CardSearch) -> dict:
        """Get all cards in the specified pipe.

        Args:
            pipe_id: The ID of the pipe
            search: Optional search filters with the following dictionary options:
                - assignee_ids: List of assignee IDs to filter by
                - ignore_ids: List of card IDs to ignore
                - label_ids: List of label IDs to filter by
                - title: Card title to search for
                - inbox_emails_read: Filter by whether there are unread email threads
                - include_done: Whether to include done cards
        """

        query = gql(
            """
            query ($pipe_id: ID!, $search: CardSearch) {
                cards(pipe_id: $pipe_id, search: $search) {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
            """
        )
        async with Client(transport=self.transport, fetch_schema_from_transport=True) as session:
            variables = {"pipe_id": pipe_id}
            variables["search"] = {}
            if search is not None:
                variables["search"] = search
            result = await session.execute(query, variable_values=variables)

        return result
