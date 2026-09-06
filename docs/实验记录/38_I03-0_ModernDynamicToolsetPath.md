# I03-0｜Modern Dynamic Toolset Path 最小实验

> 状态：Completed
> 日期：2026-09-06
> 范围：只验证 MCP SDK v2 Dynamic Path、Scoped List/Call 与 Legacy 拒绝，不接数据库和正式 Toolset Domain

## 1. 问题

I-03 计划把一个 NexusMCP Deployment 暴露为多个逻辑 MCP Endpoint：

```text
/mcp/toolsets/operations
/mcp/toolsets/risk-operations
```

编码前需要确认：

1. SDK `streamable_http_app()` 是否接受 Starlette Dynamic Route；
2. Handler 能否从 `ServerRequestContext` 读取 `{toolset_slug}`；
3. 同一个 Server 是否能按 Slug 返回不同 `tools/list`；
4. `tools/call` 是否能使用同一 Slug 做 Membership Guard；
5. Legacy Scoped Request 能否在创建/使用 Session 前明确拒绝；
6. 现有根 `/mcp` Modern/Legacy Contract 是否保持。

## 2. 实验结构

代码：

- [`examples/mcp_compatibility/toolset_scoped.py`](../../examples/mcp_compatibility/toolset_scoped.py)
- [`tests/contract/mcp/test_toolset_scoped_path.py`](../../tests/contract/mcp/test_toolset_scoped_path.py)

内存数据：

```text
operations
└── operations.get_incident

risk-operations
├── operations.get_incident
└── risk.get_score
```

SDK App 直接声明：

```python
server.streamable_http_app(
    streamable_http_path="/mcp/toolsets/{toolset_slug}",
)
```

Handler 从底层 Starlette Request 读取：

```python
ctx.request.path_params["toolset_slug"]
```

外层 `ModernToolsetOnly` ASGI Boundary 检查 `MCP-Protocol-Version`，非 `2026-07-28` 请求在进入 SDK
Session/Handler 前返回 `unsupported_protocol`。

## 3. 结果

| Case | 结果 |
|---|---|
| Modern `/operations` tools/list | 只返回 `operations.get_incident` |
| Modern `/risk-operations` tools/list | 返回 Operations + Risk 两个 Tool |
| Modern Scoped tools/call | Handler 读取同一 Slug 并验证 Member |
| Modern Protocol Version | `2026-07-28` |
| Legacy Scoped Initialize | HTTP 400 + `unsupported_protocol` |
| Legacy Session Manager | 拒绝发生在 SDK Session Handling 前 |
| Root Modern/Legacy Regression | 通过 |

Dynamic Route 的 `toolset_slug` 可以稳定进入 Request Context，不需要把 Slug 放在 Tool 参数、Client `_meta` 或
不可信自定义 Header 中。

## 4. SDK Lifespan 观察

`StreamableHTTPSessionManager.run()` 对一个 Manager Instance 只能启动一次。最初把同一个 Global Experiment App
在两个测试中分别进入 Lifespan 时，第二次启动按 SDK Contract 抛出：

```text
StreamableHTTPSessionManager .run() can only be called once per instance
```

这与 Dynamic Path 无关，但再次确认正式应用必须：

- 由 Application Lifespan 统一拥有 Session Manager；
- 一个 App Instance 只启动一次；
- Test 若需要多次独立 Lifespan，应创建 App/Server Factory，或在同一 Lifespan 中完成同组 Case。

当前实验将 Modern 与 Legacy Reject Case 放在同一个 Lifespan 中，符合最小验证目的。

## 5. 验证

```text
Scoped Path Experiment + Root Protocol Regression  8 passed
basedpyright                                      0 errors / 0 warnings
Ruff Lint                                         passed
Ruff Format                                       passed
```

覆盖：

```text
test_toolset_scoped_path.py
test_asgi_context.py
test_dual_era.py
test_formal_adapter.py
test_protocol_rejections.py
```

## 6. 结论

```text
Modern /mcp/toolsets/{slug}
→ Feasible

Legacy /mcp/toolsets/{slug}
→ Explicit Reject

Legacy /mcp
→ Keep Existing Compatibility
```

正式实现可以保留根 MCP Server，并增加一个 Modern-only Scoped MCP App/Route；两个入口共享应用层 Use Case 和
数据库事实，不为每个 Toolset 创建 Server Process/Container。

本实验只证明协议/ASGI 接缝可行，不等于已经完成 Toolset Persistence、Grant、Policy、Search 或 Audit。
