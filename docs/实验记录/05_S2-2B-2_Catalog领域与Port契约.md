# S2-2B-2｜Catalog Domain 与 Port 契约验收

> 日期：2026-08-25  
> 范围：Tool Catalog Domain、ToolBinding Domain、Repository Port、Catalog Unit of Work、
> InMemory Adapter 与 Contract Test

## 1. 本阶段目标

数据库表和 ORM Model 已经存在，但 Application 层不能直接依赖 SQLAlchemy。此阶段先从
Catalog/Publish 用例反推最小 Port，让后续 PostgreSQL Adapter 适配业务契约，而不是让业务代码适配
数据库 API。

本阶段不实现：

- SQLAlchemy Repository；
- Publish Use Case；
- Database Engine/Lifespan 组装；
- OpenAPI Import Parser。

## 2. Domain 拆分

原有 `ToolDefinition` 同时混合稳定身份、版本契约、发布状态和发现投影，现拆为：

```text
Tool
├── 稳定 ID、Tenant、Namespace、Canonical Name、Owner
└── Active/Disabled

ToolVersion
├── 版本号、Input/Output Schema、Digest、Visibility、SideEffect
└── Draft/Review/Published/Retired、生命周期时间与显式状态转换

PublishedTool
└── tools/list 所需的只读发布投影
```

`PublishedTool` 不携带 Draft/Review 状态，因为“能构造出该类型”本身就代表 Repository 已经完成：

- Tool 为 Active；
- ToolVersion 为 Published；
- 后续 PostgreSQL Query 还必须确认存在 Published Binding。

Restricted Tool 在 S3 Policy 接入前采用 Fail Closed：即使 Principal 已认证也不返回。S2 只提供
Public 与 Authenticated 的粗粒度发现行为。

`ToolVersion` 通过 `submit_for_review()`、`publish()`、`retire()` 限制状态转换，不能从 Draft
跳过 Review 直接发布。`ToolBinding` 同样只允许 Draft → Published → Disabled。

## 3. Repository Port

### 3.1 ToolCatalogRepository

契约按 Use Case 意图组织，而不是“一张表一个 Repository”：

- Tool Identity：新增、保存、按 ID/Name 读取、排他读取；
- ToolVersion：新增、保存、按 ID 读取、排他读取、读取当前 Published Version；
- Published Projection：按 Tenant 列表、按 Canonical Name 获取。

每个方法都显式接收 `tenant_id`。即使 Entity 自身已有 Tenant ID，也不允许调用者省略查询边界；
Adapter 还需要验证参数 Tenant 与 Entity Tenant 一致。

### 3.2 ToolBindingRepository

ToolBinding 属于 Connectors 限界上下文，因此 Port 位于 `modules/connectors/ports.py`。它提供：

- 新增/保存 Binding；
- 按 Binding ID 或 ToolVersion ID 读取；
- Publish 时所需的排他读取。

Catalog 的发布用例可以依赖这个公开 Port，但不拥有 ToolBinding Domain。

### 3.3 `get_*_for_update`

该命名表达“接下来的业务修改必须与并发发布互斥”的语义：

- InMemory Adapter 中等价于普通读取；
- PostgreSQL Adapter 中映射为 `SELECT ... FOR UPDATE`；
- Application 不需要 import SQLAlchemy 的 `Select` 或 Session。

## 4. CatalogUnitOfWork

一次 Publish 会同时修改 Tool、ToolVersion 和 ToolBinding，单个 Repository 无法表达“要么全部成功，
要么全部失败”。因此 `CatalogUnitOfWork` 同时暴露：

```text
uow.catalog   -> ToolCatalogRepository
uow.bindings  -> ToolBindingRepository
uow.commit()
uow.rollback()
```

使用形式：

```python
async with unit_of_work:
    tool = await unit_of_work.catalog.get_tool_for_update(tenant_id, tool_id)
    version = await unit_of_work.catalog.get_version_for_update(tenant_id, version_id)
    binding = await unit_of_work.bindings.get_for_update(tenant_id, binding_id)
    # 校验并暂存三个对象的状态变化
    await unit_of_work.commit()
```

约束：

- Repository 只读取和暂存状态，不自行 Commit；
- 顶层 Use Case 决定 Commit 时机；
- 未显式 Commit 或发生异常时默认 Rollback；
- 一个 Unit of Work 只服务一次业务事务，不跨越 OpenAPI 读取或 Upstream HTTP；
- 正式运行时每次 Command 创建独立 Unit of Work，不能在并发请求间共享打开的 Session。

## 5. InMemory Adapter

`InMemoryToolCatalogRepository` 与 `InMemoryToolBindingRepository` 实现同一业务 Port，供快速单元测试和
本地确定性组装长期使用。

`InMemoryCatalogUnitOfWork` 在进入事务时复制已提交状态：

```text
Committed State
      ↓ clone
Transaction-local Repositories
      ↓ explicit commit
Replace Committed State Together
```

不 Commit 时直接丢弃事务副本，从可观察行为上模拟 Rollback。它不模拟 SQL、Session 或数据库锁。

## 6. Contract Test

Contract Test 固定 Adapter 的共同可观察行为：

- Tool/ToolVersion/Binding 可以新增、读取和保存；
- 所有查询受 Tenant 隔离；
- Published Version 和 Published Projection 具有专用查询；
- Catalog 与 Binding 在 Unit of Work 中一起 Commit；
- 未 Commit 和显式 Rollback 都不留下部分状态。

当前由 InMemory Adapter 首先执行。S2-2B-3 的 PostgreSQL Adapter 必须复用相同 Contract，而不是另写
一套只验证 SQLAlchemy 细节的测试。

## 7. 代码位置

```text
src/nexusmcp/modules/catalog/domain.py
src/nexusmcp/modules/catalog/ports.py
src/nexusmcp/modules/catalog/adapters/in_memory.py
src/nexusmcp/modules/catalog/adapters/in_memory_uow.py
src/nexusmcp/modules/connectors/domain.py
src/nexusmcp/modules/connectors/ports.py
src/nexusmcp/modules/connectors/adapters/in_memory.py
tests/contract/repositories/test_in_memory_repository_contracts.py
```

## 8. 下一步

进入 `S2-2B-3｜PostgreSQL Repository 与 Unit of Work Adapter`：

1. 建立 ORM ↔ Domain Mapping；
2. 实现 Async SQLAlchemy Catalog/Binding Repository；
3. 实现每事务独立 AsyncSession 的 Unit of Work；
4. 让 PostgreSQL Adapter 运行同一 Repository/UoW Contract；
5. 增加 Tenant 与并发锁相关的 Integration Test。

以上内容已在 [S2-2B-3 PostgreSQL Repository 与 Unit of Work](./06_S2-2B-3_PostgreSQLRepository与UnitOfWork.md)
完成。
