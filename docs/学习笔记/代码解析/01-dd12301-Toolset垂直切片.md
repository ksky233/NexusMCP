## What：这批改动交付了什么

一句话：**给 Toolset（工具集）补齐了从管理端 Web UI 到 PostgreSQL 的完整 Control Plane 管理链路**，但不触碰 MCP Runtime 数据面（`/mcp/toolsets/{slug}` 的实际调用行为留给下一步 I03-3）。

改动分五块：

| 板块 | 文件 | 内容 |
|---|---|---|
| **应用层** | [use_cases.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/use_cases.py)（新） | 8 个 Use Case：Create / Update / ReplaceMembers / ReplaceGrants / Activate / Disable / Get / List + `ToolsetProfile` 读模型 |
| **接口层** | [toolset_routes.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/interfaces/admin/toolset_routes.py)、`toolset_models.py`（新） | 8 个冻结 Admin HTTP Operation |
| **端口/适配器** | [ports.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/ports.py)、[toolset_catalog_reader.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/infrastructure/persistence/toolset_catalog_reader.py)、`in_memory.py` | `ToolsetCatalogSnapshot` 扩展 canonical_name/description/schema_size；新增 `list_published_snapshots()` 端口方法 + SQL/内存双实现 |
| **错误契约** | [shared/errors.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/shared/errors.py) | 6 个新 Problem Code（`toolset_revision_conflict` 等） |
| **组装** | [bootstrap/app.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/bootstrap/app.py)、`persistence_factories.py` | `RuntimeToolsetUnitOfWorkFactory` + 8 个 Use Case 注入 Admin Services |

外加：前端 `web/src/features/toolsets/`（列表页 + 详情页，含 Hey API 生成的 TS Client 和 Zod 校验）、`contracts/admin.openapi.json` 重新导出、集成/单元/契约测试，以及 [42 号实验记录](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/docs/实验记录/42_I03-2_AdminAPI与WebUI.md) 和两篇学习笔记（13 Port-Adapter-UoW、14 DDD 与六边形——就是前面几轮对话的沉淀）。

---

## Why：为什么做这个

从提交历史看，这个分支的故事线非常清晰：

```
I03-0 决策与协议实验 → I03-1 Toolset 领域与 PostgreSQL 持久化（已提交 3 个 commit）
→ ★ 本次未提交：I03-2 Admin API 与 Web UI
→ 下一步 I03-3 Scoped MCP Endpoint（数据面）
```

**为什么 Control Plane 先行、Data Plane 后行？** 因为 MCP 客户端要按 `/mcp/toolsets/{slug}` 这个动态路径调用，前提是路径背后的 Toolset 得先能被创建、配置成员、授权 Principal、激活。没有管理面，数据面无从验证。这也是实验记录里明确写的：

> 本轮只管理发布面，不改变 MCP Runtime；`/mcp/toolsets/{slug}` 的实际 `tools/list/tools/call` 行为属于 I03-3。

业务上，Toolset 是「按 Principal 授予一组 Tool 的批量授权单元」——管理员不用逐个 Tool 配权限，而是配一个 Toolset 一次授权，这直接服务于整体规划里「不同 Principal 对同一 Tool 得到不同 Policy Decision」的验收证据。

---

## How：关键实现决策

### ① Profile = 持久化事实 + 动态运行投影

