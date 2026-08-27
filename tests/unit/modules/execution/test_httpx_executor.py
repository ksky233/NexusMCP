"""HTTP GET Binding 的 Path Mapping、JSON Result 与 4xx 分类测试。"""

from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI, Request

from examples.upstream_apis.employee_directory.app import app
from examples.upstream_apis.inventory.app import (
    IDEMPOTENT_RESULTS,
    REORDER_LEVEL_REQUESTS,
    REORDER_LEVELS,
)
from examples.upstream_apis.inventory.app import (
    app as inventory_app,
)
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.credentials.domain import (
    CredentialInjectionLocation,
    CredentialValueFormat,
    ResolvedCredential,
    SecretValue,
)
from nexusmcp.modules.execution.adapters.httpx_executor import HttpxToolExecutor
from nexusmcp.modules.execution.domain import (
    ExecutionErrorCategory,
    ExecutorFailure,
    ExecutorRequest,
)
from nexusmcp.shared.errors import UnsafeUpstreamEndpointError
from tests.unit.modules.execution.test_call_tool import executable_tool

protected_app = FastAPI()


class RejectingEndpointPolicy:
    async def validate(self, endpoint: str) -> None:
        _ = endpoint
        raise UnsafeUpstreamEndpointError("test endpoint was denied")


@protected_app.get("/employees/{employee_id}")
async def protected_employee(employee_id: str, request: Request) -> dict[str, str]:
    return {
        "employee_id": employee_id,
        "authorization": request.headers.get("authorization", ""),
        "api_key": request.query_params.get("api_key", ""),
    }


@pytest.mark.asyncio
async def test_http_executor_maps_path_and_returns_json() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await HttpxToolExecutor(client).execute(
            ExecutorRequest(
                execution_id="execution-1",
                tool=executable_tool(),
                arguments={"employee_id": "emp-001"},
                timeout_seconds=1,
            ),
            credential=None,
        )

    assert result.upstream_status == 200
    assert result.content_type == "application/json"
    assert result.data["name"] == "Ada Chen"


@pytest.mark.asyncio
async def test_http_executor_normalizes_upstream_404_without_body_leak() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ExecutorFailure) as captured:
            await HttpxToolExecutor(client).execute(
                ExecutorRequest(
                    execution_id="execution-1",
                    tool=executable_tool(),
                    arguments={"employee_id": "missing"},
                    timeout_seconds=1,
                ),
                credential=None,
            )

    assert captured.value.code == "upstream_404"
    assert captured.value.category is ExecutionErrorCategory.UPSTREAM_4XX


@pytest.mark.asyncio
async def test_header_credential_overrides_untrusted_argument_mapping() -> None:
    tool = executable_tool(auth_scheme="bearer")
    tool = replace(
        tool,
        binding_config={
            **tool.binding_config,
            "parameters": [
                *tool.binding_config["parameters"],
                {
                    "argument_name": "authorization",
                    # 故意使用不同大小写，验证不会形成两个 Authorization Header。
                    "upstream_name": "authorization",
                    "location": "header",
                    "required": False,
                },
            ],
        },
    )
    credential = ResolvedCredential(
        credential_binding_id="credential-binding-1",
        injection_location=CredentialInjectionLocation.HEADER,
        injection_name="Authorization",
        value_format=CredentialValueFormat.BEARER,
        value=SecretValue("trusted-secret"),
    )
    transport = httpx.ASGITransport(app=protected_app)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await HttpxToolExecutor(client).execute(
            ExecutorRequest(
                execution_id="execution-1",
                tool=tool,
                arguments={
                    "employee_id": "emp-001",
                    "authorization": "Bearer attacker-controlled",
                },
                timeout_seconds=1,
            ),
            credential=credential,
        )

    assert result.data["authorization"] == "Bearer trusted-secret"


