# ADR-0020｜Toolset Scoped MCP Endpoint 与 Agent 暴露边界

> 状态：Accepted
> 日期：2026-09-06
> 迭代：I-03 Toolset Scoped MCP Endpoints
> 实验依据：[Modern Dynamic Toolset Path](../实验记录/38_I03-0_ModernDynamicToolsetPath.md)
> 详细施工契约：[I-03 迭代记录](../迭代记录/03_ToolsetScopedMCPEndpoints.md)

## Context

NexusMCP 当前通过一个根 `/mcp` Endpoint 暴露 Tenant 内全部可见 Published Tool 和内建
`nexus.search_tools`。这适合首条纵向切片，但不能表达企业 Agent 的业务能力组合：

```text
Operations Agent → Operations Tool
Sales Agent      → Sales Tool
Risk Agent       → Risk Tool
Custom Agent     → Risk 3 个 + Operations 2 个
```

让每个 Agent 接收完整 Catalog 会增加 Tool Schema 上下文、选择干扰和暴露面。Namespace/Tag 只能分类，Tool
Call Policy 只能判定具体调用，Search Meta Tool 只能运行时发现；三者都不能表达管理员已经确认的发布组合。

MCP 标准没有 Toolset Resource。NexusMCP 需要在不改变标准 `tools/list/tools/call` Contract、不为每个组合创建
Server Process 的前提下，增加平台级 Toolset 与 Path-scoped MCP Endpoint。

## Decision

### 1. 新增独立 Toolsets Module

新增 `modules/toolsets`，拥有：

```text
Toolset
ToolsetMember
ToolsetAccessGrant
Toolset Lifecycle/Health
Endpoint Scope Resolution
```

Catalog 继续拥有 Tool、ToolVersion 和 Publish 生命周期。Toolsets 只引用逻辑 Tool，并通过 Catalog Port 解析
当前 Published ToolVersion，不导入 Catalog SQLAlchemy Adapter。

### 2. Toolset 是 Agent-facing 发布组合

```text
Toolset
├── kind = explicit | all_published
├── discovery_mode = direct | search_first
├── status = draft | active | disabled
├── revision
└── membership_digest
```

普通 Toolset 使用显式 Member Row。同一个 Tool 可以进入多个 Toolset；一个 Toolset 可以跨 Namespace 组合。
Namespace/Tag 只用于 Admin 筛选，不能作为自动包含未来 Tool 的动态 Membership Rule。

每个 Tenant 最多有一个系统 `all_published` Toolset。它动态解析全部当前 Published Tool，不写 Member Row，
不允许改名、删除或编辑成员。

这里选择动态投影而不是发布时同步 Member Row：`all_published` 表达的是“始终包含当前全部 Published Tool”这条
规则，而不是某一时刻的成员快照。动态解析可避免每次 Publish/Retire 都更新系统 Toolset、减少写放大与漂移；
代价是它不能表达版本冻结或历史成员回滚，首版接受该限制。

### 3. Member 引用逻辑 Tool

`ToolsetMember` 引用 `tool_id`，不固定 `tool_version_id`：

```text
ToolsetMember → Tool → current Published ToolVersion
```

Catalog 显式 Publish 新版本后，所有包含该 Tool 的 Toolset 自动使用新版本。Execution/Audit 保存实际
`tool_version_id`，不要求管理员逐个更新 Toolset。

首版不建立不可变 `ToolsetRevision/RevisionMember` 历史实体。Toolset Aggregate 使用单调递增 `revision` 做
Optimistic Concurrency；完整 Member/Grant Replace 在一个事务中生效，`membership_digest` 表达排序去重后的
Member Set。需要历史回滚、灰度或环境 Promotion 时再引入 Revision Entity。

Admin API 选择整体 Replace，而不是 Member/Grant 逐行 CRUD：二者属于 Toolset Aggregate 内部集合，集合去重、
Digest、Revision 与 Active 状态约束必须在同一个事务中共同成立。整体 Replace 让一次请求只有一个并发版本和
一个提交结果，不会暴露短暂的半更新状态；代价是集合很大时写入量更高，但当前 Toolset 规模与修改频率足以接受。

### 4. ToolsetAccessGrant 是基础访问事实

```text
ToolsetAccessGrant
├── tenant_id
├── toolset_id
├── principal_id
├── granted_by
└── granted_at
```

Grant 表达 `Agent Service Principal → Toolset` 多对多关系。Principal ID 来自可信
`AgentServiceAuthenticator`，NexusMCP 不为此建设 Agent/User 表。

I-03 不新增第二套 Policy Engine。保留一个 PolicyEvaluator 决策边界：

```text
ToolsetAccessGrant
→ 提供基础访问范围

Tool Policy
→ 只处理 DENY、Side Effect、Approval 等调用级治理
```

