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
        """Get a pipe by its ID, including phases, labels, and start form fields."""
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
                    labels {
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
                    fields_array.append(
                        {"field_id": key, "field_value": value, "generated_by_ai": True}
                    )
                fields = fields_array
            elif isinstance(fields, list):
                # If fields is already a list, ensure generated_by_ai is set
                for field in fields:
                    if isinstance(field, dict) and "generated_by_ai" not in field:
                        field["generated_by_ai"] = True
            else:
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
            variables = {
                "input": {
                    "card_id": card_id,
                    "destination_phase_id": destination_phase_id,
                }
            }
            result = await session.execute(query, variable_values=variables)

        return result

    async def update_card_field(self, card_id: int, field_id: str, new_value) -> dict:
        """Update a single field of a card.

        Args:
            card_id: The ID of the card containing the field to update
            field_id: The ID of the field to update
            new_value: The new value for the field

        Returns:
            dict: GraphQL response with success status and updated card information
        """
        mutation = gql(
            """
            mutation ($input: UpdateCardFieldInput!) {
                updateCardField(input: $input) {
                    card {
                        id
                        title
                        fields {
                            field {
                                id
                                label
                            }
                            value
                        }
                        updated_at
                    }
                    success
                    clientMutationId
                }
            }
            """
        )

        async with self.client as session:
            variables = {
                "input": {
                    "card_id": card_id,
                    "field_id": field_id,
                    "new_value": new_value,
                }
            }
            result = await session.execute(mutation, variable_values=variables)

        return result

    async def update_card(
        self,
        card_id: int,
        title: str | None = None,
        assignee_ids: list[int] | None = None,
        label_ids: list[int] | None = None,
        due_date: str | None = None,
        fields: dict | None = None,
        values: list[dict] | None = None,
    ) -> dict:
        """Update a card's fields and attributes with intelligent mutation selection.

        This method automatically chooses between replacement and incremental update modes
        based on the parameters provided.

        **Replacement Mode** (uses `updateCard` mutation):
        Use for simple updates like changing title, replacing all assignees, or updating custom fields.

        **Incremental Mode** (uses `updateFieldsValues` mutation):
        Use when you need to add/remove values from multi-value fields without replacing the entire list.

        Args:
            card_id: The ID of the card to update
            title: Optional new title for the card (replacement mode)
            assignee_ids: Optional list of user IDs to assign (replaces existing)
            label_ids: Optional list of label IDs to associate (replaces existing)
            due_date: Optional new due date (ISO 8601 format)
            fields: Optional dict of custom field updates with field_id as keys
            values: Optional list of field update objects for incremental operations:
                    - field_id (str): The field ID to update
                    - value (any): The value(s) to add/remove/replace
                    - operation (str, optional): "ADD", "REMOVE", or "REPLACE" (default)

        Returns:
            dict: GraphQL response with updated card information
        """
        # If fields dict is provided, convert to values format for updateFieldsValues
        # The updateCard mutation doesn't support custom field updates
        if fields is not None:
            fields_as_values = [
                {"field_id": k, "value": v, "operation": "REPLACE"}
                for k, v in fields.items()
            ]
            # Merge with existing values if any
            if values:
                values = values + fields_as_values
            else:
                values = fields_as_values

        # Use updateFieldsValues if we have values (including converted fields)
        if values:
            return await self._execute_update_fields_values(card_id, values)
        else:
            return await self._execute_update_card(
                card_id, title, assignee_ids, label_ids, due_date
            )

    def _should_use_incremental_mode(self, values: list[dict] | None) -> bool:
        """Check if any value has ADD or REMOVE operation."""
        if not values:
            return False
        return any(
            v.get("operation", "REPLACE").upper() in ("ADD", "REMOVE") for v in values
        )

    async def _execute_update_card(
        self,
        card_id: int,
        title: str | None,
        assignee_ids: list[int] | None,
        label_ids: list[int] | None,
        due_date: str | None,
    ) -> dict:
        """Execute updateCard mutation for card attributes (title, assignees, labels, due_date)."""
        mutation = gql(
            """
            mutation ($input: UpdateCardInput!) {
                updateCard(input: $input) {
                    card {
                        id
                        title
                        current_phase {
                            id
                            name
                        }
                        assignees {
                            id
                            name
                            email
                        }
                        labels {
                            id
                            name
                        }
                        due_date
                        updated_at
                    }
                    clientMutationId
                }
            }
            """
        )

        input_data: dict = {"id": card_id}

        if title is not None:
            input_data["title"] = title
        if assignee_ids is not None:
            input_data["assignee_ids"] = assignee_ids
        if label_ids is not None:
            input_data["label_ids"] = label_ids
        if due_date is not None:
            input_data["due_date"] = due_date

        async with self.client as session:
            variables = {"input": input_data}
            result = await session.execute(mutation, variable_values=variables)

        return result

    async def _execute_update_fields_values(
        self,
        card_id: int,
        values: list[dict],
    ) -> dict:
        """Execute updateFieldsValues mutation (incremental mode)."""
        mutation = gql(
            """
            mutation ($input: UpdateFieldsValuesInput!) {
                updateFieldsValues(input: $input) {
                    success
                    userErrors {
                        field
                        message
                    }
                    updatedNode {
                        ... on Card {
                            id
                            title
                            fields {
                                name
                                value
                                filled_at
                                updated_at
                            }
                            assignees {
                                id
                                name
                            }
                            labels {
                                id
                                name
                            }
                            updated_at
                        }
                    }
                }
            }
            """
        )

        formatted_values = self._convert_values_to_camel_case(values)

        async with self.client as session:
            variables = {"input": {"nodeId": card_id, "values": formatted_values}}
            result = await session.execute(mutation, variable_values=variables)

        return result

    def _convert_fields_to_array(self, fields: dict) -> list[dict]:
        """Convert fields dict to array format with generated_by_ai flag."""
        return [
            {"field_id": key, "field_value": value, "generated_by_ai": True}
            for key, value in fields.items()
        ]

    def _convert_values_to_camel_case(self, values: list[dict]) -> list[dict]:
        """Convert values to camelCase format for updateFieldsValues mutation."""
        return [
            {
                "fieldId": v["field_id"],
                "value": v["value"],
                "operation": v.get("operation", "REPLACE").upper(),
                "generatedByAi": True,
            }
            for v in values
        ]

    async def get_start_form_fields(
        self, pipe_id: int, required_only: bool = False
    ) -> dict:
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
                "start_form_fields": [],
            }

        # Filter for required fields only if requested
        if required_only:
            fields = [field for field in fields if field.get("required")]

            # Handle case where no required fields exist after filtering
            if not fields:
                return {
                    "message": "This pipe has no required fields in the start form.",
                    "start_form_fields": [],
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
