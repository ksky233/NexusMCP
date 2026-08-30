# ADR-0019｜面向管理员与 Agent Service 的身份边界

> 状态：Accepted
> 日期：2026-08-30
> 修订：收窄 ADR-0005 的产品身份范围；ADR-0005 的 Trust Boundary 原则继续有效

## Context

NexusMCP 的核心职责是把企业 HTTP/OpenAPI 能力转化为受治理的 MCP Tool，并为 Agent 服务提供统一发现、
调用、凭据、执行和审计边界。企业员工通过业务系统或 Agent 助手使用能力，不直接访问 NexusMCP 基础设施。

如果 NexusMCP 同时建设员工目录、注册登录、用户多角色、员工会话与最终用户行为追踪，会把项目扩张为企业
IAM/Employee Portal，偏离 API2MCP Gateway 的核心定位。

系统真正需要识别的调用者只有两类：

```text
Admin Operator
→ 使用 /admin 管理 Control Plane

Agent Service Principal
→ 使用 /mcp 发现并调用 Tool
```

上层 Agent 服务是否记录当前会话用户、员工身份和员工调用了哪些 MCP Tool，属于该 Agent 服务自己的产品
责任。NexusMCP 不接收、不保存、也不授权 `end_user_reference`。

## Decision

### 1. 产品参与者

NexusMCP 面向：

- 少量 Admin Operator；
- 一个或多个受信 Agent Service；
- 被接入的 Upstream System。

普通员工、消费者账号、Agent 会话用户不属于 NexusMCP Actor。

### 2. MCP 身份模式

MCP Data Plane 只规划两种 Service-Centric 模式：

```text
static_service
→ 一个 NexusMCP 部署对应一个固定 Agent Service Principal

service_identity
→ 多个 Agent Service 共用 NexusMCP
→ 由 AgentServiceAuthenticator 将机器 Credential 映射为不同 Service Principal
```

`static_service` 不根据请求动态切换 Principal。多个 Agent 需要不同 Policy/Audit 时，必须使用独立部署或
Service Identity，不信任客户端自报 Principal Header。

### 3. Admin 与 MCP 身份分离

Admin 和 Agent Service 的认证来源不同，不使用一个全局 Identity Mode：

```text
Admin Auth Boundary
→ local（当前）/ AdminAuthenticator（Future）

MCP Identity Mode
→ static_service / service_identity
```

当前 Local Admin 继续使用固定 Settings Tenant/Principal，只允许 Development。生产管理面优先委托企业
认证设施，不要求 NexusMCP 自建员工账号或密码系统。

### 4. Principal 定义

规范中的 Principal 收窄为：

```text
AdminPrincipal
AgentServicePrincipal
Anonymous（仅协议拒绝或受限开发场景）
```

I01-1/2 已删除 `InternalPrincipal.roles/attributes` 和 Role Subject。Agent Service 授权只使用稳定 Principal ID、
Tenant、Tool、Side Effect 和显式 Rule；未来只有出现真实 Service Group Case 后才重新设计分组能力。

### 5. Tenant 定义

Tenant 继续作为数据、Tool、Credential、Policy 与 Audit 的最高隔离边界。企业内部单租户部署可以固定一个
Tenant；共享/SaaS 部署必须由受信 AgentServiceAuthenticator 解析 Tenant。

Tenant 不能来自未验证 Header，也不等同于员工所属部门或当前 Agent 会话。

### 6. Policy 与 Credential

Service-Centric Policy 主要回答：

```text
哪个 Agent Service
→ 可以发现/调用哪些 Tool
→ 允许什么 Side Effect
→ 是否需要 Approval
→ 使用哪个 CredentialBinding
```

CredentialBinding 主线特异性收敛为：

```text
Agent Service Principal + Tool
Agent Service Principal + Upstream
Tenant + Tool
Tenant + Upstream
```

员工个人 OAuth Token、员工角色和 On-Behalf-Of Credential 不进入当前主线。若 Upstream 需要员工级授权，应由
上层 Agent 服务或原业务系统完成，不默认透传给 NexusMCP。

### 7. Audit 边界

NexusMCP 记录基础设施与 Agent Service 级事实：

```text
tenant_id
agent_service_principal_id
tool / version / binding
policy decision
execution / attempt / outcome
request_id / trace_id
```

NexusMCP 不记录“哪位员工发起了当前 Agent 会话”。Trace ID 用于跨系统关联请求，不等于员工身份。

### 8. Control Plane 安全

`/mcp` 采用 Service Principal 不意味着 `/admin` 可以匿名开放。生产环境必须关闭 Local Admin，或将 Admin
入口置于可信管理边界，并通过外部管理认证设施识别少量管理员。

## Rejected Alternatives

- 在 NexusMCP 建设员工注册、密码登录和用户中心；
- 建立 User ↔ Role ↔ Permission 作为核心领域；
- 接收可选 `end_user_reference` 并将其纳入 Audit；
- 信任 Agent 自报 `principal_id` 或 `tenant_id` Header；
- 所有 Agent 共用一个固定 Principal，但又宣称可以区分 Agent 权限与审计；
- 因为不接企业 IAM 就把 `/admin` 或 `/mcp` 裸露到不可信网络。

## Consequences

### Positive

- 产品定位收敛为 Enterprise MCP Gateway，而不是 IAM 平台；
- 机器身份数量远小于员工数量，Policy/Credential/Audit 更可控；
- 单 Agent 可使用极简静态模式，多 Agent 可平滑升级 Service Identity；
- 企业员工 IAM 与 Agent 会话模型不污染 NexusMCP Domain；
- 管理面认证可以委托现有企业 SSO，不阻塞 API2MCP Core。

### Trade-offs

- NexusMCP 无法回答具体员工是否有权访问某条业务数据；
- Agent Service 使用宽权限 Credential 时，员工级授权责任在 Agent 或 Upstream；
- Service Principal Audit 不能替代员工行为审计；
- 多 Agent 共享部署必须配置一个可信 `AgentServiceAuthenticator`；具体企业认证方式不由 Core 预设。

## Implementation Direction

后续代码只冻结两个独立边界：

```text
AdminAuthenticator
AgentServiceAuthenticator
```

MCP 只提供两个模式：

```ini
NEXUSMCP_MCP_IDENTITY_MODE=static_service
NEXUSMCP_STATIC_AGENT_PRINCIPAL_ID=sales-assistant-service
```

`service_identity` 统一依赖 `AgentServiceAuthenticator` Port。第一版只维护一个通用的 Static Bearer
参考 Adapter，将 Opaque Bearer Token Digest 映射为 Agent Service Principal。其他企业认证机制只有在真实
环境提出第二种 Adapter 需求后再设计，不进入当前模式枚举或配置。

Admin 继续保持独立 Local Boundary；生产 Admin Adapter 在真实环境出现后再按企业现状选择。
