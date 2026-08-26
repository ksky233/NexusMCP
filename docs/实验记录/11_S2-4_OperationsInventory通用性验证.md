# S2-4｜Operations / Inventory 通用性验证验收

> 日期：2026-08-25  
> 范围：Operations/Inventory Fake API 与 Fixture、Namespace 隔离、副作用分类、三场景共用
> Import/Review/Publish、PostgreSQL → MCP Catalog E2E、Core Demo Isolation Guard

## 1. 目标

S2-3 证明 Employee Directory 可以接入；S2-4 证明实现没有对第一个业务场景过拟合。

```text
Employee Directory ─┐
IT Operations ──────┼→ 同一 Reader / Parser / Import / Review / Publish / Catalog
Inventory ──────────┘
```

本阶段没有修改 `src/nexusmcp` 的 OpenAPI 主流程，只增加 Demo 资产、通用性测试和阶段文档。

## 2. 七个轻量接口

| Namespace | Operation | 候选 Tool | Side Effect |
|---|---|---|---|
| `directory` | `GET /employees/{employee_id}` | `directory.get_employee` | `read_only` |
| `directory` | `GET /employees` | `directory.list_employees` | `read_only` |
| `directory` | `POST /employees/search` | `directory.search_employees` | `read_only` Extension |
| `ops` | `GET /incidents/{incident_id}` | `ops.get_status` | `read_only` |
| `ops` | `POST .../acknowledge` | `ops.acknowledge_incident` | `idempotent_write` |
| `inventory` | `GET /inventory/{sku}` | `inventory.get_status` | `read_only` |
| `inventory` | `POST .../reservations` | `inventory.reserve_stock` | `non_idempotent_write` |

Operations 表达 IT 运维事件管理；Inventory 表达 SKU/仓库库存与库存预留。它们只是独立 Fake
Upstream，不属于 NexusMCP Core Domain。

## 3. Operations 验证点

Operations Fake API 覆盖：

- Incident Path Parameter；
- Required `X-Operator-Id` Header；
- JSON Acknowledge Body；
- Incident Status/Severity Enum；
- `idempotent_write`。

重复确认同一个 Incident 返回相同业务结果，用于表达幂等写入语义。

## 4. Inventory 验证点

Inventory Fake API 覆盖：

- SKU Path Parameter；
- Required Warehouse Query Parameter；
- Reservation Nested Body；
- Quantity Minimum/Maximum；
- Stock Status Enum；
- `non_idempotent_write`。

Reservation 表示创建新的库存占用记录，因此默认不能像查询一样盲目重试。

## 5. 同名 Operation ID 与 Namespace

Operations 和 Inventory 故意同时使用：

```text
operationId = getStatus
```

Parser 没有全局硬编码改名，而是使用 Upstream Namespace：

```text
ops + getStatus       → ops.get_status
inventory + getStatus → inventory.get_status
```

两个 Tool 在同一 Tenant 中合法共存，证明 Namespace 是稳定治理边界，而不是展示标签。

同一 Namespace 内的重复名称仍会标记 `name_collision`，不会被 Namespace 机制掩盖。

## 6. 三场景共用 E2E

Integration Test 使用数据驱动 `Scenario`：

```text
namespace
name
source_ref
upstream_id
endpoint
```

对每个 Scenario 执行完全相同的函数：

```text
ImportOpenApi
→ List Imported Operations
→ ReviewImportedOperation
→ SubmitToolVersionForReview
→ PublishTool
```

没有 `if directory/ops/inventory` 分支。全部发布完成后，正式 MCP Client 一次获得：

```text
directory.get_employee
directory.list_employees
directory.search_employees
inventory.get_status
inventory.reserve_stock
ops.acknowledge_incident
ops.get_status
```

并额外验证：

- Directory POST Search 仍是 `read_only`；
- Operations Acknowledge 是 `idempotent_write`；
- Inventory Reserve 是 `non_idempotent_write`。

## 7. Core Isolation Guard

Architecture Contract 扫描 `src/nexusmcp/**/*.py` 的 AST：

- 禁止 import `examples.upstream_apis`；
- 禁止出现精确 Demo 场景字符串分支：`employee_directory`、`operations`、`inventory`。

这不是替代 Code Review，而是防止未来为了 Demo 快速加特例时破坏通用架构。

## 8. 当前有意不做

- 不为两个新 Demo 建立重复学习笔记；
- 不实现真实 Operations/Inventory 数据库；
- 不实现 `tools/call` 或上游 HTTP Executor；
- 不执行写 Tool，因此尚不测试 Retry/Approval；
- 不增加新的 Core Parser 分支；
- 不在本阶段实现 FTS。

## 9. 代码位置

```text
examples/upstream_apis/operations/app.py
examples/upstream_apis/operations/openapi.json
examples/upstream_apis/inventory/app.py
examples/upstream_apis/inventory/openapi.json
tests/contract/openapi/test_operations_inventory_fixtures.py
tests/contract/architecture/test_demo_isolation.py
tests/integration/persistence/test_multi_scenario_openapi_reuse.py
```

## 10. 下一步

进入 `S2-5｜Catalog PostgreSQL FTS`：

1. 冻结搜索文档字段与 Tenant/Visibility 过滤顺序；
2. 选择 Generated `tsvector` 或显式 Search Vector；
3. 增加 Alembic Migration/Gin Index；
4. 建立 `SearchPublishedTools` Query/Port；
5. 验证 Namespace、Name、Description、Tags 的 Keyword Search；
6. 确保 Draft/Disabled/Cross-Tenant Tool 不进入结果；
7. 保留未来 pgvector/RAG 扩展边界，不在当前加入 Embedding。
