# ADR-0021｜单管理员 Direct Tool Publication Workflow

> 状态：Accepted
>
> 日期：2026-09-07
>
> 迭代：[I-04 Direct Tool Publication Workflow](../迭代记录/04_DirectToolPublicationWorkflow.md)

## Context

当前一个 Imported Operation 进入 Published Catalog 需要同一管理员依次执行：

```text
Review Operation
→ Create Draft
→ Submit Review
→ Publish Version
```

Local/Public Demo 只有一个固定 Admin Principal，没有独立 Reviewer/Publisher 身份、角色或职责分离。同一个人连续
点击 Submit Review 和 Publish 不能构成 Maker-Checker，只增加操作长度和演示成本。

Operation Review 仍有真实价值：管理员需要确认自动生成的 Tool Name、Schema、Side Effect、Visibility、Owner 和
HTTP Binding。Runtime Approval Gate 解决的是每次高风险 Tool Call，不属于发布审批，不能因为发布流程简化而删除。

## Decision

### 1. 默认管理路径使用单次 Direct Publish

Admin Web 对 Pending、无冲突的 Imported Operation 提供一次“确认并直接发布”：

```text
Preview Generated Contract
→ Confirm Direct Publish
→ Published ToolVersion + Binding
```

请求保留 `owner`、`visibility` 和可选 `review_notes`。第一版不提供 Schema、Binding、Tool Name 或 Side Effect
在线编辑；推导错误时拒绝发布，Contract Override 另立迭代。

### 2. Direct Publish 是单 Command、单事务

一个 `DirectPublishImportedOperation` Use Case 在同一个 `ReviewUnitOfWork` 中完成：

- 锁定 Operation、Upstream、Tool 和当前 Published Version；
- 生成 Draft ToolVersion/Binding；
- 执行 Draft → Review → Published 合法状态迁移；
- 校验 Schema/Binding Digest；
- 原子 Retire 旧 Published Version/Binding；
- 激活 Tool、保存 Accepted Operation；
- Commit 一次。

禁止通过依次调用三个会各自 Commit 的既有 Use Case 实现快捷按钮。任何失败必须回滚 Operation、Tool、Version、
Binding 和旧 Published 状态。

### 3. 复用既有状态机和发布规则

保留 Draft/Review/Published Domain Lifecycle、Digest 校验与 `ToolPublished` Event。抽取 Review/Publish 的事务内
函数，由旧 Use Case 与 Direct Publish 共用，不能复制第二套发布算法。

### 4. 第一版一次发布一个 Operation

不实现 Batch Publish。批量操作的全有或全无、部分失败和重试语义不属于本次减少单 Operation 点击的目标。

### 5. 旧 API 暂时兼容

新增：

```text
POST /admin/openapi/operations/{operation_id}/publish
```

旧 Review、Submit Review、Publish Endpoint 暂时保留；默认 Web UI 不再把它们作为主路径。未来只有在确认不再
支持 Maker-Checker，并完成 API Deprecation 后才删除。

### 6. 不增加发布模式开关

当前只正式实现 Direct Publish，不增加 `direct | maker_checker` Settings。真正 Maker-Checker 必须同时拥有：

- 企业 IAM 提供的不同 Actor；
- Reviewer/Publisher 角色与职责分离；
- 不可变审批 Snapshot/Digest；
- 修改后重新审批；
- 可证明不同 Actor 的持久化 Audit。

仅恢复两个按钮不算 Maker-Checker。

### 7. 明确 Toolset 暴露影响

Publish 表示 Tool 进入 Catalog，不自动加入普通 Explicit Toolset。拥有系统 `all_published` Grant 的 Agent 会立即
获得新 Tool，因此确认界面必须提示该影响及当前 Grant 数量。该提示是 Impact Preview，不是审批。

### 8. Runtime Approval 不变

Approval Gate 继续处理 Agent 每次高风险调用的单次批准、过期和防重放，与 Control Plane Direct Publish 完全
独立。

## Consequences

### Positive

- 单管理员主路径从三次人为动作缩短为一次确认；
- 不虚假声称实现职责分离；
- 事务失败不残留半完成 Draft/Review；
- 既有 Digest、版本历史、Toolset 与 Runtime Governance 全部保留；
- 旧 API 可作为兼容和未来扩展接缝。

### Trade-offs

- 需要重构 Review/Publish 的事务内函数，后端改动大于单纯 UI 串联；
- 当前没有真正的发布审批；
- 不支持批量发布和在线 Contract Override；
- `all_published` Grant 会让新 Tool 立即进入部分 Agent 的 Root/Scoped Catalog。

## Rejected Alternatives

### UI 依次自动调用现有三个 API

拒绝。任一后续步骤失败都会留下已 Commit 的中间状态，无法表达一次 Direct Publish。

### 删除 Draft/Review Domain Lifecycle

拒绝。状态迁移和 Digest Freeze 仍是安全发布规则，也为未来 Maker-Checker 保留演进空间。

### 立即实现 Direct/Maker-Checker 双模式

拒绝。当前没有生产 IAM 与不同 Actor，配置开关只会制造尚不存在的能力。

### 同时增加 Contract Editor 与 Batch Publish

拒绝。两者有独立业务语义，会把一次流程收敛扩大为 Catalog Authoring/Batch Transaction 项目。

## Validation

- Direct Publish 成功后 Version/Binding 同时 Published，Tool Active，Operation Accepted；
- Digest、Tenant、Upstream 和版本冲突仍按既有错误码拒绝；
- Commit/Flush 故障回滚所有新旧状态；
- 重复请求不重复创建版本；
- 旧三步 API Contract 继续通过；
- Web/Playwright 从 Import 直接 Publish，并继续完成 Toolset Scoped MCP Call；
- Runtime Approval Regression 不变。
