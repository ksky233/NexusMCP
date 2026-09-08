# Playwright 严格定位与 Retry 状态污染

> 日期：2026-09-08
> 状态：修复完成 / GitHub CI 验证中
> 影响范围：GitHub Actions `Nginx full-stack E2E`

## 现象

从 `672d45f` 开始，多次 Push 的 GitHub CI 都呈现相同结构：

```text
Quality and tests            success
Frontend quality and build   success
Nginx full-stack E2E         failure
```

Pages 发布和生产公网 Smoke 均通过，因此需要区分运行时故障与测试契约故障。

## Artifact 证据

### 首次 Attempt

E2E 已经完成：

```text
注册 Upstream
→ 导入 OpenAPI
→ 发布 Tool
→ 创建并启用 Toolset
→ MCP tools/call
→ 写入成功的 Execution / Attempt / Audit
```

执行列表中已经出现 `directory.get_employee` 和“成功”状态。随后以下 Locator 失败：

```ts
page.getByText("directory.get_employee", { exact: true })
```

Playwright 报告 Strict Mode Violation，因为页面同时存在两个精确文本元素：

```text
Paragraph  directory.get_employee
Span       directory.get_employee
```

测试真正需要的是 Execution Table 中可点击的详情 Link。宽泛 Text Locator 无法表达这个交互意图。

### Retry Attempt

CI 配置为失败后重试一次：

```ts
retries: process.env.CI ? 1 : 0
```

Disposable Database 只在 Playwright 启动前 Seed 一次。首次 Attempt 已经写入固定名称：

```text
directory.employee-directory-e2e
```

Retry 重新执行同一测试时再次注册该 Upstream，后端正确返回：

```text
upstream_conflict
```

Retry 因此在等待 Upstream Heading 时提前失败，掩盖了首次 Attempt 的 Locator 根因。

## 根因

存在两个相互独立的问题：

1. E2E 使用页面级 Text Locator，而实际动作要求 Execution Row Link；
2. 可变状态 E2E 使用固定 Fixture Name，但每次 Retry 前没有恢复 Disposable Database。

```text
首次 Attempt
业务链成功 → Locator 歧义 → 失败

Retry
继承首次数据 → Upstream Conflict → 更早失败
```

## 修正

### 唯一语义 Locator

将执行记录定位为 Link Role：

```ts
const executionLink = page.getByRole("link", {
  name: "directory.get_employee",
  exact: true,
});

await expect(executionLink).toBeVisible({ timeout: 30_000 });
await executionLink.click();
```

Role Locator 同时固定“文本”和“可点击执行详情入口”两层语义。

### Attempt 级数据库恢复

把 `seed_web_control_plane.py` 放到可变状态 E2E Test Body 开头。Playwright 每次 Retry 都会重新执行 Test Body，因此每次 Attempt 都从：

```text
TRUNCATE business tables
→ recreate fixed E2E Tenant
```

开始。Workflow 启动 Backend 前的首次 Seed 继续保留，保证 Application Startup 拥有合法 Tenant；Test Body Seed 负责 Attempt 隔离。

## 防回归原则

- 用 Role、Accessible Name 和稳定业务身份表达交互意图；
- 页面存在重复展示时，Locator 需要收窄到 Table/Region/Link；
- 配置 Retry 的可变状态 E2E 必须具备 Attempt 级 Reset；
- Retry 用于验证偶发基础设施问题，不能继承前一次业务写入；
- Artifact 诊断先阅读首次 Attempt，Retry Failure 可能是二次症状。

## 验证

- Frontend Typecheck：Passed；
- Frontend Lint：Passed；
- Frontend Format Check：Passed；
- 本机一次性 PostgreSQL + Fake Upstream + FastAPI + Unprivileged Nginx：Passed；
- 完整 Playwright E2E：`2 passed (18.3s)`；
- 可变状态用例 `--repeat-each=2 --workers=1`：`2 passed (30.7s)`，相同 Fixture Name 连续执行无 Conflict；
- GitHub CI：Pending。
