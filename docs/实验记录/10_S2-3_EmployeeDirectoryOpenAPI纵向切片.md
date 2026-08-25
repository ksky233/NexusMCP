# S2-3｜Employee Directory OpenAPI 首条纵向切片验收

> 日期：2026-08-25  
> 范围：Fake API、Local OpenAPI Reader、Parser/Normalizer、Import Job、Operation Review、
> Draft/Review/Publish、PostgreSQL → MCP Catalog E2E

## 1. 验收链路

```text
Employee Directory openapi.json
→ LocalOpenApiDocumentReader
→ OpenApiParser
→ OpenApiImportJob + 3 ImportedOperation
→ Review getEmployee
→ Disabled Tool + Draft ToolVersion + Draft ToolBinding
→ Submit ToolVersion Review
→ PublishTool
→ Active Tool + Published Version/Binding
→ MCP Client tools/list
→ directory.get_employee
```

E2E 没有直接 Seed Published Tool；每个状态都通过正式 Use Case 和 PostgreSQL Repository 产生。

## 2. Employee Directory Fake API

Fake API 位于 `examples/upstream_apis/employee_directory`，Core 不 import Demo 模块。

| Operation | 参数覆盖 | 候选 Tool |
|---|---|---|
| `GET /employees/{employee_id}` | Path、Required | `directory.get_employee` |
| `GET /employees` | Query、Enum | `directory.list_employees` |
| `POST /employees/search` | Header、Nested Body、Enum、Required | `directory.search_employees` |

POST Search 使用 `x-nexusmcp-side-effect: read_only`，证明副作用不能只靠 HTTP Method 猜测。Fake API
只使用内存数据，不需要真实员工系统、Token 或网络服务。

## 3. Local Document Reader

第一版只启用 `local_fixture`：

- Source Resolve 后必须仍位于 Allowed Root，拒绝 Traversal/Symlink Escape；
- 只允许 JSON，默认最大 1 MiB；
- 原始 Bytes 计算 SHA-256 Source Digest；
- Root 必须是 JSON Object；
- 不发起网络请求，因此没有 SSRF 面；
- 完整文档不保存到数据库。

## 4. Parser 与 Normalized Operation

首版支持 OpenAPI `3.0.x` / `3.1.x`：

- Path/Operation Parameter 合并；
- Path、Query、Header；
- JSON Request Body 和 2xx JSON Response；
- Local JSON Pointer `$ref`；
- Nested Object/Array、Required、Enum；
- Operation Allowlist、Security Requirement 名称/Scope；
- `x-nexusmcp-side-effect`；
- CamelCase Operation ID → snake_case Tool Name。

标准化结果包含：

```text
parameters
request_body
responses
tool_input_schema
tool_output_schema
side_effect
generated_tool_name
```

安全/停止边界：

- `example/examples` 不进入 Normalized JSON；
- Remote `$ref` 被拒绝；
- Cyclic `$ref` 和超深引用被拒绝；
- Cookie、非 JSON Body、Binary Response 标记 Unsupported；
- Missing Operation ID、Name Collision 作为 Review Conflict，不静默发布。

## 5. Import Job 事务

```text
事务外：读取 Local Fixture + Source Digest

事务 A：校验 Upstream → 创建 Validating Job → Commit
事务 B：锁定 Job → Parsing → Commit
事务外：Parse / Normalize
事务 C：写入 Operations → Completed → Commit
```

解析失败使用独立短事务标记 `failed`，只保存安全 `error_summary`，不保存 Traceback 或完整文档。

## 6. Review、Draft 与 Publish

`ReviewImportedOperation` 在一个事务中协调 Import、Catalog、Binding 与 Upstream Repository：

1. Lock Pending Operation，拒绝 Conflict；
2. Lock/验证 Active Upstream；
3. Lock 或创建稳定 Tool Identity；
4. 在 Tool Row Lock 下分配下一个 Version Number；
5. 从 Normalized Schema 创建 Draft ToolVersion；
6. 从参数位置/Body Mapping 创建 Draft HTTP Binding；
7. 计算 Schema/Binding Digest；
8. Operation 标记 Accepted 并回写 Draft IDs；
9. Commit。

新 Tool 初始 Disabled。Operation Accepted 与 ToolVersion Review 是两个明确动作：
`SubmitToolVersionForReview` 将 Draft Version 转为 Review，之后才调用既有 `PublishTool` 激活 Tool。

## 7. PostgreSQL 与 MCP E2E 证据

Integration Test 实际执行：

- 创建 Tenant/Active Upstream；
- 导入静态 Fixture，Job Completed，保存 3 个 Pending Operation；
- 只接受 `getEmployee`；
- 生成 Draft Tool/Version/Binding；
- Submit Review、Publish；
- 启动正式 Database Lifespan；
- MCP Client 调用 `/mcp` `tools/list`；
- 只返回 `directory.get_employee@1`。

另外两个 Pending Operation 不进入 Catalog，证明 ImportedOperation 不等于 Published Tool。

## 8. 新增领域与 Port

```text
OpenApiImportJob
ImportedOperation
ParsedOpenApiDocument / ParsedOperation
OpenApiDocumentReader
OpenApiImportRepository / OpenApiImportUnitOfWork
ReviewUnitOfWork
IdentifierGenerator
```

SQLAlchemy Model 仍只在 Adapter 层；Parser、Domain、Use Case 不 import SQLAlchemy/FastAPI/MCP 类型。

## 9. 当前有意不做

- Remote URL Fetch、Upload、YAML、External `$ref`；
- Callback/Webhook、Cookie、Multipart、Binary；
- 自动接受全部 Operation；
- Admin Review REST/UI；
- `tools/call` HTTP Executor；
- Import Job 重用/去重策略；
- Operations/Inventory Demo 和 FTS。

## 10. 代码位置

```text
examples/upstream_apis/employee_directory/app.py
examples/upstream_apis/employee_directory/openapi.json
src/nexusmcp/modules/openapi_import/domain.py
src/nexusmcp/modules/openapi_import/parser.py
src/nexusmcp/modules/openapi_import/import_openapi.py
src/nexusmcp/modules/openapi_import/review.py
src/nexusmcp/modules/openapi_import/ports.py
src/nexusmcp/modules/openapi_import/review_ports.py
src/nexusmcp/modules/openapi_import/adapters/*
src/nexusmcp/modules/catalog/review.py
tests/contract/openapi/test_employee_directory_fixture.py
tests/integration/persistence/test_employee_directory_openapi_slice.py
```

## 11. 下一步

进入 `S2-4｜Operations / Inventory 通用性验证`：

1. 各增加约 2 个轻量接口与静态 Fixture；
2. 复用相同 Reader/Parser/Import/Review/Publish Pipeline；
3. Core 不允许出现 Demo 场景名称分支；
4. 覆盖 Header/Body、写副作用和跨服务 Operation Name Collision；
5. 三个 Namespace 的 Published Tool 同时通过 MCP Catalog 可见；
6. 完成后再加入 PostgreSQL FTS。
