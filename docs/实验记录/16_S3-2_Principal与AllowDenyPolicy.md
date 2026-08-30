# S3-2｜Principal 与 ALLOW/DENY Policy 验收

> 2026-08-30 边界修订：多 Principal/Role Case 证明 Policy 特异性和信任边界可运行；它不代表 NexusMCP
> 建设员工 IAM。I01-2 已从当前 Core 删除 Role Subject，产品主线 Principal 是 Agent Service，见 ADR-0019。

> 日期：2026-08-26  
> 范围：Static Bearer Authentication、InternalPrincipal Roles、ActorContext 可信属性、ToolPolicy、
> Rule-Based Policy Evaluator、调用阶段重新授权、多 Principal Modern MCP E2E

## 1. 目标

证明同一个 Public Tool 即使能被多个客户端发现，`tools/call` 仍会根据可信 Principal 和 Policy 产生
不同结果：

```text
User A / employee_reader    → ALLOW → Execute
User B / inventory_operator → DENY  → No Execution
Unknown Token               → Authentication Error
Anonymous                   → Default DENY
```

本阶段不建设 OAuth Server，不把 Static Token 方案用于 Production。

## 2. Authentication Adapter

`StaticBearerPrincipalAuthenticator` 只用于确定性开发/测试：

```text
Authorization: Bearer <token>
→ SHA-256 Token Digest Lookup
→ InternalPrincipal
```

Adapter 初始化后只保存 Token Digest → Principal，不保留 Token 原文。错误消息和日志只包含稳定 Error
Code，不包含 Authorization Header。

验证：

- Bearer Scheme/Token 必须有效；
- Unknown Token 被拒绝；
- Token Principal Tenant 必须匹配 Request Tenant；
- 缺少 Header 可以降级为 Anonymous（由 Adapter 配置决定）；
- Cross-Tenant Token 被拒绝。

## 3. ActorContext 与 Principal

认证完成后，MCP Interface 把可信事实写入 ActorContext：

```text
principal_id
principal_type
authn_method
roles
principal_attributes（白名单）
```

`ContextPrincipalResolver` 再构造 `InternalPrincipal`。Raw Token 不进入 Context、Domain、Execution 或
Audit。

## 4. ToolPolicy

S3-2 最小模型：

```text
tenant_id
subject_type: principal | role | tenant
subject_id
tool_id（可选，None 表示 Tenant Tool Scope）
action: call
effect: allow | deny | require_approval
priority
version
reason_code
status
```

本阶段只在 E2E 使用 ALLOW/DENY；REQUIRE_APPROVAL 留给 S3-4，但枚举和优先级已兼容。

## 5. 确定性匹配规则

从高到低：

```text
Principal > Role > Tenant
Exact Tool > Wildcard Tool
Higher Priority > Lower Priority
同 Specificity + Priority：DENY > REQUIRE_APPROVAL > ALLOW
无匹配：Default DENY
```

例如 Exact Principal ALLOW 可以覆盖低特异性的 Role DENY；同一个 Role/Tool、同 Priority 同时出现
ALLOW 与 DENY 时 DENY 胜出。

## 6. tools/list 不替代 tools/call Policy

E2E 中 `directory.get_employee` 是 Public：

- User A 在 `tools/list` 看见；
- User B 也在 `tools/list` 看见；
- User A `tools/call` 被 ALLOW；
- User B `tools/call` 被 DENY。

这证明可发现性不是调用授权。客户端可以绕过 List 直接构造 Call，每次 Call 必须重新 Resolve、Validate
和 Evaluate Policy。

## 7. Modern MCP E2E

同一个 Server/Lifespan 中依次建立四个 MCP Client：

```text
Bearer user-a-token
→ employee_reader
→ ALLOW
→ Employee Directory HTTP GET
→ Succeeded Execution

Bearer user-b-token
→ inventory_operator
→ Explicit DENY
→ authorization_denied

Bearer unknown-token
→ authentication_failed

No Authorization
→ Anonymous
→ default_deny
```

最终只有 User A 创建一条 Execution，证明 Authentication/Policy Rejection 都发生在外部执行之前。

## 8. Composition

`create_app()` 增加可替换接缝：

```text
PrincipalAuthenticator
PolicyEvaluator
```

默认仍使用 Anonymous + StaticReadOnly，保持旧兼容测试；S3-2 E2E 注入 Static Bearer + Rule-Based
Evaluator。未来 JWT/OIDC 和 PostgreSQL Policy Adapter 替换实现时不修改 `CallTool`。

## 9. 当前有意不做

- JWT Signature/Issuer/Audience/Expiry；
- Production Agent Service Credential/Trusted Proxy Adapter；
- Policy PostgreSQL 表和 Migration；
- Policy Condition DSL；
- Policy Admin API；
- REQUIRE_APPROVAL 执行；
- CredentialBinding/Secret；
- Production Authentication。

## 10. 代码位置

```text
src/nexusmcp/modules/identity/adapters/static_bearer.py
src/nexusmcp/modules/identity/adapters/context_principal.py
src/nexusmcp/interfaces/mcp/context.py
src/nexusmcp/modules/policy/domain.py
src/nexusmcp/modules/policy/adapters/rule_based.py
src/nexusmcp/bootstrap/app.py
tests/unit/modules/identity/test_static_bearer_authenticator.py
tests/unit/modules/policy/test_rule_based_policy.py
tests/integration/persistence/test_mcp_principal_policy.py
```

## 11. 下一步

进入 `S3-3｜CredentialBinding 与 Secret Injection`：

1. Environment Secret Provider；
2. InMemory CredentialBinding Resolver；
3. ALLOW 后按 Principal/Role/Tenant Scope 选择 Binding；
4. Header Credential Injection；
5. Secret 不进入 Context/Log/Execution/Audit/Error；
6. DENY 调用不解析 Secret；
7. 暂不接真实 Vault/KMS。

实现结果见 [S3-3 CredentialBinding 与 Secret Injection](./17_S3-3_CredentialBinding与SecretInjection.md)。
