"""验证同一个 SDK v2 Server 的 MCP Modern/Legacy 契约。"""

import pytest

from examples.mcp_compatibility.dual_era import observe_client


@pytest.mark.asyncio
async def test_one_server_serves_modern_and_legacy_clients() -> None:
    # 两次连接使用同一个 Server，只改变 Client 协议模式。
    modern = await observe_client("auto", "same-business-result")
    legacy = await observe_client("legacy", "same-business-result")

    # 版本不同，但 Tool Catalog 和业务结果必须一致；协议差异不能泄漏到业务层。
    assert modern.protocol_version == "2026-07-28"
    assert legacy.protocol_version == "2025-11-25"
    assert modern.tool_names == ("echo",)
    assert legacy.tool_names == modern.tool_names
    assert modern.result_text == "same-business-result"
    assert legacy.result_text == modern.result_text
