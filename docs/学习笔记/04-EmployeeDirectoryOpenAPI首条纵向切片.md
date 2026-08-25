# Employee Directory OpenAPI 首条纵向切片：从企业 API 到 MCP Tool

> 对应阶段：S2-3  
> 学习目标：理解一份 OpenAPI 文档如何经过 Import、Review、Publish，最终成为 MCP Client 可发现的
> Tool。  
> 范围说明：本文只沉淀 Employee Directory 这一条教学切片；后续 Operations/Inventory 不再重复创建
> 同类逐步讲解。

## 1. 先理解“纵向切片”

横向开发通常一次只完成某一层：

```text
只写数据库表
只写 Parser
只写 REST Endpoint
只写 MCP Handler
```

纵向切片选择一个很小的真实场景，然后贯穿所有必要层：

```text
OpenAPI Fixture
→ Reader
→ Parser
→ Domain
→ Use Case
→ Repository / Unit of Work
→ PostgreSQL
→ MCP Interface
→ MCP Client 可观察结果
```

Employee Directory 切片只发布一个 `getEmployee`，但它证明“企业 API → MCP Tool”的主链真实可行。

## 2. 最终要证明什么

输入是一条普通企业 HTTP API：

```text
GET /employees/{employee_id}
operationId: getEmployee
```

输出是 MCP Client 能发现的 Tool：

```text
directory.get_employee@1
```

中间不能直接把 OpenAPI Operation 原样返回给 Agent，而要经历治理生命周期：

```text
Employee Directory openapi.json
→ OpenAPI Import Job
→ Imported Operation
→ Operation Review
→ Draft ToolVersion + Draft ToolBinding
→ ToolVersion Review
→ Publish
→ Published Catalog
→ MCP tools/list
```

## 3. 场景资产

### 3.1 Fake API

代码：[`examples/upstream_apis/employee_directory/app.py`](../../examples/upstream_apis/employee_directory/app.py)

Fake API 只使用内存数据，提供三个接口：

| Operation | 覆盖的 OpenAPI 特性 | 候选 MCP Tool |
|---|---|---|
| `GET /employees/{employee_id}` | Path、Required | `directory.get_employee` |
| `GET /employees` | Query、Enum | `directory.list_employees` |
| `POST /employees/search` | Header、Nested Body、Enum、`$ref` | `directory.search_employees` |

三个接口的目的不是建设完整员工系统，而是用很少的代码覆盖不同参数形态。

### 3.2 静态 OpenAPI Fixture

文件：[`examples/upstream_apis/employee_directory/openapi.json`](../../examples/upstream_apis/employee_directory/openapi.json)

静态 Fixture 是 Import Pipeline 的输入证据。即使 Fake API 代码以后变化，测试仍明确知道本次导入使用的
OpenAPI 版本和内容。

Fixture 包含：

```text
OpenAPI 3.1.0
Path / Query / Header Parameter
Request Body
Required
Enum
Nested $ref
JSON Response
x-nexusmcp-side-effect
```

Fake API 位于 `examples`，NexusMCP Core 不允许 import 它。Core 只能看到普通 OpenAPI 文档，因此没有
`if employee_directory` 之类的场景分支。

## 4. 全链路总览

```text
Control Plane：接入和发布

openapi.json
    ↓
LocalOpenApiDocumentReader
    ↓
OpenApiParser
    ↓
OpenApiImportJob
    ├── listEmployees
    ├── searchEmployees
    └── getEmployee
            ↓ Review Accepted
Tool + Draft ToolVersion + Draft ToolBinding
            ↓ Submit Version Review
Review ToolVersion + Draft Binding
            ↓ Publish
Active Tool + Published Version + Published Binding


Data Plane：发现

MCP Client
    ↓ tools/list
ListVisibleTools
    ↓
PublishedToolReader
    ↓
PostgreSQL Published Projection
    ↓
directory.get_employee
```

## 5. 第一步：安全读取 Local Fixture

实现：[`local_document_reader.py`](../../src/nexusmcp/modules/openapi_import/adapters/local_document_reader.py)

Port：

```python
class OpenApiDocumentReader(Protocol):
    async def read(self, source_ref: str) -> OpenApiDocument: ...
```

当前 Adapter 只允许受控目录中的 JSON：

```text
employee_directory/openapi.json
```

Reader 负责：

