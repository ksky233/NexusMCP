# Port 的设计与理解：不要把依赖方向、调用方向和数据流方向混在一起

> 目标：理解六边形架构中的 Port，重点解释 Repository 为什么是一种 Port，以及它与 DAO、ORM、Adapter、Use Case、Unit of Work 的关系。

## 1. 先修正一个常见印象

看到：

```text
ToolCatalogRepository
```

很容易产生以下直觉：

```text
Repository
= 数据库访问层
= 数据从数据库流向业务程序
```

这个直觉只描述了“查询数据”时的一种数据流，没有描述架构关系的全貌。

Repository 更准确的含义是：

> 业务层访问和保存领域对象所需的抽象接口。

它既可以读，也可以写：

```text
查询：Database → Adapter → Repository Port → Use Case

保存：Use Case → Repository Port → Adapter → Database
```

所以不能用数据流方向判断谁依赖谁。

## 2. 必须分开的三种方向

理解 Port 最关键的一步，是把三种方向分开。

### 2.1 调用方向

谁在运行时调用谁：

```text
MCP Handler
→ ListVisibleTools Use Case
→ ToolCatalogRepository
→ PostgreSQL Adapter
```

业务程序确实会向外调用 Repository。

### 2.2 数据流方向

数据实际向哪里流动。

查询：

```text
PostgreSQL
→ SQLAlchemy Row
→ Repository Adapter
→ PublishedTool
→ Use Case
→ MCP Client
```

保存：

```text
Use Case
→ Domain Entity
→ Repository Adapter
→ SQLAlchemy Row
→ PostgreSQL
```

数据流可以双向。

### 2.3 代码依赖方向

谁在源码中 import 谁、谁的修改会迫使谁跟着修改：

```text
Use Case
→ import Repository Port

SQLAlchemy Adapter
→ 遵守 Repository Port
→ import Domain Model

Bootstrap
→ 同时认识 Use Case 和具体 Adapter
```

核心目标是：

```text
业务代码不知道 PostgreSQL、SQLAlchemy、Redis 或 HTTP Client。
```

即使运行时调用最终到达数据库，业务代码也只依赖自己定义的抽象。

## 3. Port 到底是什么

Port 可以理解为：

> 系统核心为了与外界交互而定义的插口/契约。

Port 只描述：

```text
我需要什么能力？
输入是什么？
输出是什么？
失败语义是什么？
```

Port 不描述：

```text
具体使用 PostgreSQL 还是内存？
SQL 怎么写？
HTTP Client 用哪个库？
连接池怎么配置？
Secret 存在哪里？
```

## 4. Inbound Port 与 Outbound Port

### 4.1 Inbound Port

Inbound Port 表达系统允许外部执行什么业务。

通常就是 Application Use Case：

```text
RegisterUpstreamService
ImportOpenApi
ReviewImportedTool
PublishTool
ListVisibleTools
CallTool
```

外部 Adapter 调用它：

```text
FastAPI Router ─┐
MCP Handler    ─┼→ Application Use Case
CLI Command    ─┘
```

在 NexusMCP 中，不一定专门创建名为 `InboundPort` 的 Protocol。一个边界清晰的 Use Case 本身就可以承担 Inbound Port。

### 4.2 Outbound Port

Outbound Port 表达 Use Case 执行时需要的外部能力：

```text
ToolCatalogRepository
UpstreamRepository
OpenApiDocumentReader
ToolExecutor
CredentialProvider
AuditSink
Clock
EventPublisher
```

Use Case 调用它：

```text
Application Use Case
→ Outbound Port
→ Concrete Adapter
```

## 5. Repository 是 Outbound Port 的一种

Repository 结尾只表示：

```text
这个 Port 负责持久化领域状态或查询领域 Read Model。
```

例如：

```python
from collections.abc import Sequence
from typing import Protocol


class ToolCatalogRepository(Protocol):
    async def list_published(
        self,
        tenant_id: str,
    ) -> Sequence[PublishedTool]: ...
```

该接口只表达：

```text
Catalog Use Case 需要查询某个 Tenant 的 Published Tool。
```

它没有出现：

```text
SQL
Session
SELECT
Table
PostgreSQL
SQLAlchemy
```

因此它属于业务边界。

## 6. Adapter 是什么

Adapter 是 Port 的具体接法。

### 6.1 InMemory Adapter

```python
class InMemoryToolCatalogRepository:
    def __init__(self, tools: list[PublishedTool]) -> None:
        self._tools = tools

    async def list_published(self, tenant_id: str) -> list[PublishedTool]:
        return [tool for tool in self._tools if tool.tenant_id == tenant_id]
```

### 6.2 PostgreSQL Adapter

```python
class SqlAlchemyToolCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_published(self, tenant_id: str) -> list[PublishedTool]:
        # 这里才允许出现 SQLAlchemy 查询和 ORM → Read Model 映射。
        ...
```

两个 Adapter 遵守同一个 Port：

```text
ToolCatalogRepository
├── InMemoryToolCatalogRepository
└── SqlAlchemyToolCatalogRepository
```

