# I04｜Direct Tool Publication

> 状态：Completed（本地验证）
>
> 日期：2026-09-07
>
> 决策：[ADR-0021](../adr/0021-direct-tool-publication-workflow.md)

## 1. Application Transaction

旧 Use Case 仍保持原入口，但内部能力拆成可复用的事务函数：

```text
ReviewImportedOperation.execute()
→ execute_in_transaction()
→ commit

PublishTool.execute()
→ publish_tool_in_transaction()
→ commit
```

新的 `DirectPublishImportedOperation` 打开一个 `ReviewUnitOfWork`，依次调用两个事务内核心并只 Commit 一次：

```text
Lock/Review Imported Operation
→ Create Draft ToolVersion + Binding
→ Draft → Review
→ Digest-safe Publish
→ Retire previous Published Version/Binding
→ Activate Tool
→ Commit all
```

PostgreSQL Failing Commit Test 证明 Commit 前虽然所有 Row 已 Flush，异常退出后 Operation 仍为 Pending、Draft
Reference 为空，Tool/Version/Binding 均不可见。

重复请求读取 Accepted Operation 的既有引用；若 Version 已 Published，则返回同一 Publication 并标记
`already_published=true`，不创建 Version 2。

## 2. Admin Contract

新增：

```text
POST /admin/openapi/operations/{operation_id}/publish
operationId = directPublishImportedOperation
```

Request 沿用：

```text
owner
visibility
review_notes
```

Response 返回 Tool/Version/Binding ID、Canonical Name、Version、两个 Digest、Retired Version、PublishedAt 和
AlreadyPublished。

Import Detail 的 Operation Response 增加 Summary、Description、Side Effect、Input/Output Schema，用于在创建
Draft 前展示真实 Generated Tool Contract。旧 Review、Submit Review、Publish Operation 与 Generated Client
继续保留。

## 3. Web UX

Pending/Accepted 且未发布的 Operation 只展示一个默认入口：

```text
直接发布
→ 查看 Generated Contract
→ 填写 Owner / Visibility / 发布备注
→ 查看 all_published 影响
→ 确认并直接发布
```

发布完成后 UI 重新读取 Import、ToolVersion 与 Binding，并显示 Published 状态。没有增加 Publication Mode
Settings、Batch Publish 或 Contract Editor。

## 4. Full-stack E2E

```text
Chromium
→ Register Upstream
→ Import OpenAPI
→ Direct Publish getEmployee
→ Catalog 验证
→ Create/Activate Explicit Toolset
→ Scoped MCP Call through Nginx
→ Execution/Audit Scope 验证
```

本地结果：`2 passed / 11.7s`。临时 `nexusmcp-web-e2e-i04` Container/Image 与 Backend/Fake Upstream 已清理，
PostgreSQL 开发容器保留。

## 5. 最终门禁

```text
Python Full Suite   362 passed / 2 paid external skipped
Ruff Lint/Format    passed
basedpyright        0 errors / 0 warnings
Frontend Oxfmt      passed
Frontend Typecheck  passed
Frontend Oxlint     passed
Frontend Vitest     24 passed
Frontend Build      passed
Playwright E2E      2 passed
```

本轮没有 Migration，不改变 MCP Data Plane、Toolset、Credential、Policy 或 Runtime Approval。
