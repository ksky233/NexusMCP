# I-01｜Service-Centric Identity 代码收敛

> 状态：Planned
> 日期：2026-08-30
> 触发：项目从通用 User/Role Identity 预留收敛为面向 Admin Operator 与 Agent Service 的 MCP Gateway
> 决策依据：[ADR-0019｜面向管理员与 Agent Service 的身份边界](../adr/0019-service-centric-identity-boundary.md)
> 基线提交：`334a02d`

## 1. 迭代目标

删除没有真实产品场景支撑的员工身份和 Role 预留，让代码与已经冻结的产品边界一致：

```text
Admin Operator
→ /admin

Agent Service Principal
→ /mcp

Employee / Agent Session User
→ 留在 Agent 服务或业务系统
```

本轮以减少概念和分支为主，不用新的抽象替换旧抽象，也不为了“未来可能需要”保留未被当前场景消费的字段。

完成后应能更直接地解释：

> NexusMCP 认证和治理 Agent Service，不管理员工账号、员工 Role、Agent 会话用户或最终用户行为。

## 2. 非目标

本轮不实现：

- Production Admin OIDC/SSO；
- Production mTLS、OAuth2 Client Credentials 或 Trusted Proxy Adapter；
- 员工注册登录、User ↔ Role ↔ Permission；
- `end_user_reference`；
- 员工个人 Credential 或 On-Behalf-Of Token；
- 多租户 SaaS Provisioning；
- Policy DSL、动态 Policy Builder；
- CredentialBinding PostgreSQL 持久化；
- 修改 MCP 协议字段或 OpenAPI Tool Contract。

生产 Adapter 属于后续迭代。本轮只把领域内核和当前开发 Adapter 收敛到正确方向，并保留清晰 Port。

## 3. 当前实现盘点

### 3.1 Identity Domain

当前 `PrincipalType`：

```text
USER
SERVICE
AGENT
ANONYMOUS
```

问题：

- `USER` 没有 NexusMCP 产品 Actor；
- `SERVICE` 与 `AGENT` 在当前调用链没有不同业务行为；
- 大部分测试使用 `USER` 只是早期示例，不代表真实需求；
- 类型差异只进入 Telemetry Label，没有形成必须保留的领域规则。

当前 `InternalPrincipal` 还包含：

```text
roles
attributes
```

其中：

- `roles` 只被 Policy/Credential 的 Role Scope 消费；
- `attributes` 只在 Context 与 Principal 之间复制，未参与任何正式 Policy；
- 两者都没有持久化事实源，也没有 Admin 管理用例。

### 3.2 Request Context

当前 `ActorContext` 包含：

```text
principal_type
roles
principal_attributes
```

`RequestContext` 额外预留：

```text
agent_id
run_id
```

`agent_id/run_id` 没有被 Tool Resolution、Policy、Credential、Approval、Execution 或 Audit 使用。Trace ID
已经承担一次跨系统调用的关联职责。

### 3.3 Policy

当前 Subject：

```text
PRINCIPAL
ROLE
TENANT
```

特异性：

```text
Principal > Role > Tenant
```

Role Policy 的测试覆盖充分，但没有真实 Agent Service Group、Role 配置入口或持久化模型。对于当前少量 Agent
Service，Principal/Tenant 两级足够。

### 3.4 CredentialBinding

当前 Subject 同样支持：

```text
PRINCIPAL
ROLE
TENANT
```

Role Binding 没有实际配置来源。目标特异性只需要：

```text
Agent Service Principal + Tool
Agent Service Principal + Upstream
Tenant + Tool
Tenant + Upstream
```

### 3.5 Authentication Adapter

`StaticBearerPrincipalAuthenticator` 当前已经可以把不同 Bearer Token 映射为不同 Principal，并且只保存 Token
Digest。它是有价值的确定性测试 Adapter，但文档仍把未来方向描述为员工 JWT/OIDC。

