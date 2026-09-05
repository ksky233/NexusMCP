# 在现有服务中新增 Docker Compose 应用

> 场景：一台服务器已经运行 DualStruct，并独占 80/443；在不混合数据和发布生命周期的前提下新增 NexusMCP
> 实践环境：OpenCloudOS 9.4、Docker Engine 29、Docker Compose 5、Nginx、Let's Encrypt Wildcard TLS
> 结果：`dualstruct.dearloom.me` 与 `nexusmcp.dearloom.me` 在同一服务器独立运行，共享一个 HTTPS Edge

## 1. 这次真正解决的问题

在一台空服务器部署第一个应用相对直接：应用的 Nginx 可以绑定 80/443，并同时承担静态文件、TLS 和反向
代理。

第二个应用加入时，问题发生了变化：

```text
Port 80/443 已被占用
证书和续期已经有所有者
现有应用不能因新应用部署而改用同一数据库或同一 Compose
新应用需要独立发布、回滚和停止
两个 Compose Project 默认无法通过 Service Name 相互解析
```

因此核心任务不是“再执行一次 `docker compose up`”，而是把入口所有权、应用隔离和跨项目网络重新划清。

## 2. 最终拓扑

```text
Internet :80/:443
        ↓
Shared Edge Nginx
TLS termination + SNI/Host routing
        ├── dearloom.me
        │   └── Static Project Index
        ├── dualstruct.dearloom.me
        │   └── DualStruct Web
        │       └── DualStruct Backend
        └── nexusmcp.dearloom.me
            └── NexusMCP Web
                └── NexusMCP Backend
                    ├── PostgreSQL 18 + pgvector
                    └── Demo Upstreams
```

服务器上仍然是两个独立 Compose Project：

```text
/opt/dualstruct
/opt/nexusmcp
```

它们只在共享 Edge Network 上建立最小连接，不共享应用数据库、Volume、环境变量和内部 Network。

## 3. 为什么第二个应用不能再绑定 80/443

一个 Host Port 在同一个 IP 上只能被一个 Listener 占用。现有 Edge Container 已经发布：

```text
0.0.0.0:80  → edge-nginx:8080
0.0.0.0:443 → edge-nginx:8443
```

如果 NexusMCP Web 再声明：

```yaml
ports:
  - "443:8443"
```

Docker 会因端口冲突拒绝启动。

正确模型是：

```text
一个公网入口
→ 根据 HTTP Host/SNI 分发
→ 多个内部 Web Service
```

NexusMCP 只保留一个本机诊断端口：

```text
127.0.0.1:18080 → nexusmcp-web:8080
```

它不能从公网访问，但可以通过服务器本地 Curl 或 SSH Tunnel 在切换域名前完成验证。

## 4. Compose Network 为什么默认互相看不见

Compose 会为每个 Project 创建自己的默认 Bridge Network：

```text
dualstruct_default
nexusmcp_app
```

Docker Service Name 只在共同 Network 内提供 DNS：

```text
DualStruct Web 在 dualstruct_default 中可以解析 backend
NexusMCP Web 在 nexusmcp_app 中可以解析 backend
DualStruct Edge 默认不能解析 nexusmcp-web
```

解决方法不是把 NexusMCP 全部加入 `dualstruct_default`，而是增加职责单一的 External Network：

```text
dearloom-edge
```

最终网络成员：

| Container | 应用内部 Network | `dearloom-edge` |
|---|---|---|
| DualStruct Edge/Web | `dualstruct_default` | 是 |
| DualStruct Backend | `dualstruct_default` | 否 |
| NexusMCP Web | `nexusmcp_app` | 是 |
| NexusMCP Backend | `nexusmcp_app` | 否 |
| NexusMCP PostgreSQL | `nexusmcp_app` | 否 |
| Demo Upstreams | `nexusmcp_app` | 否 |

这形成了一个双宿主 Edge：它能访问两个应用的 Web 入口，但不能直接跨过 Web 访问另一个项目的数据库。

