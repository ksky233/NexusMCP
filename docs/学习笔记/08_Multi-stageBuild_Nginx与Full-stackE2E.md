# Multi-stage Build、Unprivileged Nginx 与 Full-stack E2E

> 日期：2026-08-28
> 场景：NexusMCP React Control Plane 作品集部署与端到端证据
> 当前状态：本地 Multi-stage Build、Unprivileged Nginx 与 Full-stack Playwright E2E 已通过

## 1. 这套实践要解决什么问题

在开发阶段，我们通常这样运行：

```text
Browser
→ Vite Dev Server :5173
→ Vite Proxy
→ FastAPI :8000
```

这能证明前端开发链正常，却不能证明最终静态文件的部署方式正常。真实部署不会在服务器上运行
`pnpm dev`，也不应该把 Node、源码和前端开发依赖放进 Runtime Image。

W4 希望补充一条更接近部署环境的链路：

```text
Browser
→ Unprivileged Nginx :8088
   ├── /assets/*  → React Static Assets
   ├── /admin/*   → FastAPI Admin API
   ├── /health/*  → FastAPI Health
   └── /mcp       → MCP Streamable HTTP
→ PostgreSQL / Fake Enterprise API
```

核心目标不是“为了 Docker 而 Docker”，而是验证以下边界：

- Production Build 是否真的可运行；
- SPA 刷新是否会返回 404；
- Browser 是否始终使用 Same-Origin；
- `/admin`、`/health`、`/mcp` 是否被正确转发；
- Runtime Image 是否不含 Node、源码和 Secret；
- Browser 操作是否真正落入 PostgreSQL；
- MCP Tool Call 后是否能在 UI 中看到 Execution/Attempt/Audit。

## 2. 需要拉取哪些镜像

### 2.1 Node Builder

Docker Desktop 搜索关键词：

```text
node official image
node 22.18.0 alpine
```

目标镜像：

```powershell
docker pull node:22.18.0-alpine
```

这个镜像只用于 Build Stage：

```text
安装 pnpm
→ Frozen Install
→ OpenAPI Codegen
→ TypeScript/Vite Build
→ 产生 dist/
```

它不会进入最终 Runtime Image，因此 Builder 镜像较大不会直接决定部署镜像体积。

当前本机已有 `node:22-slim`，但它不是项目冻结的精确版本，暂不拿它替代 `node:22.18.0-alpine`。

### 2.2 Unprivileged Nginx Runtime

Docker Desktop 搜索关键词：

```text
nginxinc nginx-unprivileged
nginx unprivileged alpine
```

目标镜像：

```powershell
docker pull nginxinc/nginx-unprivileged:1.30.4-alpine
```

当前本机已经拉取：

```text
nginxinc/nginx-unprivileged:1.30.4-alpine
Local Size: 54MB
```

Dockerfile 还使用 Multi-platform Index Digest 固定供应链输入：

```text
sha256:93722936b82ec8a1178d48448e619226680d2de3706a1640800e186cd5fa7fd3
```

`unprivileged` 的关键区别是：Nginx Worker 不需要 Root 身份，默认监听 `8080` 而不是特权端口 `80`。

### 2.3 不需要额外拉 Playwright Docker Image

当前方案通过 npm 安装：

```text
@playwright/test 1.62.1
```

浏览器二进制由下面的命令管理：

```powershell
cd web
pnpm exec playwright install chromium
```

当前 Chromium 已下载完成。因此本方案不再额外引入官方 Playwright Docker Image，避免出现两套容器编排。

Playwright 是 Browser Automation / End-to-End Test Framework。它会驱动真实浏览器执行：

```text
打开 URL
→ 点击导航
→ 填写表单
→ 等待网络响应
→ 检查可访问元素与页面状态
→ 失败时保存 Screenshot / Trace / Video
```

本次 Windows 安装实际下载：

```text
Chrome for Testing       约 191.8MB（压缩下载量）
Chromium Headless Shell  约 114.5MB（压缩下载量）
FFmpeg                    约 1.3MB
Winldd                    很小
```

压缩下载量合计约 `307MB`，解压后的磁盘占用会更大：

