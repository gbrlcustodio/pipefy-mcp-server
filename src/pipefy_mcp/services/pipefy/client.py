from gql import Client, gql
from gql.transport.httpx import HTTPXAsyncTransport
from httpx_auth import OAuth2ClientCredentials

from pipefy_mcp.services.pipefy.types import CardSearch
from pipefy_mcp.settings import settings


class PipefyClient:
    """Client for encapsulating queries and mutations using the Pipefy API"""

    def __init__(self, schema: str | None = None):
        self.client = self._create_client(schema)

    async def get_pipe(self, pipe_id: int) -> dict:
        """Get a pipe by its ID."""
        query = gql(
            """
            query ($pipe_id: ID!) {
                pipe(id: $pipe_id) {
                    id
                    name
                    phases {
                        id
                        name
                    }
                    start_form_fields {
                        id
                        label
                        required
                        type
                        options
                    }
                }
            }
            """
        )

        async with self.client as session:
            variables = {"pipe_id": pipe_id}
            result = await session.execute(query, variable_values=variables)

        return result

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

        async with self.client as session:
            # Convert fields dict to array format if needed
            if isinstance(fields, dict):
                # If fields is a dict, convert to array format
                fields_array = []
                for key, value in fields.items():
                    fields_array.append({"field_id": key, "field_value": value})
                fields = fields_array
            elif not isinstance(fields, list):
                # If it's not a list, wrap it
                fields = [fields] if fields else []
            
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

        async with self.client as session:
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
                            current_phase {
                                id
                                name
                            }
                        }
                    }
                }
            }
            """
        )

        async with self.client as session:
            variables = {"pipe_id": pipe_id}
            variables["search"] = {}
            if search is not None:
                variables["search"] = search
            result = await session.execute(query, variable_values=variables)

        return result

    async def move_card_to_phase(self, card_id: int, destination_phase_id: int) -> dict:
        """Move a card to a specific phase.

        Args:
            card_id: The ID of the card to move
            destination_phase_id: The ID of the destination phase
        """
        query = gql(
            """
            mutation ($input: MoveCardToPhaseInput!) {
                moveCardToPhase (input: $input) {
                    clientMutationId
                }
            }
            """
        )

        async with self.client as session:
            variables = {"input": {"card_id": card_id, "destination_phase_id": destination_phase_id}}
            result = await session.execute(query, variable_values=variables)

        return result

    async def get_start_form_fields(self, pipe_id: int, required_only: bool = False) -> dict:
        """Get the start form fields of a pipe.

        Args:
            pipe_id: The ID of the pipe
            required_only: If True, returns only required fields. Default: False

        Returns:
            dict: A dictionary containing the list of start form fields with their properties
        """
        query = gql(
            """
            query ($pipe_id: ID!) {
                pipe(id: $pipe_id) {
                    start_form_fields {
                        id
                        label
                        type
                        required
                        editable
                        options
                        description
                        help
                    }
                }
            }
            """
        )

        async with self.client as session:
            variables = {"pipe_id": pipe_id}
            result = await session.execute(query, variable_values=variables)

        # Extract fields from result
        fields = result.get("pipe", {}).get("start_form_fields", [])

        # Handle empty start form (no fields configured at all)
        if not fields:
            return {
                "message": "This pipe has no start form fields configured.",
                "start_form_fields": []
            }

        # Filter for required fields only if requested
        if required_only:
            fields = [field for field in fields if field.get("required")]
            
            # Handle case where no required fields exist after filtering
            if not fields:
                return {
                    "message": "This pipe has no required fields in the start form.",
                    "start_form_fields": []
                }

        return {"start_form_fields": fields}

    def _create_client(self, schema: str | None):
        transport = HTTPXAsyncTransport(
            url=settings.pipefy_graphql_url,
            auth=OAuth2ClientCredentials(
                token_url=settings.pipefy_oauth_url,
                client_id=settings.pipefy_oauth_client,
                client_secret=settings.pipefy_oauth_secret,
            ),
        )

        kwargs = {"schema": schema} if schema else {"fetch_schema_from_transport": True}

        return Client(transport=transport, **kwargs)