目标应将它解释为开发/测试用的 Service Credential Adapter。是否在本轮重命名，由影响面检查后决定，不能
只改类名却不改善领域含义。

### 3.6 Persistence

当前没有持久化 Principal、Role、ToolPolicy 或 CredentialBinding 表。已持久化的 Approval、Execution 和
Audit 只保存字符串：

```text
principal_id / actor_id
```

这些字段可以继续保存 Agent Service Principal ID，无需改列名或迁移历史数据。

结论：本轮预计不需要 Alembic Migration。

## 4. 目标模型

### 4.1 MCP Principal

建议目标：

```text
AgentServicePrincipal
├── id
├── tenant_id
└── authn_method
```

Anonymous 只用于缺少 Credential 时的协议拒绝或显式开放的开发场景。

是否直接把 `InternalPrincipal` 重命名为 `AgentServicePrincipal`，需要比较：

- 命名清晰度收益；
- Port、Test、Telemetry 的机械修改量；
- Admin ActorContext 是否共享该类型。

推荐第一步先收窄字段与枚举，再决定是否重命名，避免一次提交同时改变语义和大量标识符。

### 4.2 Admin Actor

Admin 不复用 MCP Service Authentication：

```text
Local Admin
→ 固定 ActorContext

Future Production Admin
→ 独立 AdminAuthenticator
```

本轮保持 Local Admin 行为不变，不加入登录或 Session。

### 4.3 Policy Subject

目标：

```text
AGENT_SERVICE
TENANT
```

如果保留通用名称，则至少应明确：

```text
PRINCIPAL = Agent Service Principal
```

删除 `ROLE` 后，规则顺序变为：

```text
Agent Service Principal > Tenant
Exact Tool > Upstream/Tenant Wildcard
Priority
DENY Tie-Break
```

### 4.4 Credential Subject

目标：

```text
AGENT_SERVICE
TENANT
```

同级多个 Binding 继续 Fail Closed；SecretReference、Provider 和 Injection 安全边界不变。

### 4.5 Request Context

建议保留：

```text
request_id
trace_id
tenant_id
principal_id
authn_method
principal_type（如 Telemetry 仍需要）
protocol_version
protocol_era
policy_snapshot（实际需要前再评估）
```

建议删除：

```text
roles
principal_attributes
agent_id
run_id
```

## 5. 身份模式接缝

本轮需要让代码结构允许后续出现两种 MCP 模式，但不实现生产 Credential：

### 5.1 static_service

```text
一个 NexusMCP 部署
→ 一个固定 Tenant
→ 一个固定 Agent Service Principal
```

适合单 Agent 独立部署。安全边界依赖私有网络、Ingress/mTLS/API Gateway 等外部部署控制，NexusMCP 不应把
“固定 Principal”描述为已经完成生产认证。

### 5.2 service_identity

```text
Service Credential
→ AgentServiceAuthenticator Port
→ Agent Service Principal
```

适合多个 Agent 共用部署。生产 Adapter 可以是 mTLS、Client Credentials 或 Trusted Proxy；本轮保留 Port 与
确定性 Test Adapter，不选供应商。

### 5.3 Admin Auth

Admin 身份模式独立：

```text
local
trusted_proxy（Future）
oidc（Future）
```

不能使用一个全局 `IDENTITY_MODE` 同时控制 `/admin` 与 `/mcp`。

## 6. 预计删除与保留

### 删除候选

- `PrincipalType.USER`；
- `PrincipalType.AGENT` 与 `SERVICE` 的重复语义；
- `InternalPrincipal.roles`；
- `InternalPrincipal.attributes`；
- `ActorContext.roles`；
- `ActorContext.principal_attributes`；
- `RequestContext.agent_id`；
- `RequestContext.run_id`；
- `PolicySubjectType.ROLE`；
- `CredentialSubjectType.ROLE`；
- Role 特异性分支和对应 Golden Cases。