- Chrome for Testing：完整浏览器，适合 Headed 调试；
- Headless Shell：无窗口自动化版本，适合普通 E2E/CI；
- FFmpeg：Playwright 录制失败录像时使用；
- Winldd：检查 Windows Native Dependency。

这些 Browser Binary 不在项目目录，而在用户级 Cache：

```text
Windows: %LOCALAPPDATA%\ms-playwright\

当前目录结构示例：
chromium-1234/
chromium_headless_shell-1234/
ffmpeg-1011/
winldd-1007/
```

Git 只保存：

```text
package.json / pnpm-lock.yaml
playwright.config.ts
tests/e2e/*.spec.ts
```

Lock File 记录 Playwright Package Version，Playwright 再根据该版本选择对应 Browser Revision；几百 MB 的
Browser Binary 不提交 Git。

它们也不会进入最终 Nginx Runtime Image：

```text
Playwright + Chromium
→ 只存在于 Developer Machine / CI Runner

Nginx Runtime
→ 只包含 Nginx Config + dist/
```

现代 Playwright 不要求普通 `pnpm install` 自动下载浏览器。本项目使用显式安装命令，让本地和 CI 的下载时机
可见：

```powershell
pnpm exec playwright install chromium
```

Linux CI 如果还需要补 System Library：

```text
pnpm exec playwright install --with-deps chromium
```

Playwright 也可以通过 `channel: "msedge"` 驱动本机 Edge，从而减少本机额外下载。但项目选择固定 Playwright
Revision 的 Chromium，主要为了让 Developer/CI Browser Version 一致，避免 Edge 自动升级导致结果难以复现。

W4 完成后如需释放空间，可以使用 Playwright Uninstall 或删除用户级 Cache；`--all` 会影响该用户下其他
Playwright 项目，应谨慎使用。删除 Cache 不影响 Git，下次执行 Browser Install 时会重新下载。

## 3. Multi-stage Build 是什么

当前 [Dockerfile](../../web/Dockerfile) 分成两个阶段。

### 3.1 Builder Stage

```dockerfile
FROM node:22.18.0-alpine AS builder

WORKDIR /workspace/web

RUN corepack enable && corepack prepare pnpm@10.15.1 --activate

COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY contracts /workspace/contracts
COPY web ./

RUN pnpm api:generate && pnpm build
```

为什么先复制 `package.json` 和 Lock File，再复制源码：

```text
依赖文件没变
→ Docker 可以复用 pnpm install Layer
→ 普通源码修改不需要重新安装全部依赖
```

为什么在容器里重新 Codegen：

- 证明提交的 OpenAPI 在干净 Linux 环境可生成；
- 不依赖开发者本机生成目录；
- 避免 Windows/Linux 路径差异只在 CI 才暴露；
- 确认 Build Artifact 对应当前 Contract。

### 3.2 Runtime Stage

```dockerfile
FROM nginxinc/nginx-unprivileged:1.30.4-alpine@sha256:...

COPY web/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /workspace/web/dist /usr/share/nginx/html
```

第二阶段只复制：

```text
Nginx Config
Vite dist/
```

不会复制：

```text
node_modules
Node.js
TypeScript Source
Tests
.git
.env
API Key
Source Map（当前 Build 未开启）
```

这就是 Multi-stage Build 最重要的价值：Build Environment 与 Runtime Environment 分离。

## 4. 为什么不用 FastAPI 直接托管前端

FastAPI Static Mount 可以用于非常小的 Demo，但当前选择独立 Nginx，原因是：

- SPA Fallback 和 Static Cache 更自然；
- Backend/Frontend Artifact 边界清楚；
- 可以单独验证 Reverse Proxy；
- 可以设置 CSP、Frame、Referrer 等 Browser Header；
- 不让 Python Runtime 承担静态文件部署职责；
- 更接近常见企业部署拓扑。

这不代表 Nginx 永远是唯一选择。Kubernetes Ingress、CDN/Object Storage 或平台网关出现后，可以重新定义
部署边界。

## 5. Same-Origin Proxy

Frontend Generated Client 使用：

```text
/admin
```

