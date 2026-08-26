# ADR-0001｜Python src Layout、模块组织与首批目录

## 状态

Accepted

## 背景

NexusMCP 不是单一 CRUD Web API。一个部署单元中需要同时承载：

- FastAPI Admin/Health 接口；
- Modern/Legacy MCP Protocol Adapter；
- CLI/Import 等后续入口；
- Registry、Catalog、Connectors、Policy、Execution 等业务边界；
- PostgreSQL、HTTP、Remote MCP、Secret Store、OpenTelemetry 等外部 Adapter；
- 可运行 Demo、Contract Test、E2E 和 Eval。

个人工程手册默认建议单一 FastAPI 应用使用 `app/` Layout，同时明确：需要构建可安装 Package、存在多个入口或需要严格源码隔离时采用 `src/<package>` Layout。NexusMCP 属于后一类。

S1 还暴露了一个具体工程问题：项目处于非 Package 模式时，直接调用 pytest Console Script 无法稳定导入仓库根目录下的 `examples`，需要使用 `python -m pytest`。正式业务代码不应继续依赖工作目录恰好位于 `sys.path`。

领域边界以 [业务词汇、核心用例与限界上下文](../架构/01_业务词汇核心用例与限界上下文.md) 为输入；MCP Adapter 以 [ADR-0002](./0002-mcp-protocol-and-sdk-adapter.md) 为输入。

## 决策

### 1. 使用 src Layout

正式业务代码位于：

```text
src/nexusmcp/
```

项目通过 uv 以 Package 形式安装。测试、示例和命令只 import 已安装的 `nexusmcp`，不依赖仓库根目录或手工 `PYTHONPATH`。

`src` Layout 的主要目的：

- 避免从仓库根目录意外导入未安装源码；
- 让本地、测试、CI 和发布使用同一 Import 行为；
- 支持 ASGI App、CLI、协议 Adapter 等多个入口；
- 为模块依赖检查和未来 Package 输出保留稳定边界。

### 2. 使用领域优先的模块化单体

第一层按职责类型区分：

```text
bootstrap       应用组装
interfaces      入站 Adapter
modules         领域与 Application Use Case
infrastructure  跨模块技术资源和外部 Adapter 基础设施
shared          极少量稳定跨域语义
```

业务状态和规则按限界上下文进入 `modules/`：

```text
registry
openapi_import
catalog
connectors
identity
policy
credentials
approval
execution
audit
```

这些是目标边界，不代表第一天创建十个空目录。模块只在第一个真实 Use Case 出现时建立。

### 3. Control Plane / Data Plane 不作为重复顶层目录

不采用：

```text
control_plane/catalog
data_plane/catalog
```

Control Plane 与 Data Plane 是用例和运行边界，共享相同 ToolDefinition、ToolVersion、ToolBinding 等事实源。它们通过不同 Interface/Application Use Case 使用同一领域模型，不复制实体和 Repository。

### 4. 入站 Adapter 统一位于 interfaces

```text
interfaces/
├── admin_api/
├── health/
├── mcp/
└── cli/
```

职责：

- 解析 FastAPI/MCP/CLI 输入；
- 建立或接收可信 RequestContext；
- 将协议 DTO 转换为 Command/Query；
- 调用 Application Use Case；
- 映射响应和错误。

禁止：

- 在 Router/MCP Handler 中直接写 ORM 查询；
- 在 Interface 中实现 Policy、Credential 和 Tool 执行规则；
- 将 FastAPI Request、MCP SDK Type 传入 Domain。

### 5. bootstrap 只负责应用组装

```text
bootstrap/
├── app.py
├── config.py
├── logging.py       # 真实日志需求出现时创建
└── container.py     # 显式依赖组装需要独立文件时创建
```

`bootstrap` 负责：

```text
创建 FastAPI
→ 创建并组装 Repository/Provider/Use Case
→ 注册 Middleware/Exception Handler
→ 注册 Admin/Health Router
→ 挂载 MCP ASGI App
→ 管理 Lifespan
```

`main.py` 只暴露部署入口：

```python
from nexusmcp.bootstrap.app import create_app

app = create_app()
```

业务 Endpoint、Repository 和配置读取细节不直接写入 `main.py`。

### 6. modules 内部先扁平、按职责演进

一个刚出现的简单模块使用：

```text
modules/catalog/
├── domain.py
├── ports.py
└── use_cases.py
```

职责：

| 文件 | 职责 |
|---|---|
| `domain.py` | Entity、Value Object、Enum、不变量 |
| `ports.py` | Repository/Provider 等外部边界 Protocol |
| `use_cases.py` | Command/Query、业务编排、事务意图 |

