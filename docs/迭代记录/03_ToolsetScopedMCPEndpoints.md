# I-03｜Toolset Scoped MCP Endpoints

> 状态：In Progress（I03-2 Completed）
> 日期：2026-09-06
> 触发：中央 MCP Endpoint 暴露完整 Catalog 时，单个 Agent 可能接收到与自身业务无关的大量 Tool
> 决策依据：[ADR-0020](../adr/0020-toolset-scoped-mcp-endpoints.md)
> 规划基线：`4fc1cd8`
> 当前公网镜像：`961977f1a04d`

## 0. 当前进度

```text
I03-0 领域、协议与兼容性讨论      Completed
I03-1A Domain/Port/InMemory         Completed
I03-1B PostgreSQL Schema/Adapter    Completed
I03-1C Persistence Contract Close  Completed
I03-2 Admin API 与 Web UI          Completed
I03-3 Scoped MCP Endpoint          Planned
I03-4 Scoped Search 与 Audit       Planned
I03-5 E2E、Evidence 与部署         Planned
```

本文是初步规划，不是 Accepted ADR。带“待讨论”的内容在结论冻结前不能直接进入 Migration 或公共 Contract。

## 1. 问题

当前一个 NexusMCP Deployment 暴露一个 `/mcp`：

```text
NexusMCP Catalog
→ tools/list
→ 全部可见 Published Tool + nexus.search_tools
→ Agent
```

但企业 Agent 往往只需要一组稳定的业务能力：

```text
Operations Agent → Incident、Service Health、Deployment Tool
Sales Agent      → Customer、Lead、Order Tool
Risk Agent       → Risk Score、Blacklist、Transaction Control Tool
```

还会出现跨业务自定义组合：

```text
Risk Operations Agent
→ 3 个 Risk Tool
→ 2 个 Operations Tool
```

如果所有 Agent 都连接完整 Catalog，会增加 Tool Schema 上下文、选择干扰和不必要的暴露面；全局 Search Meta
Tool 只能缓解发现问题，不能表达管理员已经确认的业务组合。

## 2. 目标

引入 Tenant-scoped `Toolset`，由管理员把 Published Tool 组合成面向 Agent 场景的逻辑 MCP Endpoint：

```text
/mcp/toolsets/operations
/mcp/toolsets/sales
/mcp/toolsets/risk-control
/mcp/toolsets/risk-operations
```

对 MCP Client 而言，每个 URL 是一个只暴露特定 Tool 集合的 MCP Server；服务端仍共享同一个 NexusMCP
进程、Catalog、Policy、Credential、Execution 和 Audit。

目标能力：

- 同一个 Tool 可以属于多个 Toolset；
- Toolset 可以按单一业务组织，也可以跨业务自定义组合；
- `tools/list` 只返回当前 Toolset 范围；
- `tools/call` 不能通过直接猜 Tool Name 绕过 Toolset；
- Toolset 小时直接暴露 Tool；Toolset 大时支持组内 Search；
- Agent Service 必须先通过 Toolset Access Policy，再执行现有 Tool Call Policy；
- 保留现有 `/mcp` 兼容路径，确定性返回当前 Agent 所有 Granted Toolset 的成员并集；
- Public Demo 能展示至少一个业务 Toolset 和一个跨业务 Toolset。

## 3. 非目标

- 不聚合或透明代理第三方 Remote MCP Server；
- 不为每个 Toolset 启动独立 Python Process/Container；
- 不建设员工 User/Role/RBAC；
- 不把 Endpoint URL 当成 Secret 或授权凭据；
- 不让普通 Toolset 通过 Namespace/Tag 动态规则自动暴露未来新增 Tool；系统 `all_published` Toolset 是唯一
  显式例外；
- 不在第一步引入组织架构、部门继承或通用 Entitlement DSL；
- 不接管、生成或维护 Agent Skill；
- 不导出 Tool Manifest 作为伪 Skill；
- 不因为 Toolset 重写现有 Tool、ToolVersion、ToolBinding 与 Publish 模型；
- 不在讨论前预先实现 Toolset Revision、灰度或多环境 Promotion。

## 4. 术语边界

| 概念 | 回答的问题 | 是否安全判定 |
|---|---|---|
| Namespace/Tag | Tool 属于什么业务、如何分类和筛选 | 否 |
| Toolset | 哪些 Tool 组合成一个 Agent-facing 发布面 | 第一层范围约束 |
| MCP Endpoint | Agent 从哪个 URL 访问 Toolset | 否，URL 不是 Credential |
| Toolset Access Policy | 当前 Agent Service 是否拥有目标 Toolset Grant | 是 |
| Tool Call Policy | 进入范围后，当前 Agent Service 是否允许执行具体 Tool | 是 |
| CredentialBinding | 允许后使用哪个 Upstream Credential | 是 |