Use Case 不需要知道当前注入的是哪一个。

## 7. Python Protocol 为什么适合 Port

Python 可以使用 `typing.Protocol` 定义结构化接口：

```python
class ToolCatalogRepository(Protocol):
    async def list_published(...) -> Sequence[PublishedTool]: ...
```

具体实现不必显式继承它：

```python
class InMemoryToolCatalogRepository:
    async def list_published(...) -> list[PublishedTool]:
        ...
```

只要方法签名满足，basedpyright 就可以判断它兼容该 Port。

这减少了为了形式而创建的大量基类。

## 8. Dependency Inversion 到底反转了什么

没有 Port 时：

```text
Use Case
→ import SqlAlchemy Repository
→ import SQLAlchemy
→ PostgreSQL
```

数据库技术变化会向内传播：

```text
PostgreSQL/SQLAlchemy 变化
→ Repository 变化
→ Use Case 也可能变化
```

使用 Port 后：

```text
Use Case
→ ToolCatalogRepository Port
← SqlAlchemy Adapter
```

Port 由业务需求定义，Adapter 反过来适配业务契约。

反转的是源码依赖：

```text
不是业务层依赖数据库实现，
而是数据库实现遵守业务层定义的 Port。
```

运行时调用方向仍然可以是：

```text
Use Case → Adapter → Database
```

这两句话并不冲突。

## 9. Repository、DAO、ORM Model 的区别

| 概念 | 关注点 | 常见语言 |
|---|---|---|
| Repository Port | 领域对象/Read Model 的读取与保存契约 | Published Tool、Import Job、Tool Version |
| Repository Adapter | 使用某种基础设施实现 Port | SQLAlchemy、InMemory、Remote Store |
| DAO | 面向表和数据访问操作 | select、insert、update、row |
| ORM Model | 数据库表的 Python 映射 | Column、Relationship、Index、Constraint |

DAO 风格：

```python
select_tool_version_rows_by_status(...)
insert_tool_binding_row(...)
```

Repository Port 风格：

```python
list_published_tools(...)
save_import_result(...)
get_review_draft(...)
```

Repository Adapter 内部可以使用 DAO/ORM，但这些细节不应出现在 Port 和 Domain 中。

## 10. 为什么 Port 文件放在业务模块里

例如：

```text
modules/catalog/
├── domain.py
├── use_cases.py
├── ports.py
└── adapters/
```

`ports.py` 放在 Catalog 中，是因为 Port 表达的是 Catalog 的需求：

```text
Catalog 需要怎样读取 Published Tool？
Catalog 发布时需要怎样保存 Version？
```

不是 PostgreSQL 在告诉 Catalog 应该有什么方法。

如果把 Port 放进全局 Infrastructure：

```text
infrastructure/repositories/tool_repository.py
```

很容易变成由数据库表结构反向定义业务接口。

## 11. Bootstrap 在其中做什么

Use Case 不能自己选择具体 Adapter：

```python
# 不推荐：业务代码在内部决定使用 PostgreSQL。
repository = SqlAlchemyToolCatalogRepository(...)
```

Bootstrap 负责组装：

```python
repository = SqlAlchemyToolCatalogRepository(session)
use_case = ListVisibleTools(repository)
mcp_server = create_mcp_server(list_visible_tools=use_case)
```

因此：

```text
Bootstrap 知道具体实现
Use Case 只知道 Port
```

## 12. Port 不一定与数据库有关

以下都是 NexusMCP 未来可能出现的 Port：

### OpenApiDocumentReader

```text
读取 Local Fixture / Upload / URL
```

### ToolExecutor

```text
执行 HTTP Binding / Remote MCP Binding
```

### CredentialProvider

```text
根据 SecretReference 读取 Secret Value
```

### AuditSink

```text
追加 Audit Event
```

### Clock

```text
提供当前时间，测试时可替换
```

### IdGenerator

```text
生成 UUID，测试时可固定
```

所以：

```text
Port ≠ Repository
Repository ⊂ Outbound Port
```

## 13. 为什么候选 Port 都以 Repository 结尾

当前讨论的是持久化模型，所以列出的主要是持久化 Port：

```text
TenantRepository
UpstreamRepository
OpenApiImportRepository
ToolCatalogRepository
ToolBindingRepository
```

这不是要求“每张表一个 Repository”。

### TenantRepository

只有 Tenant 生命周期或查询 Use Case 出现时才创建。当前可能不需要。

### UpstreamRepository

面向 UpstreamService Aggregate，不是 `upstream_service` 表的通用 CRUD DAO。

### OpenApiImportRepository

可以同时管理：

```text
OpenApiImportJob
ImportedOperation
```

因为它们属于同一个 Import 上下文和事务过程。

### ToolCatalogRepository

可以同时处理：

```text
Tool
ToolVersion
PublishedTool Projection
```

不是为 Tool 和 ToolVersion 各创建一个机械 Repository。

### ToolBindingRepository

属于 Connectors。Publish 时可能与 Catalog Repository 一起被 Unit of Work 协调。

