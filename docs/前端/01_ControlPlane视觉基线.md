# NexusMCP Control Plane 视觉基线

> 状态：Accepted
> 日期：2026-08-28（2026-08-29 按 v2 校准）
> 来源：本地“黑白-细硬”UI System v2 参考模板
> 范围：W2.5～W4.5 Web Control Plane

## 1. 设计目标

NexusMCP 是企业 Tool Governance Control Plane，不是营销型 SaaS Landing Page。视觉应表达：

- 克制、可信、可审计；
- 适合 Table、Filter、Status、Timeline 等高密度信息；
- 灰阶负责结构，颜色只负责状态语义；
- 动效负责反馈，不负责展示；
- 组件边界与 Backend 状态机保持清楚。

参考模板只提供视觉语言，不作为 Runtime Dependency。禁止复制其中的 Tailwind CDN、全局原生 DOM Script、
模拟 Toast/Modal 业务或静态页面结构。

## 2. Token

| Token | Value | 用途 |
|---|---|---|
| `ink` | `#222831` | 标题、Primary Action、强结构 |
| `slate` | `#393E46` | 正文、图标、默认边框 |
| `mist` | `#EEEEEE` | Hover、Disabled、弱分组 |
| `paper` | `#FFFFFF` | Sidebar、Card、Dialog |
| `canvas` | `#F7F7F6` | 页面背景 |
| `wine` | `#74303E` | Error、Danger、Destructive Confirm |
| `teal` | `#00ADB5` | 仅 Running/In Progress |

约束：

- 不使用装饰性渐变；
- 不为不同 Dashboard Metric 分配彩虹色；
- `teal` 不表示普通成功；Completed 使用 Ink 黑底；
- Warning、Pending、Draft、Review 优先使用灰阶、边框或虚线区分；
- Local Development Admin 是环境声明，使用 Mist/Slate，不伪装成 Error。

## 3. Shape、Border 与 Shadow

- Small Radius：`4px`；
- Medium Radius：`8px`；
- Pill 只用于 Status、Tag 和 Compact Filter；
- Card 默认 1px Slate Alpha Border；
- 普通 Card 只使用 `0 1px 2px` 极轻阴影；
- Floating Overlay 才允许 Medium/High Shadow；
- 不使用 W2 初版的 16px 大圆角、彩色 Icon Tile 和蓝色 Glow。

## 4. Typography 与密度

- 系统字体栈优先，W2.5 不增加 Web Font 网络依赖；
- Page Title 使用轻量、清晰的层级，不使用营销型 Hero；
- Eyebrow 使用 Small Uppercase + Letter Spacing；
- Table/Form 使用 `13～14px` 主字号；
- Mono 仅用于 Request ID、Trace ID、Digest、Model Version；
- Desktop 优先信息密度，Mobile 允许 Card/List 重排但不隐藏治理事实。

### 4.1 v2 后台密度校准

W4.5 不重做视觉体系，只在原基线上强化后台管理界面的结构感：

- Eyebrow 与 Component Label 使用中等字重、较窄字距和更深文字色；
- Panel、Filter、Table Frame 默认边框提高对比度，但仍保持 1px 细边框；
- Input/Select/Textarea 的默认、Hover、Focus 边界依次增强；
- Secondary Button 的边界比普通 Panel 更明确；
- Table Row 与 Section Divider 从“若隐若现”提升为可稳定扫描的分隔线；
- Card Hover 位移由 2px 收敛为 1px，减少空气感和营销式漂浮感；
- 公共 State Panel 与页面间距略微收紧，不压缩业务表单的可操作空间。

这里的“粗”指更高的颜色不透明度和更清晰的层级，不将 1px Border 普遍改为 2px。

## 5. Shell

- Desktop：White Sidebar + Thin Right Border；
- Mobile：Off-canvas Sidebar + Backdrop + Escape/Close；
- Header：当前 Section、Local Development Admin 声明、必要操作；
- Active Navigation：Mist Background + 2px Ink Inset Line；
- 主内容最大宽度由页面决定，不使用统一营销型窄容器；
- Sidebar Collapse 属于 Local UI State，不进入 Zustand。

## 6. Component Baseline

W2.5 必须冻结：

- Button：Primary/Secondary/Ghost/Danger；
- StatusPill：Active/Completed/Pending/Review/Draft/Failed/Neutral；
- Input/Textarea/Select 与 Error/Disabled；
- Table 与 Empty Row；
- Pagination；
- Dialog/Backdrop/Close；
- Loading/Empty/Error；
- Page Header、Card、Divider。

Dropdown、Tooltip、Toast、Tabs、Segmented、Switch 只有 W3 真实页面需要时再增加，不为模板完整度预建。

## 7. State Mapping

| NexusMCP State | Visual |
|---|---|
| `running` / `validating` / `parsing` | Teal Active |
| `succeeded` / `completed` / `published` / `consumed` | Ink Completed |
| `pending` / `planned` | Mist Pending |
| `review` / `needs_change` | Paper Review |
| `draft` | Dashed Draft |
| `failed` / `unknown` / destructive | Wine Failed/Danger |
| `disabled` / `retired` / `cancelled` | Muted Neutral |

状态文字由业务 Context 决定；UI Component 只接受稳定 Visual Tone，不重新判断领域状态。

## 8. Accessibility

- Focus Visible 2px Slate Ring；
- Dialog 使用 Base UI Focus Management、Escape 与 ARIA；
- Icon-only Action 必须有 Accessible Name；
- Status 不只依赖颜色，必须同时有文字、边框或形状；
- `prefers-reduced-motion` 下关闭位移和循环动效；
- Mobile Sidebar 打开时必须有 Backdrop、Close Button 和 Escape 行为。

## 9. 实施边界

```text
W2.5
→ Token + Shell + Dashboard + 必需 Primitive

W3
→ 使用已有 Primitive 实现业务页面
→ 真实需求出现时增量补组件

W4
→ Responsive/Accessibility/Visual QA
→ Screenshot 与 Full-stack E2E

W4.5
→ 用户可见 UI 文案中文化
→ 按 v2 强化边框、标签字重与后台信息密度
→ API/状态值/日志/技术标识继续使用英文
```

W2.5 不实现 Upstream、Import、Approval 等业务 Mutation，也不引入 Storybook、第二套组件库或复杂 Theme
Switch。
