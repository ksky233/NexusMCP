# Principal 的设计与理解

> 2026-08-30 边界修订：本文来源于早期协议实验。正式产品不建设员工 User/Role Identity；Principal 主线为
> Admin Operator 或 Agent Service，见 ADR-0019。

## `_principal` 函数的理解

### 1. 命名拆解

这个函数名由两部分组成：

| 部分 | 含义 |
|---|---|
| **前置下划线 `_`** | Python 社区惯例：**模块级私有函数**。表示这个函数只在 `dynamic_gateway.py` 内部使用，**不对外导出**，外部代码不应直接调用。 |
| **principal** | 安全领域标准术语。发音 /ˈprɪnsəpəl/，翻译为 **「主体」** 或 **「请求方身份」**。指发起一次请求的**实体**（用户、Agent、服务账号等），是权限判断的基本对象。 |

> 注意和 "principle"（原则/原理）区分拼写，这是英语常见易混词。在安全/IAM 语境中永远是 **principal（主体）**。

合起来 **`_principal()`** = 「本文件内部使用的、从请求中提取**调用者身份**的辅助函数」。

---

### 2. 在项目中的职能

S1 实验阶段的核心任务之一是**证明 SDK v2 的 `ServerRequestContext` 能承载「身份上下文」**，为正式项目的鉴权链路验证可行性。`_principal()` 就是这条链路的**身份提取接缝（identity extraction seam）**。

#### 具体做了什么（[L73-L87](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L73-L87)）

```
输入: ServerRequestContext（SDK 低层 Handler 的统一上下文）
  │
  ├─ 尝试路径 A：HTTP Header（Streamable HTTP Transport）
  │    读取 ctx.request.headers["x-nexusmcp-s1-principal"]
  │    → 对应测试用例中的 HTTP 传输场景（E3）
  │
  ├─ 路径 A 失败 → 尝试路径 B：MCP _meta（In-Memory Transport）
  │    读取 ctx.meta["com.nexusmcp.dev/principal"]
  │    → 对应纯 SDK 内存传输场景（E2）
  │
  └─ 都失败 → fallback "anonymous"
  │
输出: str 类型的 Principal 标识（如 "viewer"、"operator"、"anonymous"）
```

#### 为什么需要双路径提取？（对应 S1 的两个实验场景）

| Transport | 身份来源 | 代码分支 | 说明 |
|---|---|---|---|
| **In-Memory**（SDK 自带） | `ctx.meta` 的自定义 key | [L84-L87](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L84-L87) | 没有 HTTP，只能用 MCP 协议开放的 `_meta` Map 传身份 |
| **Streamable HTTP**（ASGI） | HTTP Header | [L76-L82](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L76-L82) | 真实部署场景，Header 是 Token 解析后注入身份的标准位置 |

#### 它在调用链中的位置和影响

`_principal()` 的返回值直接驱动了两条核心链路：

```
 _principal(ctx)
       │
       ├─→ _visible_tools(principal) ──→ tools/list 的结果（不同人看到不同 Tool）
       │                                      [L129]
       │
       └─→ _visible_tools(principal) ──→ tools/call 的重新鉴权（防止绕过 list 猜名）
                                              [L144]
```

即：`viewer` 能看到 `directory.get_employee` 但看不到 `ops.get_service_status`；`operator` 两个都能看到。这个差异完全由 `_principal()` 提取出的身份字符串决定。

---

### 3. 重要的安全边界注释（[L10-L13](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L10-L13)）

文件顶部已经明确标注：

> **正式项目必须先验证 Token，再生成可信 Principal，不能直接相信这两个值。**

也就是说：
- **S1 实验**：`_principal()` 直接信任 Header 和 `_meta`，方便测试快速模拟身份。
- **正式项目**：`_principal()` 所在位置将被替换为 **Token 验证 → Claims 解析 → 构建可信 InternalPrincipal 对象**的完整认证链，Header 和 `_meta` 里的值只能作为辅助信号，**绝不能直接作为身份信任**。

---

### 总结

| 维度 | 说明 |
|---|---|
| **单词含义** | `_` = 私有函数；`principal` = 安全领域的「请求主体/身份」（不是 principle） |
| **本质** | 身份提取的辅助函数（S1 实验版，信任测试输入） |
| **核心职能** | 从两种 Transport（Memory / HTTP）的 Context 中统一提取 Principal，给可见性过滤和调用鉴权提供输入 |
| **设计价值** | 证明 `ServerRequestContext` 可以同时访问 HTTP Header 和 MCP `_meta`，为正式项目的「协议层身份解析 → 领域层策略判断」链路锁定接缝 |
| **正式项目映射** | 对应 `nexusmcp.auth` 模块中的 `IdentityExtractor` / `TokenAuthenticator`，输出将升级为带角色、租户、Scope 的结构化 Principal DTO |
