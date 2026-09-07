# I-04｜Direct Tool Publication Workflow

> 状态：In Progress（Implementation Verified，Commit Pending）
>
> 日期：2026-09-07
>
> 触发：单管理员环境中，Imported Operation Review、Submit Review、Publish 由同一身份连续执行，形成流程仪式，
> 没有真正实现 Maker-Checker
>
> 决策依据：[ADR-0021](../adr/0021-direct-tool-publication-workflow.md)

## 1. 目标

- 单管理员通过一次明确确认，把 Imported Operation 直接发布为可用 Tool；
- 保留 Schema/Binding Digest、Tenant、Upstream、版本切换和并发校验；
- 让页面明确展示被发布的业务能力及发布后的 Agent 暴露影响；
- 不把单管理员连续点击包装成“四眼审批”；
- 保持 Runtime Approval Gate 不变。

## 2. 非目标

- 企业 IAM、Reviewer/Publisher RBAC 或职责分离；
- 业务人员登录 NexusMCP 审批；
- 批量 Operation 发布与部分失败编排；
- 在线编辑 OpenAPI Schema、Binding 或 Tool Name；
- 删除现有 Draft/Review/Published Domain Lifecycle；
- 修改 Runtime Tool Call Approval；
- 本轮公网部署。

## 3. 三类容易混淆的 Review/Approval

| 机制 | 发生时间 | 当前作用 | I-04 决策 |
|---|---|---|---|
| Imported Operation Review | OpenAPI 导入后 | 确认生成的 Tool 语义、Owner、Visibility | 保留为发布确认内容，合并进直接发布 |
| ToolVersion Submit Review | Tool 发布前 | 为 Maker-Checker 冻结 Review 状态 | UI 不再单独暴露；内部 Lifecycle 保留 |
| Runtime Approval Gate | 每次高风险 Tool Call | 单次人工批准并防重放 | 完全保留，不属于 I-04 |

URL、DNS/Egress 和认证方式属于平台技术校验；未来业务 Owner 真正需要确认的是 Tool 语义、数据敏感性、副作用、
幂等性以及哪些 Agent Service 可以使用，而不是只确认 URL 是否正确。

## 4. Before

```text
Register Upstream
→ Import OpenAPI
→ 审核 Operation
→ Accept + Create Draft ToolVersion/Binding
→ Submit ToolVersion Review
→ Confirm Publish
→ Published Tool
```

当前 Local/Public Demo Admin 的所有步骤都由同一个固定 Principal 完成。状态机和 Digest 校验真实存在，但人为审批
分离并不存在。

## 5. Target

```text
Register Upstream
→ Import OpenAPI
→ Preview Generated Tool Contract
→ Confirm Direct Publish
→ Published Tool
```

一次确认至少展示：

- Operation ID、HTTP Method 与 Path；
- Canonical Tool Name、Description；
- Input/Output Schema；
- Side Effect、Visibility、Owner；
- Schema Digest 与 Binding Digest；
- `all_published` 当前 Grant 数量及“未来自动暴露”提示。

发布后 Tool 进入 Catalog。普通 Agent 仍需 Explicit Toolset Membership + Grant 才能使用；拥有系统
`all_published` Grant 的 Agent 会立即获得新 Tool，因此确认框必须提示影响，但不把提示伪装成审批。

## 6. 核心实现决策草案

### 6.1 一个 Command、一个事务

推荐新增单 Operation Command：

```text
DirectPublishImportedOperation
```

它在一个 `ReviewUnitOfWork` 中完成：

```text
Lock ImportedOperation / Upstream / Tool
→ Build Draft ToolVersion + Binding
→ Transition Draft → Review
→ Verify Schema/Binding Digest
→ Retire current Published Version/Binding（如存在）
→ Publish new Version/Binding
→ Activate Tool
→ Mark Operation Accepted
→ Commit once
```

现有 `ReviewUnitOfWork` 已同时提供 Imports、Catalog、Bindings 和 Upstreams Repository，Schema 无需变化。实现时应
从 `ReviewImportedOperation` 与 `PublishTool` 抽取可复用的事务内函数，避免复制发布规则。

不采用“新 Use Case 依次调用三个现有 Use Case”：三个独立 Commit 会让中间状态泄漏，直接发布失败后仍残留
Accepted Operation 和 Draft/Review Version，不符合一次业务动作的语义。

