# S2-2B-1｜PostgreSQL 与 Migration 基线验收

> 状态：已完成
> 日期：2026-08-25
> 范围：数据库运行环境、Async Persistence 基础、ORM Model、Alembic Baseline 和真实 PostgreSQL 约束测试。

## 1. 技术基线

```text
PostgreSQL 18.6 Alpine
SQLAlchemy 2.0 Async
asyncpg
Alembic Async Environment
Docker Compose
```

Runtime 和 Alembic 使用同一个 `postgresql+asyncpg` Driver。

## 2. 本地隔离环境

```text
Container: nexusmcp-postgres-1
Host Port: 55432
Volume: nexusmcp_postgres_data

Databases:
- nexusmcp
- nexusmcp_test
```

项目 Container 不复用已有 `postgres-demo`，避免修改未知数据和本地/CI 版本不一致。

PostgreSQL 18+ Docker Image 要求 Volume 挂载到 `/var/lib/postgresql`，镜像会在其下创建按主版本区分的数据目录。

## 3. Persistence 基础

```text
infrastructure/persistence/base.py
infrastructure/persistence/engine.py
infrastructure/persistence/models.py
```

- Declarative Base 使用统一 Constraint Naming Convention；
- UUID 由应用生成；
- 时间使用 `timestamptz`；
- Async Session 不自动 Commit；
- Engine 启用 `pool_pre_ping`；
- Model 聚合器保证 Alembic Metadata 完整。

## 4. 首批 ORM Model

```text
tenant
upstream_service
openapi_import_job
imported_operation
tool
tool_version
tool_binding
```

Model 按状态所有权放在 Identity、Registry、OpenAPI Import、Catalog、Connectors 模块的 Adapter 中，没有建立全局 ORM Model 杂物箱。

## 5. Alembic Baseline

```text
Revision: 65b188208572
Message: Create initial Registry and Catalog schema
```

Autogenerate 后进行了人工审查：

- 补全稳定 Unique Constraint 名称；
- 确认 JSONB、UUID、timestamptz；
- 确认 Published Version Partial Unique Index；
- 将 ImportedOperation → Draft ToolBinding 的循环 Foreign Key 延后到两张表创建后；
- Downgrade 先删除延后 Foreign Key，再按依赖顺序删除表。

## 6. 真实数据库验收

开发库：

```text
Upgrade Head                 通过
Alembic Current              65b188208572
Alembic Check                No new upgrade operations
Downgrade Base               通过
再次 Upgrade Head            通过
```

测试库：

```text
7 张表存在                  通过
JSONB 往返                  通过
每个 Tool 单 Published 版本  约束通过
Downgrade 删除业务表         通过
测试结束恢复 Head            通过
```

## 7. ORM Flush 发现

Model 之间只定义 Foreign Key，不依赖 ORM Relationship/Lazy Load。

同一 Session 同时加入 Tenant、Tool、Upstream、Version 时，不能假设 ORM 根据业务 Aggregate 自动安排实例 Flush 顺序。测试改为显式：

```text
Add Tenant
→ Flush
Add Tool + Upstream
→ Flush
Add ToolVersion
→ Commit
```

未来 Repository/UoW 需要显式维护 Aggregate 写入顺序，不能依赖隐式 Lazy Relationship。

## 8. 当前未完成

- Domain ToolDefinition 尚未拆成 Tool/ToolVersion/PublishedTool；
- PostgreSQL Repository 尚未实现；
- Unit of Work/Publish Use Case 尚未实现；
- 跨 Tenant Binding 仍需 Application 规则与 Integration Test；
- OpenAPI Import Parser 尚未实现；
- 应用 Lifespan 尚未接入 Database Engine/Readiness；
- CI 云端首次运行等待 Push。

## 9. 下一步

1. 重构 Catalog Domain 为 Tool、ToolVersion、PublishedTool；
2. 定义 Catalog/Binding Repository Port 与 Unit of Work；
3. 实现 PostgreSQL Catalog Adapter；
4. 让正式 `tools/list` 读取 PublishedTool Projection；
5. 开始 Employee Directory Local OpenAPI Fixture。
