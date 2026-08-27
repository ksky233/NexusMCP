# ADR-0018｜Web Control Plane 工程布局与技术栈

> 状态：Accepted
> 日期：2026-08-27

## Context

NexusMCP 已经拥有 Local Admin REST API，覆盖 Upstream、OpenAPI Import、Review、Publish、Catalog Search
和 Approval，并已建立 Execution/Audit Reader 接缝。S6 前置增强需要把这些 Control Plane 状态机可视化，
提高演示、学习和面试可理解性。

当前没有普通业务员工直接使用 NexusMCP Web 的需求。普通员工通过 Codex、客服助手、销售助手等 Agent
消费 MCP Tool；Web 使用者是 Platform Administrator、Tool Owner、Security Administrator、Approver、
Operator 和 Auditor。角色不同，但共享同一个 Control Plane，而不是 `admin-web/user-web` 两个产品。

个人 React 工程手册的默认 Profile 是 React + TypeScript + Vite SPA、React Router、TanStack Query、
FastAPI OpenAPI Code Generation、Feature-first Directory 和分层质量门禁，与当前项目形态一致。但手册
默认的 `/api` 与 Production Session Auth 需要根据 NexusMCP 的 `/admin` 和 Local Development Admin
边界调整。

## Decision

### 1. 应用与目录

仓库根目录新增一个前端应用：

```text
web/
```

产品显示名称：

```text
NexusMCP Control Plane
```

不创建 `admin-web` 或假设中的 `user-web`。只有未来出现独立 Employee Portal，并且它具有不同用户、认证、
部署、发布节奏和 UX 时，才迁移为：

```text
apps/
├── control-plane-web/
└── employee-portal/
```

### 2. Runtime Profile

第一版采用：

```text
React
TypeScript Strict
Vite SPA
React Router
TanStack Query
React Hook Form + Zod
Tailwind CSS
shadcn Source Components + Base UI Primitives
pnpm
```

不使用 Next.js：当前没有 SSR、Server Component、SEO 或 Edge Rendering 需求。

不默认使用 Ant Design/MUI：当前 Table、Form、Dialog 和 Timeline 规模可以由源码拥有型组件承担，作品集也
需要展示组件边界、Token 和 Accessibility。只有复杂 Table/批量操作的真实成本出现后再评估 TanStack
Table 或完整后台组件库。

Zustand 不在初始化阶段安装。Theme、Sidebar 等真正跨页面且由浏览器拥有的状态出现后再按需引入，不把
Server State、Current User、Loading 或 Query Error 放入 Zustand。

### 3. Frontend Directory

```text
web/src/
├── app/
│   ├── router.tsx
│   └── providers.tsx
├── features/
│   ├── dashboard/
│   ├── upstreams/
│   ├── imports/
│   ├── catalog/
│   ├── approvals/
│   ├── executions/
│   ├── audit/
│   └── search-lab/
├── components/
│   ├── ui/
│   └── common/
├── generated/
│   └── api/
├── layouts/
├── lib/
├── config/
├── App.tsx
└── main.tsx
```

Feature 内按真实职责逐步创建 `pages/sections/parts/api/hooks/schemas/utils`，不为目录对称预建空文件夹。
Router 只加载 Page；Page 组合 Section/Part；`components/ui` 不理解业务；`components/common` 只保存至少
两个 Feature 稳定复用的应用组件。

### 4. State Ownership

```text
Backend Entity/List/Detail/Stats → TanStack Query
Filter/Sort/Page/Tab/Resource ID → React Router URL State
Register/Review/Edit Form        → React Hook Form + Zod
Dialog/Expanded Row/Selection    → Local State
Theme/Sidebar                    → Local State，必要时再引入 Zustand
Display/Permission Derivation    → Derived State
```

Server State 不复制到 Zustand 或 Effect Local Copy。Query Data 初始化 Form 后，Dirty Draft 由 Form 拥有，
后台 Refetch 不覆盖用户尚未提交的输入。

Approval、Import、Execution 等非终态资源第一版使用 TanStack Query Polling；Terminal State 立即停止。没有
真实双向实时需求前不引入 SSE/WebSocket。

### 5. API Contract 与 Code Generation

唯一传输契约来源是 FastAPI Admin OpenAPI：

```text
Admin Pydantic Schema + Route
→ Deterministic Export
→ contracts/admin.openapi.json
→ @hey-api/openapi-ts
→ web/src/generated/api
→ Feature API Wrapper
→ Query/Mutation Hook
→ Page/Section
```

生成器使用并锁定精确版本的 `@hey-api/openapi-ts`。第一版生成 TypeScript DTO、Fetch Client 和 Endpoint
SDK，不生成或直接使用业务 TanStack Query Hook。Query Key、Enabled、Stale Time、Retry、Polling、
Mutation Invalidation 和 Optimistic Update 属于 Feature 业务决策，由 `features/**/hooks` 手写。

