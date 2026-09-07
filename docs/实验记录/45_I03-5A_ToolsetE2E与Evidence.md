# I03-5A｜Toolset E2E 与 Evidence

> 状态：Completed
>
> 日期：2026-09-07
>
> 部署：Pending，按本轮约定暂不执行

## 1. Admin Evidence 可视化

Execution Admin Contract 新增：

```text
mcp_scope_type
toolset_id
toolset_revision
```

Execution Detail 页面现在直接展示 Root/Toolset Scope、Toolset ID 和 Revision；Audit 时间线展示
`mcp_scope_type + scope_reason_code`。管理员无需查询数据库即可确认 Agent 是从哪个发布面调用，以及访问范围基于
`active_toolset_grant` 还是 `granted_toolset_union`。

## 2. Toolset Evidence Manifest

新增机器可读清单：

```text
evals/toolsets/toolset_cases.json
```

12 个 Case 覆盖：

- Modern Dynamic Path 与 Legacy Scoped 拒绝；
- Root Granted Toolset Union；
- 非成员/失效成员 Fail Closed；
- `all_published` 动态投影；
- Scoped FTS 与 Hybrid RRF No-Leakage；
- Empty Scope 跳过在线 Embedding；
- Scoped Execution/Audit 与 Pre-Execution Denial；
- Public Demo Reset 恢复系统 Toolset/Grant。

Contract Test 会检查 Case ID 唯一、Category 覆盖，以及每条 Evidence 引用的 Pytest 文件和 Test Node 确实存在，
防止文档随重构悄悄失效。

Evidence 页面新增 Toolset Case 数量和发布面证据列表；Manifest 在 Web Build 阶段打包，不在 Runtime 读取仓库。

## 3. Full-stack Playwright

主 E2E 已扩展为完整 Toolset 纵向链路：

```text
Chromium Admin UI
→ Register Fake Upstream
→ Import / Review / Publish Tool
→ Create Explicit Toolset
→ Replace Members
→ Replace Agent Service Grant
→ Activate Toolset
→ Python MCP Client 经 Nginx 调用 Scoped Endpoint
→ Chromium 查看 Execution / Attempt / Audit
→ 验证 Toolset Revision 与 active_toolset_grant
```

测试使用 disposable `nexusmcp_test`、本地 Employee Directory Fake API 和临时 Nginx Image。第二条 E2E 继续验证
SPA Fallback、CSP/Frame/NoSniff Header 与移动端导航。

本地实际结果：

```text
Playwright Chromium  2 passed / 12.9s
Nginx Health         passed
Scoped MCP Call      passed
```

测试结束后已删除临时 `nexusmcp-web-e2e-i03` Container/Image，并停止临时 Backend/Fake Upstream；PostgreSQL
开发容器与数据卷未删除。

## 4. 工程门禁

```text
Python Full Suite   360 passed / 2 paid external skipped
Ruff Lint/Format    passed
basedpyright        0 errors / 0 warnings
Frontend Oxfmt      passed
Frontend Typecheck  passed
Frontend Oxlint     passed
Frontend Vitest     24 passed
Frontend Build      passed
Playwright E2E      2 passed
```

## 5. 后续

I03-5B 保留以下工作，本轮不执行：

- 构建正式 Backend/Web Public Demo Image；
- 更新服务器 Compose 与 Nginx；
- 数据库备份、Migration 和滚动替换；
- 公网 Smoke Test 与回滚验证。