- `Path.resolve()`；
- 确认最终路径仍位于 Allowed Root；
- 拒绝 `../` Traversal 和 Symlink Escape；
- 只允许 `.json`；
- 默认最大 1 MiB；
- 计算原始 Bytes 的 SHA-256；
- 解析 JSON；
- 确认根节点是 Object。

输出：

```text
OpenApiDocument
├── source_ref
├── source_digest
└── content
```

当前 Reader 不访问网络，因此没有 Remote URL Fetch 的 SSRF 风险。

## 6. 第二步：解析与标准化

实现：[`parser.py`](../../src/nexusmcp/modules/openapi_import/parser.py)

Parser 是纯业务服务：

```text
OpenAPI Mapping
→ ParsedOpenApiDocument
→ ParsedOperation[]
```

它不依赖文件、SQLAlchemy、FastAPI 或 MCP SDK。

### 6.1 Local `$ref`

原始文档可能只有：

```json
{
  "$ref": "#/components/schemas/Employee"
}
```

Parser 使用 JSON Pointer 找到 Component，再递归展开 Nested Object/Array/Enum。

当前边界：

- Local `$ref`：支持；
- Remote `$ref`：拒绝；
- Cyclic `$ref`：拒绝；
- 超过深度限制：拒绝；
- 找不到 Pointer：文档无效。

### 6.2 参数标准化

OpenAPI Path Parameter：

```json
{
  "name": "employee_id",
  "in": "path",
  "required": true,
  "schema": {"type": "string"}
}
```

标准化后：

```json
{
  "argument_name": "employee_id",
  "upstream_name": "employee_id",
  "location": "path",
  "required": true,
  "schema": {"type": "string"}
}
```

这里同时保存 MCP 参数名和上游参数名，因为未来执行时需要把 Tool Argument 放回正确位置。

Header：

```text
X-Directory-Region
→ x_directory_region
```

### 6.3 生成 Tool Input Schema

`getEmployee` 生成：

```json
{
  "type": "object",
  "properties": {
    "employee_id": {
      "type": "string",
      "minLength": 1
    }
  },
  "required": ["employee_id"],
  "additionalProperties": false
}
```

这份 Schema 后面进入 ToolVersion，最终成为 MCP `tools/list` 的 `inputSchema`。

### 6.4 生成候选名称

```text
namespace = directory
operationId = getEmployee

getEmployee → get_employee
→ directory.get_employee
```

### 6.5 Conflict 不等于整个 Job 失败

单个 Operation 可以标记：

```text
none
name_collision
missing_operation_id
unsupported
```

例如两个接口生成同一个 Tool Name，就把两个 Operation 都标记为 `name_collision`，交给 Review，而不是
随机覆盖。

## 7. 第三步：Import Job 与短事务

实现：[`import_openapi.py`](../../src/nexusmcp/modules/openapi_import/import_openapi.py)

```text
事务外
读取 Fixture、计算 Source Digest

事务 A
校验 Upstream Active/Tenant
→ 创建 Validating Job
→ Commit

事务 B
锁定 Job
→ Parsing
→ Commit

事务外
Parser / Normalizer

事务 C
锁定 Job
→ 写入全部 ImportedOperation
→ Completed
→ Commit
```

Parser 可能耗时，因此不能在解析期间一直占有数据库事务。

### 7.1 Job 保存什么

```text
source_type
source_ref
source_digest
openapi_version
operation_allowlist
status
created_by
started_at / completed_at
```

数据库不保存完整 OpenAPI 文档。

### 7.2 Operation 保存什么

```text
method / path / operation_id
operation_key
generated_tool_name
normalized_operation_json
conflict_status
review_status
draft_tool_version_id
draft_tool_binding_id
```

最重要的区别：

> ImportedOperation 是候选事实，不是 Agent 已经能调用的 Tool。

解析失败时 Job 进入 `failed`，只保存安全 `error_summary`，不保存 Traceback 或完整文档。

## 8. 第四步：Review ImportedOperation

实现：[`review.py`](../../src/nexusmcp/modules/openapi_import/review.py)

E2E 只接受：

```text
getEmployee
```

另外两个 Operation 保持 Pending，所以不会误入 Catalog。

Review 使用一个跨上下文 UoW：

```text
ReviewUnitOfWork
├── imports
├── catalog
├── bindings
└── upstreams
```

事务内执行：

