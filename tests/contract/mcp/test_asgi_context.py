"""验证 FastAPI 挂载和 HTTP RequestContext 契约。"""

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from examples.mcp_compatibility.asgi_app import app
from examples.mcp_compatibility.dynamic_gateway import CONTEXT_OBSERVATIONS


@pytest.mark.asyncio
async def test_fastapi_mount_exposes_mcp_and_request_context() -> None:
    # 全局列表只是测试探针；每个测试开始前清空，避免受到其他请求影响。
    CONTEXT_OBSERVATIONS.clear()

    # 测试没有启动 uvicorn，因此手动进入父 FastAPI Lifespan。
    async with app.router.lifespan_context(app):
        # 标准 httpx 直接通过 ASGITransport 测试普通 FastAPI /health，不打开真实端口。
        health_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=health_transport,
            base_url="http://testserver",
        ) as health_client:
            health_response = await health_client.get("/health")

        # MCP SDK v2 的 Streamable HTTP Client 使用 httpx2，因此 MCP 链路也使用
        # httpx2.ASGITransport，把请求送进同一个 FastAPI App。
        mcp_transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=mcp_transport,
            base_url="http://testserver",
            headers={
                # 测试身份与 Trace Header；正式项目会先认证，再构造可信 RequestContext。
                "x-nexusmcp-s1-principal": "operator",
                "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
            },
        ) as mcp_http_client:
            # 把可发送 HTTP 的 AsyncClient 包装成 SDK Transport，再交给统一 MCP Client。
            transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=mcp_http_client,
            )
            async with Client(transport) as client:
                # auto 模式会先执行 Modern server/discover，随后发送 tools/list。
                tools = await client.list_tools(cache_mode="refresh")
                protocol_version = client.protocol_version
            legacy_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=mcp_http_client,
            )
            async with Client(legacy_transport, mode="legacy") as legacy_client:
                legacy_tools = await legacy_client.list_tools(cache_mode="refresh")
                legacy_protocol_version = legacy_client.protocol_version

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert protocol_version == "2026-07-28"
    assert legacy_protocol_version == "2025-11-25"
    assert [tool.name for tool in tools.tools] == [
        "directory.get_employee",
        "ops.get_service_status",
    ]
    assert [tool.name for tool in legacy_tools.tools] == [tool.name for tool in tools.tools]

    # 从 Handler 侧探针取出 tools/list 的上下文，确认 HTTP 信息贯穿到了协议 Adapter。
    tools_list_context = next(
        observation for observation in CONTEXT_OBSERVATIONS if observation.method == "tools/list"
    )
    assert tools_list_context.protocol_version == "2026-07-28"
    assert tools_list_context.principal == "operator"
    assert tools_list_context.has_http_request is True
    assert tools_list_context.request_id != "None"
    assert tools_list_context.mcp_session_id is None
    assert (
        tools_list_context.traceparent == "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    )
    legacy_tools_list_context = next(
        observation
        for observation in CONTEXT_OBSERVATIONS
        if observation.method == "tools/list" and observation.protocol_version == "2025-11-25"
    )
    assert legacy_tools_list_context.mcp_session_id is not None
