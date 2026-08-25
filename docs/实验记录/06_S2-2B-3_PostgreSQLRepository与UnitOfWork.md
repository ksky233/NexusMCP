# S2-2B-3｜PostgreSQL Repository 与 Unit of Work Adapter 验收

> 日期：2026-08-25  
> 范围：ORM ↔ Domain Mapping、Catalog/Binding SQLAlchemy Repository、Async Unit of Work、
> InMemory/PostgreSQL 共享 Contract 与行锁测试

## 1. 本阶段目标

将 S2-2B-2 定义的业务 Port 接到真实 PostgreSQL，同时保持以下依赖方向：

```text
Use Case / Domain
       ↓
Repository + Unit of Work Port
       ↑
SQLAlchemy Async Adapter
       ↓
PostgreSQL 18.6
```

本阶段不实现：

- Publish Use Case；
- FastAPI Lifespan/Database Bootstrap；
- 正式 `tools/list` 的 PostgreSQL 装配；
- OpenAPI Import Parser。

## 2. 显式 ORM ↔ Domain Mapping

Mapping 独立于 Repository，覆盖：

```text
ToolModel         ↔ Tool
ToolVersionModel  ↔ ToolVersion
ToolBindingModel  ↔ ToolBinding
ToolModel + ToolVersionModel → PublishedTool
```

主要边界：

- Domain ID 保持协议无关的 `str`，Persistence 边界显式转换 UUID；
- JSONB 在 Mapping 时复制，避免 ORM 容器泄漏到 Domain；
- Enum 显式转换为数据库字符串，读取时重新构造 Domain Enum；
- ORM Timestamp 不被当作 Domain Entity Identity；
- Repository 不返回 ORM Model。

## 3. SQLAlchemy Repository

### 3.1 SqlAlchemyToolCatalogRepository

实现以下能力：

- Tool/ToolVersion 新增、读取和保存；
- 所有 Query 强制 Tenant 条件；
- `get_tool_for_update()` / `get_version_for_update()` 映射为
  `SELECT ... FOR UPDATE`；
- 读取当前 Published Version；
- 通过显式 Join 构造 PublishedTool Projection。

Published Projection Query 必须同时满足：

```text
Tool.status = active
ToolVersion.status = published
ToolBinding.status = published
三者 tenant_id = 当前 Tenant
```

因此 Draft/Review/Retired Version、Disabled Tool 或缺少 Published Binding 的记录不会进入普通
Catalog Query。

### 3.2 SqlAlchemyToolBindingRepository

实现 Binding 新增、保存、按 ID/ToolVersion 读取和排他读取。Binding 的 Tenant、Upstream、Version
一致性将在 Publish Use Case 中执行完整业务校验；Repository 仍对所有查询和写入显式应用 Tenant
Scope。

### 3.3 Flush 与 Commit

Repository 的新增/保存方法执行 `flush()`，让同一事务中的后续 FK 写入和约束错误及时可见，但绝不
执行 `commit()`。

```text
Repository.flush()
       ≠
UnitOfWork.commit()
```

## 4. SQLAlchemy Catalog Unit of Work

`SqlAlchemyCatalogUnitOfWork` 在每次进入时创建一个 AsyncSession，并把同一个 Session 交给：

```text
uow.catalog
uow.bindings
```

这保证 Catalog 与 Binding 处于同一 PostgreSQL Transaction。

行为：

- 显式 `commit()` 才提交；
- 未 Commit 离开 Context 时自动 Rollback；
- 异常离开时 Rollback；
- 显式 `rollback()` 后可以继续读取已提交状态；
- 离开 Context 后关闭 Session；
- 禁止同一个 UoW 嵌套进入。

`SqlAlchemyCatalogUnitOfWorkFactory` 只保存 Session Factory。每个并发 Command 调用它获得新的 UoW，
避免在请求之间共享正在使用的 AsyncSession。

## 5. 共享 Contract Test

Contract 定义与具体 Adapter Fixture 已分离：

```text
contracts.py
├── CatalogRepositoryContract
├── ToolBindingRepositoryContract
└── CatalogUnitOfWorkContract

test_in_memory_repository_contracts.py
└── InMemory Fixture

test_sqlalchemy_repository_contracts.py
└── PostgreSQL Fixture
```

两种 Adapter 执行相同业务断言：

- 新增、读取和更新；
- Tenant 隔离；
- Published Version/Projection 查询；
- Catalog 与 Binding 一起 Commit；
- 未 Commit 或显式 Rollback 不留下部分状态。

PostgreSQL 额外验证：

- Published Projection 必须拥有 Published Binding；
- `get_tool_for_update()` 会获得真实 PostgreSQL Row Lock；
- UoW Factory 不复用 UoW 实例；
- Contract Fixture 的 ID 与数据库 UUID 类型兼容。

## 6. 开发中确认的问题

### 6.1 InMemory ID 不等于数据库合法 ID

原 Contract 使用 `tenant-a` 等可读字符串；PostgreSQL Schema 使用 UUID。为保证同一 Contract 真能
跨 Adapter 运行，测试改用稳定 UUID 字符串，而不是在 PostgreSQL 测试中另写一套断言。

### 6.2 Foreign Key 让 Rollback Test 更接近真实事务

InMemory Adapter 可以单独暂存 Binding，但 PostgreSQL Binding 必须先存在 ToolVersion 和 Upstream。
共享 Contract 因此按真实 Aggregate 写入顺序创建 Tool → ToolVersion → Binding，再验证整体回滚。

### 6.3 `FOR UPDATE` 不能只检查生成的 SQL

测试使用两个独立 AsyncSession：第一个事务锁定 Tool Row，第二个事务设置短 `lock_timeout` 后尝试锁定
同一行并收到数据库异常，从行为上证明行锁生效。

### 6.4 Unit of Work 实例不能作为全局单例

FastAPI/MCP 会并发处理请求。共享 UoW 实例会导致不同 Command 争用或泄漏 Session，因此注入点应是
`CatalogUnitOfWorkFactory`，每次执行 Use Case 时再创建 UoW。

## 7. 代码位置

```text
src/nexusmcp/infrastructure/persistence/identifiers.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_mapping.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_repository.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_uow.py
src/nexusmcp/modules/connectors/adapters/sqlalchemy_mapping.py
src/nexusmcp/modules/connectors/adapters/sqlalchemy_repository.py
tests/contract/repositories/contracts.py
tests/integration/persistence/test_sqlalchemy_repository_contracts.py
```

## 8. 下一步

进入 `S2-2B-4｜Publish 事务 Use Case`：

1. 定义 Publish Command/Result 与业务错误；
2. 使用 UoW 锁定 Tool、待发布 Version 和 Binding；
3. 校验 Tenant、状态、Upstream、Schema/Binding Digest；
4. Retire 旧 Version、Publish 新 Version/Binding、激活 Tool；
5. 验证任何失败都会整体 Rollback；
6. 暴露 `ToolPublished` Domain Event/Audit Port，但暂不决定最终 Audit 原子策略。
