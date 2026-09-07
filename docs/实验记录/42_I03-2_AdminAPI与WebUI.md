# I03-2｜Toolset Admin API 与 Web UI

> 状态：Completed
>
> 日期：2026-09-07
> 决策依据：[ADR-0020](../adr/0020-toolset-scoped-mcp-endpoints.md)

## 1. 本轮交付

I03-2 完成 Toolset 从 Application 到管理界面的完整 Control Plane 链路：

```text
Admin Web
→ Generated TypeScript Client
→ FastAPI Admin Contract
→ Toolset Command / Query Use Case
→ Toolset UoW
→ PostgreSQL Toolset + Member + Grant
```

本轮只管理发布面，不改变 MCP Runtime；`/mcp/toolsets/{slug}` 的实际 `tools/list/tools/call` 行为属于 I03-3。

## 2. Admin Use Case

新增以下 Command/Query：

- Create、Update、Activate、Disable Toolset；
- Replace Members；
- Replace Access Grants；
- Get Toolset Profile；
- List Toolsets，并按文本、Status、Kind、Discovery Mode 筛选。

所有修改都通过 Aggregate Method 和 `expected_revision`。Member/Grant 没有逐行 CRUD，管理端提交完整集合，UoW
负责原子替换。

成员校验与 Catalog 使用同一个数据库事务：

- 不属于当前 Tenant 或不存在的 Tool 返回 `invalid_toolset_members`；
- Active Toolset 不能替换为不可用成员；
- Activate 前全部成员必须存在且拥有 Published Version；
- DRAFT 可以暂存 Disabled/No Published Version 成员，并在 Profile 中显示派生 Health；
- 系统 `all_published` 禁止显式编辑成员或停用。

## 3. Toolset Profile

Profile 同时返回持久化事实和动态运行投影：

```text
身份与状态
├── Kind / Status / Discovery Mode / Revision
├── Membership Digest
└── Endpoint Path

动态诊断
├── Health
├── Tool Count / Available Count
├── Serialized Schema Size
├── Member Availability / Published Version / Description
└── Principal Grant List
```

`all_published` 不写 Member Row。其 Profile 通过 `list_published_snapshots()` 动态读取当前全部 Active + Published
Tool，因此新 Tool 发布后不需要同步修改系统 Toolset。

## 4. HTTP 与 Generated Client

Admin API 实现 8 个冻结 Operation：

```text
POST /admin/toolsets
GET  /admin/toolsets
GET  /admin/toolsets/{toolset_id}
PUT  /admin/toolsets/{toolset_id}
PUT  /admin/toolsets/{toolset_id}/members
PUT  /admin/toolsets/{toolset_id}/grants
POST /admin/toolsets/{toolset_id}/activate
POST /admin/toolsets/{toolset_id}/disable
```

新增稳定 Problem Code：`toolset_not_found`、`toolset_conflict`、`toolset_revision_conflict`、
`invalid_toolset_members`、`toolset_member_unavailable`、`system_toolset_immutable`。

`contracts/admin.openapi.json` 已重新导出，Hey API Client/Zod Response Contract 已生成；前端没有手写 HTTP Path
或复制后端 DTO。

## 5. Web UI

新增一级导航“工具集”和两个页面：

- `/toolsets`：列表、四类筛选、创建 Explicit Toolset、Health/数量/Revision 诊断与 Endpoint Copy；
- `/toolsets/{id}`：运行 Profile、配置编辑、启停、Published Tool 批量成员选择、Principal Grant 原子替换。

系统 `all_published` 详情不显示 Member Editor，而是显示动态 Published Catalog 投影，并对其 Grant 风险作明确提示。
Endpoint Copy 使用当前 Web Origin 加后端返回的稳定 Path，兼容本地与公网反向代理部署。

## 6. 验证结果

```text
Python Unit/Contract                              35 passed
PostgreSQL Repository/Admin Vertical Slice       14 passed
Full Python Suite                                 342 passed / 2 paid external skipped
Ruff Lint/Format                                  passed
basedpyright                                      0 errors / 0 warnings
Admin OpenAPI Snapshot                            matched
Frontend Type Check/Oxlint/Oxfmt                  passed
Frontend Vitest                                   24 passed
Frontend Production Build                        passed
```

真实 Admin Integration 已验证：OpenAPI Tool Publish → 创建 Toolset → Replace Member → Replace Grant → Activate →
List/Profile → Stale Revision 409，且 Profile 返回 Canonical Name、Description 与 Schema Size。

## 7. 下一步

进入 `I03-3｜Scoped MCP Endpoint`：把管理面创建的 Active Toolset 接入 Modern MCP 动态 Path，并在
`tools/list` 与 `tools/call` 两条路径执行 Grant 和 Membership Guard。
