"""E1：验证同一个 SDK v2 Server 可以服务 Modern 与 Legacy Client。"""

from dataclasses import dataclass
from typing import Literal

from mcp import Client
from mcp.server import MCPServer
from mcp.types import TextContent

# SDK Client 的 mode：
# - auto：优先探测 Modern server/discover，不支持时再回退到 Legacy initialize。
# - legacy：跳过 Modern 探测，直接走旧版 Handshake。
ConnectMode = Literal["auto", "legacy"]

# MCPServer 是 SDK 的高层 API。它会根据 Python 函数签名自动生成 Tool Schema，
# 适合验证协议和编写静态 MCP Server，但不是 NexusMCP 动态 Catalog 的最终方案。
server = MCPServer(
    name="nexusmcp-s1-dual-era",
    description="Minimal dual-era compatibility server for NexusMCP S1.",
    version="0.1.0",
)


@server.tool()
async def echo(message: str) -> str:
    """原样返回输入，用最小业务逻辑隔离协议差异。"""
    return message


@dataclass(frozen=True)
class CompatibilityObservation:
    """把 Client 连接后的关键事实收集起来，供测试做确定性断言。"""

    requested_mode: ConnectMode
    protocol_version: str
    tool_names: tuple[str, ...]
    result_text: str


async def observe_client(mode: ConnectMode, message: str) -> CompatibilityObservation:
    """用内存 Transport 连接同一个 Server，并观察指定协议时代的行为。"""

    # Client(server) 不打开端口，但仍会走 SDK 的真实协议协商、tools/list 和 tools/call。
    async with Client(server, mode=mode) as client:
        # SDK 将 list_tools() 编码为 MCP tools/list，并返回强类型 ListToolsResult。
        tools_result = await client.list_tools()
        # 参数会按 @server.tool() 从函数签名生成的 JSON Schema 进行校验。
        call_result = await client.call_tool("echo", {"message": message})

        # MCP Result.content 是多态 Content Block 列表，不能假定它本身就是字符串。
        # 本实验的 echo 只返回文本，因此只提取 TextContent。
        text_blocks = [
            block.text for block in call_result.content if isinstance(block, TextContent)
        ]
        if not text_blocks:
            raise AssertionError("echo returned no text content")

        return CompatibilityObservation(
            requested_mode=mode,
            protocol_version=client.protocol_version,
            tool_names=tuple(tool.name for tool in tools_result.tools),
            result_text=text_blocks[0],
        )
