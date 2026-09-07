# I03-4｜Scoped Search 与 Audit

> 状态：Completed
>
> 日期：2026-09-07
>
> 决策依据：[ADR-0020](../adr/0020-toolset-scoped-mcp-endpoints.md)

## 1. 本轮交付

I03-4 关闭两个 Data Plane 边界：

```text
Scoped Search
→ Toolset 成员范围进入 FTS/Vector Candidate Query
→ RRF 只能看到范围内候选

Scoped Call
→ Execution 保存真实 Root/Toolset Scope
→ Audit 同步保存 Scope 与独立授权理由
```

本轮复用既有 `tool_execution` Scope 列和 `audit_event.metadata`，没有新增 Migration。

## 2. Search Scope 下推

`SearchToolsQuery` 与 `SearchPublishedToolsQuery` 新增服务端注入的 `eligible_tool_ids`。该字段不进入 Meta Tool
JSON Schema，Agent 无法指定或扩大它；MCP Handler 只使用 `ResolvedToolsetAccess.available_tool_ids` 生成。

范围同时进入：

- InMemory/SQLAlchemy Lexical Search；
- PostgreSQL FTS 的 `ToolModel.id IN (...)`；
- Vector Search 的 Eligible Coverage Query；
- pgvector Exact Candidate Query；
- Lexical/Vector 并行完成后的 RRF。

因此过滤发生在排序和 `LIMIT` 前，不会出现组外高分 Tool 占用 Top-K、再被结果后过滤导致组内 Tool 召回不足。
最终结果仍保留一次 ID Filter 作为 Defense in Depth。

空 Scope 直接返回空结果；Hybrid 不调用在线 Embedding Provider，避免无授权 Agent 产生付费请求。

## 3. Execution Scope

MCP Handler 将可信 Endpoint Scope 注入 `CallToolCommand`，再由 CallTool 传到 `PlanExecutionCommand`：

```text
Scoped
→ mcp_scope_type = toolset
→ toolset_id = 当前解析出的稳定 ID
→ toolset_revision = 本次授权时 Revision

Root
→ mcp_scope_type = root
→ toolset_id = null
→ toolset_revision = null
```

这些字段随 ToolExecution 写入现有 PostgreSQL 列，成功、失败、取消和未知结果不会丢失最初请求入口。

## 4. Audit Scope 与 Reason 分工

没有覆盖既有 `policy_reason_code`：

```text
policy_reason_code
→ Tool Policy 判定理由
→ 例如 read_only_allowed / sales_agent_allowed

AuditEvent.metadata.scope_reason_code
→ Toolset 访问理由
→ Scoped: active_toolset_grant
→ Root: granted_toolset_union
```

Execution 派生的 Allowed/Succeeded/Failed Audit 均写入：

```text
mcp_scope_type
scope_reason_code
toolset_id        # Scoped only
toolset_revision  # Scoped only
```

## 5. Pre-Execution Denial

以下拒绝发生在 ToolExecution 创建前，但现在会持久化独立 Denied Audit：

- Toolset 不存在或未启用；
- Principal 没有 Grant；
- 猜测调用非成员 Tool；
- Member 已 Disabled 或失去 Published Version；
- Direct Endpoint 猜测调用 `nexus.search_tools`。

Denied Event 使用 `resource_type=tool_name`，保存 Arguments Digest、Endpoint Scope、Toolset Slug/ID/Revision（当时
可解析的字段）和稳定错误码。它不保存原始 Arguments、Result、Authorization、Token 或 Credential。

`tools/list` 与正常 Meta Search 继续只产生结构化 Log/Trace，不写高噪声持久化 Audit。

## 6. 验证证据

- PostgreSQL FTS 在 `LIMIT` 前只保留指定 Tool ID；
- Exact Vector Search 的 Eligible/Indexed Count 同样受 Toolset Scope 限制；
- Scoped Hybrid 的组外最相似向量无法进入 RRF，最终只返回成员 Tool；
- Empty Scope 不调用 Fake Embedding Provider；
- Scoped 成功调用的 ToolExecution 保存 Toolset ID/Revision；
- Root 成功调用保存 Root Scope，不选择某个 Grant；
- `policy_reason_code=read_only_allowed` 保持不变，Scope Reason 独立存在；
- 四种提前拒绝只产生 Denied Audit，不增加 Execution，Fake Upstream 只收到一次真正允许的请求；
- Audit Metadata 不包含原始 Arguments 或 Secret。

最终门禁：

```text
Full Python Suite   353 passed / 2 paid external skipped
Ruff Lint/Format    passed
basedpyright        0 errors / 0 warnings
```

## 7. 下一步

进入 `I03-5｜E2E、Evidence 与部署`：更新 Public Demo Seed/Reset、Web/Playwright 场景、架构与作品集证据，构建并
滚动替换公网镜像。
