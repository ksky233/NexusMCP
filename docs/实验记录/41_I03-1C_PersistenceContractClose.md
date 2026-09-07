# I03-1C｜Persistence Contract Close

> 状态：Completed  
> 日期：2026-09-06  
> 前置：[I03-1B｜Toolset PostgreSQL Schema 与 Adapter](40_I03-1B_PostgreSQLSchema与Adapter.md)

## 1. 本轮目标

本轮不增加 Schema 或业务功能，只关闭 Toolset Persistence 在进入 Admin Use Case 前仍未被直接证明的边界：

- InMemory 与 SQLAlchemy Adapter 遵守同一份 Revision Contract；
- Aggregate Row、Member 与 Grant 在 PostgreSQL 中一起提交或一起回滚；
- Repository 自身可以阻止绕过 Domain 的非法版本写入；
- 确认 InMemory Adapter 是否仍有长期价值。

## 2. Revision 保存契约

`save()` 现在只接受两类输入：

```text
replacement == current
→ 幂等重放，不执行数据库写入

replacement != current
且 replacement.revision == current.revision + 1
→ 接受一次合法领域变更
```

同 Revision 偷改字段、一次跨越多个 Revision 都会被拒绝。稳定身份字段仍不可修改。

SQLAlchemy Repository 的 `save()` 自身取得 PostgreSQL Row Lock。I03-2 的 Command Use Case 仍应先调用
`get_for_update()` 表达并发意图，但即使调用方遗漏，Repository 也不会在无锁读取后直接覆盖现有状态。

## 3. Aggregate 原子性证据

Integration Test 在真实 PostgreSQL 中执行同一组 Grant Replace 两次：

1. 第一次更新 Aggregate、删除并重建 Member/Grant Row，但不调用 `commit()`；退出 UoW 后，新的 Session 读到完整旧状态；
2. 第二次执行相同变更并 `commit()`；新的 Session 同时读到新 Revision、新 Grant 集合和原 Member 集合。

这证明 Toolset 主 Row 与两个子集合不是各自独立保存，而是处于同一数据库事务：

```text
Toolset + Members + Grants
→ commit all
或 rollback all
```

## 4. InMemory Adapter 保留结论

保留，不是生产运行时 Adapter，也不是一次性代码。它继续承担两项稳定职责：

- 运行 Repository/UoW 共享 Contract，先发现与数据库无关的行为错误；
- 为 I03-2 Command/Query Use Case 提供快速、确定性、无需 PostgreSQL 的 Unit Test 依赖。

真实并发锁、FK、Unique Constraint 和事务隔离仍必须由 PostgreSQL Integration Test 证明，InMemory 不模拟这些数据库能力。

## 5. I03-2 接缝结论

Admin Command Use Case 已可直接依赖 `ToolsetUnitOfWorkFactory`：

```text
enter UoW
→ get_for_update
→ Catalog Snapshot 校验成员
→ 调用 Aggregate Method
→ Repository.save
→ commit
```

因此 I03-1 Persistence 已收口，下一步进入 `I03-2｜Admin API 与 Web UI`，无需继续扩展 Persistence Port。

## 6. 验证结果

```text
InMemory Toolset Repository/UoW Contract              7 passed
SQLAlchemy Toolset Repository/UoW + PostgreSQL Tests 12 passed
Ruff Lint/Format                                      passed
basedpyright                                          0 errors / 0 warnings
```