`ToolsetProfile` 分两部分（见 [use_cases.py L98-L119](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/use_cases.py#L98-L119)）：

- **静态身份**：slug、kind、status、revision、membership_digest（来自聚合）
- **动态诊断**：health、available_tool_count、serialized_schema_size（每次从 Catalog 快照**现算**，不落库）

派生健康度（HEALTHY/DEGRADED/UNAVAILABLE）在 `_profile()` 里实时计算，保证详情页永远反映发布面的真实状态。

### ② `all_published` 系统 Toolset 不写 Member Row

这是本轮最有意思的设计。系统级「全部已发布工具」集合**不物化成员关系**，而是 [list_published_snapshots()](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/infrastructure/persistence/toolset_catalog_reader.py#L73-L131) 动态 JOIN 查询当前所有 Active + Published 的 Tool：

> 「新 Tool 发布后不需要同步修改系统 Toolset」——消除了一个必然 eventual consistency 陷阱。

### ③ 成员校验与聚合修改共用一个事务

`ReplaceToolsetMembers` 的执行序（[L191-L215](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/use_cases.py#L191-L215)）：

```python
async with uow_factory() as uow:
    toolset = await uow.toolsets.get_for_update(...)      # SELECT FOR UPDATE 锁聚合
    snapshots = await uow.catalog.list_member_snapshots(...)  # 同事务读 Catalog
    _require_available(snapshots)                          # 校验成员可用性
    updated = toolset.replace_members(...)                 # 聚合方法执法不变量
    await uow.toolsets.save(...)
    profile = await _profile(uow, updated)                 # 同事务组装 Profile
    await uow.commit()
```

这正好回答了上一轮 UoW 存在的意义：**「toolsets 存在性」和「catalog 发布状态」两个数据源的校验必须原子**——否则可能出现「校验时成员可用、提交时已下架」的竞态。`get_for_update` 防止并发修改，Profile 事务内组装保证返回值与提交一致。

### ④ 集合整体替换，不做逐行 CRUD

Members 和 Grants 都是 `PUT` 语义的 `replace_*`：管理端每次提交完整集合，UoW 原子替换。没有 `POST /members`、`DELETE /members/{id}`。

### ⑤ 乐观并发 + `expected_revision`

所有变更命令都带 `expected_revision`，聚合方法内校验（`_require_revision`），冲突映射为 `toolset_revision_conflict`（409）。前端拿到 409 就知道要刷新后重试。

### ⑥ Contract-First 前端

后端 FastAPI 路由定义 `operation_id` → 导出 `contracts/admin.openapi.json` 快照（契约测试守护）→ Hey API 生成 `web/src/generated/api/*`（含 Zod 校验）→ 前端 features 只调生成的 SDK。**前端零手写 HTTP 路径、零复制后端 DTO**。

---

## Trade-off：每个决策付出了什么代价

| 决策 | 得到 | 失去 / 风险 |
|---|---|---|
| **整体替换 Members/Grants** | 原子性强、UI 简单（一个表单提交）、无部分状态 | ❌ 审计粒度粗——无法回答「谁在什么时候把 Tool X 移出了集合」，只能看到快照变化；成员多时每次全量提交 |
| **`all_published` 动态投影** | 无同步开销、永远准确 | ❌ 每次读 Profile 都要全量 JOIN；成员数极大时列表页会慢；无 member added_at 等历史信息（VO 上有字段但没意义） |
| **Profile 事务内组装** | 返回值与 DB 状态强一致 | ❌ 拉长事务持有时间（锁+读+算），高并发下热点 Toolset 的行锁窗口变大 |
| **`serialized_schema_size` 现算** | 无冗余存储、无失效风险 | ❌ 每次都 `json.dumps` 全部成员的 Schema（[L135-L141](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/infrastructure/persistence/toolset_catalog_reader.py#L135-L141)），O(成员数 × Schema 大小) |
| **ListToolsets 内存过滤分页** | 实现简单，单租户 Toolset 数量少时足够 | ❌ `list_by_tenant` 全量载入后 Python 切片（[L305-L324](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/use_cases.py#L305-L324)），数据量上来必须换 SQL 分页 |
| **显式 UoW** | 事务边界清晰、测试可注入 InMemory | ❌ 比 Spring `@Transactional` 样板多；Use Case 持有 Factory 的模式每个类重复一遍 |

**一个真实的代码坏味道**（面试可以主动讲）：[_map_mutation_error](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/use_cases.py#L414-L420) 靠 `ValueError` 的**消息字符串关键词**（`"revision"`、`"all_published"`）来映射领域错误到 HTTP 错误码。脆弱——领域层改一句文案就会破坏错误映射。更稳的做法是领域层抛类型化异常。同样，`_require_expected_revision` 在 Use Case 层预检了一次（L193、L249），而聚合方法内部还会再检一次——双保险但也说明 `ValueError` 无法类型化导致防御性重复。

---

## Alternative：被放弃的方案

1. **逐行 Member CRUD**（`POST/DELETE /members/{id}`）→ 放弃。部分失败状态难处理，且与聚合不变量「Active 必须有成员」冲突（逐行删可能删空）。
2. **`all_published` 物化 Member Rows + 发布事件同步** → 放弃。需要 `ToolPublished` 领域事件消费者维护一致性，多了 eventual consistency 窗口和补偿逻辑；动态查询在这个数据规模下成本可接受。
3. **Profile 做成读模型/物化视图**（CQRS 读侧）→ 推迟。当前规模现算即可，架构已预留 `ToolsetCatalogReader` 端口，未来可无感替换为物化实现。
4. **前端手写 API 层或用 tRPC/GraphQL** → 放弃。维持 OpenAPI 契约快照 + 生成式客户端，和已有的 admin 页面保持同一套机制。
5. **`ValueError` 换成类型化领域异常** → 这是该做的，但会牵动 domain.py 大面积改动，可能留到重构轮（或者是个已知债）。

---

## Interview Question：面试官会怎么问

**Q1: 「为什么 Member 校验要放在数据库事务里做，不能先查后改吗？」**
要点：先查后改存在 TOCTOU 竞态（check-then-act）。校验成员存在性和发布状态、修改聚合、写回，三者必须原子。`get_for_update` 拿行锁串行化同一 Toolset 的并发修改，Catalog Reader 复用 UoW 的 Session 保证读到同一快照。可以延伸讲「锁跨越外部调用」的反例——本项目 registry 模块就有「DNS/Policy 检查放事务外」的注释，说明边界判断是显式设计而非默认。

**Q2: 「expected_revision 是什么并发控制？和 SELECT FOR UPDATE 什么关系？」**
要点：两层。乐观并发（revision 比对）防御「读到旧状态后提交」的丢失更新，跨请求生效（前端提交 stale revision 得 409）；悲观锁（FOR UPDATE）防御「同一事务内并发读改写」，只在事务内生效。二者正交：锁解决进程内竞态，revision 解决进程间/客户端竞态。

**Q3: 「all_published 为什么不物化成员？什么时候你会改主意？」**
要点：一致性 vs 读性能的取舍。动态投影牺牲读成本换零同步。改主意的信号：成员数过万、Profile 读 QPS 高、需要成员级审计历史。由于 Port 已抽象（`list_published_snapshots`），届时可以在 Adapter 层换物化实现 + 事件驱动刷新，Use Case 不动——这就是六边形架构的回报。

**Q4: 「你的错误处理是怎么跨层传递的？有什么问题？」**
要点（主动暴露上面那个坏味道会加分）：领域层 `ValueError` → Use Case 映射为类型化 `NexusMcpError`（带 `code` 和 `safe_message`）→ 接口层渲染成 RFC 7807 Problem JSON。问题在于映射靠字符串匹配，脆弱。正确姿势是领域层定义领域异常。另外 `safe_message` 的设计意图是**错误信息不泄漏内部细节**——呼应项目「Credential 不进日志」的安全主线。

**Q5: 「前端为什么不手写 API 调用？」**
要点：Contract-first。OpenAPI JSON 是被契约测试守护的快照，前端类型和运行时校验全部生成，后端改契约 → 快照 diff → 前端编译期即报错。避免前后端 DTO 漂移这类经典集成事故。

**Q6: 「这个 Use Case 类为什么这么薄，是不是过度设计？」**
要点：薄是因为业务规则在聚合上（充血模型），Use Case 只剩编排：锁→校验→调聚合→存→组装 Profile→提交。这是 DDD 的预期形态，不是贫血转移。Use Case 的不可替代职责是**事务边界和错误映射**。对比反例：如果规则散在 Handler 里，`tools/call` 数据面（I03-3）就无法复用激活前校验逻辑。

**Q7（架构收尾题）: 「管理面和数据面共用同一套聚合和 UoW，会不会互相拖累？」**
要点：共用领域模型保证不变量单点执法（管理面配置错了，数据面立刻体现为不可用成员）；分离靠端口（Admin 走 Command Use Case，MCP 走 `ListVisibleTools` 查询路径）和未来的读侧优化。这正好引到 I03-3 的悬念：数据面如何用同一份 Grant 数据做 `tools/list` 过滤。

---

**整体评价**：这是一次教科书级的 Control Plane 垂直切片——契约先行、双 Adapter 契约测试守护、聚合不变量单点执法、投影与事实分离。最值得在提交前顺手修的是 `_map_mutation_error` 的字符串匹配；最值得写进 ADR 的取舍是「整体替换 vs 逐行 CRUD」和「all_published 动态投影」。需要我把这些整理成提交拆分建议或 ADR 草稿吗？