预期集合关系：

```text
Published Tool
∩ Active Toolset Member
∩ Tool Visibility
∩ Toolset Access Policy
∩ Tool Call Policy
= 当前请求可调用 Tool
```

Toolset 负责 Least Exposure；Toolset Access Policy 防止 Agent 通过更换 URL 进入未授权范围；Tool Call Policy
继续处理具体 Tool、Side Effect 和 Approval。Agent 侧只负责“要不要调用”，不能替代 Gateway 判断“允不允许
调用”。

当前 `PolicyEvaluationInput` 只包含 `principal + tool_id + tool_version_id + side_effect`，不能直接判断
Toolset Scope。I-03 不再新增第二个 Policy Engine；保留一个 `PolicyEvaluator` 作为统一决策入口，
由 `ToolsetAccessGrant` 提供 Principal 与 Toolset 的访问事实，现有 ToolPolicy 只保留 DENY、Side Effect、
Approval 等调用级治理。

这里的 Evaluation 表示“应用规则并产生 Decision”，不是 Retrieval/Model Evaluation 实验。

## 5. 初步领域草案

### 5.1 Toolset

```text
Toolset
├── id
├── tenant_id
├── slug
├── name
├── description
├── kind
├── discovery_mode
├── status
├── revision
├── membership_digest
├── created_by
├── created_at
└── updated_at
```

初步约束：

- `tenant_id + slug` 唯一；
- Slug 进入 Agent 配置 URL，激活后不应随意修改；
- `kind = explicit | all_published`；普通 Toolset 必须是 `explicit`；
- `DRAFT | ACTIVE | DISABLED`；
- Disabled Endpoint Fail Closed；
- 每次原子 Replace Membership 时 `revision + 1` 并重新计算 `membership_digest`；
- Toolset 不拥有 Tool 生命周期。

系统可以为每个 Tenant 建立一个可选 `all_published` Toolset：

```text
slug = all-published
kind = all_published
members = all current Published Tools（动态解析，不写 ToolsetMember）
```

它仍通过普通 `ToolsetAccessGrant` 授予 Agent，不引入 Full Catalog Policy、特殊 Grant 或配置 Allowlist。系统
Toolset 不允许编辑成员、改名或删除；Admin UI 在授权时提示它会包含所有当前及未来 Published Tool。

### 5.2 ToolsetMember

```text
ToolsetMember
├── toolset_id
├── tool_id
├── added_by
└── added_at
```

首版引用逻辑 `tool_id`：运行时解析当前 Published ToolVersion，Audit 记录实际 ToolVersion。Catalog 中显式
Publish 新 ToolVersion 后，包含该 Tool 的 Toolset 自动使用新版本，不要求管理员逐个维护 Toolset。

### 5.3 Membership Revision 边界

首版不建立 `ToolsetRevision/ToolsetRevisionMember` 历史实体：

```text
Replace complete member set in one transaction
→ revision + 1
→ membership_digest changes
→ new member set becomes visible atomically
```

Revision Number 用于 Audit、Cache Invalidation 和并发更新检查，但数据库不保留旧成员快照，因此不能直接回滚
到历史 Revision。出现灰度发布、历史回滚或环境 Promotion 的真实需求后，再引入不可变 Revision Entity。

### 5.4 ToolsetAccessGrant

`ToolsetAccessGrant` 是一个简单的多对多访问事实，不是第二套 Policy：

```text
ToolsetAccessGrant
├── tenant_id
├── toolset_id
├── principal_id
├── granted_by
└── granted_at
```

约束：

- `tenant_id + toolset_id + principal_id` 唯一；
- Principal ID 来自受信 `AgentServiceAuthenticator`，不接受客户端自报；
- NexusMCP 不为此建立员工或 Agent 用户表；
- Grant 存在表示可以进入 Toolset，撤销时删除 Grant 并记录 Admin Audit；
- 一个 Agent 可以拥有多个 Grant，一个 Toolset 也可以授予多个 Agent；
- Public Demo 创建 Toolset 时可以自动授予配置中的 `public-demo-agent`。

请求时统一 Policy 流程使用该事实：

```text
PolicyEvaluator
→ Check ToolsetAccessGrant
→ Check Toolset Membership
→ Apply optional Tool DENY / Side Effect / Approval rule
→ Produce PolicyDecision
```