出现真实复杂度后再演进为：

```text
modules/catalog/
├── domain/
├── application/
├── ports/
└── adapters/
```

触发拆分的证据包括：

- Use Case 拥有不同事务边界；
- 文件承担多个无法用一个名称解释的职责；
- 外部依赖和测试策略明显不同；
- 多人修改持续冲突；
- 模块 Adapter 需要独立演进。

禁止为目录对称预先创建空文件、空 Service 和一对一 Interface。

### 7. 模块专用 Adapter 优先归属业务模块

业务专用 Repository/Adapter 优先放在所属模块的 `adapters/`，例如：

```text
modules/catalog/adapters/sqlalchemy_repository.py
modules/connectors/adapters/http_executor.py
```

`infrastructure/` 只保存稳定的跨模块技术资源或公共 Adapter 基础：

```text
infrastructure/
├── persistence/       # Engine、Session、Migration Metadata 基础
├── http/              # 共享 Async Client、Transport Security 基础
├── secrets/           # Provider 基础设施实现
└── observability/     # OpenTelemetry/Metric/Logging Adapter
```

`infrastructure` 不是全局 Repository、Model、Client 的杂物箱。

### 8. shared 保持极小且无反向依赖

允许进入 `shared` 的内容：

- 稳定跨域 ID/基础错误；
- RequestContext 等已经确认的跨域契约；
- Clock 等需要可测试替换的基础 Port；
- 与具体业务无关的安全摘要原语。

禁止进入 `shared`：

- 无法归类的业务代码；
- Catalog/Policy/Connector 的具体规则；
- ORM Model；
- FastAPI/MCP SDK 类型；
- 通用名 `utils.py`、`common_service.py` 作为收容区。

`shared` 不得 import 任何具体业务模块。

### 9. 测试按业务和证据类型组织

```text
tests/
├── unit/
│   └── modules/
├── contract/
│   └── mcp/
├── integration/
├── e2e/
├── security/
└── fixtures/
```

规则：

- Unit Test 按业务模块聚合；
- Contract Test 证明 MCP/OpenAPI/Audit 等外部契约；
- Integration Test 验证 PostgreSQL、HTTP、Secret Provider 等 Adapter；
- E2E 验证 Client → NexusMCP → Fake Upstream；
- Security Test 验证 AuthZ、SSRF、Secret、Tenant 和 Retry；
- Test Helper 不进入 `src/nexusmcp`；
- 测试使用安装后的 Package，不设置手工 `PYTHONPATH`。

### 10. examples 与 Core 单向依赖

```text
examples/
├── mcp_compatibility/
├── upstream_apis/
│   ├── employee_directory/
│   ├── operations/
│   └── inventory/
└── demo_client/
```

外部 Knowledge RAG Demo 已由 ADR-0013 移出主线；pgvector 改为服务 NexusMCP 内部 Tool Semantic
Retrieval，不改变本 ADR 的 `examples → core` 单向依赖原则。

允许：

```text
examples → import nexusmcp
```

禁止：

```text
src/nexusmcp → import examples
```

### 11. 首批实际创建目录

第一批骨架只创建当前真实需要的目录和文件：

```text
src/
└── nexusmcp/
    ├── __init__.py
    ├── main.py
    ├── bootstrap/
    │   ├── __init__.py
    │   ├── app.py
    │   └── config.py
    ├── interfaces/
    │   ├── __init__.py
    │   ├── health/
    │   │   ├── __init__.py
    │   │   └── router.py
    │   └── mcp/
    │       ├── __init__.py
    │       ├── server.py
    │       ├── context.py
    │       └── errors.py
    ├── modules/
    │   ├── __init__.py
    │   └── catalog/
    │       ├── __init__.py
    │       ├── domain.py
    │       ├── ports.py
    │       ├── use_cases.py
    │       └── adapters/
    │           └── in_memory.py
    └── shared/
        ├── __init__.py
        ├── errors.py
        └── request_context.py
```

第一批不创建：

- 空的 Registry/OpenAPI Import/Connectors/Policy 等模块；
- `infrastructure/` 空目录；
- Alembic/Migration（等待 PostgreSQL ADR 和第一个 Model）；
- Admin API（等待第一个 Control Plane Use Case）；
- CLI（等待第一个 Import 命令）；
- Eval/RAG 目录；
- Redis/Celery/Kubernetes 配置。

