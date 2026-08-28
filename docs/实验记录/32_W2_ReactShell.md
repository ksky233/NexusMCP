# W2｜React Shell

> 日期：2026-08-28  
> 状态：完成

## 1. 目标

正式建立唯一的 `web/` 前端应用，跑通：

```text
Browser
→ React Router / App Shell
→ Feature Hook / TanStack Query
→ Feature API Wrapper
→ Generated Hey API SDK
→ Vite Same-Origin /admin Proxy
→ FastAPI Admin Query
→ PostgreSQL
```

W2 建设可运行的基础设施与第一条真实 Dashboard Slice，不提前实现 W3 的完整管理业务页面。

## 2. 工程基线

| Dependency | Exact Version |
|---|---:|
| Node.js | 22.18.0 |
| pnpm | 10.15.1 |
| React / React DOM | 19.2.8 |
| React Router | 7.18.2 |
| TanStack Query | 5.102.8 |
| Vite | 8.2.2 |
| TypeScript | 5.9.3 |
| Hey API | 0.99.0 |
| Tailwind CSS | 4.3.3 |
| Base UI | 1.7.0 |
| Vitest | 4.1.11 |
| MSW | 2.15.0 |
| Oxlint / Oxfmt | 1.80.0 / 0.65.0 |

所有版本在 `package.json` 和 `pnpm-lock.yaml` 精确锁定。第一版不引入 Zustand、Next.js、Ant Design、
MUI、Production Login 或前端权限事实源。

## 3. 已建立的 Shell

- `NexusMCP Control Plane` 产品标题；
- 响应式 Sidebar 与 React Router；
- Dashboard、Upstreams、Imports、Catalog、Approvals、Executions、Search Lab 路由；
- W3/W4 页面使用明确 Placeholder，不伪装为已完成功能；
- 全局持续显示 `Local Development Admin · Not Production Authentication`；
- 404 Page；
- Loading、Empty、Error、Refreshing 状态；
- Tailwind Semantic Token 与 Reduced Motion；
- Base UI + CVA Source-owned Button。

## 4. API 与状态边界

```text
contracts/admin.openapi.json
→ @hey-api/openapi-ts
→ TypeScript DTO + Fetch SDK + Zod Response Schema
→ Feature API
→ Feature Query Hook
→ Page
```

- Generated Directory 提交 Git，禁止手工修改；
- 生成代码参与 Type Check，但由生成器拥有 Lint/Format 风格；
- `runtimeConfigPath` 在 Client 初始化前设置 Same-Origin `/admin`；
- Artifact 根据浏览器当前 Origin 计算 URL，不绑定 Build-time API Host；
- Dashboard Page 不直接调用 Generated SDK；
- Feature API 设置 10 秒 Abort Timeout；
- Feature Hook 拥有 Query Key、15 秒 Stale Time、30 秒 Polling 与一次 Network-only Retry；
- Server State 只进入 TanStack Query，不复制到 Context/Zustand/Effect Local State。

## 5. Error Contract

Client 将错误统一为 `ApiClientError`：

- `problem`：合法 `application/problem+json`；
- `network`：无法连接；
- `timeout`：请求超时；
- `abort`：主动取消；
- `protocol`：非法 Content-Type、Problem Envelope 或成功响应 Schema Drift；
- `unknown`：无法安全分类的客户端异常。

Expected Error 按稳定 `code/status` 分支，UI 只展示安全 `detail` 与 `request_id`。Hey API 生成 Zod Response
Validator，使 HTTP 200 但字段类型错误时也会转为 `invalid_response_schema`，不会把错误数据交给页面。

## 6. Dashboard Slice

Dashboard 已展示真实：

- Active Upstream；
- Published Tool；
- Pending Review/Approval；
- Failed/Unknown Execution；
- Embedding Coverage 与 `Model@Dimensions`；
- Response `X-Request-ID`。

后台 Refresh 保留已有数据；初次加载、空环境、Problem Details、Network Error 和 Schema Drift 具有独立
状态。

## 7. 开发中发现的兼容问题

### 7.1 TypeScript 7 与 Hey API 0.99

npm Registry 当前把 TypeScript `7.0.2` 标为 Latest，但 Hey API `0.99.0` Codegen 在运行时访问旧 Compiler
API 时失败。Peer Dependency 没能阻止这个组合。

最终将 TypeScript 精确固定为 `5.9.3`。这说明“依赖能安装”不等于“工具链能够运行”，Codegen 必须进入
CI。

### 7.2 `exactOptionalPropertyTypes`

Hey API 当前内置 Fetch Runtime 会把若干 Optional Field 显式传为 `undefined`，与该额外严格开关冲突。
项目继续启用 TypeScript `strict`、`noUncheckedIndexedAccess` 和 Generated Code Type Check，只关闭
`exactOptionalPropertyTypes`；不手改生成代码掩盖问题。

### 7.3 Fetch Client Package

当前 Fetch Client 已内置在 `@hey-api/openapi-ts`。单独安装旧 `@hey-api/client-fetch` 会收到 Deprecated
警告，因此只保留同名生成插件，不保留额外 Runtime Package。

## 8. 验证

Frontend Local Gate：

- `pnpm install --frozen-lockfile`；
- `pnpm api:generate`；
- Oxfmt Check；
- TypeScript Type Check；
- Oxlint 0 Warning；
- Vitest/MSW `9 passed`；
- Vite Production Build 成功。

Runtime Smoke：

- Vite Shell `200`；
- `/admin/dashboard` Proxy `200`，读取 PostgreSQL 真实 Projection；
- `/health/ready` Proxy `200`；
- Smoke 后已关闭临时 Uvicorn/Vite Process。

GitHub Actions 新增独立 Frontend Job，执行 Frozen Install、Codegen Drift、Format、Type Check、Lint、Test
与 Build。Playwright Full-stack E2E 按原计划在 W4 加入，不在 W2 制造仅 Mock 的伪 Full-stack 证据。

## 9. 下一步

进入 `W3｜核心业务页面`，按业务主链实现：

```text
Upstreams
→ Import / Review / Publish
→ Tool Catalog / Version / Binding
→ Approval
→ Execution / Attempt / Audit
```