### 5.5 显式成员而不是动态规则

Admin UI 可以提供：

```text
按 Namespace 筛选
→ 全选候选 Tool
→ 保存明确的 Tool ID Membership
```

但不保存以下动态规则：

```text
namespace = risk 的所有当前和未来 Tool 自动加入
```

否则新增 Tool 可能未经 Toolset 管理员确认就进入 Agent 暴露面。

### 5.6 Member Availability 与 Toolset Health

Toolset 生命周期与成员运行健康分离：

```text
status = DRAFT | ACTIVE | DISABLED
→ 管理员是否希望 Toolset 对外服务

health = HEALTHY | DEGRADED | UNAVAILABLE
→ 当前成员能否解析为可执行的 Published Tool
```

写入时严格：

- Activate 和 Active Membership Replace 要求每个 Member 属于同一 Tenant；
- Tool 必须是 `ACTIVE`；
- Tool 必须存在当前 `PUBLISHED` ToolVersion；
- 任一成员不满足时拒绝 Command，不发布一个初始即降级的 Toolset。

运行时部分降级：

- Tool 后续被 Disabled 或没有当前 Published Version 时，Member 关系保留；
- `tools/list` 和 Scoped Search 隐藏该成员；
- `tools/call` 重新校验并以 `toolset_member_unavailable` 拒绝；
- 其他可用成员继续服务，Toolset `status` 不自动变为 Disabled；
- Admin Profile 显示失效成员和具体原因。

派生健康度：

```text
全部 Explicit Member 可用 → HEALTHY
部分可用                  → DEGRADED
全部不可用                → UNAVAILABLE
```

候选诊断原因首版只冻结：

```text
AVAILABLE
TOOL_DISABLED
NO_PUBLISHED_VERSION
```

Binding/Upstream Runtime Health 不在第一版扩张 Member Health；调用链仍通过现有 Resolver/Egress/Error 处理。
正常 Publish 新版本会在同一事务中 Retire 旧版本并 Publish 新版本，Toolset 引用逻辑 Tool 后自动解析新版本，
不产生预期的短暂 `NO_PUBLISHED_VERSION`。

## 6. 初步请求链

### 6.1 tools/list

```text
POST /mcp/toolsets/{slug}
→ Resolve Agent Service Principal
→ Resolve Tenant + Toolset
→ Check Toolset ACTIVE
→ Evaluate Toolset Access Policy
→ Load Members
→ Resolve Published ToolVersion
→ Apply Visibility
→ Apply Discovery Mode
→ Return standard MCP tools/list
```

### 6.2 tools/call

```text
POST /mcp/toolsets/{slug}
→ Resolve Agent Service Principal
→ Resolve Toolset
→ Evaluate Toolset Access Policy
→ Resolve Tool Name
→ Assert Tool is an ACTIVE Toolset Member
→ Evaluate Tool Call Policy
→ Resolve CredentialBinding
→ Approval / Retry / Idempotency
→ Execute Upstream
→ Persist Execution/Audit with Toolset Context
```

Membership 检查必须发生在 Credential 解析和 Upstream IO 之前。

### 6.3 Tool Search

```text
nexus.search_tools
→ Inject current toolset_id from trusted Endpoint Context
→ Lexical Candidate restricted by ToolsetMember
→ Vector Candidate restricted by ToolsetMember
→ RRF
→ Policy Filter
→ Return only Toolset members
```

Agent 不传 `toolset_id` 参数，避免通过参数搜索其他 Toolset。

### 6.4 根 `/mcp`

根 `/mcp` 作为兼容入口继续存在，但它不是 Policy Bypass：

```text
POST /mcp
→ Resolve Agent Service Principal
→ Load all Granted ACTIVE Toolsets
→ Resolve each Toolset Membership
→ Distinct union by tool_id
→ tools/list / tools/call
```

一个 Agent 可以拥有多个 ToolsetAccessGrant；根 Endpoint 对普通 Agent 返回这些 Toolset 当前成员的去重并集，
因此更换到 `/mcp` 不会扩大可见或可调用范围。需要全部 Catalog 的 Agent 也不获得特殊权限语义，只需授予
系统 `all_published` Toolset；根 Endpoint 的 Union 自然等于全部 Published Tool。未来若不再需要根入口，可以
直接删除兼容 Route，而不影响 Toolset Endpoint 与 Grant 模型。

### 6.5 Execution 与 Audit Scope

请求入口与授权依据是两个不同事实：

```text
Request Scope
→ Client 实际从 root 还是具体 Toolset Endpoint 调用

Authorization Basis
→ Grant、Membership 和 Tool Policy 为什么允许/拒绝
```