## 5. 为什么 Network 必须写进 Compose

以下命令可以临时连接正在运行的 Container：

```bash
docker network connect dearloom-edge some-container
```

但 Container 被 Compose Recreate 后，这条手工连接可能丢失。部署状态会变成“当前能运行，但无法从配置重建”。

因此两个项目都把 Network Membership 写入 Compose：

```yaml
services:
  web:
    networks:
      default:
      edge:

networks:
  edge:
    external: true
    name: dearloom-edge
```

External 表示 Network 生命周期不属于任意一个应用 Compose。`docker compose down` 不会因为停止一个应用而删除
共享入口网络。

## 6. TLS 为什么不需要重新申请

现有证书覆盖：

```text
dearloom.me
*.dearloom.me
```

因此 `nexusmcp.dearloom.me` 已在证书 SAN 范围内。新增应用只需要增加 Nginx Host Route，不需要：

- 再签发一张证书；
- 再运行一套 Certbot；
- 把私钥复制到 NexusMCP；
- 让每个应用分别续期。

TLS 生命周期继续由 Edge 统一拥有：

```text
Certbot DNS-01
→ 更新 Wildcard Certificate
→ Deploy Hook 复制只读证书
→ Reload Edge Nginx
```

这是共享 Edge 的直接收益：应用只处理 HTTP，域名和证书在入口层治理。

## 7. 新应用的安全发布顺序

### 7.1 先盘点，不先改配置

部署前先确认：

```text
CPU Architecture
Available Memory/Disk
Existing 80/443 Owner
Docker/Compose Version
Current Networks
DNS Resolution
TLS Expiry/Renewal Timer
Existing Application Rollback Point
```

本次实际服务器具有 4 Core、约 2.3 GiB Available Memory 和约 30 GiB Free Disk，负载接近空闲，因此通过
Go/No-Go Gate。

### 7.2 本地构建目标平台 Image

开发机是 Windows，服务器是 Linux AMD64：

```powershell
docker buildx build `
  --platform linux/amd64 `
  --tag nexusmcp-backend:<git-sha> `
  --load .
```

Image 使用 Git SHA，不复用含义不明确的 `latest`：

```text
nexusmcp-backend:961977f1a04d
nexusmcp-web:961977f1a04d
```

### 7.3 先做独立 Production Compose 演练

本地使用独立 Project Name 和全新 Volume：

```text
nexusmcp-prodtest
```

验证：

```text
Migration
→ PostgreSQL Health
→ Backend Health
→ Demo Upstream Health
→ Web Same-Origin Proxy
→ Reset Demo Workspace
```

验证后只删除该明确命名的测试 Project/Volume，不影响开发数据库。

### 7.4 导出不可变 Release

```text
docker save
→ nexusmcp-images.tar
→ SHA256SUMS
→ scp
→ 服务器 sha256sum -c
→ docker load
```

Release 不包含 `.env`、Provider Key、数据库密码或证书私钥。PostgreSQL Image 使用锁定版本和 Digest。

### 7.5 先私有启动，再切公网

NexusMCP 首先只发布到：

```text
127.0.0.1:18080
```

在服务器验证 Health、Container DNS、Fake Upstream 和非 Root UID 后，才把 NexusMCP Web 加入
`dearloom-edge`。

通过 SSH Tunnel 可以在公网切换前检查真实浏览器页面：

```powershell
ssh -N -L 18080:127.0.0.1:18080 root@server
```

### 7.6 最后修改 Host Route

```nginx
server {
    listen 8443 ssl;
    server_name nexusmcp.dearloom.me;

    location / {
        proxy_pass http://nexusmcp-web:8080;
    }
}
```

MCP Streamable HTTP 单独关闭 Proxy Buffering，并保留较长 Read Timeout，避免 Edge 把流式协议当成普通短响应。

## 8. Fake Upstream 的部署方式

三个 Fake API 不放进 NexusMCP Backend 进程，而是使用同一 Backend Image 启动另一个 Container：

```text
nexusmcp-backend container
→ NexusMCP Gateway