生成目录提交 Git、禁止手工修改、参与 Type Check，并根据生成器输出明确排除或受控执行 Lint/Format。
生成目录不保存 Query Key、Toast、Router、Mapper 或业务错误分支。

Page 不直接调用 Generated SDK。Feature API 负责解包、受控 Mapper 和业务命名，但不重复声明生成 DTO。

### 6. W0 Backend Contract Requirements

正式生成 SDK 前，Admin API 必须完成：

1. 为公开 Route 设置稳定、唯一的 `operationId`；
2. 确定性导出 `contracts/admin.openapi.json`，不依赖临时线上 URL；
3. List/Detail/Pagination Contract 统一；
4. Date/Enum/Nullable/UUID 语义明确；
5. Remote MCP Admin Input 在 Connector 实现前 Reject/Hide；
6. Expected Error 进入 OpenAPI Response Schema。

当前 Admin Error：

```json
{
  "code": "upstream_not_found",
  "message": "The requested upstream service was not found.",
  "request_id": "..."
}
```

W0 将其升级为 RFC 9457-compatible Problem Details，同时保留稳定 NexusMCP Error Code：

```json
{
  "type": "urn:nexusmcp:error:upstream_not_found",
  "title": "Request rejected",
  "status": 404,
  "detail": "The requested upstream service was not found.",
  "code": "upstream_not_found",
  "request_id": "..."
}
```

Frontend 只按 `status/code` 做业务分支，不解析 `title/detail/message`。非法 Content-Type/Envelope/Schema 转为
Protocol Error，并显示有限 Safe Summary + Request ID。

### 7. HTTP Client Boundary

```text
Page
→ Feature Hook
→ Feature API
→ Generated SDK
→ Configured Fetch Client
→ relative /admin
```

项目适配：

- 手册示例 `/api` 改为 NexusMCP 已有的相对 `/admin`；
- Development 由 Vite Proxy 转发 `/admin` 和 `/health`；
- Production/Demo 由 Nginx Same-Origin Proxy；
- MCP `/mcp` 保留现有 Backend 协议入口，本 ADR 不要求 Frontend Nginx 代理或改写 MCP Transport；
- API Client 负责 Timeout、Abort、Problem Details、Request ID/Trace ID 和错误分类；
- API Client 不调用 Toast、Router 或 React Component；
- 默认不自动 Retry，TanStack Query 只对允许的幂等 Query 做有限 Retry；
- Mutation 默认不 Retry，Publish/Approval 等高风险操作等待后端权威结果。

### 8. Local Admin Authentication Boundary

第一版明确是：

```text
Local Development Admin
Fixed Tenant / Principal from Backend Settings
No Login / No Session / No CSRF / No Production RBAC
```

UI 必须持续显示 `Local Development Admin · Not Production Authentication`。不制作虚假 Login、不把固定
Principal 包装成真实用户系统、不在浏览器保存 Token。

未来 Production Admin OIDC/AuthN/AuthZ 形成独立 ADR 后，再引入 Session Bootstrap、Route Guard、Role
Navigation、Logout、CSRF 和 User Cache 清理。Frontend Permission 只控制展示和交互引导，永远不能替代
Backend 鉴权。

### 9. UI and Interaction

- shadcn/Base UI Source Component 进入 `components/ui` 并正常 Review；
- Tailwind 使用 Semantic Token，不建立第二套视觉组件体系；
- Page/Section/Part 按职责拆分，不按固定行数；
- Table Filter/Sort/Page 进入 URL + Query Key；
- 危险 Publish/Approve/Reject/Disable 使用明确 Confirm；
- Loading、Empty、Error、Refreshing、Stale 分开表达；
- 后台刷新保留已有数据；
- Form Field、Form Summary、Page Error 和 Toast 不重复展示同一错误；
- Keyboard、Focus、Accessible Name 和 Error Recovery 属于验收条件。

### 10. Quality Gate

前端统一使用：

```text
TypeScript Strict
Oxlint --max-warnings=0
Oxfmt
Vitest
React Testing Library
MSW
Playwright
```

本地/CI 基础门禁：

