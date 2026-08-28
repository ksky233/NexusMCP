import type { StatusTone } from "@/components/ui/status-pill";

const dateTimeFormatter = new Intl.DateTimeFormat("en", {
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
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
