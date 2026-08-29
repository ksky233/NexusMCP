# 09｜S6 前置 Web Control Plane 与 Remote MCP 边界

> 状态：产品与工程规划已冻结；W0～W4 已完成，W5 待开始
> 日期：2026-08-27
> 决策：Remote MCP Deferred；优先 Admin Query API 与 Web UI MVP
> 工程基线：见 ADR-0018

## 1. 目标

在不改变 NexusMCP 当前 HTTP/OpenAPI Tool Governance 定位的前提下，用 Web Control Plane 把已经完成的
接入、审核、发布、搜索、审批、执行和审计链路可视化，为 S6 作品集提供可操作 Demo。

本计划不是新的大型管理平台，也不引入 Production Admin Authentication。

## 2. Remote MCP 边界

当前不实现：

- Remote MCP Federation/Proxy；
- Developer MCP Usage Tracking；
- Enterprise-wide Personal MCP Enforcement；
- Transparent MCP Relay；
- Remote Resources/Prompts/Sampling；
- Remote Legacy Session；
- MCP Marketplace。

触发条件与理由以
[ADR-0017](../adr/0017-defer-remote-mcp-and-focus-web-control-plane.md) 为准。

实现前修正：

- Admin Request Schema 不再暴露当前无法执行的 `remote_mcp`；
- Domain Enum 可以保留，但明确标记 Reserved/Unsupported；
- 错误使用时返回稳定 `feature_not_enabled`；
- README、Quick Start、Architecture 和 Demo 只承诺 HTTP/OpenAPI Upstream。

## 3. 当前 Admin API

已有能力：

- Register/List/Update/Disable Upstream；
- Submit OpenAPI Import；
- Get Import Detail；
- Review Imported Operation；
- Submit ToolVersion Review；
- Publish Tool；
- Catalog Search；
- Get/Approve/Reject Approval；
- Swagger `/admin/docs`。

当前 `/admin` 使用固定 Local Tenant/Principal，只适合 Development/Learning。

## 4. Web UI 所需 Query API

### Must

- Dashboard Aggregate；
- Upstream Detail；
- Import Job List/Pagination；
- Review Queue List；
- Tool Catalog List/Pagination/Filter；
- Tool Detail；
- ToolVersion History；
- ToolBinding Detail；
- Approval List/Status Filter；
- Execution List/Detail；
- Attempt List；
- Audit List，支持 Trace/Principal/Tool Filter；
- Embedding Projection Coverage/Indexed Time。

### Deferred

- Production Admin User/Role；
- Dynamic Policy Editor；
- Credential Secret Value 输入；
- Egress Policy 在线编辑；
- Drag-and-Drop Tool Builder；
- 多租户切换；
- Dashboard 自定义图表。

## 5. Web UI 页面

### 5.1 Dashboard

- Active Upstream；
- Published Tool；
- Pending Review；
- Pending Approval；
- Failed/Unknown Execution；
- Search Index Coverage；
- 最近 Audit；
- PostgreSQL/Embedding/Telemetry 状态摘要。

### 5.2 Upstreams

- 注册 HTTP/OpenAPI Upstream；
- 编辑 Owner、Endpoint、Auth Scheme、非敏感 Config；
- Disable；
- 提交 OpenAPI Import；
- 展示 Egress Validation 错误；
- 不展示 Remote MCP 选项。

### 5.3 Import 与 Review

- Import Job 列表和详情；
- Operation Diff/Conflict/Unsupported Feature；
- Input/Output Schema；
- Side Effect、Visibility、Owner；
- Review；
- Submit Review；
- Publish Digest Conflict。

### 5.4 Tool Catalog

- Namespace/Status/Visibility/Side Effect Filter；
- Canonical Name、Description、Tags、Owner；
- Version History；
- ToolBinding；
- Input/Output Schema；
- Search Document Digest；
- Embedding Model/Dimensions/Indexed Time。

### 5.5 Approval

