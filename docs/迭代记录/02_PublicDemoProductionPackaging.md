# I-02｜Public Demo Production Packaging

> 状态：Completed（本地，待提交与服务器 D0 检查）  
> 日期：2026-09-05  
> 触发：需要把已完成的 Local Control Plane 作为公开求职 Demo 部署到现有腾讯云服务器  
> 决策依据：[ADR-0019](../adr/0019-service-centric-identity-boundary.md)、
> [单机生产部署规划](../项目规划/11_单机生产部署规划.md)  
> 基线提交：`3825136`

## 1. 目标

- HR/面试官打开 `nexusmcp.dearloom.me` 后可以直接体验；
- 不使用 `development + Local Admin` 冒充部署配置；
- 三个 Fake HTTP/OpenAPI Upstream 以独立容器边界运行；
- 补齐 Backend/Web/PostgreSQL Production Compose；
- 能重置持久化工作区并重新演示完整 OpenAPI Onboarding；
- 在修改公网 Edge 前先完成本地 `linux/amd64` Clean Rehearsal。

## 2. 非目标

- 企业 SSO/OIDC/Trusted Proxy Admin Adapter；
- 员工注册、Session、RBAC 或用户中心；
- Kubernetes、Registry、CI/CD 与多区域部署；
- Demo 限流、定时数据恢复和独立展示站；
- 真实企业 Upstream 或 Credential。

## 3. Before

```text
Development Local Admin
Web Image → host.docker.internal:8000
Backend → Host Process
PostgreSQL → Local Compose
Fake API → 三个手工 Uvicorn Process
```

Local Admin 被 Settings 正确禁止在 Production 启用，因此现有代码不能通过把环境变量改成 `production` 直接
上线。

## 4. Target

```text
Existing TLS Edge
→ NexusMCP Web Nginx
→ NexusMCP Backend
   ├── PostgreSQL 18 + pgvector
   └── demo-upstreams
       ├── /employee-directory
       ├── /operations
       └── /inventory
```

身份语义：

```text
Browser → public-demo-admin
MCP     → public-demo-agent
```

这两个 ID 表示公开访客共享身份，不表示 NexusMCP 已认证真实自然人。

## 5. 实施结果

### 5.1 Public Demo Identity

- Settings 增加 `admin_identity_mode = local | public_demo`；
- Production Control Plane 只有显式 `public_demo` 才可启动；
- Public Demo 启动时幂等创建固定 Tenant；
- Admin Request Context 使用 `public_demo` Authn Method；
- MCP 继续使用已有 `static_service` 固定 Agent Service Principal；
- Local Development 行为保持不变。

### 5.2 Reset Demo Workspace

新增：

```text
POST /admin/demo/reset
```

它只在 `public_demo` 组装时注册。PostgreSQL Adapter 在一个事务中清理业务表并恢复固定 Tenant，不删除：

- Database；
- Alembic Version；
- Table/Constraint/Index；
- pgvector Extension。

Web Production Build 显示共享 Demo 身份和“重置演示工作区”按钮；Development Build 仍显示 Local Admin。

### 5.3 Combined Demo Upstreams

一个 Uvicorn 进程挂载三个已有 FastAPI 子应用：

```text
http://demo-upstreams:9000/employee-directory
http://demo-upstreams:9000/operations
http://demo-upstreams:9000/inventory
```

`backend` 与 `demo-upstreams` 复用同一 Backend Image，但运行在不同 Container/Process，保留真实容器间 HTTP
调用、超时、重试、幂等和审计边界。

### 5.4 Production Packaging

- Backend Multi-stage Image：Python 3.12、Frozen uv、非 Root UID 10001；
- Web Multi-stage Image：`VITE_PUBLIC_DEMO=true`、Unprivileged Nginx；
- Nginx Upstream 从 `host.docker.internal` 改为 `backend:8000`；
- Production Compose：PostgreSQL、Backend、Web、Demo Upstreams；
- PostgreSQL/Backend/Demo Upstream 不发布 Host Port；
- Web 只发布 `127.0.0.1:18080` 供本机诊断，并可通过 Overlay 接入共享 Edge Network；
- Health Check、日志轮转、资源上限、`no-new-privileges` 与 Alembic 启动 Migration；
- Buildx 构建脚本与 Tar/SHA256 Release 导出脚本。

## 6. Contract 与兼容性

- Admin OpenAPI 从 34 增加为 35 个 Operation；
- 新增 `resetDemoWorkspace`，Generated Hey API SDK 已同步；
- Reset Route 只在 Public Demo Runtime 注册；
- 现有 Local Admin API、MCP Tool Contract 和数据库 Schema 未变化；
- 没有新增 Migration。

## 7. 本地验证证据

```text
uv sync --frozen                         passed
Ruff Lint                               passed
Ruff Format                             passed
basedpyright                            0 errors / 0 warnings
Backend                                 302 passed / 2 paid external skipped
Frontend Frozen Install                 passed
Admin OpenAPI Codegen                   passed
Oxfmt / Type Check / Oxlint             passed
Vitest                                  22 passed
Vite Build                              passed
Backend linux/amd64 Image               222,248,567 bytes
Web linux/amd64 Image                    54,661,594 bytes
Production Compose Config               passed
Production Nginx Syntax                 passed
Four-container Health                   passed
Backend → Demo Employee API             passed
Upstream 1 → Reset → 0                  passed
```

完整测试中的两个 Skip 是需要显式开启并调用付费 SiliconFlow API 的 External Smoke/Eval，不属于失败。

## 8. 清理与影响

本地演练使用独立 Compose Project `nexusmcp-prodtest` 和独立 PostgreSQL Volume。验证完成后已核对 Docker
Compose Label，并删除该 Project 的容器、Network 和测试 Volume。现有 `nexusmcp-postgres-1` 开发数据库保持
运行且未被修改。

本地保留两个预期构建制品：

```text
nexusmcp-backend:local
nexusmcp-web:local
```

## 9. 遗留项

- 登录服务器执行 D0 Capacity/Port/Certificate 检查；
- 使用 Git SHA Tag 构建并导出正式 Release Bundle；
- 创建/复用 `dearloom-edge` Network，并将现有 TLS Edge Container 接入；
- 修改 `nexusmcp.dearloom.me` Host Route；
- 完成公网 HTTPS、MCP Call、Reset 与重启持久化验收；
- 建立 PostgreSQL 备份和 Image 回滚记录。
