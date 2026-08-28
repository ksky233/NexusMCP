# W1｜Admin Query API

> 日期：2026-08-28  
> 状态：完成

## 1. 目标

为后续 React Web Control Plane 提供稳定的只读 API，使页面不需要访问 PostgreSQL、拼装多个写模型
Repository，或在浏览器复制领域状态机。

W1 只增加 Query Side，不修改现有表结构，也不改变 Register、Import、Review、Publish、Approval Decision
等写用例。

## 2. 结构

```text
Admin Route
  → ControlPlaneQueryPort
    → SqlAlchemyControlPlaneQueries
      → PostgreSQL Read Model Query
        → 专用 Response Contract
```

新增 `control_plane` 模块只拥有跨上下文 Read Model 与 Query Port。SQLAlchemy Adapter 位于
`infrastructure/persistence`，允许为 Dashboard 和后台列表 Join Registry、Catalog、Approval、Execution、
Audit 与 Search Projection 表，但不会把 ORM Model 暴露给 Web 层。

这里没有复用写事务 Repository，原因是两者职责不同：

- Repository 服务领域 Aggregate 的一致性、锁与状态变更；
- Admin Query 服务列表、过滤、统计和跨上下文 Projection；
- Query 不获取 `FOR UPDATE` 锁，也不创建 Unit of Work；
- 后续若拆分读库，只需要替换 Query Port Adapter。

## 3. 新增 Query API

| Method | Path | Operation ID | 用途 |
|---|---|---|---|
| GET | `/admin/dashboard` | `getDashboard` | Control Plane 聚合计数与搜索覆盖率 |
| GET | `/admin/upstreams/{id}` | `getUpstream` | Upstream 详情 |
| GET | `/admin/openapi/imports` | `listOpenApiImports` | Import Job 分页与筛选 |
| GET | `/admin/openapi/operations` | `listReviewOperations` | Review Queue 分页与筛选 |
| GET | `/admin/tools` | `listTools` | Tool Catalog 分页与筛选 |
| GET | `/admin/tools/{id}` | `getTool` | 稳定 Tool Identity 详情 |
| GET | `/admin/tools/{id}/versions` | `listToolVersions` | Tool Version History |
| GET | `/admin/tool-bindings/{id}` | `getToolBinding` | 非敏感执行绑定详情 |
| GET | `/admin/approvals` | `listApprovals` | Approval 分页与状态筛选 |
| GET | `/admin/executions` | `listExecutions` | Execution 分页与多条件筛选 |
| GET | `/admin/executions/{id}` | `getExecution` | Execution 详情 |
| GET | `/admin/executions/{id}/attempts` | `listExecutionAttempts` | Retry Attempt 时间线 |
| GET | `/admin/audit-events` | `listAuditEvents` | Audit 分页与 Trace/Principal/Tool 筛选 |
| GET | `/admin/search/projection-status` | `getSearchProjectionStatus` | 当前模型的 Embedding 覆盖率 |

原有 `listUpstreams` 同时升级为真正的数据库分页，并增加 Namespace/Status 筛选，不再先读取全部数据后在
HTTP 层切片。

## 4. Dashboard 语义

Dashboard 返回：

- Active HTTP Upstream；
- Published ToolVersion；
- Pending/Needs Change Review；
- Pending Approval；
- Failed/Unknown Execution；
- 当前 `Embedding Model@Dimensions` 下的 Published/Indexed/Pending Tool 与最后索引时间。

当 Published Tool 为 0 时，Coverage 返回 `100%`，含义是“当前没有待索引对象”；UI 仍同时显示 `0 / 0`，
不应把它解读为已经建立了向量数据。

## 5. 分页与筛选

普通资源列表继续遵循 W0 契约：

```json
{
  "items": [],
  "page": {
    "offset": 0,
    "limit": 50,
    "total": 0
  }
}
```

- 默认 `limit=50`，最大 `100`；
- Count 与 Page Query 使用相同 Filter；
- 时间线按时间倒序，Attempt 按 `attempt_number` 正序；
- Enum Filter 由 OpenAPI 限定，非法值返回统一 `422 request_validation_failed`；
- ID Filter 使用精确匹配，不接受模糊搜索；
- Catalog Search 仍是 Top-K Search，不改造成资源分页。

## 6. 安全边界

- Tenant 只来自 Backend `ActorContext`，不接受浏览器伪造 Tenant Header；
- 所有 Detail/List/Count Query 都带 Tenant Predicate；
- 跨 Tenant Detail 返回与不存在相同的 `404`；
- Remote MCP Upstream/Binding 不进入公开列表或详情能力；
- Approval/Execution 只返回 `has_idempotency_key`，不返回 Key Value；
- Audit/Execution 不返回完整 Arguments、Result、Credential 或 Token；
- `arguments_digest`、Policy Version、Reason Code、Request ID 和 Trace ID 作为治理证据保留；
- Tool Binding 只返回已经约定为非敏感的 Mapping Config，不解析 Secret Reference Value。

## 7. Contract 与验证

- Admin OpenAPI 从 13 个 Operation 扩展为 27 个稳定 Operation；
- `contracts/admin.openapi.json` 已重新导出；
- Contract Test 校验 Operation ID、Pagination Envelope、HTTP-only Literal 与敏感字段缺失；
- PostgreSQL Integration Test 构造 Upstream、Import、Review、Tool、Binding、Approval、Embedding，并通过
  一次真实 MCP Call 生成 Execution、Attempt 与 Audit；
- 同一测试验证第二 Tenant 的 Upstream 无法由当前 Tenant 读取；
- 全量门禁结果见本次提交记录。

> W3 Addendum：为保证 Review/Publish 与 Catalog/Binding 页面刷新后可恢复，新增 `getToolVersion` 和
> `getToolVersionBinding`，当前 Admin Contract 为 29 个稳定 Operation。

## 8. 下一步

进入 `W2｜React Shell`：创建唯一的 `web/` 应用，锁定 pnpm/Node/Hey API 版本，从当前 Contract 生成 Fetch
SDK，并建立 Router、TanStack Query、Problem Details Client、Local Development Admin Banner 与基础页面状态。
