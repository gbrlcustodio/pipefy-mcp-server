"""Unit tests for ServiceAccountService (create, delete)."""

import pytest
from _shared.mock_clients import mock_executor

from pipefy_sdk import PipefyGraphQLError
from pipefy_sdk.queries.service_account_queries import (
    CREATE_SERVICE_ACCOUNT_MUTATION,
    DELETE_SERVICE_ACCOUNT_MUTATION,
)
from pipefy_sdk.services.service_account_service import ServiceAccountService

ORG = "341c1327-261c-4766-bb96-7953e4c3970d"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_service_account_minimal():
    payload = {
        "createServiceAccount": {
            "serviceAccount": {"id": "1", "uuid": "u", "email": "sa@x.com"}
        }
    }
    executor = mock_executor(payload)
    service = ServiceAccountService(executor=executor)
    result = await service.create_service_account(
        organization_uuid=ORG, name="sa", role="normal"
    )

    executor.execute_query.assert_awaited_once()
    query, variables = executor.execute_query.call_args[0]
    assert query is CREATE_SERVICE_ACCOUNT_MUTATION
    inp = variables["input"]
    assert inp == {"organizationUuid": ORG, "name": "sa", "role": "normal"}
    assert result == payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_service_account_with_description_and_expiration():
    executor = mock_executor({"createServiceAccount": {"serviceAccount": {}}})
    service = ServiceAccountService(executor=executor)
    await service.create_service_account(
        organization_uuid=ORG,
        name="sa",
        role="normal",
        description="ci bot",
        expiration={"unit": "days", "value": 1},
    )
    _q, variables = executor.execute_query.call_args[0]
    inp = variables["input"]
    assert inp["description"] == "ci bot"
    assert inp["expirationTime"] == {"unit": "days", "value": 1}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_service_account_transport_error():
    executor = mock_executor(side_effect=PipefyGraphQLError([{"message": "denied"}]))
    service = ServiceAccountService(executor=executor)
    with pytest.raises(PipefyGraphQLError):
        await service.create_service_account(
            organization_uuid=ORG, name="sa", role="normal"
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_service_account():
    payload = {"deleteServiceAccount": {"success": True}}
    executor = mock_executor(payload)
    service = ServiceAccountService(executor=executor)
    result = await service.delete_service_account(
        organization_uuid=ORG, service_account_uuid="sa-uuid-1"
    )

    query, variables = executor.execute_query.call_args[0]
    assert query is DELETE_SERVICE_ACCOUNT_MUTATION
    assert variables["input"] == {
        "organizationUuid": ORG,
        "serviceAccountUuid": "sa-uuid-1",
    }
    assert result == payload
