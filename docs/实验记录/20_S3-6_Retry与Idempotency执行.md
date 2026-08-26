# S3-6｜Retry/Idempotency 执行与 S3 收口

> 日期：2026-08-26  
> 状态：完成  
> 范围：ExecutionAttempt、有界 Retry、幂等 Claim、Inventory PUT 与 S3 总验收

## 1. 业务结果

一次 Agent Tool Call 只创建一个 ToolExecution，Transient Failure 可以产生多个持久化 Attempt：

```text
ToolExecution: inventory.set_reorder_level
├── Attempt 1 → upstream_503
├── Attempt 2 → network_error
└── Attempt 3 → 200 succeeded
```

Policy、Approval、Credential 和 Arguments 在整个 Retry Loop 中保持不变。Retry 不会重新消费审批或
创建新的 Execution。

## 2. Retry 执行

`ExecuteWithRetry` 在每次 Upstream 调用前后通过 `ExecutionLifecycle` 写入 Attempt，并使用已冻结的
Retry Matrix：

| Side Effect | Failure | 行为 |
|---|---|---|
| Read-Only | Network/5xx/Timeout | 有界 Retry |
| Idempotent Write + Key | Network/5xx/Timeout | 有界 Retry |
| Idempotent Write 无 Key | 任意 | 调用前拒绝 |
| Non-Idempotent/Unknown | After-Send Timeout | 不 Retry，UNKNOWN |
| 任意 | Validation/Auth/Approval/Credential/4xx | 不 Retry |

默认最多 3 次 Attempt，Backoff 为 `initial * 2^(attempt-1)`。最大次数限制在 1～10；本阶段不加入
随机 Jitter 和总时间预算，保证测试确定性。

## 3. Idempotency Claim

可信 Key 通过：

```text
_meta["com.nexusmcp/idempotencyKey"]
```

进入 `CallToolCommand`，HTTP PUT Executor 在参数映射后覆盖注入 `Idempotency-Key` Header。客户端
不能通过普通 Tool Argument 伪造该 Header。

PostgreSQL Partial Unique Index：

```text
tenant_id + principal_id + tool_version_id + idempotency_key
```

处理结果：

```text
New Key                         → Claim + Execute
Same Key + Different Digest     → idempotency_conflict
Same Key + Running              → idempotency_in_progress
Same Key + Succeeded            → idempotency_already_completed
Same Key + Unknown              → idempotency_outcome_unknown
Same Key + Failed/Cancelled     → idempotency_previous_failed
```

错误 Result 在 `_meta` 返回 `com.nexusmcp/existingExecutionId`。当前不保存完整业务 Result，所以
Completed Duplicate 不伪造原 Tool Output，而是明确返回原 Execution ID。

## 4. 受控 Inventory PUT

新增第八个 Demo Operation：

```text
inventory.set_reorder_level
PUT /inventory/{sku}/reorder-level
SideEffect = idempotent_write
```

相同 SKU/Warehouse/Reorder Level 和 Idempotency Key 重复提交返回相同状态；相同 Key 不同 Payload
返回 409。Gateway 只新增 PUT 白名单，已有 Operations POST 与 Inventory Reservation POST 仍不执行。

## 5. PostgreSQL 模型

Migration `e4a7c9d21b35`：

- 新增 `execution_attempt`，当前共 11 张 ORM 业务表；
- `tool_execution.attempt_count`；
- `approval_request.idempotency_key`；
- Execution Idempotency Partial Unique Index；
- `(execution_id, attempt_number)` Attempt Unique Index。

## 6. 验收证据

- Unit：Retryable Failure 两次后成功，验证 Attempt 与指数 Backoff；
- Unit：Non-Idempotent After-Send Timeout 不 Retry并进入 UNKNOWN；
- Unit：同 Key 的 InProgress/Completed/Digest Conflict 分类；
- PostgreSQL：两个并发 Claim 只创建一条 Execution；
- HTTP Executor：PUT JSON Body、可信 Header 覆盖、POST 继续拒绝；
- OpenAPI Contract：Inventory PUT 被标准 Pipeline 解析为 Idempotent Write；
- Modern MCP E2E：503、503、200 后成功，AttemptCount=3；
- Modern MCP E2E：Duplicate/Conflict/Missing Key 均不再次调用 Upstream；
- Alembic Upgrade/Downgrade 与 Schema Drift；
- 完整 Test、Ruff、basedpyright 与 Package Build。

## 7. 当前边界

- 不保存完整 Result，因此不支持透明 Completed Result Replay；
- 不跨进程继续一次正在运行的 Retry Loop；
- 不实现 Retry Jitter、总时间预算或 Circuit Breaker；
- Failed/Unknown Idempotency Key 默认 Fail Closed，需要查询/Reconciliation 后决定新业务意图；
- 不开放 POST、DELETE 或 Non-Idempotent HTTP Write；
- 不宣称 Exactly Once；
- Production JWT/OIDC、外部 Secret Store 和通用写治理仍待后续阶段。

## 8. S3 收口

S3 已完成 Identity → Policy → Approval → Credential → Execution → Retry/Idempotency → Audit 的
Modern MCP 纵向治理链。下一阶段进入 S4：先为现有 PostgreSQL Tool Search 建立 Eval，再实现小型
Knowledge RAG Demo。
