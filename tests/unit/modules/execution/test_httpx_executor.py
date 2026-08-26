"""HTTP GET Binding 的 Path Mapping、JSON Result 与 4xx 分类测试。"""

import httpx
import pytest

from examples.upstream_apis.employee_directory.app import app
from nexusmcp.modules.execution.adapters.httpx_executor import HttpxToolExecutor
from nexusmcp.modules.execution.domain import (
    ExecutionErrorCategory,
    ExecutorFailure,
    ExecutorRequest,
)
from tests.unit.modules.execution.test_call_tool import executable_tool


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