### 6.2 第一版只发布单个 Operation

推荐继续以 Operation Card 为单位直接发布。批量发布会引入全有或全无、部分成功、重试和错误汇总决策，与本次
减少点击的目标无关。

### 6.3 保留旧 API，先替换默认 UI

推荐新增：

```text
POST /admin/openapi/operations/{operation_id}/publish
```

请求沿用当前 Review 所需的 Owner、Visibility、Review Notes。现有 Review、Submit Review、Publish Endpoint
暂时保留，避免立即破坏 Generated Client、自动化测试和未来 Maker-Checker 扩展；默认 Web UI 只展示直接发布。

### 6.4 不增加发布模式开关

当前只正式支持单管理员直接发布，不新增 `direct | maker_checker` 配置。真正 Maker-Checker 必须等企业 IAM 能
提供不同 Actor、角色和不可变审批快照后再设计，不能只恢复两个按钮。

## 7. 需要关闭的三个实施问题

### T-001｜直接发布是否必须单事务

推荐：**是**。这是本次唯一会显著增加代码量的地方，但能避免半完成状态，也是直接发布成为业务 Use Case 而非
UI 自动点击脚本的关键。

### T-002｜旧三步 API 是否立即删除

推荐：**不删除**。先从 UI 主路径移除，保留兼容和底层测试。只有确定不再做 Maker-Checker 且完成 API
Deprecation 后再删除。

### T-003｜本轮是否允许修改生成的 Tool Contract

推荐：**不扩展编辑能力**。沿用当前 Owner、Visibility、Review Notes，并完整展示自动推导的 Side Effect、Schema
和 Binding。发现推导错误时不发布，Contract Override 作为单独迭代讨论，避免把流程简化变成 Catalog Editor。

## 8. 代码影响面与规模

```text
Backend
├── OpenAPI Review/Publish 事务内函数抽取
├── Direct Publish Use Case
├── Admin Request/Response/Route
└── Unit + PostgreSQL Atomicity Test

Frontend
├── Generated Client
├── Operation Card 直接发布确认
└── 删除默认 Submit Review 中间交互

Evidence
├── Playwright 主流程缩短
└── OpenAPI Contract / Full Suite
```

预计不新增 Migration，不改变 MCP Data Plane、Toolset、Policy、Credential 或 Runtime Approval。属于中等规模的
跨层改动，不是大型架构重构。

## 9. 验证矩阵

- 成功路径只提交一次，最终直接得到 Published Tool/Binding；
- Digest、Tenant、Upstream、Conflict 校验不回归；
- 任一步失败后 Operation、Tool、Version、Binding 和旧 Published Version 均保持原状态；
- 重复请求幂等返回既有 Published 结果，不重复创建版本；
- `all_published` 影响提示可见；
- Runtime Approval 测试完全不变；
- Playwright 从 Import 直接进入 Publish，再完成 Toolset Scoped MCP Call。

## 10. 回滚

旧 Review/Submit/Publish API 暂时保留，因此新 Direct Publish Route/UI 出现问题时，可以回退 Web 主路径，不需要
回滚 Schema 或删除已发布 Tool。Direct Publish 必须复用既有 Digest 与版本切换规则，不能产生第二套发布语义。

## 11. 实施结果

- ADR-0021 已 Accepted；
- 抽取 `ReviewImportedOperation.execute_in_transaction()`；
- 抽取 `publish_tool_in_transaction()`，旧 Publish Use Case 继续复用；
- 新增单事务 `DirectPublishImportedOperation`；
- 新增 `directPublishImportedOperation` Admin Operation；
- Import Detail Response 增加 Generated Contract Preview；
- 默认 Web UI 改为“直接发布”，旧三步 API 保留；
- 确认区域显示 `all_published` Grant 影响；
- Playwright 已切换为 Direct Publish → Toolset → Scoped MCP → Audit 主路径。

验证结果：

```text
Full Python Suite   362 passed / 2 paid external skipped
Ruff Lint/Format    passed
basedpyright        0 errors / 0 warnings
Frontend Vitest     24 passed
Frontend Build      passed
Playwright E2E      2 passed / 11.7s
```

最终提交完成后，将状态更新为 Completed 并补充 Commit ID。