如果实际 Use Case 证明两个 Port 总是一起变化，也可以重新调整边界，不需要为了文档列表强行创建文件。

## 14. Unit of Work 与 Repository 的关系

Repository 负责对象的读取和暂存修改；Unit of Work 负责事务。

```text
Repository
= get/add/list

Unit of Work
= begin/commit/rollback
```

Publish 示例：

```python
async with catalog_uow:
    tool = await catalog_uow.tools.get_for_update(...)
    binding = await catalog_uow.bindings.get_draft(...)

    tool.publish(...)
    binding.publish(...)

    await catalog_uow.commit()
```

推荐规则：

- Repository 不自行 Commit；
- 顶层 Use Case 决定事务完成或回滚；
- 同一事务内的多个 Repository 由 Unit of Work 提供；
- 外部 HTTP 调用不放在长数据库事务中。

## 15. 从 Use Case 反推 Port

不要先打开编辑器创建：

```text
repositories/
interfaces/
providers/
```

正确顺序：

### 第一步：写清 Use Case

```text
ListVisibleTools
输入：Tenant、Principal
输出：当前可见的 Published Tool
```

### 第二步：找出业务无法自己完成的事情

```text
需要取得 Published Tool
```

### 第三步：定义最小 Port

```python
class ToolCatalogRepository(Protocol):
    async def list_published(...) -> Sequence[PublishedTool]: ...
```

### 第四步：先写 InMemory Adapter 和 Use Case Test

证明该抽象能够承载业务规则。

### 第五步：再写 SQLAlchemy Adapter

让 PostgreSQL 实现已经存在的业务契约。

## 16. Port 设计检查表

设计一个 Port 时，逐项检查：

### 是否来自真实 Use Case

如果没有调用者，不创建。

### 名称是否使用业务语言

优先：

```text
list_published_tools
save_import_result
get_review_draft
```

谨慎：

```text
select_rows
flush_session
execute_query
```

### 输入/输出是否泄露基础设施

Port 不应接收或返回：

```text
AsyncSession
SQLAlchemy Select
ORM Row
HTTP Response
Redis Client
```

### 方法是否最小

不要提前设计几十个 CRUD 方法。

### 是否可以有至少两个 Adapter

```text
InMemory
PostgreSQL
```

如果完全无法替换或测试，可能还没有找到正确边界。

### 失败语义是否属于业务

不要把底层 `IntegrityError` 直接抛给 Use Case/MCP Client，应映射成稳定内部错误。

## 17. 常见错误

### 每张表一个 Repository

这是按数据库建模，不是按 Aggregate/Use Case 建模。

### Repository 返回 ORM Model

会让业务代码依赖 SQLAlchemy、Lazy Load 和 Session 生命周期。

### Use Case import 具体 Repository

会失去替换、隔离测试和依赖倒置。

### Repository 内部自动 Commit

多个状态无法形成一个原子事务。

### 创建万能 GenericRepository

```text
create/update/delete/get/list
```

这种抽象通常只有数据库语言，没有领域语义。

### 为每个 Class 创建 Port

Port 用来隔离外部边界和重要策略，不是给所有类配 Interface。

### 把 Port 当成数据流方向

Port 描述依赖边界，不描述数据只能从哪边流向哪边。

## 18. NexusMCP 完整示例

### tools/list

```text
MCP Client
→ MCP Adapter
→ ListVisibleTools Use Case
→ ToolCatalogRepository Port
→ SqlAlchemyToolCatalogRepository Adapter
→ PostgreSQL
```

数据返回：

```text
PostgreSQL
→ PublishedTool Projection
→ Use Case 过滤
→ MCP Tool Schema
→ Client
```

### OpenAPI Import

```text
Admin/CLI Adapter
→ ImportOpenApi Use Case
→ OpenApiDocumentReader Port
→ LocalFileReader Adapter

ImportOpenApi Use Case
→ OpenApiImportRepository Port
→ SqlAlchemyOpenApiImportRepository
→ PostgreSQL
```

### tools/call

```text
MCP Adapter
→ CallTool Use Case
→ ToolCatalogRepository
→ PolicyEvaluator
→ CredentialProvider
→ ToolExecutor
→ AuditSink
```

只有其中一部分 Port 是 Repository。

## 19. 最终心智模型

记住下面四句话即可：

### 第一句

```text
Port 是业务核心定义的外部能力契约。
```

### 第二句

```text
Repository 是负责领域状态持久化/查询的一类 Outbound Port。
```

### 第三句

```text
Adapter 使用 PostgreSQL、内存、HTTP 等技术实现 Port。
```

### 第四句

```text
数据流可以双向；真正要控制的是源码依赖始终朝向业务核心。
```

最简图：

```text
                  Runtime Call
Use Case ─────────────────────────→ Adapter ─→ Database
   │                                  │
   └──── depends on Port ─────────────┘
              ↑
       Port 由业务定义
```

因此看到 `Repository` 结尾时，不要只想到“数据库把数据传给业务程序”，而应该想到：

> 这是业务层定义的持久化插口；数据可以读写，具体数据库只是插在该 Port 上的一个 Adapter。
