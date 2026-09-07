# I03 Toolset 代码 Review 判定

> 日期：2026-09-07
>
> 范围：I03-1 至 I03-5A
>
> 原则：先核对事实与架构取舍，再决定是否修改；不直接接受 Review 中的优先级。

## 1. 结论

Review 中 7 条事实成立，1 条部分成立，2 条不构成当前问题。原始 P0 定级偏重，最终处理边界如下：

```text
本轮修复      1 / 2 / 3 / 4 / 9
记录触发条件  6 / 7 / 8
不修改        5 / 10
```

## 2. 逐条判定

### 1. 拒绝审计失败遮蔽原始错误

事实成立：`_record_scope_denial()` 被内联 `await`，Audit 写入异常会离开原有 NexusMCP Error 分支，客户端无法
继续收到 `toolset_access_denied` 等稳定语义。它不造成越权执行，但造成错误契约与 Audit 可用性耦合。

决策：当前项目选择 **Best Effort Denial Audit**。拒绝已经生效后，Audit 写入失败降级为结构化错误日志，客户端
仍收到原始拒绝。成功执行及状态变更 Audit 继续保持原有事务强一致。未来严格合规部署需要 Durable Outbox，
不使用可能丢事件的进程内异步队列。

### 2. ValueError 消息字符串映射

核心成立：`_map_mutation_error()` 依赖 `"revision"/"system"` 文案，存在重构脆弱性。

“没有测试能拦住”不准确：现有 Use Case Test 已断言 Revision/System Error 类型。`_require_expected_revision()`
也不是纯重复，它让 Replace/Activate 在读取 Catalog 前先拒绝过期 Revision，保持错误优先级并减少无效查询。

决策：为可预期的 Toolset Revision/System Mutation 定义类型化 Domain Error；输入格式等普通领域校验仍可使用
`ValueError`。保留 Revision 预检，但让预检与 Aggregate 抛出相同类型。

### 3. Scope Metadata 双份实现

事实成立：Execution 使用 `McpScopeType`，Approval 使用字符串，Scope Reason 规则存在漂移风险。

决策：收敛为一个 Scope Evidence Value Object/Mapper。它属于 MCP Execution/Audit 交界，不把零散 Helper 塞进
顶层 Shared Kernel。

### 4. Scope Error Code 白名单

事实成立：按字符串集合识别 Scope Error，新错误可能漏审。

决策：建立 `ToolsetScopeError` 类型族，Server 使用 `isinstance` 判断；稳定 Error Code 仍由具体异常负责。

### 5. InMemory UoW Catalog Reader 共享引用

不构成问题。`ToolsetCatalogReader` Port 明确只有读取方法，内部 Snapshot 不可变，外部也无法通过公共 API 修改
Reader。现有 UoW Contract 已覆盖 Toolset 写入后退出/显式 Rollback 对外不可见。

决策：不为不存在的“Reader 写入”场景增加测试。未来若 Port 引入写能力，必须重新设计 UoW，而不是继续称其为
Reader。

### 6. ListToolsets 全量过滤分页

事实成立，而且实际还包含 Aggregate Member/Grant 与 Profile Catalog 的 N+1 Query。当前每 Tenant Toolset 数量很
小，不在本轮预优化。

触发条件：真实租户出现明显数量增长、Admin List P95/数据库 Query Count 随 Toolset 数线性恶化时，建立专用
Toolset Admin Query Projection，在 SQL 中完成过滤、分页与批量摘要；仅增加 Repository `list_page()` 不足以消除
完整 N+1。

### 7. serialized_schema_size 重复计算

事实成立。Published ToolVersion 的 Schema 稳定，Profile/List 重复 `json.dumps` 属于可消除计算。

触发条件：Profile/List Profiling 显示 Schema 序列化成为主要耗时，或同一 Tool 被大量 Toolset 重复引用时，再在
Publish Projection 中预计算大小或建立查询缓存。本轮不增加冗余列和 Migration。

### 8. all_published 动态全量 JOIN

事实成立，但这是 ADR-0020 已接受的一致性取舍。

触发条件：Published Tool 规模或 Admin 查询频率使详情查询出现稳定慢查询。第一优化顺序是 List 只读摘要、Detail
按需展开；只有出现明确证据后才考虑物化投影。事件驱动物化会重新引入同步与漂移成本，不作为默认方案。

### 9. MCP Header 字符串硬编码

事实成立。当前 SDK v2 提供 `mcp.shared.inbound.MCP_PROTOCOL_VERSION_HEADER`。

决策：直接复用 SDK 常量，避免协议字符串存在第二事实源。

### 10. Use Case 构造器样板

不构成问题。显式构造器注入是当前 Ports/Adapters 的依赖透明性，`ToolsetAdminServices` 只负责 Interface
Composition。为减少几行构造器而让 Use Case 依赖大 Services Container，容易退化为 Service Locator。

决策：保持现状；只有依赖组合出现新的业务内聚边界时才提取 Facade，不按代码行数抽象。

## 3. 本轮验收要求

- Audit Store 故障时，原始 Scope Denial Error Code 保持不变，并产生脱敏结构化错误日志；
- Toolset Domain 文案变化不再影响 HTTP/MCP Error 类型；
- Scope Metadata 只有一个生成规则；
- 新增 `ToolsetScopeError` 子类时自动进入 Denial Audit 路径；
- HTTP Transport 使用 SDK Header 常量；
- Ruff、basedpyright、相关测试和 Full Suite 通过。

## 4. 实施结果

已完成：

- `ToolsetRevisionConflict/SystemToolsetMutationError` 类型化 Domain Error；
- `ToolsetScopeError` 类型族，Server 不再维护 Error Code 字符串白名单；
- `McpScopeAuditEvidence` 成为 Execution/Approval 共用的唯一 Scope Metadata Mapper；
- Denial Audit 写入失败降级为 `mcp_scope_denial_audit_failed` 结构化错误日志，并保留原始 Scope Error Code；
- Streamable HTTP Guard 改用 SDK `MCP_PROTOCOL_VERSION_HEADER`；
- 新增消息无关 Error Mapping、Scope Evidence Invariant 和 Audit Store 故障协议测试。

保持不变：

- 成功调用、Execution 状态变化和 Approval 的 Audit 仍与业务事务强一致；
- Revision 预检继续在 Catalog 查询前执行；
- P2 性能项只记录触发条件；
- InMemory Reader 与 Use Case 构造方式不变。

验证结果：

```text
Targeted Unit/Contract        49 passed
Related PostgreSQL/MCP         6 passed
Full Python Suite            360 passed / 2 paid external skipped
Ruff Lint/Format              passed
basedpyright                  0 errors / 0 warnings
```
