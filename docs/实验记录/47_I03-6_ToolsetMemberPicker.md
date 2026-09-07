# I03-6｜Toolset Member Picker 可用性增强

> 状态：Completed
>
> 日期：2026-09-07

## 1. 触发问题

Explicit Toolset 原有成员编辑器一次列出最多 100 个 Published Tool，只显示 Canonical Name 与 Description。随着
Upstream 和 Tool 数量增加，管理员无法快速判断 Tool 来源，也不能按名称缩小候选范围。

## 2. 实现边界

Admin Query Contract 增加：

```text
GET /admin/tools?q={plain_text}&upstream_service_id={uuid}
```

Tool Summary 增加：

```text
upstream_service_id
upstream_name
upstream_namespace
```

Upstream 信息来自当前 ToolVersion 的 `ToolBinding.upstream_service_id`，不是根据 Tool Namespace 推测。查询继续保持
Tenant 边界；名称搜索覆盖 Canonical Name、Display Name 和 Description，并把 `%`、`_` 作为普通字符处理。

## 3. UI 行为

- 候选按 `upstream_namespace.upstream_name` 分组；
- 支持普通文本搜索；
- 支持 Upstream 下拉过滤；
- 支持“仅看已选”和实时已选数量；
- 切换搜索或 Upstream 时不修改 Selection Set；
- 保存仍调用 `ReplaceToolsetMembers`，一次原子替换完整成员集合。

当前成员诊断区继续独立展示 Retired、Disabled 或 No Published Version 成员，候选筛选不会把这些既有成员静默删除。

## 4. 非目标

- 不引入 FTS、Embedding 或 Hybrid Search；管理面名称筛选使用 PostgreSQL `ILIKE`；
- 不改变 Toolset Membership、Revision 和并发冲突语义；
- 不新增数据库表或 Migration；
- 不在本轮实现超过 100 个候选的虚拟滚动或连续分页。

## 5. 验证

- Admin OpenAPI Snapshot 与 HeyAPI Client 已刷新；
- PostgreSQL Integration Test 覆盖文本命中、无命中、Upstream 过滤和 Tenant 隔离；
- Frontend Test 覆盖真实 Upstream 分组与名称搜索；
- Python：`362 passed / 2 paid external skipped`；
- Frontend：`24 passed`，Production Build 通过；
- Ruff Lint/Format、basedpyright `0 errors / 0 warnings`、Frontend Lint/Typecheck/Format 通过。
