# W0｜Admin API Contract 固化

> 日期：2026-08-27  
> 状态：完成

## 1. 目标

在生成 Web API Client 前，把现有 Local Admin API 从“可以调用”提升为“可稳定生成客户端的公开契约”：

- Route 使用稳定且唯一的 `operationId`；
- OpenAPI 可以脱离运行中的数据库和 HTTP Server 确定性导出；
- Expected Error 与 Request Validation Error 使用同一种 Problem Details；
- 普通资源列表统一分页 Envelope；
- 未实现的 Remote MCP 不进入公开能力；
- 提交 Contract Snapshot，并用测试阻止无意 Drift。

W0 不新增 Dashboard、Execution、Audit 等查询业务；这些属于 W1。

## 2. 已冻结的契约

### 2.1 Operation ID

| Method | Path | Operation ID |
|---|---|---|
| POST | `/admin/upstreams` | `registerUpstream` |
| GET | `/admin/upstreams` | `listUpstreams` |
| PUT | `/admin/upstreams/{upstream_service_id}` | `updateUpstream` |
| POST | `/admin/upstreams/{upstream_service_id}/disable` | `disableUpstream` |
| POST | `/admin/openapi/imports` | `submitOpenApiImport` |
| GET | `/admin/openapi/imports/{import_job_id}` | `getOpenApiImport` |
| POST | `/admin/openapi/operations/{operation_id}/review` | `reviewImportedOperation` |
| POST | `/admin/tool-versions/{tool_version_id}/submit-review` | `submitToolVersionReview` |
| POST | `/admin/tools/{tool_id}/versions/{tool_version_id}/publish` | `publishToolVersion` |
| GET | `/admin/catalog/search` | `searchCatalog` |
| GET | `/admin/approvals/{approval_id}` | `getApproval` |
| POST | `/admin/approvals/{approval_id}/approve` | `approveApproval` |
| POST | `/admin/approvals/{approval_id}/reject` | `rejectApproval` |

`operationId` 是 Hey API 生成函数名的主要来源。业务含义不变时不得随意重命名；确需修改时必须同时更新
Snapshot、前端 Generated SDK 与 Contract Test。

### 2.2 Problem Details

Expected Error 与 FastAPI 请求校验错误统一返回 `application/problem+json`：

```json
{
  "type": "urn:nexusmcp:error:upstream_not_found",
  "title": "Request rejected",
  "status": 404,
  "detail": "The requested upstream service was not found.",
  "code": "upstream_not_found",
  "request_id": "..."
}
```

字段职责：

- `status`：HTTP 状态码的 Body 镜像；
- `code`：前端可依赖的稳定业务分支；
- `detail`：安全的人类可读信息，不作为程序判断依据；
- `request_id`：与服务端 Log 对照；
- `errors[]`：仅校验失败时返回 `field/code/detail`，不回显用户提交的 Value。

### 2.3 普通列表与搜索结果

普通资源列表采用 Offset Pagination：

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

默认 `limit=50`，最大 `100`。W1 的 Upstream、Import、Tool、Approval、Execution 和 Audit 列表沿用
`items + page`，但为每个资源定义明确 Response Model，不依赖难以阅读的匿名 Generic Schema。

`/catalog/search` 是相关性 Top-K Search，不是后台资源浏览，因此继续返回有序命中数组，并使用 `limit` 表达
候选数量。

### 2.4 Date、ID、Enum 与 Nullable

- 时间统一由 OpenAPI 声明为 `string/date-time`，语义为带时区时间；
- NexusMCP 领域 ID 是带类型前缀的 opaque string，不向前端承诺 UUID 格式；
- Enum 使用 OpenAPI Enum 生成 TypeScript Union，前端不自行复制常量；
- `null` 表示字段在当前业务状态下确实不存在；缺失字段不用于表达同一种业务含义。

### 2.5 Remote MCP

公开注册 Schema 的 `service_type` 与 `transport_type` 只允许 `http`。Domain 中保留的
`remote_mcp` Enum 是未来预留，不等于当前功能。绕过生成客户端提交未支持值时，后端返回：

```json
{
  "status": 501,
  "code": "feature_not_enabled"
}
```

## 3. Contract Export 与 Drift Gate

导出命令：

```powershell
uv run nexusmcp export-admin-openapi --output contracts/admin.openapi.json
```

导出过程只组装 Application/Route/Schema，不启动 Lifespan，也不连接 PostgreSQL。JSON 使用固定缩进、Key
排序与换行，因此相同源码应产生逐字节一致结果。

正式快照位于 `contracts/admin.openapi.json`。Contract Test 会重新构建文档并与快照比较；未来 CI 再结合
`pnpm api:generate` 检查 Generated SDK Drift。

## 4. Web 路由与首批字段草图

| Web Route | 主数据 | W1 所需 API |
|---|---|---|
| `/` | Count、健康状态、最近异常 | Dashboard Aggregate |
| `/upstreams` | Namespace、Owner、Endpoint、Status | List/Detail/Register/Update/Disable |
| `/imports` | Source、Status、Conflict、Operations | List/Detail/Review Queue |
| `/catalog` | Name、Version、Visibility、Side Effect | List/Detail/Version/Binding |
| `/approvals` | Principal、Tool、Status、Expiry | List/Detail/Approve/Reject |
| `/executions` | Tool、Principal、Status、Latency | List/Detail/Attempts/Audit |
| `/search-lab` | Query、Strategy、Rank、Index Version | Lexical/Hybrid Search |

页面展示的是后端状态机的 Projection，不在浏览器复制审批、发布或策略判断。

## 5. 验收结果

- 13 个现有 Admin Operation 具有稳定唯一 ID；
- Contract 只暴露 HTTP/OpenAPI Upstream；
- Expected/Validation Error 均进入 OpenAPI Problem Details Response；
- Upstream List 已采用统一 Pagination Envelope；
- Contract 可以无数据库、无网络导出且连续两次结果一致；
- Contract、Unit 与真实 PostgreSQL Admin Integration Test 通过；
- 全量门禁结果见本次提交记录。

## 6. 下一步

进入 `W1｜Admin Query API`：先冻结公共 Query/Pagination Input，再实现 Dashboard、Upstream Detail、Import
List、Catalog Detail、Approval List、Execution/Audit 等 Web 所需读模型。