- Pending/Approved/Rejected/Expired/Consumed；
- Principal、Tool、Policy、Expiry；
- Arguments Digest；
- Approve/Reject；
- 不展示完整敏感 Arguments；
- Dangerous Action Confirm。

### 5.6 Execution 与 Audit

- Execution Status；
- Attempt Timeline；
- Retry/Error Category/Upstream Status；
- Idempotency Key 是否存在，不展示敏感 Payload；
- Principal/Tool/Trace；
- Audit Timeline；
- Request ID/Trace ID Copy。

### 5.7 Search Lab（Should）

- Query；
- Lexical/Hybrid；
- Namespace/Side Effect；
- Candidate Rank；
- Full Tool Schema；
- Index Version；
- 明确提示 Candidate 不等于最终正确 Tool；
- No-Match Confidence Gap 提示。

## 6. 技术方案

工程布局、状态所有权、API Code Generation、质量和部署已由
[ADR-0018](../adr/0018-web-control-plane-engineering.md) 冻结。

采用：

```text
React
TypeScript
Vite
React Router
TanStack Query
React Hook Form + Zod
shadcn + Base UI + Tailwind
Vitest
React Testing Library
MSW
Playwright（1 条核心 E2E）
```

目录：

```text
web/
├── src/
│   ├── app/
│   ├── features/
│   ├── components/
│   └── generated/api/
├── tests/
├── package.json
└── vite.config.ts
```

不预建 `admin-web/user-web`；只有未来出现独立 Employee Portal 后才根据真实用户、认证和部署边界拆分。

Development：

```text
Vite Dev Server
→ Proxy /admin /health
```

作品集 Demo：

```text
Static Build
→ 独立 Nginx 或 FastAPI Static Mount
```

第一版优先 Same-Origin，避免为 Demo 扩大 CORS/Auth 范围。

## 7. UI 安全边界

- 页面顶部持续显示 `Local Development Admin`；
- 不制作虚假 Login；
- 不输入/返回 Secret Value，只管理 SecretReference；
- 不展示 Token、Credential、完整 Arguments/Result；
- Unexpected Error 只展示 Safe Message + Request ID；
- Publish 使用 Expected Digest 并处理 Conflict；
- Approval/Disable/Publish 使用确认交互；
- 前端权限显示不能替代后端鉴权；
- UI 不直接访问 PostgreSQL。

## 8. 工作包

### W0｜边界修正（已完成）

- Remote MCP Admin Input Reject/Hide；
- README/Architecture 叙事修正；
- Admin API OpenAPI Contract Snapshot；
- UI 路由与字段草图。

完成记录：

- 13 个现有 Admin Route 已设置稳定 `operationId`；
- `contracts/admin.openapi.json` 可无网络确定性导出并受 Contract Test 保护；
- Expected Error 与 Validation Error 统一为 `application/problem+json`；
- 普通资源列表冻结为 `items + page(offset/limit/total)`；
- Remote MCP 已从公开输入隐藏，并在绕过 Schema 时返回 `feature_not_enabled`；
- 详细结果见 [W0 Admin API Contract 固化](../实验记录/30_W0_AdminAPIContract固化.md)。

### W1｜Admin Query API（已完成）

- Dashboard；
- List/Detail/Pagination；
- Approval/Execution/Audit Filter；
- Tool Version/Binding；
- Search Projection Status；
- Contract/Integration Test。

完成记录：

- 新增跨上下文 `ControlPlaneQueryPort` 与 PostgreSQL Read Model Adapter；
- Admin OpenAPI 从 13 个扩展为 27 个稳定 Operation；
- Dashboard、Upstream/Import/Review、Tool/Version/Binding、Approval、Execution/Attempt、Audit 与
  Search Projection Query 已接通；
- 所有普通列表统一数据库分页、精确过滤和 Tenant Predicate；
- Operational Query 只返回摘要、Digest、Request/Trace ID，不返回完整 Arguments、Result、Credential；
- 详细结果见 [W1 Admin Query API](../实验记录/31_W1_AdminQueryAPI.md)。