而不是写死：

```text
http://127.0.0.1:8000/admin
```

浏览器只访问 Nginx：

```text
http://127.0.0.1:8088
```

Nginx 在服务端转发：

```nginx
location /admin/ {
    proxy_pass http://host.docker.internal:8000;
}
```

这样做的收益：

- 浏览器不需要 CORS；
- 同一份 Frontend Artifact 可以部署到不同 Host；
- API 地址不进入 Build-time Environment；
- 未来 Cookie/Session/CSRF 边界更容易统一；
- 网络拓扑只由部署层管理。

`host.docker.internal` 表示“从 Container 访问宿主机”。Linux CI 需要显式添加：

```text
--add-host=host.docker.internal:host-gateway
```

## 6. Nginx 的四类 Route

### 6.1 Static Assets

```nginx
location /assets/ {
    try_files $uri =404;
    expires 1y;
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

Vite Asset 文件名包含 Hash。文件内容变化时 URL 也变化，因此可以长期缓存。

### 6.2 SPA Fallback

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

如果用户直接刷新：

```text
/catalog/{tool_id}
```

Nginx 文件系统中没有这个目录，因此必须返回 `index.html`，再由 React Router 解释 URL。

### 6.3 Admin/Health Proxy

```text
/admin/*
/health/*
```

这两类普通 HTTP Query 使用有限 Connect/Read Timeout。

### 6.4 MCP Streamable HTTP

```nginx
location /mcp {
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
}
```

MCP 可能使用流式响应。关闭 Buffer/Cache 可以避免代理层等待完整响应后才一次性交付，也避免协议消息被缓存。

## 7. Runtime Security Header

当前配置加入：

- `X-Content-Type-Options: nosniff`；
- `X-Frame-Options: DENY`；
- `Referrer-Policy: no-referrer`；
- Content Security Policy；
- `server_tokens off`；
- `client_max_body_size 1m`。

CSP 当前只允许 Same-Origin Script、Style、Connect、Font 和 Image，并禁止 Frame Ancestor。因为 Frontend 没有
CDN Script、Inline Script 和远程字体，所以能够使用较严格的默认策略。

这些 Header 不是 Production IAM，也不能替代 Backend Authorization。

## 8. 测试分层：为什么已有 MSW 还需要 Playwright

| 测试层 | 证明什么 | 不证明什么 |
|---|---|---|
| Vitest Unit | Mapper、Error Class、状态函数 | Browser/Network |
| RTL + MSW | Component、Generated SDK、Loading/Error | 真实 FastAPI/PostgreSQL |
| Backend Integration | FastAPI/Repository/Transaction | React/Nginx |
| Playwright Full-stack | Browser 到数据库和 MCP 的整条链 | 生产容量与多区域 |

只写 Playwright + MSW，本质仍是更昂贵的 Component Mock Test。W4 选择真实 Backend/PostgreSQL 是为了补足
现有证据矩阵，而不是追求测试数量。

Playwright 运行时位于系统外部：

```text
Playwright Test Runner + Chromium（Host 或 CI Runner）
        ↓ HTTP
Nginx Container
        ↓ Proxy
FastAPI Process
        ↓
PostgreSQL / Fake Upstream
```

因此测试浏览器不是“项目服务的一部分”，而是站在系统外部验证系统的测试客户端。这与用户真实打开浏览器
访问 Control Plane 的位置一致。

## 9. Full-stack E2E 编排

验收拓扑：

```text
Disposable nexusmcp_test
        ↓
Seed Tenant
        ↓
Employee Directory Fake API :9001
        ↓
NexusMCP :8000
        ↓
Unprivileged Nginx :8088
        ↓
Playwright Chromium
```

浏览器步骤：

```text
Register Upstream
→ Import OpenAPI
→ Review getEmployee
→ Submit Review
→ Publish
→ Catalog 验证 Tool
```

随后 Playwright 进程调用 Python MCP Client：

```text
Nginx /mcp
→ directory.get_employee
→ Fake Employee Directory
→ ToolExecution + Attempt + Audit
```

最后浏览器回到：

```text
Executions
→ Execution Detail
→ Attempt Timeline
→ Audit Timeline
```

使用 Python MCP Client 而不手写 JSON-RPC，是为了继续复用项目已经验证过的官方 MCP SDK 协议边界。

## 10. 测试数据库安全

E2E Seed 会执行 `TRUNCATE`，所以必须设置强边界：

```text
NEXUSMCP_TEST_DATABASE_URL 必须存在
Database Name 必须包含 test
只操作显式 Test URL
```

当前脚本：

[seed_web_control_plane.py](../../tests/e2e/seed_web_control_plane.py)

它不会读取 `NEXUSMCP_DATABASE_URL`，也不会操作开发数据库 `nexusmcp`。完成清理后只写入一个固定 Test
Tenant，后续业务状态全部由 Browser 通过 Admin API 创建。

## 11. 当前文件

- [Dockerfile](../../web/Dockerfile)
- [Nginx Config](../../web/nginx/default.conf)
- [Playwright Config](../../web/playwright.config.ts)
- [Browser E2E](../../web/tests/e2e/control-plane.spec.ts)
- [Test DB Seed](../../tests/e2e/seed_web_control_plane.py)
- [MCP Call Helper](../../tests/e2e/call_published_tool.py)

## 12. 最终验收结果

- Node Builder：`node:22.18.0-alpine`，Index Digest 已固定；
- Runtime：`nginxinc/nginx-unprivileged:1.30.4-alpine`，Index Digest 已固定；
- Docker Build Context 正确包含 Contract 与 Evidence Snapshot；
- Final Image：约 `54.6MB`；
- Runtime User：`101`；
- Container Health：Healthy；
- `/healthz`、SPA Fallback、`/health/ready`、`/admin/dashboard`：`200`；
- HTML/Asset 均具有 CSP、Frame Deny、NoSniff、No Referrer；
- Static Asset 具有 Immutable Cache；
- Playwright：`2 passed / 7.3s`；
- Full Control Plane + MCP + Execution/Audit 主链通过；
- GitHub Actions Full-stack E2E Job 已加入，首次 Cloud Run 等待 Push。

### 12.1 发现：Nginx Header 继承

第一次检查发现 HTML 缺少 CSP。原因不是 Server 层没有设置，而是：

```text
location /
→ internal redirect /index.html
→ location = /index.html 定义 Cache-Control
→ Nginx 默认不再继承父级 add_header
```

当前 Nginx 使用：

```nginx
add_header_inherit merge;
```

使 Location 自己的 Cache Header 与 Server Security Header 合并。该问题只有通过真实 Nginx Header Smoke 才
会暴露，Vite/MSW 不会发现。

### 12.2 发现：Runtime ORM Model 注册

第一次 Browser Register 返回 500。Alembic 和 Integration Test 会先集中导入全部 ORM Model，但正常
Application Runtime 只按 Repository Import 业务 Model，导致 SQLAlchemy 首次 Flush 时找不到 `tenant` Table
来解析 Foreign Key。

修复方式是在 Database Engine Boundary 集中注册 `ALL_MODELS`，保证：

```text
Alembic Metadata
= Runtime Metadata
= Integration Test Metadata
```

这说明 E2E 的价值不只是测试 UI，它还验证了真实进程启动时的 Import/Composition 行为。

## 13. 面试表达

可以这样描述这项工作：

> 我没有把 Vite Dev Server 当成部署证据。前端使用 Multi-stage Build，在 Node Stage 进行 Frozen Install、
> OpenAPI Codegen 和 Vite Build，Runtime 只保留 Unprivileged Nginx 与静态文件。Nginx 同源代理 Admin API、
> Health 和 MCP Streamable HTTP，并验证 SPA Fallback、安全 Header 和缓存策略。Playwright 使用 disposable
> PostgreSQL，从 Browser 完成注册、导入、审核、发布，再通过官方 MCP Client 调用 Tool，最后回到 UI 验证
> Execution、Attempt 和 Audit。测试数据库通过名称包含 `test` 的硬限制避免误清理开发库。

这段叙事的重点是“可验证的边界”，不是简单列出 Docker、Nginx 和 Playwright 名词。
