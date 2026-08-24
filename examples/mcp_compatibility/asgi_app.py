"""E3: mount the low-level MCP server inside a FastAPI host application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from examples.mcp_compatibility.dynamic_gateway import server

# MCP HTTP Transport 默认启用 DNS Rebinding 防护。testserver 是 ASGITransport
# 使用的虚拟 Host；生产环境必须换成真实部署域名，不能照抄此白名单。
transport_security = TransportSecuritySettings(
    allowed_hosts=["127.0.0.1", "127.0.0.1:*", "testserver", "testserver:*"],
    allowed_origins=[],
)

# 把低层 MCP Server 转为可被 FastAPI/Starlette 承载的 ASGI App。
# 未指定路径时，SDK 在子应用内部注册默认 /mcp 路由。
mcp_app = server.streamable_http_app(
    transport_security=transport_security,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """由父应用启动 MCP Session Manager，保证请求处理 Task Group 已就绪。"""

    # Mounted 子应用的 Lifespan 不会被父 FastAPI 自动执行，因此必须显式进入 run()。
    async with server.session_manager.run():
        # yield 期间 FastAPI 对外提供服务；退出上下文时 SDK 完成资源清理。
        yield


app = FastAPI(title="NexusMCP S1 ASGI Experiment", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """宿主应用自己的健康检查，不经过 MCP 协议。"""

    return {"status": "ok"}


# Mount("/") 是 Catch-all，必须最后注册，否则 /health 和未来 /admin 会被它截获。
# MCP 子应用内部仍然只在默认 /mcp 路径处理协议请求。
app.mount("/", mcp_app)
