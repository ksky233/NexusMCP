# S3-3｜CredentialBinding 与 Secret Injection 验收

> 日期：2026-08-26  
> 状态：完成  
> 范围：Credential Binding 选择、Environment Secret Provider、HTTP Header/Query Injection 与
> Modern MCP 纵向验证

## 1. 本阶段解决的问题

MCP Client 只携带用于访问 NexusMCP 的 Inbound Credential。NexusMCP 完成认证和授权后，再根据
可信 Internal Principal 选择访问企业 Upstream 的 Egress Credential。两类 Credential 不透传、
不复用：

```text
Inbound Bearer
→ Internal Principal
→ Tool Resolve
→ Arguments Validation
→ Policy ALLOW
→ CredentialBinding Resolve
→ SecretReference Resolve
→ Header / Query Injection
→ Upstream HTTP Call
```

Policy DENY、REQUIRE_APPROVAL 或参数校验失败时，流程不会进入 Secret Resolve。

## 2. CredentialBinding 选择规则

Resolver 先过滤 Tenant、Upstream、Tool 和 Active Status，再计算特异性：

```text
Principal + Tool     31
Principal + Upstream 30
Role + Tool          21
Role + Upstream      20
Tenant + Tool        11
Tenant + Upstream    10
```

`tool_id=None` 表示该 Subject 在指定 Upstream 下的通配 Binding。最高分若仍有多条候选，系统返回
`credential_binding_conflict`，不依赖列表或数据库返回顺序选取 Credential。

## 3. Environment Secret Provider

`SecretReference` 只保存：

```text
provider = environment
reference = EMPLOYEE_API_TOKEN
```

Provider 在执行时读取环境变量，返回临时 `SecretValue`。Reference 必须是大写环境变量名；Provider
不支持、Reference 非法、变量缺失或为空都统一返回 `credential_resolution_failed`。错误消息不会带
Reference 或 Secret Value。

Environment Provider 只用于本地学习与确定性测试。未来 Vault、AWS Secrets Manager 或 Azure Key
Vault 通过实现相同 `CredentialProvider` Port 接入，不修改 `CallTool`。

## 4. 注入与 Execution 边界

HTTP Executor 先完成普通参数映射，最后才按受信 Binding 注入 Credential：

- `location=header, name=Authorization, format=bearer` 生成 Bearer Header；
- `location=query, name=api_key, format=raw` 生成 Query 参数；
- Credential 与普通参数同名时，Credential 覆盖客户端输入；
- `SecretValue.reveal()` 只在 Executor 注入的最后时刻调用；
- `ToolExecution` 只记录 `credential_binding_id`，不记录 SecretReference 或 Secret Value。

Query Credential 已具备功能和安全测试，但生产场景优先 Header，因为 Query 更容易被代理访问日志、
浏览器历史或监控系统记录。

## 5. 代码位置

```text
src/nexusmcp/modules/credentials/adapters/environment.py
src/nexusmcp/modules/credentials/adapters/in_memory.py
src/nexusmcp/modules/execution/call_tool.py
src/nexusmcp/modules/execution/adapters/httpx_executor.py
src/nexusmcp/modules/execution/adapters/sqlalchemy_resolver.py
src/nexusmcp/bootstrap/app.py
```

## 6. 验收证据

单元测试证明：

- Principal、Role、Tenant 与 Tool/Upstream 通配特异性顺序；
- Disabled Binding 不参与匹配，同特异性冲突 Fail Closed；
- Environment Provider 成功、非法、缺失和脱敏行为；
- ALLOW 解析一次 Credential，DENY 零次解析；
- Header Credential 覆盖不可信参数，Query Credential 正确注入；
- 缺少 Binding 时不创建 Execution。

Modern MCP E2E 证明：

```text
User A → Policy ALLOW → Resolve Secret → Bearer Injection → Upstream 200
User B → Policy DENY  → 不解析 Secret → authorization_denied
```

最终只有 User A 的一条成功 Execution，记录 Binding ID；MCP Result、Execution Repr 和捕获日志中均
不存在 Secret Value。

## 7. 当前有意不做

- CredentialBinding PostgreSQL 表、Repository 与 Admin API；
- 真实 Vault/KMS/Cloud Secret Manager；
- OAuth2 Client Credentials、Token Refresh 与 Cache；
- Secret Rotation、Version Pinning 和 Lease Renewal；
- Inbound Token Passthrough；
- Approval 后的 Credential Resolve。

## 8. 下一步

进入 `S3-4｜Approval Gate 与单次消费`：让 `REQUIRE_APPROVAL` 绑定 Principal、Tool Version 和
Arguments Digest，并证明批准只能消费一次；Secret 仍必须在 Approval 成功消费后才解析。
