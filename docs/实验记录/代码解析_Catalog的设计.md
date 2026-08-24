## `CatalogTool` 的理解

### 1. 单词含义

这是一个合成词，由两部分组成：

| 部分 | 含义 |
|---|---|
| **Catalog** | 目录/注册中心。对应 NexusMCP 核心概念 **Tool Catalog**（工具目录），即所有已发布 Tool 的中心化清单，未来会持久化在 PostgreSQL 中。 |
| **Tool** | MCP 协议中的工具，Agent 通过 `tools/list` 发现、通过 `tools/call` 调用的能力单元。 |

合起来 **CatalogTool** = **「在 Tool Catalog 中注册的一条 Tool 定义记录」**，是 Catalog 层的**领域数据模型**。

---

### 2. 在项目中的职能

结合代码来看，`CatalogTool` 在 S1 实验阶段承担了三个关键角色：

#### ① 模拟未来正式 Catalog 的数据形态（[L36-L43](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L36-L43)）

```python
@dataclass(frozen=True)
class CatalogTool:
    name: str              # Tool 唯一名称，如 directory.get_employee
    description: str       # Tool 描述，展示给 Agent
    input_schema: dict[str, Any]  # 入参 JSON Schema（直接存原始 Schema）
    visible_to: frozenset[str]    # 可见性：哪些 Principal 能看到这个 Tool
```

它是一个 **不可变（frozen）数据类**，字段设计直接对应未来 PostgreSQL 中 `catalog_tool` 表的核心列，提前锁定 Tool 元数据的领域形状。

#### ② 证明「动态 Tool 暴露」的可行性（[L45-L70](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L45-L70)）

注释 [L45-L46](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L45-L46) 特别说明了设计意图：

> 这里故意直接保存 JSON Schema，而不是从 Python 函数签名生成。这正是 **OpenAPI 导入并发布 Tool 后**，NexusMCP 运行时需要处理的数据形态。

也就是说，`CatalogTool` 不走 SDK 那种 `@server.tool()` 装饰器的静态路线，而是模拟了「OpenAPI 导入 → 存入 Catalog → 运行时动态读取」的真实业务路径。

#### ③ 作为可见性过滤与协议映射的输入源

- 在 `_visible_tools()` [L109-L113](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L109-L113) 中，用 `visible_to` 字段做**极简版 Principal 可见性过滤**（正式实现将是 Catalog Query + Policy Evaluator）
- 在 `list_visible_tools()` [L123-L130](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L123-L130) 中，把领域模型 `CatalogTool` **映射**为 MCP SDK 的协议类型 `types.Tool` — 刻意保持领域模型不反向依赖 SDK 类型
- 在 `call_tool()` [L144](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L144) 中，调用时**再次用同样规则做鉴权**，防止客户端绕过 `tools/list` 直接猜测 Tool Name

---

### 总结

| 维度 | 说明 |
|---|---|
| **本质** | Tool Catalog 的领域数据对象（Data Object），不可变值对象 |
| **模拟来源** | 未来 PostgreSQL `catalog_tool` 表的一条记录 |
| **核心能力** | 承载 Tool 元数据 + 可见性规则 |
| **设计价值** | 证明 NexusMCP 可以脱离 `@tool` 装饰器、基于外部 Catalog 动态暴露 Tool，为 OpenAPI 导入发布链路铺路 |
| **正式项目映射** | 对应 `nexusmcp.catalog` 模块中的 Tool 实体 + Repository 读出的 DTO |

和它配合的另外两个实验文件 [asgi_app.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/asgi_app.py)（传输层）与 [dual_era.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dual_era.py)（新旧协议兼容）一起，构成了 S1 协议校准的三条实验主线。