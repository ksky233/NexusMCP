"""Employee Directory Fake API 与静态 OpenAPI Fixture Contract。"""

from pathlib import Path

import httpx
import pytest

from examples.upstream_apis.employee_directory.app import app
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.domain import OperationConflictStatus
from nexusmcp.modules.openapi_import.parser import OpenApiParser

UPSTREAM_ROOT = Path(__file__).resolve().parents[3] / "examples" / "upstream_apis"
SOURCE_REF = "employee_directory/openapi.json"


@pytest.mark.asyncio
async def test_fake_api_serves_path_query_header_and_nested_body() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://employee.test") as client:
        employee = await client.get("/employees/emp-001")
        filtered = await client.get("/employees", params={"department": "engineering"})
        searched = await client.post(
            "/employees/search",
            headers={"X-Directory-Region": "cn"},
            json={
                "filter": {"department": "engineering", "statuses": ["active"]},
                "limit": 1,
            },
        )

    assert employee.status_code == 200
    assert employee.json()["employee_id"] == "emp-001"
    assert [item["employee_id"] for item in filtered.json()] == ["emp-001", "emp-003"]
    assert [item["employee_id"] for item in searched.json()] == ["emp-001"]


@pytest.mark.asyncio
async def test_static_fixture_normalizes_three_operations_and_local_refs() -> None:
    document = await LocalOpenApiDocumentReader(UPSTREAM_ROOT).read(SOURCE_REF)

    parsed = OpenApiParser().parse(document.content, namespace="directory")

    assert parsed.openapi_version == "3.1.0"
    assert [operation.generated_tool_name for operation in parsed.operations] == [
        "directory.list_employees",
        "directory.search_employees",
        "directory.get_employee",
    ]
    assert all(
        operation.conflict_status is OperationConflictStatus.NONE for operation in parsed.operations
    )

    by_id = {operation.operation_id: operation for operation in parsed.operations}
    get_input = by_id["getEmployee"].normalized_operation["tool_input_schema"]
    assert get_input["required"] == ["employee_id"]
    list_input = by_id["listEmployees"].normalized_operation["tool_input_schema"]
    assert list_input["properties"]["status"]["enum"] == [
        "active",
        "leave",
        "terminated",
    ]
    search = by_id["searchEmployees"].normalized_operation
    assert search["parameters"][0]["argument_name"] == "x_directory_region"
    assert search["tool_input_schema"]["required"] == ["body"]
    assert search["tool_input_schema"]["properties"]["body"]["required"] == ["filter"]
    assert search["side_effect"] == "read_only"
    assert "$ref" not in str(search)