### 必须保留

- Tenant Boundary；
- 稳定 Agent Service Principal ID；
- `authn_method`；
- Anonymous Fail-Closed；
- PrincipalAuthenticator/Resolver Port；
- Principal/Tenant Policy；
- Principal/Tenant CredentialBinding；
- Approval 对 Principal 的快照绑定；
- Execution `principal_id`；
- Audit `actor_id`；
- Request ID、Trace ID；
- Credential 与 Inbound Identity 分离。

## 7. 影响面

| 模块 | 预计调整 |
|---|---|
| `identity` | 收窄 PrincipalType，删除 roles/attributes，调整 Adapter 命名和默认值 |
| `shared.request_context` | 删除未消费身份字段与 agent/run 预留 |
| `interfaces.mcp` | 只复制 Agent Service Principal 必要字段 |
| `interfaces.admin` | 保持固定 Local Admin；删除无意义的 Role/Attribute 透传 |
| `policy` | 删除 Role Subject 与特异性分支 |
| `credentials` | 删除 Role Subject 与特异性分支 |
| `approval` | 字段不变，语义明确为 Agent Service Principal |
| `execution/audit` | 字段与表结构不变，更新命名说明和测试数据 |
| `telemetry` | Principal Type Label 收敛，更新证据快照 |
| `bootstrap/config` | 评估 `MCP_AUTH_MODE` 与固定 Service Principal 设置，不与 Admin 配置混用 |
| `evals/security` | 将 User/Role Case 改为多个 Agent Service/Tenant Case |
| `docs` | 代码完成后回填最终字段、Commit 和验证结果 |

## 8. 数据与兼容性

### 8.1 数据库

预计无需 Migration：

- `tenant` 不变；
- Approval/Execution/Audit 的 `principal_id/actor_id` 类型仍为字符串；
- Policy/CredentialBinding 尚未持久化；
- 不存在员工 User/Role 历史数据。

实施前必须通过 Alembic Schema Diff 或 Migration Test 再确认，不能只凭文档判断。

### 8.2 Admin API

Admin Query 中的 `principal_id` Filter 保持字段名不变，但语义改为 Agent Service Principal。Local Admin
Decision 的 `decided_by` 继续记录 Admin Actor。

### 8.3 MCP Contract

`tools/list`、`nexus.search_tools`、`tools/call` 和业务 Tool Schema 不应变化。身份变化属于 Transport/Auth
Boundary，不进入 Tool Arguments。

### 8.4 Evidence

Security Golden Case 的名称、Manifest 和报告会变化。应保留“不同受信调用者产生不同 ALLOW/DENY”的证据，
但调用者改为不同 Agent Service，而不是员工用户/Role。

## 9. 实施工作包

### I01-0｜冻结代码级决策

- 确认最终 Principal Type 命名；
- 确认是否本轮引入 `MCP_AUTH_MODE`；
- 确认 `StaticBearerPrincipalAuthenticator` 重命名策略；
- 记录删除字段的引用清单；
- 冻结无数据库 Migration 结论。

### I01-1｜Identity 与 Context 收敛

- 收窄 `PrincipalType`；
- 删除 roles/attributes；
- 删除 agent_id/run_id；
- 更新 MCP Context Resolver；
- 保持 Local Admin E2E。

### I01-2｜Policy 与 Credential 收敛

- 删除 Role Subject；
- 保留 Agent Service/Tenant 特异性；
- 更新冲突和 Default DENY 测试；
- 更新 Approval/Credential E2E 调用主体。

### I01-3｜Auth Adapter 与配置接缝

- 把 Static Bearer 明确为 Agent Service Test Adapter；
- 如本轮实现 `static_service`，增加受控固定 Principal Resolver/Authenticator；
- 保持 Admin Auth 与 MCP Auth 配置独立；
- 不实现生产 mTLS/OIDC/Trusted Proxy。

