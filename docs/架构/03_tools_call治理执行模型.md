# tools/call 治理执行模型

> 状态：Accepted，作为 S3 实现输入  
> 日期：2026-08-26  
> 范围：Call、Identity、Policy、Credential、Approval、Execution、Audit 的模型、编排与事务边界

## 1. 结论

S3 将 NexusMCP 从“可发布、可发现的 Tool Catalog”扩展为“安全受控的 Tool Execution Gateway”。

```text
MCP tools/call
→ Authenticate / Internal Principal
→ Resolve Published Tool + Binding
→ Validate Arguments
→ Evaluate Policy
→ Resolve/Consume Approval（如需要）
→ Resolve Credential Binding
→ Resolve Secret Reference
→ Create ToolExecution
→ Execute HTTP / Remote MCP
→ Normalize Result/Error
→ Finish ToolExecution
→ Append AuditEvent
→ MCP Result
```

任何客户端都可以直接构造 `tools/call`，因此不能因为 Tool 曾经出现在 `tools/list` 就跳过调用时治理。

## 2. 稳定模型

### 2.1 ActorContext 与 InternalPrincipal

```text
ActorContext
= request/trace/tenant/principal/authn_method

RequestContext
= ActorContext + MCP protocol/agent/run context

InternalPrincipal
= 认证 Adapter 产生的可信 Principal Type、Roles 和白名单 Attributes
```

InternalPrincipal 不保存原始 Token、Authorization Header 或完整 Claims。

### 2.2 CallToolCommand

```text
context
tool_name
arguments
arguments_digest（Canonical JSON SHA-256）
idempotency_key（可选）
approval_id（可选）
```

Arguments 只在单次调用内流转；持久化、Approval 和 Audit 使用 Digest。

### 2.3 PolicyDecision

```text
ALLOW
DENY
REQUIRE_APPROVAL
```

Decision 还包含：

- `policy_version`；
- 稳定英文 `reason_code`。

没有匹配 Policy 时默认 DENY。Condition DSL 留给真实 Policy Case，不在 S3-0 发明通用语言。

### 2.4 SecretReference 与 CredentialBinding

```text
SecretReference
├── provider
├── opaque reference
└── version（可选）

CredentialBinding
├── Tenant
├── Subject Scope：Principal / Role / Tenant
├── Tool Scope（可选）
├── Upstream Scope
├── SecretReference
├── Injection Location / Name / Format
└── Active / Disabled
```

`SecretValue` 只存在于单次执行内存，`str/repr` 永远显示 `[REDACTED]`。只有 Injection Adapter 可以在
最后时刻 `reveal()`。

### 2.5 ApprovalRequest

```text
pending → approved → consumed
        → rejected
        → expired
```

Approval 固定绑定：

- Tenant；
- Principal；
- Tool ID / ToolVersion ID；
- Arguments Digest；
- Policy Version；
- Expiry。

消费时重新校验 Principal、Version、Arguments Digest，只能消费一次。

### 2.6 ToolExecution

```text
planned → running → succeeded
                  → failed
                  → unknown
                  → cancelled
planned ─────────→ cancelled
```

`unknown` 表示无法确认上游是否已产生副作用，不等于普通 `failed`。

Execution 持久化：

- Principal/Tool/Version/Binding ID；
- Arguments Digest；
- Side Effect；
- Idempotency Key；
- Start/Finish 时间；
- Error Code/Category；
- Outcome。

不默认保存完整 Arguments/Result。

### 2.7 AuditEvent

Audit 是追加式、脱敏事件：

```text
tenant / actor
action / resource
outcome
request / trace
arguments_digest
policy_version / reason_code
execution_id
safe metadata
```

Audit 不拥有授权决定，不保存 Secret、Token、完整 Arguments 或完整 Result。

## 3. Call 编排顺序

顺序是安全不变量：

```text
1. Resolve InternalPrincipal
2. Resolve Active Tool + Published Version + Published Binding
3. Validate Tenant/Visibility/Arguments
4. Calculate Arguments Digest
5. Evaluate Policy
6. DENY：立即返回，不解析 Credential
7. REQUIRE_APPROVAL：创建或消费绑定快照的 Approval
8. Resolve CredentialBinding Metadata
9. 短事务消费 Approval（如需要）+ 创建 running ToolExecution + ALLOWED Audit
10. Resolve SecretReference → SecretValue
11. 事务外执行 Connector
12. 归一化 success/failed/unknown/cancelled
13. 短事务保存终态 + Terminal Audit
14. 映射 MCP Result/Error
```

