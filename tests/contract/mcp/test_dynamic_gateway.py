"""Contract assertions for request-scoped Tool discovery and dispatch."""

import pytest
from mcp import Client
from mcp.types import TextContent

from examples.mcp_compatibility.dynamic_gateway import PRINCIPAL_META_KEY, server


def _meta(principal: str) -> dict[str, str]:
    """为内存 Transport 构造测试身份；正式身份不能直接信任客户端 _meta。"""

    return {PRINCIPAL_META_KEY: principal}


@pytest.mark.asyncio
async def test_tools_list_is_dynamic_for_each_principal() -> None:
    async with Client(server) as client:
        # refresh 强制发送两次 tools/list，避免 Client Cache 掩盖请求级可见性差异。
        viewer = await client.list_tools(meta=_meta("viewer"), cache_mode="refresh")
        operator = await client.list_tools(meta=_meta("operator"), cache_mode="refresh")

    assert [tool.name for tool in viewer.tools] == ["directory.get_employee"]
    assert [tool.name for tool in operator.tools] == [
        "directory.get_employee",
        "ops.get_service_status",
    ]


@pytest.mark.asyncio
async def test_tool_call_dispatches_by_binding_and_visibility() -> None:
    async with Client(server) as client:
        # 同一个 Tool 对 operator 可调用，对 viewer 不可调用。
        allowed = await client.call_tool(
            "ops.get_service_status",
            {"service_id": "svc-001"},
            meta=_meta("operator"),
        )
        denied = await client.call_tool(
            "ops.get_service_status",
            {"service_id": "svc-001"},
            meta=_meta("viewer"),
        )

    # Client 返回的是 Content Block，需要按实际类型读取文本。
    allowed_text = [block.text for block in allowed.content if isinstance(block, TextContent)]
    denied_text = [block.text for block in denied.content if isinstance(block, TextContent)]

    assert allowed.is_error is False
    assert allowed_text == ["service:svc-001:healthy"]
    assert denied.is_error is True
    assert denied_text == ["tool is not visible to this principal"]
