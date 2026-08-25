# S2-2B-5｜Database Bootstrap 与正式 Catalog Query 验收

> 日期：2026-08-25  
> 范围：Catalog Backend 配置、Database Runtime、Application Lifespan、Readiness、
> PublishedToolReader、MCP → PostgreSQL 纵向集成

## 1. 目标

把已经通过独立 Integration Test 的 PostgreSQL Adapter 正式接入运行中的 NexusMCP：

```text
Application Startup
→ Create Engine / Session Factory
→ PostgreSQL Ping
→ Start MCP Session Manager
→ Serve Health + MCP

MCP tools/list
→ RequestContext Tenant
→ ListVisibleTools
→ PublishedToolReader
→ Short AsyncSession
→ PostgreSQL Published Projection

Application Shutdown
→ Stop MCP Session Manager
→ Dispose Engine Pool
```

App 对象构造本身不执行网络 I/O，只有进入 Lifespan 才连接数据库。

## 2. 运行模式

Settings 增加：

```text
catalog_backend = memory | postgresql
database_url
database_echo
database_readiness_timeout_seconds
local_tenant_id
```

规则：

- 默认 `memory`，保证 Unit/Contract Test 和最小学习运行无需数据库；
- `.env.example` 正式本地配置为 `postgresql`；
- PostgreSQL 模式必须提供 Database URL；
- Production 禁止静默使用空 InMemory Catalog；
- 测试仍可显式注入 Reader/Runtime，不读取全局 Session。

## 3. DatabaseRuntime

`DatabaseRuntime` 是 Engine 和 Session Factory 的进程级 Lifespan Owner：

```text
start()
├── create AsyncEngine
├── create async_sessionmaker
└── SELECT 1；失败则 Dispose 并中止启动

is_ready()
└── 在 Timeout 内 SELECT 1；失败返回 False

stop()
├── 清除 Session Factory 引用
└── dispose Engine
```

Database URL 使用 `SecretStr` 进入 Bootstrap，只在创建 Runtime 时读取真实值；日志事件不包含 URL、用户
名或密码。

## 4. PublishedToolReader

原 `ListVisibleTools` 只需要两个查询，却依赖了包含 Add/Save/Lock 的完整 Repository。S2-2B-5 按
Interface Segregation 拆出：

```text
PublishedToolReader
├── list_published_by_tenant
└── get_published_by_name

ToolCatalogRepository
└── extends PublishedToolReader + Write/Lock Methods
```

`InMemoryToolCatalogRepository` 继续满足 Reader；正式运行使用
`SqlAlchemyPublishedToolReader`。后者每次 Query 从 DatabaseRuntime 获取 Session Factory，创建短
Session 并在查询结束后关闭，不在并发 MCP 请求间共享 Session。

Publish 写事务仍只能通过 `CatalogUnitOfWorkFactory`，不会误用 Read Session。

## 5. Application Factory 与 Lifespan

Composition Root 根据配置选择：

```text
memory
→ InMemoryToolCatalogRepository
→ Readiness 永远 Ready

postgresql
→ DatabaseRuntime
→ SqlAlchemyPublishedToolReader
→ Database Readiness
```

显式注入 `tool_reader` 时优先使用注入对象；这是 Unit/Contract Test 的替换接缝。显式注入 Runtime
时，Lifespan 仍负责 Start/Stop，便于验证启动失败与 Readiness。

Startup 顺序保证 Database 先 Ready，再启动 MCP Session Manager；Shutdown 顺序相反，确保仍在处理的
MCP 请求不会遇到提前 Dispose 的连接池。

## 6. Health 语义

```text
GET /health
GET /health/live
→ 200 {"status":"ok"}
→ 只证明进程/Event Loop 存活

GET /health/ready
→ 200 {"status":"ok"}       Database Ready
→ 503 {"status":"not_ready"} 未启动、探针失败或已 Shutdown
```

数据库不可用不会把 Liveness 变成失败，避免容器平台因依赖短暂抖动反复重启进程。

## 7. 测试证据

Unit Test：

- PostgreSQL Backend 缺 URL 时 Settings 拒绝；
- Production 不能使用 Memory Backend；
- App 构造不会调用 Runtime.start；
- Lifespan 精确调用一次 Start/Stop；
- Runtime 启动失败时 App 不进入 Serving；
- Database Not Ready 时 Liveness 200、Readiness 503；
- Reader 在 Lifespan 外拒绝查询。

PostgreSQL Integration Test：

- DatabaseRuntime 可以 Start、SELECT 1、提供 Session Factory、Stop；
- 无效数据库地址启动失败后 Runtime 状态被清理；
- Lifespan 前 Readiness 503、运行中 200、Shutdown 后 503；
- 真实 MCP Client 通过 `/mcp` 调用 `tools/list`；
- 返回值来自 PostgreSQL Active Tool + Published Version + Published Binding Projection。

## 8. 有意不做

- 不在应用启动时自动执行 Alembic Migration；Migration 仍是显式部署步骤；
- 不自动创建默认 Tenant 或 Demo Tool；这些状态必须由后续 Control Plane/Fixture 创建；
- 不在 Readiness 中执行复杂 Catalog Query，只做轻量 `SELECT 1`；
- 不增加全局 Session；
- 不在本阶段实现 Pool Metric、Replica Routing 或自动 Failover。

## 9. 代码位置

```text
src/nexusmcp/bootstrap/app.py
src/nexusmcp/bootstrap/config.py
src/nexusmcp/infrastructure/persistence/runtime.py
src/nexusmcp/interfaces/health/router.py
src/nexusmcp/modules/catalog/ports.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_reader.py
tests/unit/bootstrap/test_config.py
tests/unit/bootstrap/test_app.py
tests/unit/infrastructure/test_database_runtime.py
tests/integration/persistence/test_database_runtime.py
tests/integration/persistence/test_postgresql_catalog_bootstrap.py
```

## 10. 下一步

进入 `S2-3｜Employee Directory OpenAPI 首条纵向切片`：

1. 建立约 3 个接口的轻量 Employee Directory Fake API；
2. 保存第一个 UpstreamService；
3. 加载 Local OpenAPI Fixture；
4. 校验并标准化 path/query/header/body、ref/required/enum；
5. 创建 Import Job 与 ImportedOperation；
6. Review 后生成 Draft ToolVersion + ToolBinding；
7. 调用现有 Publish Use Case；
8. 通过正式 PostgreSQL Catalog 在 MCP `tools/list` 中发现 Tool。