### W2｜React Shell（已完成）

- Layout/Navigation；
- API Client；
- Query Cache；
- Loading/Empty/Error；
- Local Admin Banner；
- Request ID。

完成记录：

- 唯一 `web/` React + TypeScript + Vite SPA 已创建；
- Router、Responsive Shell、Local Admin Banner 与 W3/W4 Placeholder Route 已建立；
- Hey API 从提交的 Admin OpenAPI 生成 DTO、Fetch SDK 与 Zod Response Validator；
- Problem Details、Network、Timeout、Abort、Protocol Error 与 Request ID Client Boundary 已建立；
- TanStack Query 接通真实 Dashboard，Vite `/admin`、`/health` Proxy 已完成 PostgreSQL Runtime Smoke；
- CI 增加 Frontend Frozen Install、Codegen Drift、Format、Type Check、Lint、Test 与 Build；
- 详细结果见 [W2 React Shell](../实验记录/32_W2_ReactShell.md)。

### W2.5｜Control Plane UI 基线（已完成）

- 将“黑白-细硬”参考模板提炼为 NexusMCP Semantic Token；
- 替换 White Sidebar、Header、Mobile Navigation 与 Dashboard 视觉；
- 冻结 Button、Status、Form、Table、Pagination、Dialog 和 Query State；
- 保持 Base UI Accessibility，不复制模板原生 DOM Script；
- 视觉规范见 [Control Plane 视觉基线](../前端/01_ControlPlane视觉基线.md)。

完成记录：

- 黑白灰 Semantic Token、3px/6px Radius、Hairline Border/Shadow 已冻结；
- White Sidebar、Sticky Header、Base UI Mobile Navigation 与 Dashboard 已替换；
- Button、Status、Form、Table、Pagination、Dialog 和 Query State 已建立；
- Dashboard Lazy Route 完成 Chunk 拆分，Desktop/Narrow Screenshot 与组件交互测试通过；
- 详细结果见 [W2.5 Control Plane UI 基线](../实验记录/33_W2.5_ControlPlaneUI基线.md)。

### W3｜核心业务页面（已完成）

- Dashboard；
- Upstreams；
- Import/Review；
- Catalog；
- Approval；
- Execution/Audit。

完成记录：

- Upstream Register/List/Detail/Edit/Disable；
- OpenAPI Import/List/Detail、Operation Review、Submit Review、Digest-safe Publish；
- Catalog Filter、Tool Detail、Version History、Schema 与 Binding；
- Approval Filter 与 Confirm Approve/Reject；
- Execution/Attempt/Audit Filter 与 Timeline；
- 为刷新恢复新增 `getToolVersion` 与 `getToolVersionBinding`，Admin Contract 扩展为 29 Operation；
- 详细结果见 [W3 核心业务页面](../实验记录/34_W3_核心业务页面.md)。

### W4｜Search Lab 与 Evidence（已完成）

- Lexical/Hybrid 对照；
- Retrieval Snapshot 展示；
- Benchmark/Security/Protocol Evidence 页面或链接；
- 一条 Playwright E2E。

完成记录：

- Live Lexical/Hybrid Search Lab 与 Retrieval Snapshot；
- Benchmark/Security/Protocol/Failure/Residual Risk Evidence 页面；
- 30-Operation Admin Contract；
- Multi-stage Build + Unprivileged Nginx + Same-Origin Admin/Health/MCP；
- Full-stack Playwright `2 passed`，覆盖 Browser Publish→MCP Call→Execution/Audit；
- 详细结果见 [W4 Search Lab、Evidence 与 Full-stack E2E](../实验记录/35_W4_SearchLabEvidence与FullstackE2E.md)。

### W4.5｜Web UI 中文化与后台密度校准（已完成）

