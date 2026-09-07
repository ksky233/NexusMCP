# I03-3｜Scoped MCP Endpoint

> 状态：Completed
>
> 日期：2026-09-07
>
> 决策依据：[ADR-0020](../adr/0020-toolset-scoped-mcp-endpoints.md)

## 1. 本轮交付

I03-3 将 Control Plane 中的 Active Toolset 接入 MCP Data Plane：

```text
Agent Service
→ /mcp 或 /mcp/toolsets/{slug}
→ 可信 Path Scope + 已认证 Principal
→ Toolset Grant / Membership / Availability
→ tools/list 或 tools/call
```

同一进程、同一 SDK Server 和同一 Session Manager 同时承载根 Endpoint 与动态 Toolset Endpoint，不为每个
Toolset 建独立 Server、Process 或 Container。

## 2. 可信 Endpoint Scope

Scoped 请求的 Slug 只读取 Starlette Router 产生的 `path_params.toolset_slug`。Agent 不能通过 Header、MCP
Argument 或 `_meta` 自报 Toolset ID，因此业务参数不能扩大服务端确定的 Endpoint Scope。

```text
/mcp                         → root
/mcp/toolsets/operations     → toolset(operations)
```

Resolver 按顺序执行：

1. 在当前 Tenant 查找 Toolset；
2. 要求 Toolset 为 Active；
3. 要求当前 Agent Service Principal 拥有 Grant；
4. 解析 Explicit Member 或 `all_published` 动态投影；
5. 只保留当前 Published 且对 Principal 可见的 Tool。

## 3. tools/list

Scoped Endpoint 遵守 Toolset 自己的 Discovery Mode：

```text
direct
→ 只返回当前可用业务成员
→ 不返回 nexus.search_tools

search_first
→ 只返回 nexus.search_tools
```

根 `/mcp` 使用部署级 Discovery Mode，并把当前 Principal 所有 Granted Active Toolset 的成员按 `tool_id` 去重
合并。更换到根 URL 不会获得额外 Tool；拥有系统 `all_published` Grant 时，该 Union 自然等于完整 Published
Catalog。

List 继续返回 `cache_scope=private, ttl_ms=0`。每次请求重新读取 Toolset 与 Catalog，不引入缓存失效协议。

## 4. tools/call 防绕过

业务调用在既有 CallTool 编排之前增加 Scope Guard：

```text
Resolve Endpoint Scope
→ Check Grant
→ Check Membership / Availability
→ existing Tool Policy
→ Egress / Credential / Approval
→ Upstream Execution
```

即使 Client 跳过 `tools/list` 并猜出 Tool Name：

- 非成员返回 `toolset_access_denied`；
- 成员后来被 Disabled 或失去 Published Version，返回 `toolset_member_unavailable`；
- 两者都发生在 Credential 解析、Execution 创建和 Upstream IO 之前。

Direct Endpoint 不允许通过猜测调用未暴露的 `nexus.search_tools`。Search-first Endpoint 可调用 Meta Tool；本轮
先在结果边界按 Toolset 可用 Tool ID 再过滤，确保不返回越界 Tool。FTS/Vector Candidate 查询阶段的原生 Scope
下推与 RRF No-Leakage Eval 属于 I03-4。

## 5. Modern/Legacy 路由

自定义 Streamable HTTP Transport 让两个 Route 共用一个 `StreamableHTTPSessionManager`：

```text
Modern 2026-07-28
├── /mcp
└── /mcp/toolsets/{slug}

Legacy 2025-11-25
├── /mcp
└── /mcp/toolsets/{slug} → unsupported_protocol
```

Legacy Scoped 请求在进入 SDK Session Manager 前返回确定性 JSON-RPC Error。根 Endpoint 的 Modern/Legacy
兼容实现不变。

非 Tool Result 方法的业务异常新增 MCP Error 映射，`tools/list` 可以在 `data.errorCode` 中稳定返回
`toolset_not_found/toolset_not_active/toolset_access_denied`，同时不泄露内部诊断消息。

## 6. all_published Bootstrap

PostgreSQL Data Plane 启动时幂等建立每 Tenant 唯一的系统 `all_published` Toolset：

- `static_service`：自动追加配置中的固定 Service Principal Grant，保持既有单 Agent 部署兼容；
- `service_identity`：只建立系统 Toolset，不推测企业 Principal，必须由 Admin 明确配置 Grant；
- 多实例同时启动时依靠数据库唯一约束收敛，失败实例重新读取并合并 Grant；
- Public Demo Reset 后重新建立系统 Toolset 与 `public-demo-agent` Grant。

Bootstrap 只追加当前部署要求的 Grant，不删除管理员已经配置的其他 Principal。

## 7. 验证证据

真实 PostgreSQL + ASGI Fake Upstream + MCP SDK Client 已验证：

- Direct Scoped List 只返回一个成员 Tool；
- Search-first Scoped List 只返回 Meta Tool，检索结果不越界；
- Scoped 成员 Tool 可正常执行 Fake Upstream；
- Scoped/Root 猜测非成员均被拒绝；
- Member Disabled 后立即返回 `toolset_member_unavailable`，不创建第二条 Execution；
- Unknown Toolset List 返回稳定 `toolset_not_found`；
- Legacy Scoped 初始化返回 `unsupported_protocol`；
- Public Demo Reset 后系统 Toolset/Grant 恢复；
- 既有 Approval、Credential、Policy、Retry/Idempotency 测试已显式增加 Toolset Grant，证明两层治理同时生效。

最终门禁：

```text
Full Python Suite   350 passed / 2 paid external skipped
Ruff Lint/Format    passed
basedpyright        0 errors / 0 warnings
```

## 8. 下一步

进入 `I03-4｜Scoped Search 与 Audit`：

- 将 Toolset Scope 下推到 FTS/Vector Candidate 查询，而不是结果后过滤；
- 验证 Hybrid RRF 不产生跨 Toolset Leakage；
- 把 Root/Toolset Scope 和 Revision 写入 Execution/Audit；
- 固化 `active_toolset_grant | granted_toolset_union` 授权原因。
