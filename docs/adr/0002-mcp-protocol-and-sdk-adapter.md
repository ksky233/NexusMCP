# ADR-0002｜MCP 协议时代与 SDK Adapter 层级

## 状态

Accepted

## 背景

NexusMCP 的 Tool 来自 Registry/Catalog，而不是编译期固定的 Python 函数。MCP 入口必须同时满足：

- Modern MCP `2026-07-28` 为默认主线；
- Legacy Handshake/Session Client 可兼容；
- `tools/list` 根据 RequestContext、Visibility 和 Policy 动态返回；
- `tools/call` 将任意 Tool Name 路由到协议无关 Application Use Case；
- MCP 与 FastAPI Admin/Health 入口共享一个 ASGI 部署单元；
- 不修改或依赖 SDK 私有成员。

## 决策

1. 锁定官方 Python MCP SDK `mcp==2.0.0` 作为 S1 基线。
2. Modern MCP `2026-07-28` 是默认协议；Legacy `2025-11-25` 及更早版本由同一 SDK Server 兼容。
3. NexusMCP 动态 Gateway 优先使用 SDK v2 低层 `mcp.server.lowlevel.Server`：
   - `on_list_tools` 适配 `ListVisibleTools`；
   - `on_call_tool` 适配 `CallTool`；
   - Tool Schema 由 Catalog 提供，不从 Python 函数签名生成。
4. 高层 `MCPServer` 只用于静态示例、独立 Demo MCP Server，或 Schema 与 Python 函数一一对应的场景。
5. MCP Starlette App 挂载到 FastAPI/Starlette 宿主时，由父应用 Lifespan 显式进入 `server.session_manager.run()`。
6. Protocol Adapter 只负责协议解析、Context 转换和结果/错误映射；Catalog、Policy、Credential、Execution、Audit 不依赖 MCP SDK 类型。

## 备选方案

### 高层 MCPServer + 动态增删 Tool

不作为 NexusMCP Gateway 主方案。该 API 适合装饰器和 Python Signature 驱动的静态 Tool；动态 Catalog 会把运行时状态同步到 SDK Tool Registry，并增加并发、一致性和权限隔离风险。

### 完全手写 JSON-RPC/MCP

拒绝。会重复实现版本协商、Schema 校验、Transport、Session 和标准错误，偏离项目的企业治理重点。

### 分别部署 Modern Server 与 Legacy Server

当前拒绝。SDK v2 已验证同一 Server 可同时服务两个协议时代，拆分会复制业务 Adapter 和部署配置。

## 影响

正面影响：

- Tool Catalog 可以直接提供确定性 JSON Schema；
- Modern/Legacy 复用同一 Application Use Case；
- FastAPI 可以统一承载 Admin、Health 和 MCP；
- 协议版本、Request ID、Header/Trace 可进入内部 RequestContext；
- SDK 升级可通过 Contract Test 复验。

代价与风险：

- 低层 SDK 需要显式构造 `Tool`、`ListToolsResult` 和 `CallToolResult`；
- FastAPI 挂载必须正确管理父 Lifespan 和路由顺序；
- Legacy Session 的多 Worker/Sticky Routing 仍需后续兼容测试；
- HTTP Header 只是认证输入，不能直接作为可信 Principal；
- SDK v2 初始稳定版仍可能存在待修复问题，升级前必须运行协议契约矩阵。

## 验证

S1 自动化实验：

- `tests/contract/mcp/test_dual_era.py`；
- `tests/contract/mcp/test_dynamic_gateway.py`；
- `tests/contract/mcp/test_asgi_context.py`。

已验证：

- Modern 协议为 `2026-07-28`；
- Legacy 协议为 `2025-11-25`；
- 两个协议时代发现并调用同一个 Tool，结果一致；
- 低层 Server 可按 Principal 动态生成 Tool 列表并执行可见性检查；
- FastAPI 挂载后可取得 Protocol Version、Request ID、Header 和 Trace Context；
- 所有实验未访问 SDK 私有成员。

## 复审触发条件

- SDK 高层 API 提供针对外部 Catalog 的稳定动态 Provider；
- SDK 低层公开 API发生破坏性变化；
- Conformance Suite 或目标 Client 揭示双时代路由不兼容；
- 需要拆分 Modern/Legacy 部署以满足安全、扩缩容或故障隔离要求；
- FastAPI 宿主无法满足后续 Auth/Trace Middleware 接入。
