"""从 Nginx `/mcp` 调用 W4 E2E 刚发布的 Tool。"""

import asyncio
import sys

from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def call(mcp_url: str) -> None:
    async with Client(streamable_http_client(mcp_url)) as client:
        result = await client.call_tool(
            "directory.get_employee",
            {"employee_id": "emp-001"},
        )
    if result.is_error:
        raise RuntimeError(f"E2E tool call failed: {result}")
    if not isinstance(result.structured_content, dict):
        raise RuntimeError("E2E tool call did not return structured content")
    if result.structured_content.get("name") != "Ada Chen":
        raise RuntimeError("E2E tool call returned an unexpected employee")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: call_published_tool.py <mcp-url>")
    asyncio.run(call(sys.argv[1]))