Toolset Membership/Grant 不替代 `tools/call` 服务端检查；Client 即使保存旧 Tool List 或猜出 Tool Name，
也必须重新通过当前 Grant、Membership、Availability 和 Tool Policy。

### 5. 根 `/mcp` 返回 Granted Toolset Union

根 `/mcp` 保留 Modern/Legacy 兼容，但不无条件暴露完整 Catalog：

```text
Resolve Principal
→ Load all Granted ACTIVE Toolsets
→ Resolve Membership
→ distinct union by tool_id
→ tools/list / tools/call
```

需要完整 Catalog 的 Agent 通过普通 Grant 获得系统 `all_published` Toolset，不增加 Full Catalog Policy、特殊
Grant 或配置 Allowlist。授权该 Toolset 时，Admin UI 必须提示它包含所有当前及未来 Published Tool。

Public Demo Bootstrap 为 `public-demo-agent` 建立 `all_published` Grant，以保持当前公开根 Endpoint 行为。

### 6. Discovery Mode 互斥且手动切换

```text
direct
→ tools/list 只返回当前 Toolset 业务 Tool
→ 不返回 nexus.search_tools

search_first
→ tools/list 初始只返回 nexus.search_tools
→ FTS/Vector/RRF 只在当前 Toolset 内搜索
```

普通 `explicit` 默认 `direct`，系统 `all_published` 默认 `search_first`。管理员可以手动切换；不根据 Tool
数量或 Schema Size 自动改变 MCP Contract，也不提供“业务 Tool + Search Tool 并列”的第三种模式。

Tool Count/Serialized Schema Size 只作为 Toolset Profile 诊断信息。

### 7. NexusMCP 不拥有 Agent Skill

Tool Description 来自 OpenAPI `description → summary → operationId/canonical_name`，不能自动推导企业工作流。
NexusMCP 不生成 Tool Manifest 或 Skill，只在 Toolset Profile 展示 Endpoint、Mode、成员、Published Version、
Description、Tool Count 和 Schema Size。Agent Skill 由 Agent 项目维护。

### 8. 写入严格，运行时部分降级

Activate/Active Replace 时，Explicit Member 必须属于同一 Tenant、Tool ACTIVE 且存在当前 Published Version。

Toolset 激活后，如果某个 Tool 被 Disabled 或失去 Published Version：

```text
Toolset status         → 保持 ACTIVE
tools/list/Search      → 隐藏该成员
tools/call             → toolset_member_unavailable
其他成员               → 继续服务
Admin Profile health   → DEGRADED / UNAVAILABLE
```

`HEALTHY | DEGRADED | UNAVAILABLE` 是查询时派生 Health，不写回 Toolset Lifecycle Status。首版 Member
Availability 只冻结 `AVAILABLE | TOOL_DISABLED | NO_PUBLISHED_VERSION`。

### 9. Scoped Endpoint 只支持 Modern MCP

```text
Modern 2026-07-28
├── /mcp
└── /mcp/toolsets/{slug}

Legacy 2025-11-25
├── /mcp                 保持现有兼容
└── /mcp/toolsets/{slug} unsupported_protocol
```

SDK v2 实验已经证明 Dynamic Starlette Route 可以把 `{toolset_slug}` 放入
`ServerRequestContext.request.path_params`，同一 Server 可按 Slug返回不同 List/Call 结果。

不为 Legacy Scoped Endpoint 建立 Session-to-Toolset Binding、动态 SSE/DELETE Path 或跨 URL Session 校验。
Legacy 请求在进入 SDK Session Manager 前明确拒绝。

### 10. 第一版不启用 Tool List Cache

继续返回：

```text
cache_scope = private
ttl_ms = 0
```

不实现 Redis/In-Memory Tool List Cache，也不实现 List Changed/Subscription。下一次 `tools/list` 读取最新
Toolset/Catalog；`tools/call` 每次重新校验，因此旧 Client List 不能形成越权。

Toolset Revision 先服务于并发控制、Audit 和诊断。非零 TTL 出现实测需求后，再设计包含 Principal、Tenant、
Toolset Revision 和 Published Version Fingerprint 的 Cache Key/Change 机制。

### 11. Execution/Audit 记录真实请求 Scope

Scoped Endpoint：

```text
mcp_scope_type = toolset
toolset_id = required
toolset_revision = required
policy_reason_code = active_toolset_grant
```

根 `/mcp`：

```text
mcp_scope_type = root
toolset_id = null
toolset_revision = null
policy_reason_code = granted_toolset_union
```

根调用不从多个匹配 Grant 中任意选择一个 Toolset，避免虚假精确性。ToolExecution 保存结构化 Scope；Denied
Call 可能早于 Execution，因此 Audit Metadata 同步保存 Scalar Scope。第一版不保存 Matched Grant 数组或 Access
Basis Digest。