nexusmcp-demo-upstreams container
→ /employee-directory
→ /operations
→ /inventory
```

这不会复制 Image Layer，但会保留一次真实 Container-to-Container HTTP 调用，从而继续验证：

- Endpoint Policy；
- HTTP 参数映射；
- Timeout/Retry；
- Idempotency；
- Execution/Audit。

它比把 Fake Route 直接挂在 Gateway 进程中更接近真实 Upstream 边界。

## 9. 共享 Edge 的现实取舍

当前 Edge Nginx 仍由 DualStruct Web Deployment 所有。这对只有两个项目的个人单机服务器是务实方案，但存在
生命周期耦合：

```text
修改 NexusMCP Host Route
→ 需要更新或重建 dualstruct-web
```

当出现以下情况时，应把 Edge 拆成独立 `/opt/dearloom-edge` Project：

- 第三个及更多独立应用加入；
- 不同应用由不同人员维护；
- Edge 配置更新频率显著高于业务 Web；
- 需要统一 WAF、Access Log、Rate Limit 或 Upstream Health；
- 任意应用发布都不应影响其他域名入口。

企业环境未必使用 Docker Compose，但同一问题依然存在，只是 Edge 可能变成：

```text
Cloud Load Balancer
API Gateway
Kubernetes Ingress/Gateway API
Service Mesh Gateway
```

可迁移的核心经验是：**公网入口应有独立所有者；应用只暴露内部 Service，路由通过明确契约接入。**

## 10. Web-only 更新为什么值得独立设计

项目首页从“部署预告”改成 ONLINE，并增加两个项目的核心 Use Case 流程时，只重新构建和替换 Edge/Web Image：

```text
DualStruct Backend    不变
NexusMCP Stack        不变
Database/Volume       不变
TLS Certificate       不变
dualstruct-web Image  更新
```

将 Web-only Update 作为独立发布路径，可以减少上传体积、重启范围和回滚风险。这也是按 Artifact/Service 边界
发布，而不是“整个服务器重新部署”。

## 11. 不推荐的做法

- 让第二个应用争抢 80/443；
- 在生产 Container 中继续使用 `host.docker.internal`；
- 为方便解析，把两个应用的所有服务塞进同一个默认 Network；
- 只执行 `docker network connect`，却不回填 Compose；
- 每个子域名重复维护一套 Wildcard Certificate；
- 未验证新应用 Health 就修改公网 Host Route；
- 直接覆盖 Edge 配置而不保留 `.pre-*` 回滚副本；
- 使用 `latest` 后无法确认服务器运行的 Commit；
- 看到 Reclaimable 就执行全局 `docker system prune`，误删回滚 Image；
- 把 `.env`、API Key 或数据库密码打进 Release Bundle。

## 12. 本次结果与边界

完成：

- NexusMCP 独立四服务 Compose 上线；
- PostgreSQL 18 + pgvector 独立持久化；
- 一个 Container 承载三个 Fake Upstream；
- Public Demo Admin/Agent 固定身份；
- Demo Workspace Reset；
- `nexusmcp.dearloom.me` HTTPS Host Route；
- DualStruct 与 NexusMCP 继续独立运行；
- 项目首页显示两个 ONLINE 项目及各自五步核心链路。

仍然诚实保留：

- 当前是个人单机 Demo，不是多区域生产系统；
- Edge 暂时由 DualStruct Web Project 所有；
- PostgreSQL 自动备份和恢复演练尚未建设；
- Public Demo 身份不是企业 Admin Authentication；
- 正式企业环境应使用 Registry/CI/CD、Secret Manager、SSO 和独立 Edge。

这次实践最有价值的部分不是某条 Docker 命令，而是学会在已有运行系统旁边增加服务时，先识别入口所有权、
网络可达性、状态隔离、制品边界和回滚路径，再进行公网切换。
