# S2-6｜S2 收口与 Control Plane 接缝验收

> 日期：2026-08-26  
> 范围：ActorContext、Registry 写用例、Runtime UoW Factory、Local Admin Sub-App、
> Admin REST → PostgreSQL → MCP 总验收、S2 阶段收口

## 1. 收口目标

S2-5 前，业务能力只能通过 Test 或直接调用 Use Case 驱动。S2-6 提供最小正式入口：

```text
Admin REST
→ Register Upstream
→ Import Local OpenAPI
→ Inspect Job/Operations
→ Review Operation
→ Submit ToolVersion Review
→ Publish
→ FTS Search
→ MCP tools/list 验收
```

不建设复杂 UI；FastAPI OpenAPI/Swagger 页面作为当前本地管理界面。

## 2. ActorContext

Control Plane 不是 MCP Request，不能伪造 `protocol_era=modern`。共享上下文拆为：

```text
ActorContext
├── request_id / trace_id
├── tenant_id / principal_id
└── authn_method

RequestContext extends ActorContext
├── protocol_version / protocol_era
└── agent/run/policy fields
```

Import、Review、Publish、Search 等 Application Command 依赖 `ActorContext`；MCP `tools/list` 继续使用
完整 `RequestContext`。

## 3. Registry 写链路

新增：

- `RegisterUpstream`；
- `UpdateUpstream`；
- `DisableUpstream`；
- `ListUpstreams`；
- Registry Unit of Work；
- InMemory/SQLAlchemy Add/Save/Name Query。

注册后 Upstream 为 Active，可以立即进入 Local OpenAPI Import。

安全校验：

- Namespace 必须是稳定小写标识；
- HTTP Endpoint 只允许 `http/https`；
- Endpoint 禁止 UserInfo Credential；
- Config 递归拒绝 Token、Password、API Key、Cookie、Client Secret、Private Key 等 Key；
- `(tenant_id, namespace, name)` 冲突返回稳定 `upstream_conflict`；
- Tenant 始终由 ActorContext 决定。

## 4. Runtime 延迟 UoW Factory

App Factory 构造 Admin Use Case 时 Database Lifespan 尚未开始，不能提前取得 Session Factory。

```text
Runtime*UnitOfWorkFactory
→ 只保存 DatabaseRuntime Port
→ 每次 Command 执行时 require_session_factory()
→ 创建新的 SQLAlchemy UoW/AsyncSession
```

覆盖 Catalog、OpenAPI Import、Review、Registry 四类 UoW，保证 App 构造无数据库 I/O。

## 5. 独立 Admin Sub-Application

路由：

| Method | Path | 用途 |
|---|---|---|
| POST | `/admin/upstreams` | 注册 Upstream |
| GET | `/admin/upstreams` | 列出当前 Tenant Upstream |
| PUT | `/admin/upstreams/{id}` | 更新非敏感配置 |
| POST | `/admin/upstreams/{id}/disable` | 禁用 Upstream |
| POST | `/admin/openapi/imports` | 提交 Local Fixture Import |
| GET | `/admin/openapi/imports/{id}` | 查看 Job 与 Operations |
| POST | `/admin/openapi/operations/{id}/review` | Accept 并生成 Draft |
| POST | `/admin/tool-versions/{id}/submit-review` | Draft → Review |
| POST | `/admin/tools/{tool_id}/versions/{version_id}/publish` | 原子发布 |
| GET | `/admin/catalog/search?q=...` | PostgreSQL FTS |

Admin 是独立 FastAPI Sub-App，Expected Error Handler 只注册在 `/admin`，不会把 MCP 异常翻译成普通
HTTP JSON。宿主注册顺序为 Health → Admin Mount → MCP Catch-All Mount。

## 6. Local 身份安全边界

当前没有 S3 Authentication，因此：

- `control_plane_enabled` 默认 False；
- 只使用 Settings 中固定 `local_tenant_id` / `local_admin_principal_id`；
- 客户端 `X-NexusMCP-Tenant-ID` 等 Header 被忽略；
- 每个请求生成内部 Request/Trace ID；
- `production + control_plane_enabled` 被 Settings 拒绝；
- S3 前不得暴露到非可信网络。

Tenant 属于部署/Identity 前置状态，当前由 README 的显式本地 Bootstrap SQL 创建，不在启动时静默 Seed。

## 7. S2 总验收 E2E

Integration Test 只预置 Tenant，其余全部通过 HTTP：

```text
POST Admin Register Upstream
→ Duplicate Conflict Mapping
→ PUT Update
→ GET List
→ POST Import Employee Fixture
→ GET Completed Job + 3 Operations
→ POST Review getEmployee
→ POST Submit Version Review
→ POST Publish
→ GET FTS Search employee
→ MCP Client tools/list
→ POST Disable Upstream
```

验证结果：

- Forged Tenant Header 不改变数据库 Tenant；
- Error Code/HTTP Status 安全映射；
- Review Response 返回 Publish 所需 Schema/Binding Digest；
- Admin FTS 找到 `directory.get_employee`；
- 同一进程 MCP `tools/list` 返回 Published Tool；
- Admin 与 MCP Transport Contract 互不污染。

## 8. S2 完成范围

S2 已形成：

- PostgreSQL/Alembic/Repository/UoW；
- Registry HTTP Upstream；
- Local OpenAPI Reader/Parser/Import Job；
- Operation Review、ToolVersion Review、Publish；
- 三场景 7 接口通用性证明；
- Published Catalog 与 MCP `tools/list`；
- PostgreSQL Weighted FTS/GIN；
- Local Admin Control Plane；
- Error/Logging/Health/CI 基线。

## 9. 有意留给 S3

- Authentication/JWT/OAuth；
- Principal/Policy；
- CredentialBinding/SecretReference；
- Approval；
- Audit/Execution Record；
- `tools/call` HTTP/Remote MCP Executor；
- Retry/Idempotency/Unknown Outcome；
- Production Admin 暴露；
- Remote URL OpenAPI Fetch。

## 10. 代码位置

```text
src/nexusmcp/shared/request_context.py
src/nexusmcp/modules/registry/use_cases.py
src/nexusmcp/modules/registry/ports.py
src/nexusmcp/bootstrap/persistence_factories.py
src/nexusmcp/interfaces/admin/app.py
src/nexusmcp/bootstrap/app.py
tests/unit/modules/registry/test_registry_use_cases.py
tests/integration/persistence/test_admin_control_plane.py
```

## 11. 下一步

进入 `S3｜Gateway 与治理执行链`，先冻结 `tools/call` 的最小执行模型、Policy Decision、Credential
Injection、Approval、Execution Outcome 和 Audit 边界，再选择第一条只读 Tool 执行切片。
