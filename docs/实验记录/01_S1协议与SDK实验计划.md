# S1｜协议与 SDK 实验计划

> 状态：已完成
> 日期：2026-08-24
> 目标：用三个最小实验降低协议 Adapter 风险，不实现正式业务模块。

## 1. 已锁定基线

```text
Python 3.12
uv
mcp 2.0.0
Modern MCP 2026-07-28
pytest + pytest-asyncio
```

SDK 精确版本先锁定为 PyPI 稳定版 `mcp==2.0.0`。若实验触发 SDK 缺陷，再记录 Issue、Expected Failure 和替代 commit，不静默切换版本。

## 2. 实验范围

### E1｜Modern + Legacy 最小兼容

同一个 Server 和 Tool，分别由 Modern/Legacy Client 调用：

```text
Modern → server/discover → tools/list → tools/call
Legacy → initialize       → tools/list → tools/call
```

验收：

- Modern 协议版本为 `2026-07-28`；
- Legacy 使用 Handshake Era 版本；
- 两个 Client 能看到并调用相同 Tool；
- 两个时代得到一致业务结果；
- 记录 Modern 无协议 Session、Legacy Session 的实际行为。

### E2｜动态 Tool Gateway

使用内存 Catalog 和 Fake Executor，不连接数据库或 Fake API：

```text
Request Context
→ ListVisibleTools
→ 动态 Tool Schema

CallTool
→ ToolBinding
→ Fake Executor
```

验收：

- Tool 不依赖静态 Python 函数签名生成；
- 不同请求上下文可返回不同 Tool；
- 任意 Tool Name 可路由到协议无关的 CallTool Use Case；
- 确认使用 SDK 高层 `MCPServer` 还是低层 `Server`。

### E3｜FastAPI 挂载与 RequestContext

```text
FastAPI
├── /health
└── /mcp
```

验收：

- MCP ASGI App 可以与 FastAPI Lifespan 正确组合；
- 可以读取 Protocol Version、HTTP Header、Request/Trace 信息；
- 认证结果能够转换为内部 RequestContext；
- 验证一个 Tool Not Found 或 Policy Denied 错误映射；
- 不依赖 SDK 私有成员。

## 3. 明确后置

- OpenAPI Parser 与 Fake API；
- PostgreSQL、SQLAlchemy、Alembic；
- Redis；
- 完整 Policy/Credential/Audit；
- 完整 Conformance Suite；
- 多 Worker 与 Legacy Sticky Session；
- 10 个 Java Fixture 的完整迁移。

## 4. 实验代码位置

```text
examples/mcp_compatibility/  # 最小可运行示例
tests/contract/mcp/          # 自动化协议断言
tests/fixtures/mcp/          # 后续固化的 Golden Messages
```

这些目录属于仓库实验与测试资产，不代表正式 `src/nexusmcp` 业务结构。

## 5. 退出条件

S1 满足以下条件立即结束，不继续扩展 SDK 示例：

- E1～E3 通过；
- Python/SDK 版本锁定；
- Modern/Legacy 行为有自动化断言；
- 动态 Tool 与 RequestContext 接缝得到验证；
- MCP Adapter 层级形成 ADR；
- 已知限制和后置项已记录。

## 6. 执行记录

| 实验 | 状态 | 结果 | 阻塞/限制 |
|---|---|---|---|
| E1 Modern + Legacy | 通过 | 同一 Server 分别协商 `2026-07-28`、`2025-11-25`，Tool 与结果一致 | HTTP Session Header 留在后续兼容测试 |
| E2 Dynamic Tool | 通过 | 低层 `Server` 按 Principal 动态返回 Schema，并路由任意 Tool Name | S1 的 Meta/Header 仅用于模拟身份，不是正式认证 |
| E3 FastAPI/Context | 通过 | `/health` 与 `/mcp` 共存，可读取 Version、Request ID、Header、Trace；Modern HTTP 请求无 `Mcp-Session-Id` | 父应用必须显式管理 MCP Session Manager Lifespan |

## 7. 实验结论

### 7.1 协议

- SDK v2 的同一个 Server 可以服务 Modern 和 Legacy Client；
- Modern 默认协商 `2026-07-28`；
- `mode="legacy"` 协商 `2025-11-25`；
- 两个协议时代可以复用同一个 Tool 业务实现；
- Modern HTTP 已验证不携带 `Mcp-Session-Id`；Legacy HTTP Session Header 与 Sticky Routing 后续通过兼容测试补充。

### 7.2 动态 Gateway

SDK v2 低层 `Server` 的公开构造参数直接支持：

```text
on_list_tools(ctx, params)
on_call_tool(ctx, params)
```

它允许 NexusMCP：

- 从 Catalog 返回精确、外部生成的 JSON Schema；
- 按 RequestContext 动态过滤 Tool；
- 将任意 Tool Name 路由到 Application Use Case；
- 不把数据库 Tool 动态注册成 Python 装饰器函数；
- 不访问 SDK 私有成员。

结论：正式 MCP Gateway 优先采用低层 `Server`。高层 `MCPServer` 保留给静态 Demo/独立 MCP Server。

### 7.3 FastAPI / ASGI

- SDK 生成的 Starlette App 可以与 FastAPI 共存；
- MCP App 挂载为 Catch-all 时必须最后注册，保证 `/health`、未来 `/admin` 优先匹配；
- Mounted App 的 Lifespan 不会自动运行，父 FastAPI Lifespan 必须进入 `server.session_manager.run()`；
- Low-level Handler 的 Context 提供 Protocol Version、Method、Request ID、Meta 和 HTTP Request；
- `traceparent` 与认证 Header 可以在 Adapter 层读取，但只有通过 Authenticator 验证后才能生成可信 Principal。

### 7.4 工程命令

当前项目尚未安装为正式 Python Package，测试统一使用：

```powershell
uv sync --frozen
uv run python -m pytest
uv run ruff check .
```

不设置手工 `PYTHONPATH`。

## 8. 产出文件

```text
examples/mcp_compatibility/dual_era.py
examples/mcp_compatibility/dynamic_gateway.py
examples/mcp_compatibility/asgi_app.py
tests/contract/mcp/test_dual_era.py
tests/contract/mcp/test_dynamic_gateway.py
tests/contract/mcp/test_asgi_context.py
docs/adr/0002-mcp-protocol-and-sdk-adapter.md
```

## 9. 实际问题与修正

1. 当前非 Package 模式下，直接运行 pytest Console Script 不包含仓库根目录；统一使用 `python -m pytest`，不使用手工 `PYTHONPATH`。
2. 将 MCP 子应用直接挂载到 `/mcp` 且内部路径设为 `/` 时产生尾斜杠 Redirect，SDK 收到非 MCP Content-Type。按官方推荐改为：先注册宿主路由，再把包含默认 `/mcp` 路由的 MCP App 挂载到 `/`。
3. Mounted ASGI App 不运行自身 Lifespan，必须由父应用启动 Session Manager；该行为已通过自动化测试覆盖。
