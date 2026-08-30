# S3-4｜Approval Gate 与单次消费验收

> 2026-08-30 边界修订：本文 Approval 绑定的 Principal 在产品主线中指 Agent Service Principal，不指
> Agent 会话里的员工。员工侧审批或行为追踪属于上层 Agent/业务系统。

> 日期：2026-08-26  
> 状态：完成  
> 范围：PostgreSQL Approval、Modern MCP MRTR、Control Plane 异步决策与原子单次消费

## 1. 结论

Approval 不会让一次 MCP/HTTP 请求持续等待人工操作。第一次调用创建持久化 `PENDING`
Approval，并立即返回 Modern MCP `InputRequiredResult`：

```text
tools/call #1
→ Resolve Principal / Tool / Arguments / Policy
→ Policy = REQUIRE_APPROVAL
→ INSERT approval_request(status=pending)
→ Commit
→ InputRequiredResult(requestState, approvalId, Elicitation)
→ Request End
```

批准后的恢复是一次新的 `tools/call`：

```text
tools/call #2
→ Verify/Decrypt requestState
→ Re-resolve Principal / Tool / Arguments / Policy
→ SELECT Approval FOR UPDATE
→ APPROVED → CONSUMED
→ Commit
→ Resolve Credential
→ Create Execution / Call Upstream
```

## 2. 两条 Interface 路径

### 2.1 Host 内短时确认

Modern Client 自动把 `InputRequiredResult.inputRequests.approval` 分派给 Elicitation Callback。用户在
Host UI 接受后，SDK 使用 `inputResponses + requestState` 发起第二轮调用。Decline/Cancel 会把
Approval 标记为 `REJECTED`，不会创建 Execution 或解析 Credential。

### 2.2 Control Plane 异步审批

等待主管或外部系统时，Host 手动保存 opaque `requestState` 与 `approval_id`，当前 Agent Run 可以
结束。审批人通过：

```text
GET  /admin/approvals/{approval_id}
POST /admin/approvals/{approval_id}/approve
POST /admin/approvals/{approval_id}/reject
```

处理后，Host 可以在新进程或新 Agent Run 中使用原 `requestState` 恢复相同 Tool Call。

## 3. 持久化与单次消费

Migration `c1f8a3d42e90` 新增第八张业务表 `approval_request`：

```text
id / tenant_id / principal_id
tool_id / tool_version_id
arguments_digest / policy_version
status / requested_at / expires_at
decided_by / decided_at / consumed_at
```

消费事务使用 `SELECT ... FOR UPDATE`。两个并发请求读取同一 Approval 时，第一个提交
`CONSUMED`，第二个获得行锁后只能看到 `CONSUMED`，返回 `approval_already_consumed`。

状态机为：

```text
PENDING → APPROVED → CONSUMED
        → REJECTED
PENDING/APPROVED → EXPIRED
```

## 4. requestState 安全边界

低层 MCP Server 不会自动安装 `requestState` 安全 Middleware，因此 NexusMCP 显式注册 SDK
`RequestStateBoundary`。它使用 AES-GCM 并验证：

- MCP Method 与 Tool Name；
- 原始 Arguments Digest；
- Audience 与 TTL；
- Token 完整性。

开发单进程默认生成 Ephemeral Key。Production Tool Execution 强制配置至少 32 Bytes 的
`NEXUSMCP_REQUEST_STATE_KEY`；多 Worker/跨重启实例必须共享该 Key。

即使 `requestState` 验证通过，Application 仍重新检查 Tenant、Principal、Tool Version、Arguments
Digest 与 Policy Version，不能只依赖协议 Token。

## 5. 安全顺序

本阶段保持以下不变量：

```text
DENY                 → 不创建 Approval、不解析 Secret
REQUIRE_APPROVAL     → 未消费前不解析 Secret、不创建 Execution
APPROVED + CONSUMED  → 才进入 Credential Resolution 与 Execution
REJECTED/EXPIRED     → 不执行
CONSUMED Replay      → 不执行
```

Approval 表不保存完整 Arguments、Secret、Inbound Token 或明文 `requestState`。

## 6. 验收证据

- Approval Domain 与 Use Case 状态测试；
- InMemory 事务并发消费测试；
- PostgreSQL Repository/UoW 行锁并发测试；
- MRTR Accept 自动恢复并执行；
- MRTR Decline 不创建 Execution；
- `requestState` 篡改和 Arguments 篡改被拒绝；
- 第一轮应用关闭后，第二个应用实例通过共享 Key 恢复；
- Control Plane Approve 后成功执行，Replay 被拒绝；
- Alembic Upgrade/Downgrade 与 Schema Drift 检查。

## 7. 当前边界

- `/admin` 仍使用本地固定 Admin Principal，禁止作为生产审批权限边界；
- MRTR 当前表达当前 Host 用户确认，不声明职责分离；
- Approval Detail 只展示 Arguments Digest，尚未设计通用安全参数预览；
- Legacy Approval Resource/Compatibility Adapter 尚未实现；
- Production Key Rotation/KMS Adapter 尚未实现；
- Approval Notification、Webhook 和待办列表尚未实现；
- ToolExecution/Audit 仍未持久化，因此 Approval Consume 与 planned Execution 暂时不是同一事务；
  中间失败会 Fail Closed 并要求新审批，S3-5 将关闭这个一致性窗口。

## 8. 下一步

进入 `S3-5｜持久化 ToolExecution 与 Audit 接缝`，把当前 InMemory Execution 升级为短事务持久化，
并记录不含 Secret/完整 Arguments/Result 的治理证据。

实现结果见 [S3-5 持久化 ToolExecution 与 Audit 接缝](./19_S3-5_持久化Execution与Audit接缝.md)，
上述一致性窗口已关闭。