Scoped Endpoint 保存具体 Toolset：

```text
mcp_scope_type = toolset
toolset_id = <operations-id>
toolset_revision = 3
policy_reason_code = active_toolset_grant
```

根 `/mcp` 保存真实 Root Scope，不从多个匹配 Grant 中任意挑选一个 Toolset：

```text
mcp_scope_type = root
toolset_id = null
toolset_revision = null
policy_reason_code = granted_toolset_union
```

`ToolExecution` 增加结构化 Scope 字段：

```text
mcp_scope_type = root | toolset
toolset_id = nullable
toolset_revision = nullable
```

数据库约束：

```text
root
→ toolset_id IS NULL
→ toolset_revision IS NULL

toolset
→ toolset_id IS NOT NULL
→ toolset_revision IS NOT NULL
```

DENY/Not Member 可能发生在创建 ToolExecution 之前，因此 `AuditEvent.metadata` 同时保存相同的 Scalar Scope
字段。第一版不保存完整 Matched Grant 数组，也不计算 Access Basis Digest；`policy_version + reason_code` 足以
表达当前授权算法和结论，严格合规需求出现后再增加快照摘要。

## 7. Discovery Mode

两种模式互斥，不设计 Auto Algorithm，也不根据 Tool 数量自动切换：

```text
direct
→ tools/list 返回当前 Toolset 的全部业务 Tool
→ 不返回 nexus.search_tools

search_first
→ tools/list 初始只返回 nexus.search_tools
→ Search 仅在当前 Toolset 内执行
```

默认值：

```text
普通 explicit Toolset → direct
系统 all_published Toolset → search_first
```

管理员可以手动切换任意 Toolset 的 Discovery Mode。系统可以在 Profile 中显示 Tool Count 与序列化 Schema
Size，帮助管理员判断，但不会设置 `10/20` 之类阈值并自动改变 MCP Contract。新增一个 Tool 不应导致 Endpoint
突然从“全部业务 Tool”切换成“只剩 Search Tool”。

不提供“全部业务 Tool + nexus.search_tools 并列”的第三种模式：它不会减少 Schema 上下文，却会让 Meta Tool
与已经可见的业务 Tool 竞争模型注意力并增加额外调用。

### 7.1 与 Agent Skill 的边界

Skill 属于 Agent 侧业务工作流知识，告诉 Agent 在什么场景下优先使用哪个 Tool；NexusMCP 只负责服务端
Toolset、标准 MCP Schema、访问范围和执行治理，不接管 Skill 生命周期。

当前 Tool Description 的事实来源是：

```text
OpenAPI operation.description
→ fallback operation.summary
→ fallback operationId / canonical_name
→ Published ToolVersion.description
```

这些 Description 可以来自质量不稳定的上游 OpenAPI，无法自动推导“先检查风险再退款”之类企业业务流程，
因此不生成 Tool Manifest 或 Skill。Admin Web 只展示 Toolset Profile：

- Toolset Name/Description；
- Endpoint URL；
- Discovery Mode；
- Tool Count 与 Schema Size；
- 成员 Tool Name、Published Version 和 Catalog Description。

## 8. Admin Control Plane 草案

### 8.1 Admin API

候选 Operation：

```text
createToolset
listToolsets
getToolset
updateToolset
replaceToolsetMembers
replaceToolsetAccessGrants
activateToolset
disableToolset
```

Membership 使用一次批量 Replace Command，保证自定义组合在一个事务中切换，不暴露逐条 Add/Delete 造成的
中间状态。

### 8.2 Web UI

```text
工具集列表
→ 创建 Toolset
→ 按 Namespace/Tag/Catalog Search 筛选 Tool
→ 勾选明确成员
→ 选择 Discovery Mode
→ Activate
→ 复制 MCP Endpoint URL
```

详情页需要同时展示：

- 当前成员和实际 Published Version；
- Catalog Description、Tool Count 与 Schema Size；
- 派生 `HEALTHY | DEGRADED | UNAVAILABLE`；
- 每个成员的 `AVAILABLE | TOOL_DISABLED | NO_PUBLISHED_VERSION`；
- Endpoint URL；
- Discovery Mode；
- 最近调用/审计是否需要展示（待讨论）。

## 9. 协议与兼容性

MCP `2026-07-28` 没有标准 Toolset Resource；Toolset 是 NexusMCP 的服务端发布与路由能力。每个 Endpoint
仍只使用标准 `tools/list`、`tools/call`、Error 和 List Cache/Change 语义：

