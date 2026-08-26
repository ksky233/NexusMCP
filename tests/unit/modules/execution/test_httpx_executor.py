"""HTTP GET Binding 的 Path Mapping、JSON Result 与 4xx 分类测试。"""

from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI, Request

from examples.upstream_apis.employee_directory.app import app
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
from tests.unit.modules.execution.test_call_tool import executable_tool

protected_app = FastAPI()


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
