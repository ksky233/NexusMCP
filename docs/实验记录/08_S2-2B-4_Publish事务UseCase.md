# S2-2B-4｜Publish 事务 Use Case 验收

> 日期：2026-08-25  
> 范围：Publish Command/Result、Upstream Read Model/Repository、Digest、Clock、Domain Event、
> InMemory/PostgreSQL 原子事务测试

## 1. 目标

将已 Review 的 ToolVersion 与 Draft ToolBinding 原子发布，并保证任何校验、Flush 或 Commit 失败都
不会留下部分 Published 状态。

```text
PublishToolCommand
→ Lock Tool / Version / Binding / Upstream
→ Validate Tenant / State / Digest / Version Order
→ Retire + Disable Old
→ Publish New Version + Binding
→ Activate Tool
→ Commit
→ Return ToolPublished Event
```

本阶段不实现 Admin REST Endpoint、MCP Publish 方法、OpenAPI Review Use Case 或 Audit 持久化策略。

## 2. Command、Result 与 Event

`PublishToolCommand` 包含：

```text
RequestContext
tool_id
tool_version_id
expected_schema_digest
expected_binding_digest
```

Expected Digest 来自调用方看到并确认的 Review Snapshot；Use Case 同时重算当前 Schema/Binding
Digest。因此既能发现“Review 后数据改变”，也能发现数据库中保存的 Digest 与实际 JSON 不一致。

`PublishToolResult` 返回：

- `ToolPublished` Domain Event；
- 被 Retire 的旧 ToolVersion ID（首次发布为空）。

Event 包含 Tenant、Tool/Version/Binding、Canonical Name、Version、Actor、Request/Trace 和时间。
事件在数据库 Commit 成功后构造并返回，供未来 Audit/Outbox/Interface 处理；当前不宣称 Event
Delivery 与数据库事务原子。

## 3. Unit of Work 扩展

Publish 不只读取 Catalog 和 Binding，还必须确认 Upstream 在提交瞬间仍为 Active。因此
`CatalogUnitOfWork` 增加：

```text
uow.catalog
uow.bindings
uow.upstreams
```

三个 PostgreSQL Repository 共用同一个 AsyncSession。`UpstreamRepository.get_for_update()` 锁定
Upstream Row，防止 Publish 校验完成后被并发 Disable。

Binding Repository 新增 `get_by_tool_version_for_update()`，保证目标/旧 Binding 的状态切换不会与
其他发布流程并发穿透。

## 4. Registry 最小领域模型

为支持 Publish 的真实校验，Registry 增加：

- `UpstreamService`；
- `UpstreamServiceType`；
- `UpstreamStatus`；
- InMemory/SQLAlchemy `UpstreamRepository`。

此处只实现 Publish 真实需要的读取与行锁，不提前实现 Register/Update/Disable Use Case。

## 5. Digest

Schema Digest 使用以下 Canonical JSON：

```text
{
  input_schema,
  output_schema
}
```

Binding Digest 使用执行语义：

```text
{
  binding_type,
  upstream_service_id,
  binding_config
}
```

统一规则：UTF-8、Key Sort、无多余空白、禁止 NaN、SHA-256。Binding 不包含 Secret Value，
`imported_operation_id` 只属于来源证据，不进入执行语义 Digest。

## 6. Publish 前置条件

Use Case 验证：

- Tool、Version、Binding、Upstream 都属于 Command Tenant；
- Version 指向目标 Tool；
- Binding 精确指向目标 Version；
- Version 状态为 Review；
- Binding 状态为 Draft；
- Upstream 状态为 Active；
- Stored/Expected/Recalculated Schema Digest 三者一致；
- Stored/Expected/Recalculated Binding Digest 三者一致；
- 新 Version Number 大于当前 Published Version。

违反条件时使用 S2-2B-3.5 的协议无关错误：Invalid State、Tenant Boundary、Publish Conflict、
Upstream Not Active、Schema/Binding Digest Mismatch 等。

## 7. 原子切换顺序

```text
BEGIN
  Lock Tool
  Lock Target Version / Binding
  Lock Upstream

  Read + Lock Current Published Version / Binding
  Current Version  → Retired
  Current Binding  → Disabled
  Target Version   → Published
  Target Binding   → Published
  Tool              → Active
COMMIT
```

先 Flush 旧 Version 的 Retired 状态，再 Flush 新 Version 的 Published 状态，满足 PostgreSQL
“每个 Tool 最多一个 Published Version”的 Partial Unique Index。所有中间状态对其他事务不可见。

## 8. 测试证据

InMemory Unit Test 验证：

- 首次发布；
- 新版本替换旧版本；
- Invalid State 不落库；
- Expected Digest 改变被拒绝；
- Stored JSON 与 Digest 不一致被重算发现；
- Inactive/Cross-Tenant Upstream 被拒绝；
- Version Number 倒退被拒绝；
- Commit 失败后所有状态恢复。

PostgreSQL Integration Test 验证：

- 旧 Version/Binding 与新 Version/Binding 在真实数据库原子切换；
- Published Projection 只返回新 Version；
- 多次 Flush 后模拟 Commit 失败，整个 Transaction Rollback；
- 数据库 FK 允许、但业务禁止的 Cross-Tenant Upstream Binding 在写入前被拒绝。

## 9. 当前有意保留的边界

### 9.1 ImportedOperation Accepted

OpenAPI Import/Review 尚未实现，且手工/Remote MCP Binding 的 `imported_operation_id` 可以为空。因此
当前 Publish 信任 Draft 创建流程已经完成来源 Review；当 Import Pipeline 提供
`OpenApiImportRepository` 后，对非空 `imported_operation_id` 增加 Accepted 与 Draft ID 一致性校验。

### 9.2 Audit/Event Delivery

当前只在 Commit 后返回 `ToolPublished`。Audit 同库事务、Transactional Outbox 或异步 Sink 留给
ADR-0010，不在本阶段假装已经实现 Exactly-Once Event Delivery。

### 9.3 Interface Logging

Publish 仍是纯 Application Use Case，没有直接依赖 Logger。未来 Admin/MCP Interface 调用它时，最外层
边界使用 S2-2B-3.5 记录 `tool_publish_completed/rejected/failed`，避免 Use Case 与 Interface 重复日志。

## 10. 代码位置

```text
src/nexusmcp/modules/catalog/publish.py
src/nexusmcp/modules/catalog/events.py
src/nexusmcp/modules/catalog/digests.py
src/nexusmcp/modules/connectors/digests.py
src/nexusmcp/modules/registry/domain.py
src/nexusmcp/modules/registry/ports.py
src/nexusmcp/modules/registry/adapters/in_memory.py
src/nexusmcp/modules/registry/adapters/sqlalchemy_repository.py
src/nexusmcp/shared/clock.py
src/nexusmcp/infrastructure/clock.py
tests/unit/modules/catalog/test_publish_tool.py
tests/integration/persistence/test_postgresql_publish_tool.py
```

## 11. 下一步

进入 `S2-2B-5｜Database Bootstrap 与正式 Catalog Query`：

1. Application Lifespan 创建/释放 Async Engine；
2. Readiness 执行轻量数据库探针；
3. 正式运行根据 Settings 选择 PostgreSQL Repository；
4. MCP `tools/list` 从 PublishedTool Projection 读取真实数据库；
5. 保留显式 InMemory 注入供 Unit/Contract Test 使用；
6. 验证启动失败、数据库不可用和 Shutdown Dispose 行为。
