# S3-5｜持久化 ToolExecution 与 Audit 接缝验收

> 日期：2026-08-26  
> 状态：完成  
> 范围：PostgreSQL Execution/Audit、共享 UoW、三段式 Call 编排与脱敏治理证据

## 1. 本阶段关闭的问题

S3-4 中 Approval 已经可以原子消费，但 Execution 仍在内存，存在：

```text
Approval 已 CONSUMED
→ 进程崩溃
→ Execution 尚未创建
```

S3-5 把调用拆为两个本地短事务和一次事务外执行：

```text
短事务 A
→ Lock/Consume Approval（如需要）
→ INSERT Running ToolExecution
→ INSERT ALLOWED Audit
→ Commit

事务外
→ Resolve Secret Value
→ HTTP/MCP Upstream Call

短事务 B
→ Lock Running ToolExecution
→ UPDATE Terminal State
→ INSERT Terminal Audit
→ Commit
```

数据库事务不跨越 Upstream，避免长事务、连接占用和把网络失败带入 PostgreSQL Lock 生命周期。

## 2. PostgreSQL 模型

Migration `d7e2b4c91a60` 新增：

### tool_execution

持久化 Request/Trace、Principal、Tool/Version/Binding、Approval/Credential Binding ID、Arguments
Digest、Policy Snapshot、Side Effect、Idempotency Key、状态、时间与安全 Error Code/Category。

不保存完整 Arguments、Result、Secret 或上游错误 Body。

### audit_event

Append-Only 保存 Actor、Action、Resource、Outcome、Request/Trace、Arguments Digest、Policy/Reason、
Execution ID 和脱敏 Metadata JSONB。

当前共 10 张 ORM 业务表。

## 3. ExecutionLifecycle

`ExecutionLifecycle` 代替 `CallTool` 直接操作 Repository，统一负责：

- `plan()`：Approval Consume + Running Execution + ALLOWED Audit；
- `succeed()`：Succeeded + SUCCEEDED Audit；
- `fail()`：Failed/Unknown + FAILED/UNKNOWN Audit；
- `cancel()`：Cancelled + CANCELLED Audit；
- `record_call_decision()`：持久化 Policy DENY 等无 Execution 决策。

终态写入使用 `SELECT ... FOR UPDATE`，已经结束的 Execution 不能再次改变终态。

## 4. Approval Audit

Approval 自身也进入同库审计事务：

```text
Create PENDING → TOOL_CALL / APPROVAL_REQUIRED
Approve        → APPROVAL_DECISION / ALLOWED
Reject         → APPROVAL_DECISION / DENIED
Consume + Plan → TOOL_CALL / ALLOWED
```

这样可以区分“谁请求了审批”“谁批准了审批”和“谁实际调用了 Tool”。

## 5. Credential 与失败语义

CredentialBinding Metadata 在计划事务前选择，但 Secret Value 必须在 Approval 已消费、Execution 已
持久化后才解析：

- Secret Provider 失败：Execution 进入 `FAILED/credential`；
- Executor 明确失败：Execution 进入 `FAILED`；
- 请求可能已发送且结果不明：Execution 进入 `UNKNOWN`；
- Task Cancel：Execution 进入 `CANCELLED`；
- 成功：Execution 进入 `SUCCEEDED`。

每个终态都与对应 Audit 在同一事务提交。

## 6. 验收证据

- InMemory UoW 故障注入证明 Audit Append 失败会回滚 Approval Consume 与 Execution Plan；
- PostgreSQL Repository/UoW 验证 Succeeded 与 Unknown 终态及两阶段 Audit；
- Approval E2E 验证 Execution 保存 `approval_id`，Replay 不创建第二条 Execution；
- Principal Policy E2E 验证 ALLOW/DENY Audit；
- Credential E2E 验证 Secret 不进入 Execution、Audit、MCP Result 或 Log；
- Modern MCP Read-Only E2E 验证 Request/Trace 与成功终态持久化；
- Alembic Upgrade/Downgrade 与 Schema Drift 检查；
- 完整测试、Ruff、basedpyright 与 Package Build。

## 7. 当前边界

- Execution Result 与完整 Arguments 不持久化；
- 不在本阶段实际执行自动 Retry；
- Idempotency Key 已记录但尚未建立唯一约束与复用语义；
- 外部 SIEM/Event Bus Outbox 未实现；
- Audit Partition、Retention 和归档未设计；
- Authentication Failure、Invalid RequestState、Approval Replay 的持久化安全审计仍待补齐；
- 写 Tool 与 Reconciliation 尚未实现。

## 8. 下一步

进入 `S3-6｜Retry/Idempotency 执行与 S3 收口`：把已经冻结的 Retry Matrix 接入执行链，并验证
Read-Only 有界 Retry、Idempotent Write Key 冲突以及 Non-Idempotent Unknown 不盲目重试。