- <https://blog.modelcontextprotocol.io/posts/2026-07-28/>
- <https://modelcontextprotocol.io/specification/2025-11-25/schema>

协议支持边界冻结为：

```text
Modern 2026-07-28
├── /mcp
└── /mcp/toolsets/{slug}

Legacy 2025-11-25
├── /mcp                 保持现有兼容
└── /mcp/toolsets/{slug} 明确返回 unsupported_protocol
```

Modern Stateless Request 每次独立解析 Toolset Slug；不为 Legacy Handshake/Session 增加 Toolset Session Binding、
跨 URL Session 校验或动态 SSE/DELETE Path。I-03 只验证 Modern Dynamic Path 正常工作、Legacy Scoped Path
明确拒绝，以及现有 Legacy Root Contract 无回归。

最小实验已经通过，结果见：

- [I03-0｜Modern Dynamic Toolset Path 最小实验](../实验记录/38_I03-0_ModernDynamicToolsetPath.md)

### 9.1 Tool List Cache

当前 NexusMCP 的 `tools/list` 返回：

```text
cache_scope = private
ttl_ms = 0
```

这表示列表只属于当前可信身份，并且立即过期。当前没有 Redis/In-Memory Tool List Cache；Contract/Integration
Test 也使用 `cache_mode=refresh` 强制读取。因此 I-03 第一版：

- 继续使用 `ttl_ms=0`；
- 不实现 Tool List 服务端缓存；
- 不实现 List Changed/Subscription；
- 下次 `tools/list` 直接读取最新 Toolset Revision 与 Published Tool；
- `tools/call` 每次重新检查 Grant、当前 Membership 和 Policy，旧 Client List 不能形成越权。

Toolset Revision 第一版用于 Membership 并发更新、Audit 和诊断。只有未来实测 `tools/list` 成本需要非零 TTL
时，才把 Principal、Tenant、Toolset Revision 和 Published Version Fingerprint 纳入 Cache/Change 设计。

## 10. 决策清单

| 编号 | 问题 | 当前结论 | 状态 |
|---|---|---|---|
| T-001 | 成员引用 Tool 还是 ToolVersion | 引用逻辑 Tool，执行时解析 Published Version | Closed |
| T-002 | 是否首版建立 ToolsetRevision | 不建立历史实体；保留 Revision Number + Digest | Closed |
| T-003 | `/mcp` 是否继续存在 | 保留；返回 Agent 所有 Granted Toolset 的成员并集 | Closed |
| T-004 | URL/协议支持 | `/mcp/toolsets/{slug}` 只支持 Modern；Legacy 仅保留根 `/mcp` | Closed |
| T-005 | Discovery Mode 行为 | `direct | search_first` 互斥、手动切换、无 Auto Threshold | Closed |
| T-006 | Agent 是否需要显式获准访问 Toolset | 需要；统一 PolicyEvaluator 检查 Grant | Closed |
| T-007 | Audit 如何记录 Toolset/Root | Execution 保存结构化 Scope；Audit Metadata 同步；Root 不任选 Grant | Closed |
| T-008 | Toolset 变化如何通知 Client | 首版 `ttl_ms=0`，不缓存、不发 List Changed | Closed |
| T-009 | Active Toolset 能否直接改成员 | 允许批量原子 Replace，Revision + 1 | Closed |
| T-010 | Retired/Unpublished Member 行为 | 写入严格；运行时部分降级；Profile 派生 Health | Closed |
| T-011 | Toolset Access Policy 数据放在哪里 | 持久化 ToolsetAccessGrant | Closed |
| T-012 | 根 `/mcp` 的普通 Agent 语义 | 所有 Granted Active Toolset 成员的去重并集 | Closed |
| T-013 | Full Catalog Access 如何表达 | 系统 `all_published` Toolset + 普通 Grant | Closed |
| T-014 | NexusMCP 是否导出 Tool Manifest/Skill | 不导出；只展示 Toolset Profile | Closed |

## 11. I03-0 Schema/Admin API/UI 汇总

本节把已关闭的领域决策翻译成可以直接实现和验收的 Contract。ADR 只提炼长期边界；字段、Operation 和页面
动作以本节为 I-03 施工基线。

### 11.1 模块归属

新增独立业务模块：

```text
src/nexusmcp/modules/toolsets/
├── domain.py
├── ports.py
├── use_cases.py
└── adapters/
    ├── in_memory.py
    ├── sqlalchemy_models.py
    ├── sqlalchemy_mapping.py
    ├── sqlalchemy_repository.py
    └── sqlalchemy_uow.py
```

Toolset 不塞进 Catalog：