1. Lock ImportedOperation；
2. 拒绝带 Conflict 的 Operation；
3. Lock 并验证 Active Upstream；
4. Lock 或创建稳定 Tool Identity；
5. 在 Tool Lock 下计算下一个 Version Number；
6. 创建 Draft ToolVersion；
7. 创建 Draft HTTP ToolBinding；
8. 计算 Schema/Binding Digest；
9. Operation 标记 Accepted 并回写 Draft IDs；
10. Commit。

生成结果：

```text
Tool
├── directory.get_employee
└── disabled

ToolVersion@1
├── input/output schema
├── schema_digest
├── read_only
└── draft

ToolBinding
├── GET
├── /employees/{employee_id}
├── Path Parameter Mapping
├── binding_digest
└── draft
```

新 Tool 初始 Disabled，因为还没有 Published Version。

相同 Accepted Operation 再次 Review 会返回原 Draft IDs，不重复创建对象。

## 9. 为什么有两层 Review

```text
ImportedOperation Review
= 这个 API Operation 是否值得转换成 Tool？

ToolVersion Review
= 生成后的 Schema、描述、副作用和 Binding 是否允许发布？
```

Operation Accepted 后，ToolVersion 仍是 Draft。

实现：[`catalog/review.py`](../../src/nexusmcp/modules/catalog/review.py)

```text
Draft ToolVersion
→ SubmitToolVersionForReview
→ Review ToolVersion
```

只有 Review ToolVersion 才能进入 Publish。

## 10. 第六步：Publish

复用上一阶段的 `PublishTool`：

```text
Lock Tool / Version / Binding / Upstream
→ 验证 Tenant、状态、Digest、版本顺序
→ Version Published
→ Binding Published
→ Tool Active
→ Commit
```

如果任一步失败，所有状态一起 Rollback。

## 11. 第七步：MCP Catalog

Data Plane 执行：

```text
MCP Client
→ /mcp tools/list
→ RequestContext Tenant
→ ListVisibleTools
→ PublishedToolReader
→ PostgreSQL Join Query
```

Query 只返回：

```text
Tool = active
ToolVersion = published
ToolBinding = published
Tenant 全部一致
```

因此最终只看到：

```text
directory.get_employee@1
```

另外两个 Pending Operation 已经导入数据库，但没有 Review/Publish，所以不会出现。

## 12. 四个限界上下文的所有权

```text
Registry
└── UpstreamService

OpenAPI Import
├── OpenApiImportJob
└── ImportedOperation

Catalog
├── Tool
├── ToolVersion
└── PublishedTool

Connectors
└── ToolBinding
```

对应协作：

```text
ImportOpenApi
→ Import + Registry

ReviewImportedOperation
→ Import + Registry + Catalog + Connectors

PublishTool
→ Catalog + Connectors + Registry

ListVisibleTools
→ Catalog Read Model
```

多个 UoW 不是重复设计，而是每个 Use Case 只暴露它真正需要参与同一事务的 Repository。

## 13. 推荐阅读顺序

1. [`test_employee_directory_openapi_slice.py`](../../tests/integration/persistence/test_employee_directory_openapi_slice.py)
2. [`openapi.json`](../../examples/upstream_apis/employee_directory/openapi.json)
3. [`parser.py`](../../src/nexusmcp/modules/openapi_import/parser.py)
4. [`import_openapi.py`](../../src/nexusmcp/modules/openapi_import/import_openapi.py)
5. [`openapi_import/review.py`](../../src/nexusmcp/modules/openapi_import/review.py)
6. [`catalog/review.py`](../../src/nexusmcp/modules/catalog/review.py)
7. [`catalog/publish.py`](../../src/nexusmcp/modules/catalog/publish.py)
8. [`sqlalchemy_reader.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_reader.py)

先读 E2E 可以看到业务故事，再进入每个组件，不容易陷入单个 Repository 或 Mapping 细节。

## 14. 当前边界

本切片有意不做：

- URL Fetch、Upload、YAML、External `$ref`；
- Multipart、Cookie、Binary、Callback；
- Admin Review UI/API；
- 自动接受全部 Operation；
- Import Job 复用/去重；
- `tools/call` HTTP Executor；
- Operations/Inventory 和 FTS。

## 15. 最后记住三句话

1. OpenAPI Operation 只是候选事实，不是 Published Tool。
2. ToolDefinition 与 HTTP 执行细节分离为 ToolVersion 和 ToolBinding。
3. 只有经过 Import、Operation Review、Version Review 和 Publish，Tool 才会进入 MCP Catalog。
