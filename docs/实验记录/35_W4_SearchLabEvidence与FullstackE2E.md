# W4｜Search Lab、Evidence 与 Full-stack E2E

> 日期：2026-08-28  
> 状态：完成（本地）；GitHub Actions 首次 Cloud Run 等待 Push

## 1. Search Lab

- 新增 `/admin/search/tools`；
- Admin Contract 扩展为 30 个稳定 Operation；
- 复用正式 `SearchTools` Use Case；
- Lexical/Hybrid 均执行 Tenant、Visibility 与 Policy Filter；
- 返回 Rank、完整 Input/Output Schema、Owner、Tag 与 Index Version；
- UI 并排展示 Lexical FTS 与 Hybrid RRF；
- Hybrid 不可用时返回正式 `tool_search_mode_unavailable`；
- 明确 Candidate 不等于最终正确 Tool；
- 明确 No-Match Confidence Threshold 尚未实现。

## 2. Evidence 页面

Build-time 读取并展示仓库事实源：

- 24 条 Tool Retrieval Eval；
- SiliconFlow/Qwen3 Embedding Snapshot；
- 5 场景 Local PostgreSQL 18 Benchmark；
- Security Golden Cases；
- Modern/Legacy Protocol Matrix；
- Failure Injection Cases；
- Residual Risk 与非 Production SLO 声明。

Snapshot 被打包成 Lazy Evidence Chunk，不在 Runtime 读取仓库文件。

## 3. Production-like Nginx

- Node `22.18.0-alpine` Builder；
- pnpm Frozen Install；
- Container 内 OpenAPI Codegen + Type Check + Vite Build；
- Unprivileged Nginx `1.30.4-alpine` Runtime；
- Node/Nginx 均固定 Multi-platform Index Digest；
- Final Image 约 `54.6MB`，User `101`；
- Runtime 只包含 Nginx Config 与 `dist/`；
- Same-Origin `/admin`、`/health`、`/mcp` Proxy；
- MCP 关闭 Proxy Buffer/Cache；
- SPA Fallback；
- Immutable Asset Cache；
- CSP、Frame Deny、NoSniff、No Referrer；
- Healthcheck `/healthz`。

## 4. Full-stack Playwright

Disposable `nexusmcp_test` 强制名称包含 `test`，Seed 前清空业务表并创建固定 Tenant。

完整路径：

```text
Chromium
→ Nginx :8088
→ FastAPI :8000
→ PostgreSQL 18
→ Employee Directory :9001
```

主测试：

```text
Register Upstream
→ Import OpenAPI
→ Review getEmployee
→ Submit Review
→ Publish
→ Catalog 验证
→ Python MCP Client 经 Nginx /mcp 调用 Tool
→ Browser 验证 Execution / Attempt / Audit
```

第二条 Runtime Test 验证：

- Direct SPA Route Fallback；
- CSP/Frame/NoSniff Header；
- 390×844 Mobile Navigation Dialog。

结果：`2 passed / 7.3s`。

## 5. E2E 发现并修复的问题

### 5.1 SQLAlchemy Runtime Metadata 不完整

真实 Application 首次 Register 时，`UpstreamServiceModel` 的 `tenant_id` Foreign Key 无法解析 Tenant Table。
Integration Test/Alembic 因提前导入全部 Model 掩盖了问题。

修复：Database Engine Boundary 导入 `ALL_MODELS`，统一 Alembic/Test/Runtime Metadata。

### 5.2 Nginx Security Header 被 Location 覆盖

`index.html` Location 设置 Cache-Control 后，默认覆盖父级全部 `add_header`。修复为
`add_header_inherit merge`，重新验证 HTML 和 Asset Header。

### 5.3 Accessible Name Selector

Playwright 的 `getByLabel("Name")` 同时匹配 `Namespace`。测试改为 Exact Accessible Name，说明 E2E Selector
应优先使用稳定 ARIA/Label Contract，而不是 CSS Selector。

## 6. CI

GitHub Actions 新增 `Nginx full-stack E2E` Job：

- PostgreSQL 18 + pgvector Service；
- uv/Python/pnpm/Node Frozen Toolchain；
- Playwright Chromium + Linux Dependency；
- Migration + Disposable Seed；
- Fake Upstream + NexusMCP；
- Multi-stage Nginx Build；
- Playwright E2E；
- Failure Log、Screenshot、Trace Artifact；
- Always Cleanup Nginx Container。

## 7. 验证摘要

- Frontend Vitest/RTL/MSW：`20 passed`；
- Playwright：`2 passed`；
- Backend Pytest：`294 passed / 2 paid external skipped`；
- Admin Contract Target：通过；
- Docker Multi-stage Build：通过；
- Nginx Header/Cache/Fallback/Health：通过；
- 全量 Python/Frontend 门禁结果见本次提交记录。

## 8. 下一步

进入 W5/S6 包装：Screenshot、Architecture/Sequence Diagram、Quick Start、Demo Script、English Overview、
Limitations 与 Clean Environment Reproduction。