### I01-4｜Evidence 与文档回填

- 更新 Security Golden Matrix；
- 更新 Threat Model/Evidence Manifest；
- 更新 Telemetry Principal Type；
- 全局搜索并清理员工 IAM 代码叙事；
- 回填本记录的完成结果。

## 10. 验证矩阵

### Domain/Unit

- Agent Service Principal 必须有非空 ID/Tenant/Auth Method；
- Anonymous 不能获得受信权限；
- Agent Service Exact Policy 优先于 Tenant Policy；
- 同优先级 DENY 仍优先；
- Agent Service CredentialBinding 优先于 Tenant Binding；
- 同级 Binding 冲突继续 Fail Closed。

### Integration

- 两个 Agent Service 对同一 Tool 得到不同 Decision；
- 不同 Agent Service 可以选择不同 Egress Credential；
- Approval 恢复必须匹配原 Agent Service Principal；
- Idempotency Scope 继续包含 Agent Service Principal；
- Execution/Audit 记录正确 Service Principal；
- Cross-Tenant Search/Call/Credential 继续拒绝；
- Local Admin 注册、导入、发布、审批流程不回归。

### Contract/E2E

- Modern/Legacy MCP Contract 不漂移；
- Search-first Dynamic Activation 不回归；
- Browser Publish → MCP Call → Execution/Audit 通过；
- OpenAPI Snapshot 无无关变化；
- 不出现 `end_user_reference`、User Role 或员工字段。

### 完整门禁

```text
uv sync --frozen
pytest
ruff check
ruff format --check
basedpyright
uv build
pnpm frozen install / codegen / format / typecheck / lint / test / build
Full-stack Playwright
```

## 11. 风险与控制

### 风险一：删除 Role 后丢失 Agent 分组能力

当前没有真实 Service Group Case。若未来 Agent 数量大到逐 Principal Policy 难以维护，再基于证据引入
`service_group`，而不是保留员工 Role 抽象。

### 风险二：Static Service 被误解为无安全边界

文档和配置必须明确：Static Principal 只表示 NexusMCP 内部身份固定，入口仍需私有网络、mTLS、Ingress 或
API Gateway 保护。`/admin` 不能因此开放。

### 风险三：机械重命名扩大 Diff

先删除无用字段和分支，再决定类名重构。每个工作包独立测试，避免一个 Commit 同时包含语义变化、全局重命名
和配置变化。

### 风险四：历史文档与代码证据不一致

实验记录保留历史事实并加修订说明；规范文档描述当前目标。完成后通过全局术语扫描确认不再把员工 IAM 当成
未来主线。

## 12. 回滚策略

- 每个工作包独立 Commit；
- 不在同一 Migration 中删除数据库列，因为预计没有 Schema 变化；
- Policy/Credential 收敛前保留现有 Golden Snapshot 作为对照；
- 若发现真实 Role Consumer，暂停删除并在本记录中补充证据，不静默保留整个员工身份模型；
- MCP/Admin Public Contract 发生非预期变化时回滚当前工作包，而不是修改客户端适配错误设计。

## 13. 完成条件

只有以下条件全部满足，I-01 才能标记 Completed：

- ADR-0019 与代码 Principal 模型一致；
- Core 中不存在员工 User/Role/Agent Session 字段；
- Policy/Credential 只依赖 Agent Service Principal/Tenant；
- Approval/Execution/Audit 继续保留 Service Principal 追踪；
- Admin 与 MCP Auth 边界没有被混为一个开关；
- 无数据库 Migration 或已记录实际 Migration；
- Backend/Frontend/Full-stack 门禁通过；
- 本文回填最终 Commit、测试数量、删除项和遗留项。

## 14. 完成结果

当前为空。实现完成后填写：

```text
状态：
完成日期：
Commits：
删除内容：
保留内容：
数据库影响：
Contract 影响：
测试结果：
遗留项：
```