```text
Catalog
→ 拥有 Tool、ToolVersion、Publish 生命周期

Toolsets
→ 拥有组合、Grant、Endpoint Scope 和派生 Health
→ 通过 Catalog Port 解析当前 Published Tool
```

依赖方向：

```text
Admin/MCP Interface
→ Toolsets Use Case
→ Toolsets Port
→ SQLAlchemy Adapter

Toolsets Use Case
→ Catalog PublishedToolReader Port
```

Toolsets Module 不导入 Catalog SQLAlchemy Model/Repository；跨模块查询使用专用 Read Port/Adapter。

### 11.2 PostgreSQL Schema

#### toolset

```text
id                   UUID PK
tenant_id            UUID FK tenant.id RESTRICT
slug                 VARCHAR(64) NOT NULL
name                 VARCHAR(128) NOT NULL
description          TEXT NULL
kind                 VARCHAR(32) NOT NULL
discovery_mode       VARCHAR(32) NOT NULL
status               VARCHAR(16) NOT NULL
revision             INTEGER NOT NULL
membership_digest    VARCHAR(64) NOT NULL
created_by           VARCHAR(255) NOT NULL
created_at           TIMESTAMPTZ NOT NULL
updated_at           TIMESTAMPTZ NOT NULL
```

约束与 Index：

```text
UNIQUE (tenant_id, slug)
CHECK kind IN ('explicit', 'all_published')
CHECK discovery_mode IN ('direct', 'search_first')
CHECK status IN ('draft', 'active', 'disabled')
CHECK revision > 0
每个 tenant 最多一个 kind = all_published（Partial Unique Index）
```

`revision` 是 Toolset Aggregate 的 Optimistic Concurrency Token，初始为 1；Update、Replace Members、Replace
Grants、Activate/Disable 成功后递增。Command 必须携带 `expected_revision`，不匹配返回 Conflict。

`membership_digest`：

```text
explicit
→ sorted distinct tool_id 的 Canonical JSON Digest

all_published
→ 固定规则标识 all_published:v1 的 Digest
```

Catalog Publish/Disable 不修改 Toolset Revision；实际调用继续保存 ToolVersion，Profile Health 动态解析。

#### toolset_member

```text
tenant_id            UUID FK tenant.id RESTRICT
toolset_id           UUID FK toolset.id RESTRICT
tool_id              UUID FK tool.id RESTRICT
added_by             VARCHAR(255) NOT NULL
added_at             TIMESTAMPTZ NOT NULL

PRIMARY KEY (toolset_id, tool_id)
INDEX (tenant_id, tool_id)
```

Use Case 必须在 Flush 前验证 Tenant 一致；`all_published` 禁止写 Member Row。

#### toolset_access_grant

```text
tenant_id            UUID FK tenant.id RESTRICT
toolset_id           UUID FK toolset.id RESTRICT
principal_id         VARCHAR(255) NOT NULL
granted_by           VARCHAR(255) NOT NULL
granted_at           TIMESTAMPTZ NOT NULL

PRIMARY KEY (toolset_id, principal_id)
INDEX (tenant_id, principal_id)
```

Principal 是 AgentServiceAuthenticator 输出的稳定字符串，不增加本地 Principal/User 表。Replace Grants 删除
不再存在的关系、插入新关系，并写 Admin Audit。

#### tool_execution 扩展

```text
mcp_scope_type        VARCHAR(16) NOT NULL DEFAULT 'root'
toolset_id            UUID NULL FK toolset.id RESTRICT
toolset_revision      INTEGER NULL
```

Migration 将既有 Execution 回填为 Root Scope。Check Constraint：

```text
(mcp_scope_type = 'root' AND toolset_id IS NULL AND toolset_revision IS NULL)
OR
(mcp_scope_type = 'toolset' AND toolset_id IS NOT NULL AND toolset_revision > 0)
```

`audit_event` 不增加列；Tool Call Audit Metadata 使用 Scalar `mcp_scope_type/toolset_id/toolset_revision`。

### 11.3 Domain/Read Model

```text
ToolsetKind                 = EXPLICIT | ALL_PUBLISHED
ToolsetDiscoveryMode        = DIRECT | SEARCH_FIRST
ToolsetStatus               = DRAFT | ACTIVE | DISABLED
ToolsetHealth（派生）        = HEALTHY | DEGRADED | UNAVAILABLE
ToolsetMemberAvailability   = AVAILABLE | TOOL_DISABLED | NO_PUBLISHED_VERSION
```

Profile 同时返回管理事实和运行投影，不把 Health 写回 Toolset Row。