```text
pnpm install --frozen-lockfile
pnpm api:generate
pnpm format:check
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

Contract Drift Gate：

```text
Export Admin OpenAPI
→ Generate SDK
→ git diff --exit-code
```

测试边界：

- Unit：Zod、Mapper、URL Parser、Query Key、纯状态函数；
- Component：Form、Dialog、Permission、Loading/Empty/Error；
- MSW：真实 Generated SDK/Fetch Client、Problem/Network/Abort/Cache；
- Playwright：Browser → Web/Nginx → `/admin` → FastAPI → PostgreSQL Test DB；
- 第一条 E2E 不测试 Login，测试 Register → Import → Review → Publish → Catalog → MCP Call → Audit。

### 11. Build and Deployment

- pnpm 只提交一个 Lock File，CI 使用 Frozen Install；
- Node/pnpm/Vite/Codegen 精确版本在 Scaffold 时锁定并进入工程档案；
- Vite 输出 `dist`；
- Demo/Production-like 使用 Multi-stage Build + Unprivileged Nginx Runtime；
- Runtime Image 不包含 Node、源码、Secret、Source Map 或测试报告；
- Frontend 使用 Same-Origin `/admin`，同一 Artifact 不因 API Host 重建；
- `/healthz` 只证明 Frontend Nginx 存活，Backend `/health/ready` 单独验证；
- 当前不引入 Runtime Config、CDN、Sentry 或 Production Release Manifest，真实需求出现后再评估。

### 12. Feature Scope

第一版页面：

```text
Dashboard
Upstreams
Imports / Review
Tool Catalog
Approvals
Executions / Audit
Search Lab（Should）
```

业务路径：

```text
Register HTTP Upstream
→ Import OpenAPI
→ Review / Submit / Publish
→ Catalog
→ Search Lab
→ MCP Call
→ Execution / Attempt / Audit
```

## Non-Goals

- `admin-web/user-web` 多应用拆分；
- Remote MCP；
- Production Login/OIDC/RBAC；
- 动态 Policy Builder；
- Secret Value 输入或展示；
- Egress Policy 在线编辑；
- Drag-and-Drop Tool Builder；
- File Upload/SSE/WebSocket；
- 大屏动画和完整企业设计系统；
- Next.js/SSR；
- 为 UI 重写 Backend 状态机。

## Rejected Alternatives

- 预建 `admin-web/user-web`：当前没有第二类 Web 用户和独立发布边界；
- 使用 Next.js：没有 SSR/SEO/Server Component 需求；
- Page 直接使用 Generated SDK：会让传输 DTO、错误和 Cache 语义扩散；
- 全量生成 TanStack Query Hook：无法表达当前 Mutation Invalidation 和业务恢复语义；
- 手写重复 API Interface：会与 FastAPI Pydantic Contract 漂移；
- 所有状态进入 Zustand：制造第二份 Server Cache；
- 第一版制作 Login：会把固定 Local Admin 伪装成 Production Auth；
- 默认使用大型后台组件库：当前需求尚未证明其成本收益；
- FastAPI 直接承担前端源码构建：混淆 Python Runtime 与 Node Build Boundary。

## Consequences

- 仓库增加 Node/pnpm Toolchain、Frontend CI 和生成代码 Diff；
- W0 必须先补齐 Admin Query API、Operation ID、Problem Details 和 Contract Export；
- Generated SDK 使前后端字段变化在 Compile/CI 阶段显式失败；
- Feature Hook 保留 Query/Mutation 语义，代码比全自动 Hook 多，但边界更清楚；
- Local Admin UI 可以立即展示当前治理链，但不能对外声称 Production Admin IAM；
- Nginx 与 Full-stack Playwright 增加部署资产，但能证明真实 Same-Origin Route 和数据库联通；
- 未来 Employee Portal 如出现，可以依据独立用户/认证/部署证据再拆应用。

## Verification

- `web/` 是唯一 Frontend App；
- Frontend 标题和导航使用 `NexusMCP Control Plane`；
- 页面持续显示 Local Admin 安全声明；
- OpenAPI 可以确定性导出并生成 SDK；
- Generated SDK 无手改，CI Drift Check 通过；
- Page 不直接拼 Endpoint 或调用 Generated SDK；
- Server/URL/Form/Local State Owner 唯一；
- Admin Problem Details 与 Request ID 可以进入错误 UI；
- Remote MCP 不出现在注册选项；
- Unit/Component/MSW/Playwright 边界按风险落地；
- 一条 Full-stack E2E 可以从空 Test DB 完成 Control Plane 主链；
- Production Build、Nginx SPA Fallback 和 `/admin` Proxy 验证通过。

## References

- [Hey API OpenAPI TypeScript](https://heyapi.dev/)
- [TanStack Query](https://tanstack.com/query/latest)
- [Vite](https://vite.dev/)
- [Playwright](https://playwright.dev/)
- [ADR-0017｜延后 Remote MCP，优先 Web Control Plane](./0017-defer-remote-mcp-and-focus-web-control-plane.md)
- [09｜S6 前置 Web Control Plane 与 Remote MCP 边界](../项目规划/09_S6前置WebControlPlane与RemoteMCP边界.md)
