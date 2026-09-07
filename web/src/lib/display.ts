import type { StatusTone } from "@/components/ui/status-pill";

const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date);
}

export function statusTone(status: string): StatusTone {
  if (["running", "validating", "parsing"].includes(status)) return "active";
  if (["succeeded", "completed", "published", "consumed", "active", "approved"].includes(status)) {
    return "completed";
  }
  if (["pending", "planned"].includes(status)) return "pending";
  if (["review", "needs_change", "accepted"].includes(status)) return "review";
  if (status === "draft") return "draft";
  if (["failed", "unknown", "rejected"].includes(status)) return "failed";
  return "neutral";
}

export function humanize(value: string): string {
  const localized: Record<string, string> = {
    active: "已启用",
    disabled: "已停用",
    draft: "草稿",
    pending: "待处理",
    planned: "已计划",
    validating: "校验中",
    parsing: "解析中",
    review: "审核中",
    needs_change: "需要修改",
    accepted: "已接受",
    approved: "已批准",
    rejected: "已拒绝",
    expired: "已过期",
    consumed: "已消费",
    published: "已发布",
    retired: "已退役",
    completed: "已完成",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
    unknown: "结果未知",
    cancelled: "已取消",
    public: "公开",
    authenticated: "需认证",
    restricted: "受限",
    read_only: "只读",
    idempotent_write: "幂等写",
    non_idempotent_write: "非幂等写",
    allowed: "已允许",
    denied: "已拒绝",
    approval_required: "需要审批",
    tool_call: "Tool 调用",
    approval_decision: "审批决策",
    credential_resolution: "凭据解析",
    none: "无",
    missing: "未索引",
    stale: "等待更新",
    current: "已索引",
    explicit: "显式工具集",
    all_published: "全部已发布工具",
    direct: "直接暴露",
    search_first: "检索优先",
    healthy: "健康",
    degraded: "部分降级",
    unavailable: "不可用",
    tool_disabled: "Tool 已停用",
    no_published_version: "无 Published Version",
  };
  if (localized[value]) return localized[value];
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