Secret Value 必须位于 Policy ALLOW 和 Approval Consume 之后解析，避免拒绝或待审批调用仍读取
Secret。CredentialBinding Metadata 可以在计划事务前选择，以便记录 `credential_binding_id`，但不读取
Secret Value。

## 4. 主要 Port

```text
ExecutableToolResolver
PolicyEvaluator
ApprovalRepository
CredentialBindingResolver
CredentialProvider
ToolExecutionRepository
ToolExecutor
AuditSink
Clock / IdentifierGenerator
```

Port 使用 Domain/Application 类型，不暴露 MCP SDK、FastAPI、SQLAlchemy、httpx 或 Secret Store SDK。

## 5. 事务边界

数据库事务绝不跨越 Upstream HTTP/MCP：

```text
短事务 A
→ Resolve/Lock Approval（如需要）
→ Consume Approval
→ Create planned/running ToolExecution
→ Append ALLOWED Audit
→ Commit

事务外
→ Resolve Ephemeral Secret
→ Execute Connector

短事务 B
→ Save succeeded/failed/unknown/cancelled
→ Append Terminal Audit
→ Commit

后续外部投递
→ Transactional Outbox（尚未实现）
```

S3-5 已由 ADR-0010 决定：核心治理 Audit 与 Approval/Execution 使用同一 PostgreSQL 短事务同步
写入；外部 SIEM/消息系统不进入事务，未来通过 Outbox 投递。数据库事务仍不跨越 Upstream，系统
不宣称 Upstream Side Effect 与本地状态 Exactly Once。

## 6. Retry 与 Unknown Outcome

| Side Effect | Error/Outcome | 默认决策 |
|---|---|---|
| Read Only | Network/5xx/Timeout | 有界 Retry |
| Idempotent Write + Key | Network/5xx/Timeout | 有界 Retry |
| Idempotent Write 无 Key | Transport Failure | 不自动 Retry |
| Non-Idempotent/Unknown | Timeout After Send/Unknown | Require Reconciliation |
| 任意 | Validation/Auth/AuthZ/Approval/Credential/4xx | 不 Retry |

`timeout_before_send` 与 `timeout_after_send` 必须区分。后者可能已经产生副作用。

## 7. Error Normalization

内部至少区分：

```text
validation
authentication
authorization
approval
credential
timeout_before_send
timeout_after_send
network
upstream_4xx
upstream_5xx
cancelled
unknown
```

Interface 只返回安全 Error Code/Message；内部 URL、Credential、Stack 和 Upstream 敏感 Body 不进入 MCP
Result。

## 8. Deferred 决策

S3-0 不冻结：

- Policy Condition DSL；
- Secret Store 精确产品；
- HTTP Retry 库与 Backoff 参数；
- Execution Result 长期保留策略。

这些问题需要真实执行切片、客户端兼容测试或 Benchmark 证据。

## 9. S3-1 输入

下一步选择 `directory.get_employee` 跑只读无 Secret HTTP 执行：

```text
tools/call
→ Resolve Published HTTP Binding
→ JSON Schema Arguments Validation
→ Static ALLOW Policy
→ Create Execution
→ HTTP GET /employees/{employee_id}
→ Normalize JSON
→ Finish Execution
→ MCP Result
```

Approval、真实 Credential 与写 Tool 不进入第一条执行切片。

## 10. 实现进度

- S3-1 已完成 Modern MCP Read-Only HTTP `tools/call`；
- S3-2 已完成 Static Bearer Principal 与 Rule-Based ALLOW/DENY；
- S3-3 已在 ALLOW 之后接入 CredentialBinding、Environment Secret Provider 与 Header/Query
  Injection；同特异性冲突 Fail Closed，DENY 不读取 Secret；
- S3-4 已接入 PostgreSQL Approval、Modern MCP MRTR、Control Plane 异步决策、加密防篡改
  `requestState` 和 `FOR UPDATE` 单次消费；等待审批不占用 HTTP 请求或数据库事务；
- S3-5 已持久化 ToolExecution/Audit，并将 Approval Consume + Running Execution + ALLOWED Audit
  以及 Terminal Execution + Terminal Audit 分别放入两个短事务；
- 下一步 S3-6 实现有界 Retry/Idempotency 并收口 S3；写 Tool 仍按本文边界待实现。