### 12. Control Plane 以 Toolset 为 Aggregate Root

持久化新增：

```text
toolset
toolset_member
toolset_access_grant
```

`tool_execution` 增加 Scope 字段；既有 Row 回填为 Root。Admin API 使用完整集合 Replace Member/Grant，不暴露
逐行 CRUD。

Web 只增加 Toolset List 与 Detail/Aggregate Editor 两个页面。系统 `all_published` 不显示 Member Editor，Grant
操作显示风险提示。详细字段、Operation、错误码与页面分区由 I-03 迭代文档维护。

## Rejected Alternatives

### 每个 Agent/Toolset 部署独立 MCP Server

拒绝。它复制 Process、配置、Catalog、Policy、Secret 与运维生命周期，不能表达中央 Gateway 的组合发布价值。

### 只使用 Namespace/Tag 动态过滤

拒绝。分类变化可能未经管理员确认自动扩大 Agent 暴露面，也不能表达跨业务自定义组合。

### ToolsetMember 固定 ToolVersion

首版拒绝。它要求每次 Tool Publish 后逐个更新所有 Toolset，增加漂移和维护成本。需要版本 Pin 时再扩展。

### 首版建立完整 ToolsetRevision 历史

暂缓。原子 Replace、Revision Number 和 Digest 已满足当前并发与 Audit 需求；没有灰度/回滚证据支撑额外表。

### 为 Full Catalog 增加特殊 Policy/Grant/Allowlist

拒绝。系统 `all_published` Toolset 与普通 ToolsetAccessGrant 已能统一表达。

### 按 Tool 数量自动切换 Search

拒绝。第 N+1 个 Tool 会让 Endpoint Contract 突然从全部业务 Tool 变成只剩 Meta Tool，破坏 Skill/Client 预期。

### direct 模式同时并列 Search Tool

拒绝。它不减少 Schema 上下文，却增加模型选择干扰和额外网络调用。

### NexusMCP 自动生成 Agent Skill

拒绝。OpenAPI Description 不是业务流程知识；Skill 生命周期属于 Agent 项目。

### Toolset Endpoint 支持 Legacy Session

拒绝。新功能是 Modern 主线，Legacy 继续通过根 Endpoint 兼容；Scoped Session Binding 的复杂度没有业务收益。

### 任一成员失效就自动禁用整个 Toolset

拒绝。一个成员的 Catalog 漂移不应扩大为整个 Agent Endpoint 故障；采用部分降级与管理端诊断。

## Consequences

### Positive

- Agent 只接收管理员确认的最小 Tool 组合；
- 业务分组和跨业务自定义组合使用同一模型；
- 根 Endpoint 有确定性的 Granted Toolset Union 语义；
- Full Catalog 不污染 Policy Domain；
- Scoped Search 在候选阶段消除跨组 Leakage；
- Toolset、Tool Policy、Credential 和 Audit 责任清晰；
- 同一部署可呈现多个逻辑 MCP Server，而不复制 Runtime；
- Modern Dynamic Path 已有 SDK 实验证据。

### Trade-offs

- 新增三张表、Admin 页面和跨 Catalog Read Port；
- Toolset Aggregate 与 Catalog Publish 存在运行时派生关系；
- Agent 当前 Turn 可能短暂保留旧 List，但 Call 会 Fail Closed；
- Legacy Client 无法使用 Scoped Endpoint；
- 根 Endpoint 行为从全 Catalog 调整为 Principal Grant Union，需要兼容 Bootstrap；
- 没有 Toolset 历史快照，首版不能一键回滚旧 Membership。

## Compatibility and Rollout

1. Migration 新增 Toolset/Member/Grant 和 nullable Scope 字段；
2. 既有 ToolExecution 回填 `mcp_scope_type=root`；
3. 每个既有 Tenant 幂等建立系统 `all_published` Toolset；
4. `static_service/public_demo` 为当前配置 Principal 建立系统 Grant，保持根 Endpoint 可用；
5. `service_identity` 在启用 Toolset Enforcement 前必须完成明确 Grant；
6. 根 `/mcp` Modern/Legacy 回归先通过，再启用 Modern Scoped Route；
7. Scoped Route 或 UI 可独立关闭并回滚 Image，不删除 Catalog/Execution 历史；
8. Public Demo Reset 同步清理 Toolset 状态并重建系统 Toolset/Grant。

## Revisit Triggers

- 需要 Membership 历史回滚、灰度发布或跨环境 Promotion；
- 需要 Pin 特定 ToolVersion；
- 非零 Tool List TTL/Cache 带来实测收益；
- Client 需要 List Changed/Subscription；
- Legacy Scoped Endpoint 出现不可替代的真实业务需求；
- Toolset Health 需要纳入 Binding/Upstream Runtime 状态；
- 三个及以上部署单元要求共享 Toolset Change Event。