### 11.4 Admin API Contract

```text
POST /admin/toolsets                         createToolset
GET  /admin/toolsets                         listToolsets
GET  /admin/toolsets/{toolset_id}            getToolset
PUT  /admin/toolsets/{toolset_id}            updateToolset
PUT  /admin/toolsets/{toolset_id}/members    replaceToolsetMembers
PUT  /admin/toolsets/{toolset_id}/grants     replaceToolsetAccessGrants
POST /admin/toolsets/{toolset_id}/activate   activateToolset
POST /admin/toolsets/{toolset_id}/disable    disableToolset
```

不为 Member/Grant 暴露逐行 CRUD；它们属于 Toolset Aggregate，通过完整集合 Replace 原子更新。

Create Toolset：

```text
slug
name
description = optional
discovery_mode = direct（default）
```

公共 Create API 只创建 `kind=explicit`。`all_published` 由 Tenant Bootstrap 幂等创建。

Update Toolset：

```text
expected_revision
name
description
discovery_mode
```

Slug、Kind 和 CreatedBy 不可修改。

Replace Members：

```text
expected_revision
tool_ids[]
```

服务端去重并按 Tool ID 排序后计算 Digest。DRAFT 可以编辑；ACTIVE Replace 要求全部目标成员当前可用。
`all_published` 拒绝 Member Replace。

Replace Grants：

```text
expected_revision
principal_ids[]
```

服务端原子替换完整 Principal 集合。Public Demo 创建普通 Toolset 时，可由 Use Case 自动包含配置中的
`public-demo-agent`；真实 Service Identity 部署不自动授权。

Activate/Disable：

```text
expected_revision
```

Activate 要求 Explicit Toolset 至少一个成员且全部可用；系统 `all_published` 由 Bootstrap 保持 Active。

List Query：

```text
offset / limit
query
status
kind
discovery_mode
```

Detail Response 即 Toolset Profile，包含：

```text
Toolset 字段与 Revision
Endpoint URL
Health
Tool/Available/Schema Size Count
Member Availability + Published ToolVersion
Granted Principal IDs
```

第一版错误码：

```text
toolset_not_found
toolset_conflict
toolset_revision_conflict
toolset_not_active
toolset_access_denied
toolset_member_unavailable
invalid_toolset_members
system_toolset_immutable
unsupported_protocol
```

### 11.5 Web UI 信息架构

新增一级导航“工具集”，只建立两个页面：

```text
/toolsets
→ List、Filter、Create

/toolsets/{toolsetId}
→ Profile 与 Aggregate Editor
```

列表列：

```text
Name / Slug
Kind
Status / Health
Discovery Mode
Available Tool Count
Grant Count
Revision
Endpoint Copy
```

详情页分区：

```text
Profile Header
├── Name/Description
├── Status/Health/Revision
├── Endpoint URL + Copy
└── Activate/Disable

Discovery
├── direct | search_first
├── Tool Count
└── Serialized Schema Size

Members
├── Catalog Filter：Namespace/Tag/Search
├── Batch Selection
├── Published Version/Description
└── Availability Reason

Agent Service Access
├── Principal ID List
└── Atomic Replace Grants
```

系统 `all_published` Profile 不显示 Member Editor；授权时显示“包含所有当前及未来 Published Tool”的风险提示。
UI 不生成 Tool Manifest/Skill，不为 Member/Grant 建独立导航。

### 11.6 MCP Contract 对齐

```text
/mcp/toolsets/{slug}
→ Modern only
→ direct：业务 Tool only
→ search_first：nexus.search_tools only（初始）

/mcp
→ Modern + Legacy
→ 当前 Principal 所有 Granted Active Toolset 的成员并集
→ 使用既有部署级 Discovery Mode
```

Scoped Search 在 FTS/Vector Candidate Query 阶段限制 Toolset 成员；Scoped Call 在 Credential/Upstream IO 前
验证 Grant、Member Availability 和 Tool Policy。Public Demo Reset 清理普通 Toolset/Member/Grant，并重新建立
系统 `all_published` 与 `public-demo-agent` Grant。

## 12. 实施工作包

### I03-0｜领域、协议与 ADR

- 所有领域决策已关闭，完成 ADR 与 Schema/API 冻结；
- Modern Dynamic Path 正向实验与 Legacy Scoped Path 显式拒绝实验已通过；
- 冻结 Toolset、Membership、Discovery、Policy 与 Audit 边界；
- 创建 ADR。

### I03-1｜Persistence

