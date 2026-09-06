# I03-1B｜Toolset PostgreSQL Schema 与 Adapter

> 状态：Completed
> 日期：2026-09-06
> 决策依据：[ADR-0020](../adr/0020-toolset-scoped-mcp-endpoints.md)
> Migration：`b8d1f3a4c520`

## 1. Schema

新增：

```text
toolset
toolset_member
toolset_access_grant
```

`toolset` 建立 Tenant+Slug Unique、Kind/Discovery/Status/Revision Check、Tenant+Status Index 和每 Tenant 一个
`all_published` 的 Partial Unique Index。

Member/Grant 使用 Composite Primary Key，并分别建立 Tenant+Tool、Tenant+Principal 查询 Index。FK 均为
RESTRICT，不允许删除仍被组合/授权事实引用的 Toolset/Tool/Tenant。

`tool_execution` 新增：

```text
mcp_scope_type
toolset_id
toolset_revision
```

Check Constraint 保证 Root 与 Toolset Scope 形状互斥。既有 Row 通过 Server Default 回填 Root；开发库实际 1 条
历史 Execution 已验证为 `root + null + null`。

## 2. ORM 与 Mapping

新增 Toolset/Member/Grant Model 和显式 Domain Mapping。Toolset Model 不复用带 `onupdate=now()` 的通用
TimestampMixin，因为 Aggregate UpdatedAt 由应用 Clock 决定；否则数据库会静默覆盖 Domain 时间，导致
Round-trip 不相等。

Execution Domain 增加：

```text
McpScopeType.ROOT
McpScopeType.TOOLSET
```

默认 Root 保持现有 Lifecycle/Test 兼容，Toolset Scope 必须同时提供 ID 与正 Revision。

## 3. Repository 与同事务 Catalog Reader

`SqlAlchemyToolsetRepository` 实现 I03-1A 共享 Contract：

- Aggregate Add/Save/Load；
- GetBySlug/GetAllPublished；
- ListByTenant/ListGrantedActive；
- GetForUpdate；
- Member/Grant 全集合原子替换；
- Tenant 与稳定 Identity 校验；
- PostgreSQL Unique Error 映射为 Adapter 边界错误。

跨模块 Adapter 放在 Infrastructure：

```text
SqlAlchemyToolsetUnitOfWork
├── SqlAlchemyToolsetRepository
└── SqlAlchemyToolsetCatalogReader
```

二者由同一 AsyncSession 构造。Catalog Reader 通过 Tool + Published ToolVersion Outer Join 返回：

```text
AVAILABLE + published_tool_version_id
TOOL_DISABLED
NO_PUBLISHED_VERSION
```

缺失 Tool 不伪装成 No Published Version，而是不返回 Snapshot，交给后续 Use Case 映射为 Invalid Member。

## 4. Migration 验证

开发数据库：

```text
upgrade a7c4e91d2f60 → b8d1f3a4c520  passed
alembic current                         b8d1f3a4c520
alembic check                           no drift
```

专用 Test Database：

```text
downgrade b8d1f3a4c520 → a7c4e91d2f60  passed
upgrade   a7c4e91d2f60 → b8d1f3a4c520  passed
alembic check                             no drift
```

Migration 只创建 Schema，不插入系统 Toolset/Grant。System Bootstrap 留在后续 Application Use Case。

## 5. PostgreSQL 证据

- SQLAlchemy Toolset Repository/UoW 通过与 InMemory 相同的共享 Contract；
- Toolset Row Lock 第二事务在 100ms Lock Timeout 下失败，证明 `FOR UPDATE` 生效；
- Catalog Reader 按请求顺序返回三种 Availability；
- Root/Toolset Execution Scope 完整 Round-trip；
- 数据库拒绝 `scope_type=toolset` 但缺少 Toolset ID/Revision 的非法 Row；
- Integration Persistence 全套通过；
- Public Demo Reset/E2E Seed 已纳入三张 Toolset Table。

## 6. 验证结果

```text
SQLAlchemy Repository Contract + Toolset PostgreSQL  24 passed
Integration Persistence                              60 passed / 1 paid external skipped
Migration Upgrade/Downgrade/Check                    passed
Ruff Lint/Format                                     passed
basedpyright                                         0 errors / 0 warnings
```

## 7. 下一步

`I03-1C｜Persistence Contract Close`：

- 汇总 InMemory/SQLAlchemy Contract；
- 检查 Revision/Lock/Atomic Replace 边界是否需要 Use Case 才能最终证明；
- 执行 InMemory Adapter 保留审查；
- 确认 I03-2 Admin Use Case 可以直接消费 UoW；
- 完成 I03-1 Persistence 收口。