@pytest.mark.asyncio
async def test_query_credential_is_injected_at_last_moment() -> None:
    credential = ResolvedCredential(
        credential_binding_id="credential-binding-1",
        injection_location=CredentialInjectionLocation.QUERY,
        injection_name="api_key",
        value_format=CredentialValueFormat.RAW,
        value=SecretValue("trusted-secret"),
    )
    transport = httpx.ASGITransport(app=protected_app)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await HttpxToolExecutor(client).execute(
            ExecutorRequest(
                execution_id="execution-1",
                tool=executable_tool(auth_scheme="api_key"),
                arguments={"employee_id": "emp-001"},
                timeout_seconds=1,
            ),
            credential=credential,
        )

    assert result.data["api_key"] == "trusted-secret"


@pytest.mark.asyncio
async def test_put_executor_maps_json_body_and_trusted_idempotency_header() -> None:
    IDEMPOTENT_RESULTS.clear()
    REORDER_LEVELS.clear()
    REORDER_LEVEL_REQUESTS.clear()
    tool = replace(
        executable_tool(),
        canonical_name="inventory.set_reorder_level",
        side_effect=ToolSideEffect.IDEMPOTENT_WRITE,
        binding_config={
            "method": "PUT",
            "path_template": "/inventory/{sku}/reorder-level",
            "parameters": [
                {
                    "argument_name": "sku",
                    "upstream_name": "sku",
                    "location": "path",
                    "required": True,
                },
                {
                    "argument_name": "untrusted_key",
                    "upstream_name": "idempotency-key",
                    "location": "header",
                    "required": False,
                },
            ],
            "request_body": {
                "argument_name": "body",
                "content_type": "application/json",
                "required": True,
            },
        },
    )
    transport = httpx.ASGITransport(app=inventory_app)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await HttpxToolExecutor(client).execute(
            ExecutorRequest(
                execution_id="execution-1",
                tool=tool,
                arguments={
                    "sku": "laptop-pro-14",
                    "untrusted_key": "attacker-key",
                    "body": {"warehouse_id": "shanghai-01", "reorder_level": 12},
                },
                timeout_seconds=1,
                idempotency_key="trusted-key",
            ),
            credential=None,
        )

    assert result.data == {
        "sku": "laptop-pro-14",
        "warehouse_id": "shanghai-01",
        "reorder_level": 12,
    }
    assert REORDER_LEVEL_REQUESTS == ["trusted-key"]
    assert REORDER_LEVELS[("laptop-pro-14", "shanghai-01")] == 12


@pytest.mark.asyncio
async def test_post_write_remains_disabled_even_with_idempotency_key() -> None:
    tool = replace(
        executable_tool(),
        side_effect=ToolSideEffect.IDEMPOTENT_WRITE,
        binding_config={
            "method": "POST",
            "path_template": "/inventory/laptop-pro-14/reservations",
            "parameters": [],
            "request_body": {
                "argument_name": "body",
                "content_type": "application/json",
                "required": True,
            },
        },
    )
    transport = httpx.ASGITransport(app=inventory_app)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ExecutorFailure) as captured:
            await HttpxToolExecutor(client).execute(
                ExecutorRequest(
                    execution_id="execution-1",
                    tool=tool,
                    arguments={"body": {}},
                    timeout_seconds=1,
                    idempotency_key="trusted-key",
                ),
                credential=None,
            )

    assert captured.value.code == "write_execution_not_enabled"


@pytest.mark.asyncio
async def test_executor_rechecks_egress_before_opening_network_connection() -> None:
    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("unsafe endpoint must not reach HTTP transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        with pytest.raises(ExecutorFailure) as captured:
            await HttpxToolExecutor(
                client,
                endpoint_policy=RejectingEndpointPolicy(),
            ).execute(
                ExecutorRequest(
                    execution_id="execution-1",
                    tool=executable_tool(),
                    arguments={"employee_id": "emp-001"},
                    timeout_seconds=1,
                ),
                credential=None,
            )

    assert captured.value.code == "unsafe_upstream_endpoint"
    assert captured.value.category is ExecutionErrorCategory.AUTHORIZATION