- 用户可见的导航、标题、说明、表单、操作、状态与错误界面使用中文；
- API 字段、状态码、错误码、日志、Trace/Request ID 与代码标识继续使用英文；
- 保留 Namespace、Principal、Tool、Policy、Binding、Schema 等必要领域术语，避免生硬全译；
- 按“黑白-细硬 v2”强化 Panel、Filter、Table、Control 与 Secondary Action 边界；
- 加深 Eyebrow、Component Label 与 Field Label，收敛 Hover 位移和空气感；
- Vitest 与 Playwright Accessible Name Selector 同步中文 Contract；
- 详细结果见 [W4.5 Web UI 中文化与视觉密度](../实验记录/36_W4.5_WebUI中文化与视觉密度.md)。

### W4.6｜Tool Search Index Management（已完成）

- Catalog 增加检索索引管理入口，展示 Published、Current、Missing、Stale 与 Model@Dimensions；
- 普通更新只处理 Missing/Stale Projection，Current Tool 不重复调用付费 Embedding API；
- 新增持久化 Reindex Job、每租户单 Active Job 去重、任务状态查询与进程重启中断恢复；
- Admin API 使用 `202 Accepted + Background Task`，浏览器不持有 Embedding API Key；
- 第一版 Background Task 与 Web 进程同生命周期，不声称已经是独立分布式 Worker；
- Search Lab 展示 RRF 分数、Vector 排名、Vector Cosine、Lexical 排名和 FTS 分数；
- RRF 继续只融合名次，不改变 Agent-facing `lexical | hybrid` Contract；
- Development Control Plane 启动时幂等创建 Local Tenant，修复首次注册的外键失败；
- PostgreSQL Repository 只将 `23505 unique_violation` 映射为 `upstream_conflict`；
- 详细结果见 [W4.6 Tool Search Index Management](../实验记录/37_W4.6_ToolSearchIndexManagement.md)。

### W5｜S6 包装

- Screenshot；
- Architecture/Sequence Diagram；
- Quick Start；
- Demo Script；
- English Overview；
- Limitations；
- Clean Environment Reproduction。

## 9. 验收 Demo

```text
启动 PostgreSQL/pgvector + NexusMCP + Web
→ 注册 Employee Directory Upstream
→ Import OpenAPI
→ Review / Submit / Publish
→ Catalog 出现 Tool
→ Search Lab 找到 Tool
→ Modern MCP Client 调用 Tool
→ UI 查看 Execution / Attempt / Audit
→ 演示 Approval 或 SSRF 拒绝
```

验收约束：

- UI 不包含 Demo 场景专用业务代码；
- 所有业务状态来自 Admin API；
- 后端仍是权限与状态机唯一事实源；
- 一台干净环境按 Quick Start 可复现；
- 不因 UI 延迟现有测试、限制说明和安全证据。

## 10. 投入估算

| 工作包 | 预计投入 |
|---|---:|
| W0 边界与 Contract | 4～8 小时 |
| W1 Admin Query API | 12～20 小时 |
| W2 React Shell | 6～10 小时 |
| W2.5 UI 基线 | 4～8 小时 |
| W3 核心页面 | 18～28 小时 |
| W4 Search Lab/Test | 8～14 小时 |
| W4.5 中文化/视觉密度 | 3～5 小时 |
| W4.6 Search Index Management | 8～14 小时 |
| W5 S6 包装 | 20～30 小时 |

Web 增强本身约 63～107 小时；S6 完整包装另计。若求职时间受限，优先 Dashboard、Import/Review、Catalog、
Execution/Audit 四条可视化主链。

## 11. 停止条件

- 不做 Production Admin IAM；
- 不做复杂动态 Policy Builder；
- 不做 Remote MCP；
- 不做拖拽式 Tool Builder；
- 不做大屏动画；
- 不为了 UI 重写后端状态机；
- 核心 E2E、Screenshot 和 Demo Script 完成后停止扩展。
