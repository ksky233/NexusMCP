"""Operations/Inventory Fake API 与 OpenAPI 通用解析 Contract。"""

from pathlib import Path

import httpx
import pytest

from examples.upstream_apis.inventory.app import app as inventory_app
from examples.upstream_apis.operations.app import app as operations_app
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.domain import OperationConflictStatus
from nexusmcp.modules.openapi_import.parser import OpenApiParser

UPSTREAM_ROOT = Path(__file__).resolve().parents[3] / "examples" / "upstream_apis"


@pytest.mark.asyncio
async def test_operations_api_supports_status_and_idempotent_acknowledge() -> None:
    transport = httpx.ASGITransport(app=operations_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://operations.test") as client:
        incident = await client.get("/incidents/inc-001")
        acknowledged = await client.post(
            "/incidents/inc-001/acknowledge",
            headers={"X-Operator-Id": "operator-1"},
            json={"note": "Investigating"},
        )

    assert incident.status_code == 200
    assert incident.json()["status"] == "investigating"
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_inventory_api_supports_query_idempotent_update_and_reservation() -> None:
    transport = httpx.ASGITransport(app=inventory_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inventory.test") as client:
        stock = await client.get(
            "/inventory/laptop-pro-14",
            params={"warehouse_id": "shanghai-01"},
        )
        reservation = await client.post(
            "/inventory/laptop-pro-14/reservations",
            json={"warehouse_id": "shanghai-01", "order_id": "order-1", "quantity": 2},
        )
        reorder = await client.put(
            "/inventory/laptop-pro-14/reorder-level",
            headers={"Idempotency-Key": "fixture-key-1"},
            json={"warehouse_id": "shanghai-01", "reorder_level": 12},
        )
        reorder_replay = await client.put(
            "/inventory/laptop-pro-14/reorder-level",
            headers={"Idempotency-Key": "fixture-key-1"},
            json={"warehouse_id": "shanghai-01", "reorder_level": 12},
        )

    assert stock.status_code == 200
    assert stock.json()["available"] == 80
    assert reservation.status_code == 200
    assert reservation.json()["status"] == "created"
    assert reorder.status_code == 200
    assert reorder_replay.json() == reorder.json()


@pytest.mark.asyncio
async def test_same_operation_id_is_isolated_by_upstream_namespace() -> None:
    reader = LocalOpenApiDocumentReader(UPSTREAM_ROOT)
    operations_document = await reader.read("operations/openapi.json")
    inventory_document = await reader.read("inventory/openapi.json")

    operations = OpenApiParser().parse(operations_document.content, namespace="ops")
    inventory = OpenApiParser().parse(inventory_document.content, namespace="inventory")

    assert [operation.generated_tool_name for operation in operations.operations] == [
        "ops.get_status",
        "ops.acknowledge_incident",
    ]
    assert [operation.generated_tool_name for operation in inventory.operations] == [
        "inventory.get_status",
        "inventory.set_reorder_level",
        "inventory.reserve_stock",
    ]
    assert operations.operations[0].operation_id == "getStatus"
    assert inventory.operations[0].operation_id == "getStatus"
    assert all(
        operation.conflict_status is OperationConflictStatus.NONE
        for operation in (*operations.operations, *inventory.operations)
    )

    operations_by_id = {
        operation.operation_id: operation.normalized_operation
        for operation in operations.operations
    }
    inventory_by_id = {
        operation.operation_id: operation.normalized_operation for operation in inventory.operations
    }
    acknowledge = operations_by_id["acknowledgeIncident"]
    reserve = inventory_by_id["reserveStock"]
    reorder = inventory_by_id["setReorderLevel"]
    assert acknowledge["side_effect"] == "idempotent_write"
    assert acknowledge["tool_input_schema"]["required"] == [
        "incident_id",
        "x_operator_id",
        "body",
    ]
    assert reserve["side_effect"] == "non_idempotent_write"
    assert reorder["side_effect"] == "idempotent_write"
    assert reorder["method"] == "PUT"
    assert reorder["tool_input_schema"]["required"] == ["sku", "body"]
    assert reserve["tool_input_schema"]["properties"]["body"]["required"] == [
        "warehouse_id",
        "order_id",
        "quantity",
    ]