`catalog/adapters/in_memory.py` 是 Application Factory 和确定性测试实际需要的 Port 实现，会作为本地开发/测试 Adapter 长期保留，不属于为目录对称创建的空骨架。

### 12. 依赖方向

```text
bootstrap/main
    ↓ 组装
interfaces
    ↓ 调用
modules/*/use_cases
    ↓
modules/*/domain + modules/*/ports
    ↑ 实现 Port
module adapters / infrastructure adapters
```

硬性约束：

- Domain 只依赖标准库、同模块 Domain 和受控 Shared；
- Use Case 不返回 FastAPI Response 或 MCP SDK Result；
- Adapter 可以依赖 Port 和外部库；
- bootstrap 可以依赖所有组装对象，但不拥有业务规则；
- 业务模块之间通过公开 Use Case/Port/ID 协作，不 import 对方私有实现；
- 不允许形成循环依赖。

## 目标仓库结构

最终候选结构：

```text
NexusMCP/
├── src/nexusmcp/
│   ├── main.py
│   ├── bootstrap/
│   ├── interfaces/
│   ├── modules/
│   ├── infrastructure/     # 有真实跨模块技术职责后创建
│   └── shared/
├── migrations/             # PostgreSQL Model 出现后创建
├── examples/
├── tests/
├── evals/                  # S4 创建
├── docs/
├── pyproject.toml
├── uv.lock
└── README.md
```

## 备选方案

### app Layout

拒绝作为 NexusMCP 正式布局。它适合单一 FastAPI 应用，但 NexusMCP 有多个入口、协议 Adapter 和 Package 隔离需求。个人工程手册中的其余初始化、依赖、DI 和演进规则继续适用。

### 按技术层组织

不采用全局：

```text
controllers/
services/
repositories/
models/
schemas/
```

该结构优先回答技术职责，无法清晰表达 Registry、Catalog、Policy 等状态所有权，容易形成跨业务大文件。

### Control Plane / Data Plane 两棵目录树

拒绝。会复制 Tool、Policy、Credential 等模型，并增加状态同步和循环依赖风险。

### 开工即创建完整 Clean Architecture 目录

拒绝。会产生大量空目录、空 Interface、透传 Service 和无证据抽象。

### Java Maven Module 一对一翻译

拒绝。Java 七模块用于学习旧职责，不决定 Python Package 数量和命名。

### 每个 Bounded Context 独立服务/Package

当前拒绝。第一版是模块化单体，只有负载、安全、故障域或组织边界提供证据后才拆分部署。

## 影响

正面影响：

- 领域语言和源码模块一致；
- 测试只验证已安装 Package，减少 Import 偶然性；
- MCP/Admin/CLI 不复制业务逻辑；
- 模块专用 Adapter 保持业务归属；
- 可以从简单文件渐进到子包；
- Control/Data Plane 后续可拆部署而不复制 Domain。

代价：

- 比单文件 FastAPI 项目多一层 `src/nexusmcp`；
- 需要配置 Package Build Backend 和 uv 安装；
- 开发者需要理解 Interface、Use Case、Port、Adapter 的依赖方向；
- 模块边界错误时需要显式重构，不能依赖全局 Service 互相调用。

## 验证

创建骨架后必须满足：

```text
uv sync --frozen
uv run python -c "import nexusmcp"
uv run python -m pytest
uv run ruff check .
uv run basedpyright
```

并验证：

- 从仓库根目录以外仍能 import 已安装 Package；
- `main.py` 只暴露 Application Factory 结果；
- `/health` 与 `/mcp` 可运行；
- S1 动态 Tool Contract 迁移到正式 MCP Interface 后继续通过；
- `src/nexusmcp` 不 import `examples` 和 `tests`；
- 没有手工 `PYTHONPATH`；
- 首批未创建无内容的业务模块。

## 复审触发条件

- 项目需要独立发布多个 Python Distribution；
- Control Plane/Data Plane 拆成独立部署单元；
- 模块间出现持续循环依赖或无法执行的事务边界；
- 插件系统要求 Namespace Package；
- 多团队所有权要求将某个 Bounded Context 独立仓库化；
- `src` Layout 阻碍目标部署平台且存在可复现证据。

## 实施记录

2026-08-24 已按本 ADR 创建首批骨架：

- 使用官方 `uv_build` 和默认 `src/nexusmcp` 模块发现；
- Package 可从仓库目录外导入；
- Application Factory、Health 和正式 MCP `tools/list` Adapter 可运行；
- Catalog Domain/Port/Use Case/In-Memory Adapter 已建立；
- pytest、Ruff、basedpyright、sdist/wheel 构建通过。
