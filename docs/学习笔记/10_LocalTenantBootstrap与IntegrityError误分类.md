# Local Tenant Bootstrap 与 IntegrityError 误分类

> 日期：2026-08-29
> 场景：第一次通过 Web Control Plane 注册本地 Upstream

## 1. 表面现象

在 Web UI 中多次修改 Namespace 和名称后，注册仍返回：

```text
POST /admin/upstreams
409 Conflict
error_code="upstream_conflict"
```

当时填写的组合已经不同：

```text
demo_directory_1 / employee-directory-demo-1
```

因此问题不像真正的名称唯一键冲突。

## 2. 如何定位

第一步检查领域规则与数据库约束。Upstream 的唯一身份约束只有：

```text
(tenant_id, namespace, name)
```

Endpoint 不参与唯一约束，同一 HTTP 服务允许在不同 Namespace 或治理配置下注册。

第二步只读检查开发数据库：

```text
upstream_service = 0 rows
tenant           = 0 rows
```

既然 Upstream 表为空，就不可能发生真实的 Upstream 唯一键冲突。

第三步读取 PostgreSQL 原始日志，得到真正原因：

```text
insert or update on table "upstream_service"
violates foreign key constraint
"fk_upstream_service_tenant_id_tenant"

Key (tenant_id)=(00000000-0000-0000-0000-000000000001)
is not present in table "tenant".
```

## 3. 根因一：配置中的 Tenant ID 不等于数据库 Tenant

本地启动配置包含：

```text
NEXUSMCP_LOCAL_TENANT_ID=00000000-0000-0000-0000-000000000001
```

该配置只告诉 Request Context “当前请求属于哪个 Tenant”，不会自动创建数据库实体：

```text
Settings.local_tenant_id
≠
tenant 表中的一行数据
```

Migration 只创建了表和约束，没有插入 Local Tenant。Admin Middleware 构造出 Tenant ID 后，Repository
尝试写入 `upstream_service`，最终被 Foreign Key 拒绝。

这说明启动成功和数据库可连接还不够。应用依赖的最小业务基线数据也必须存在。

## 4. 根因二：Repository 过度捕获 IntegrityError

原实现接近：

```python
try:
    await session.flush()
except IntegrityError as error:
    raise UpstreamConflictError(...) from error
```

`IntegrityError` 是数据库完整性错误的大类，可能包含：

- `23505 unique_violation`：唯一键冲突；
- `23503 foreign_key_violation`：外键目标不存在；
- `23502 not_null_violation`：必填字段为空；
- Check Constraint 失败；
- 其他数据库完整性错误。

把整个大类映射为 `upstream_conflict`，会将真实的数据库或启动配置错误伪装成用户输入重复。

这不仅影响错误文案，还会影响排障方向：用户不断改名字，但永远无法解决外键问题。

## 5. 修复一：Development Lifespan 幂等初始化 Tenant

现在 Application Lifespan 在以下条件同时满足时初始化 Local Tenant：

```text
environment == development
control_plane_enabled == true
PostgreSQL Runtime 已启动
```

执行语义：

```sql
INSERT INTO tenant (...)
ON CONFLICT (id) DO NOTHING;
```

它具有几个边界：

- 必须在 Database Runtime 启动后执行；
- 必须在应用开始接收 Admin 请求前完成；
- 重复启动不会重复插入；
- 不修改已经存在的 Tenant；
- 只适用于 Development Local Admin；
- Test/Production 不隐式创建业务 Tenant。

## 6. 为什么不把 Local Tenant 写死在 Alembic Migration

Alembic 的核心职责是演进数据库结构。把固定 Local Tenant 写入正式 Migration 会产生问题：

- 所有环境都会获得一条本地开发数据；
- Production Tenant 生命周期被部署脚本绑架；
- 不同环境可能需要不同 Tenant ID；
- Schema 回滚和业务数据回滚耦合；
- 无法表达真实 Tenant 的审批、停用和审计流程。

因此当前选择是：

```text
Alembic
→ 管理 Schema

Development Lifespan Bootstrap
→ 管理本地最小基线数据

Production Tenant Provisioning
→ 未来由显式管理流程负责
```

## 7. 修复二：按 PostgreSQL SQLSTATE 精确分类

Repository 现在只在以下情况转换为 `UpstreamConflictError`：

```text
SQLSTATE == 23505
```

也就是确实发生 Unique Violation 时才返回：

```text
409 upstream_conflict
```

Foreign Key 等其他 IntegrityError 不再被错误翻译。未被预期分类的数据库异常应该进入服务端诊断和 500
边界，而不是向客户端伪装成一个可通过修改输入解决的业务冲突。

更进一步的生产实现可以读取 Constraint Name，而不只是 SQLSTATE：

```text
23505 + uq_upstream_service_tenant_namespace_name
→ upstream_conflict
```

这样同一个 Repository 中新增其他 Unique Constraint 后，也不会错误复用同一个业务错误。

## 8. 测试证据

修复后增加了两类验证：

1. 空数据库执行 Migration 后，以 Development Control Plane 启动；
2. 不手工 Seed Tenant，直接注册 Upstream。

预期：

```text
Application Lifespan
→ Local Tenant 存在
→ Register Upstream = 201 Created
```

原有重复注册测试继续证明：

```text
相同 tenant + namespace + name
→ 23505
→ 409 upstream_conflict
```

## 9. 可以复用的工程经验

### 9.1 配置引用必须有实体基线

配置中的 ID 不是数据库实体。任何“默认 Tenant、默认 Principal、默认 Organization”都要回答：

```text
谁创建它？
什么时候创建？
是否幂等？
哪些环境允许自动创建？
```

### 9.2 不要按异常父类猜业务含义

技术异常到业务异常的转换必须基于可证明的信息：

```text
SQLSTATE
Constraint Name
Operation Context
```

### 9.3 Safe Error 与诊断错误要分层

客户端只需要稳定、安全、可行动的错误；服务端日志必须保留真正的 SQLSTATE、Constraint 和 Trace ID。
如果安全错误与真实原因不一致，既伤害用户体验，也降低运维证据质量。

### 9.4 Bootstrap 必须受环境边界约束

Local Demo 可以自动创建 Tenant，Production 不应在进程启动时静默创建组织。生产 Tenant 属于显式、可审计
的 Provisioning 流程。
