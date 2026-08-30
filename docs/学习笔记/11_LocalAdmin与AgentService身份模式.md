# Local Admin 与 Agent Service 身份模式

> 日期：2026-08-30
> 定位：用最小身份体系支撑管理员和 Agent 服务，不建设员工 IAM

## 1. 先确定谁真正使用 NexusMCP

NexusMCP 的直接使用者只有：

```text
管理员
→ 使用 Web / Admin API 管理 Upstream、Tool、Policy、Approval 和 Audit

Agent 服务
→ 使用 MCP tools/list、nexus.search_tools 和 tools/call
```

企业员工不会直接登录 NexusMCP：

```text
员工
→ 登录原业务系统或 Agent 助手
→ Agent 服务调用 NexusMCP
```

因此员工账号、员工角色、Agent 会话用户以及“哪位员工调用了哪个 MCP”都由 Agent 服务自己管理。即使只作
关联追踪，NexusMCP 也不接收 `end_user_reference`。

## 2. 当前 Local Admin 到底是什么

当前 Admin Middleware 不执行注册登录，而是为每个 `/admin` 请求直接创建固定 Context：

```text
tenant_id    = NEXUSMCP_LOCAL_TENANT_ID
principal_id = NEXUSMCP_LOCAL_ADMIN_PRINCIPAL_ID
authn_method = local_admin
```

所以 Local Admin 是：

```text
所有能够访问本地 /admin 的请求
→ 都被标记成同一个 local-admin
```

它没有用户表、密码、Login、Session、Cookie、JWT 或角色关系，只适合 Development/Learning。

## 3. 为什么 Admin 和 Agent 身份必须分开

两类调用者的认证来源不同：

```text
Admin Operator
→ 人类管理员
→ Local Admin / 企业 SSO / Trusted Proxy

Agent Service
→ 机器调用方
→ Static Identity / API Key / mTLS / Client Credentials / Trusted Proxy
```

因此不应只有一个全局 `IDENTITY_MODE`。目标应拆成：

```text
ADMIN_AUTH_MODE
MCP_AUTH_MODE
```

## 4. Agent 模式一：static_service

适用拓扑：

```text
Sales Assistant
→ 专用 NexusMCP
```

配置概念：

```ini
NEXUSMCP_MCP_AUTH_MODE=static_service
NEXUSMCP_STATIC_AGENT_PRINCIPAL_ID=sales-assistant-service
```

该实例的所有 MCP 请求都使用同一个固定 Service Principal。它不会根据请求自动切换身份。

如果 Customer Service 使用独立 NexusMCP：

```ini
NEXUSMCP_STATIC_AGENT_PRINCIPAL_ID=customer-service-agent
```

这是一实例一 Agent 身份的简单隔离模式。

## 5. Agent 模式二：service_identity / trusted_proxy

适用拓扑：

```text
Sales Assistant ───┐
Customer Service ──┼→ Shared NexusMCP
Ticket Assistant ──┘
```

每个 Agent 使用不同的机器 Credential：

```text
Credential A → sales-assistant-service
Credential B → customer-service-agent
Credential C → ticket-assistant-service
```

Credential 可以来自：

- API Key；
- mTLS Client Certificate；
- OAuth2 Client Credentials；
- 企业 API Gateway 验证后注入的签名身份。

NexusMCP 只管理少量机器调用方，不管理企业员工。不能直接相信普通 HTTP Header 自报的 Principal/Tenant。

## 6. Tenant 与 Principal

在这个模型中：

```text
Tenant
→ 企业或组织的数据隔离边界

AgentServicePrincipal
→ 当前调用来自哪个 Agent 服务

AdminPrincipal
→ 当前管理操作来自哪个管理员
```

单企业内部部署可以固定一个 Tenant。多企业/SaaS 部署必须从受信 Service Credential 或 Trusted Proxy 解析
Tenant，不能由 Agent 随意提交。

## 7. Policy 应该判断什么

主线不需要 User ↔ Role ↔ Permission。Agent Policy 只回答：

```text
哪个 Agent Service
→ 能看到哪些 Tool
→ 能调用哪些 Tool
→ 允许 read_only 还是 write
→ 是否需要 Approval
→ 使用哪个 CredentialBinding
```

例如：

```text
sales-assistant-service
→ ALLOW crm.get_customer
→ DENY inventory.set_reorder_level

customer-service-agent
→ ALLOW ticket.get_case
→ REQUIRE_APPROVAL ticket.refund_order
```

现有 Role 能力可以保留为通用实现，但不作为员工角色系统建设主线。

## 8. Credential 应该绑定给谁

推荐顺序：

```text
Agent Service + Tool
Agent Service + Upstream
Tenant + Tool
Tenant + Upstream
```

这允许不同 Agent 调用同一 Upstream 时使用不同 Credential。员工个人 Token、员工 OAuth 和 On-Behalf-Of
流程不进入 NexusMCP 当前主线。

如果某个 Upstream 必须按员工权限访问，应由 Agent 服务携带并处理 Delegated Credential，或者由 Upstream
重新验证最终用户；不能让 NexusMCP 静默使用宽权限 Service Credential 绕过业务权限。

## 9. NexusMCP 审计什么

NexusMCP 关心的是基础设施调用事实：

```text
customer-service-agent
→ 调用 crm.get_customer
→ ToolVersion v3
→ Policy allowed
→ Execution succeeded
→ Trace ID / Request ID
```

它不关心：

```text
当前 Agent 会话属于哪位员工
员工在 Agent 中输入了什么
员工调用历史如何展示
```

这些属于 Agent 服务自己的 Session、Product Audit 和用户行为追踪。

因此 NexusMCP 的 Audit 是 Agent Service/Tool/Execution Audit，不声称是员工行为审计。

## 10. Admin 生产边界

Agent 使用机器身份，不代表 `/admin` 可以裸露。

推荐：

```text
Development
→ ADMIN_AUTH_MODE=local

Production
→ ADMIN_AUTH_MODE=trusted_proxy 或 oidc
```

生产 Admin 最省事的方案是复用企业已有 SSO/API Gateway。NexusMCP 只消费可信管理员身份，不建设员工注册、
密码和通用角色中心。

管理员数量很少时，第一版甚至可以只有：

```text
platform_admin
auditor（可选）
```

不需要为了理论完整性建设复杂多角色管理后台。

## 11. 推荐的整体配置方向

独立 Agent 部署：

```ini
NEXUSMCP_ADMIN_AUTH_MODE=trusted_proxy
NEXUSMCP_MCP_AUTH_MODE=static_service
NEXUSMCP_STATIC_AGENT_PRINCIPAL_ID=sales-assistant-service
```

共享 Agent 部署：

```ini
NEXUSMCP_ADMIN_AUTH_MODE=trusted_proxy
NEXUSMCP_MCP_AUTH_MODE=service_identity
```

具体配置名仍需在代码实现 ADR 中冻结；这里冻结的是产品边界。

## 12. 一句话总结

```text
NexusMCP
= 面向管理员和 Agent 服务的企业 MCP Gateway

不是
= 企业员工账号、角色和会话平台
```

员工身份停留在业务系统或 Agent 服务；NexusMCP 只治理 Admin Operator、Agent Service、Tool、Credential、
Execution 与 Audit。