- Alembic Migration；
- ORM/Mapping；
- Repository/UoW；
- Toolset、Member 与 AccessGrant 的 Tenant/Unique/FK/Atomic Replace Integration Test。

I03-1A 已完成，证据见：

- [I03-1A｜Toolset Domain、Port 与 InMemory Adapter](../实验记录/39_I03-1A_ToolsetDomain与Port.md)

I03-1B 已完成，证据见：

- [I03-1B｜Toolset PostgreSQL Schema 与 Adapter](../实验记录/40_I03-1B_PostgreSQLSchema与Adapter.md)

I03-1C 已完成，I03-1 Persistence 正式收口，证据见：

- [I03-1C｜Persistence Contract Close](../实验记录/41_I03-1C_PersistenceContractClose.md)

### I03-2｜Admin API 与 Web UI

- Admin Command/Query；
- OpenAPI Contract 与 Generated Client；
- Toolset List/Create/Detail/Member Selection；
- Endpoint Copy 与状态诊断。

I03-2 已完成，证据见：

- [I03-2｜Toolset Admin API 与 Web UI](../实验记录/42_I03-2_AdminAPI与WebUI.md)

### I03-3｜Scoped MCP Endpoint

- 可信 Endpoint Context；
- Scoped `tools/list`；
- Direct `tools/call` Membership Guard；
- Root `/mcp` 兼容；
- Modern Scoped Endpoint Protocol Matrix；
- Legacy Scoped Endpoint `unsupported_protocol` 与 Legacy Root Regression。

### I03-4｜Scoped Search 与 Audit

- FTS/Vector Candidate Toolset Filter；
- RRF No-Leakage；
- Toolset/Root Scope 写入 Execution 与 Audit Metadata；
- `active_toolset_grant | granted_toolset_union` Policy Reason；
- Search Eval 增加跨 Toolset Leakage Case。

### I03-5｜收口与部署

- Backend/Frontend/Playwright E2E；
- Fake Operations 与 Risk-style Custom Toolset Demo；
- Migration/Backup/Reset Demo Workspace 兼容；
- Public Demo Image、Release 与滚动替换；
- 更新架构图、README、学习笔记和作品集叙事。

## 13. 验收草案

```text
operations Endpoint
→ tools/list 不出现 Inventory/Risk Tool

risk-operations Endpoint
→ 同时出现明确选择的跨业务 Tool

直接 tools/call 非成员 Tool
→ 在 Policy/Credential/Upstream 前拒绝

Toolset Scoped Hybrid Search
→ FTS/Vector/RRF 均无跨 Toolset Leakage

同一 Tool 加入多个 Toolset
→ 各 Endpoint 使用同一 Published Tool 事实源

现有 /mcp
→ 保持当前 Modern/Legacy Contract

Modern /mcp/toolsets/{slug}
→ tools/list / tools/call 正常

Legacy /mcp/toolsets/{slug}
→ 明确 unsupported_protocol，不创建 Toolset Session

Membership Revision 变化
→ 下次 tools/list 读取新成员
→ 旧 List 中已移除 Tool 的 tools/call 仍被服务端拒绝

Scoped Endpoint Call
→ Execution/Audit 记录 toolset_id + toolset_revision

Root Endpoint Call
→ Execution/Audit 记录 root Scope，不任意归因给某个 Grant

Public Demo Reset
→ 同时清理 Toolset 状态并恢复空白 Tenant

Tool 后续 Disabled/No Published Version
→ Toolset Status 仍为 ACTIVE
→ Profile Health 变为 DEGRADED/UNAVAILABLE
→ 失效成员不进入 List/Search/Call
```

## 14. 风险与回滚

- Modern Dynamic MCP Path 已验证可行；正式 Adapter 仍需保持 Slug 来自可信 Path Context；
- Toolset 与 Policy 如果边界不清，会形成两套授权事实；
- Agent 当前 Turn 可能暂时持有旧 Tool List，但 `tools/call` 每次重新校验 Membership；
- Search 只在结果阶段过滤会产生跨 Toolset 排名污染，必须在 FTS/Vector Candidate Query 阶段限制；
- 公网数据库 Migration 必须向后兼容，旧 `/mcp` 在新 Image 健康前继续可用；
- 新 Endpoint 默认不替换根 `/mcp`，出现问题可以关闭 Toolset Route 并回滚 Image。

## 15. I03-0 完成结论

领域决策、Schema/Admin API/UI 汇总、Modern Dynamic Path 实验与 ADR-0020 已完成。I03-0 结束；下一工作包是
`I03-1｜Toolset Persistence`，在修改 Migration 前以 ADR 和本迭代文档第 11 节为实现基线。
