import {
  AlertOctagon,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  Clock3,
  Network,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import type { ComponentType, SVGProps } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import { useDashboardQuery } from "@/features/dashboard/hooks/use-dashboard-query";

const numberFormatter = new Intl.NumberFormat("zh-CN");

export function DashboardPage() {
  const dashboard = useDashboardQuery();

  if (dashboard.isPending) {
    return <LoadingState label="正在加载治理概览…" />;
  }
  if (dashboard.isError) {
    return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  }

  const snapshot = dashboard.data;
  const data = snapshot.data;
  const hasGovernedState =
    data.active_upstreams +
      data.published_tools +
      data.pending_reviews +
      data.pending_approvals +
      data.failed_executions +
      data.unknown_executions >
    0;

  return (
    <section aria-labelledby="dashboard-title" className="page-enter">
      <div className="flex flex-col justify-between gap-6 xl:flex-row xl:items-end">
        <div>
          <p className="eyebrow">NexusMCP · Control Plane</p>
          <h1 className="page-title" id="dashboard-title">
            系统概览
          </h1>
          <p className="page-description">
            实时查看 Registry、Catalog、审批、执行与检索的 PostgreSQL 投影。
          </p>
        </div>
        <div className="flex items-center gap-3">
          {dashboard.isFetching ? (
            <span className="inline-flex items-center gap-2 text-xs font-normal text-slate/55">
              <RefreshCw aria-hidden="true" className="size-3.5 animate-spin" /> 正在刷新
            </span>
          ) : null}
          <Button variant="secondary" size="small" onClick={() => void dashboard.refetch()}>
            <RefreshCw aria-hidden="true" className="size-3.5 stroke-[1.5]" />
            刷新数据
          </Button>
        </div>
      </div>

      <div className="hairline-divider my-10" />

      {!hasGovernedState ? (
        <EmptyState
          title="暂无治理资源"
          description="注册一个 HTTP/OpenAPI 上游服务，开始导入、审核与发布流程。"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <MetricCard icon={Network} label="已启用上游服务" value={data.active_upstreams} />
          <MetricCard icon={Boxes} label="已发布 Tool" value={data.published_tools} />
          <MetricCard icon={Clock3} label="待审核操作" value={data.pending_reviews} />
          <MetricCard icon={ShieldCheck} label="待处理审批" value={data.pending_approvals} />
          <MetricCard
            alert={data.failed_executions > 0}
            icon={AlertOctagon}
            label="失败执行"
            value={data.failed_executions}
          />
          <MetricCard
            alert={data.unknown_executions > 0}
            icon={ArrowUpRight}
            label="结果未知"
            value={data.unknown_executions}
          />
        </div>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.45fr_1fr]">
        <article className="panel p-6 sm:p-7">
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
            <div>
              <p className="component-label">检索投影</p>
              <h2 className="mt-3 text-xl font-light tracking-[-0.015em] text-ink">
                Embedding 覆盖率
              </h2>
            </div>
            <StatusPill tone={data.search_projection.pending_tools > 0 ? "active" : "completed"}>
              已索引 {data.search_projection.coverage_percent.toFixed(2)}%
            </StatusPill>
          </div>
          <div className="mt-7 h-1.5 overflow-hidden rounded-full bg-mist shadow-[inset_0_1px_2px_rgba(34,40,49,0.04)]">
            <div
              aria-label={`已索引 ${data.search_projection.coverage_percent}%`}
              className="h-full rounded-full bg-slate transition-[width] duration-500"
              style={{ width: `${Math.min(data.search_projection.coverage_percent, 100)}%` }}
            />
          </div>
          <div className="mt-7 grid gap-4 sm:grid-cols-3">
            <ProjectionStat label="已发布" value={data.search_projection.published_tools} />
            <ProjectionStat label="已索引" value={data.search_projection.indexed_tools} />
            <ProjectionStat label="待索引" value={data.search_projection.pending_tools} />
          </div>
          <p className="mt-7 break-all border-t border-slate/12 pt-4 font-mono text-xs leading-5 text-slate/55">
            {data.search_projection.embedding_model}@{data.search_projection.embedding_dimensions}
          </p>
        </article>

        <article className="panel flex flex-col justify-between p-6 sm:p-7">
          <div>
            <CheckCircle2 aria-hidden="true" className="size-6 stroke-[1.35] text-slate" />
            <p className="component-label mt-6">传输边界</p>
            <h2 className="mt-3 text-lg font-light text-ink">Contract 已连接</h2>
            <p className="mt-3 text-sm leading-7 text-slate/68">
              Dashboard 数据通过生成的 Hey API SDK 获取，由生成的 Zod Schema 校验，并使用 TanStack
              Query 缓存。
            </p>
          </div>
          <div className="mt-7 border-t border-slate/15 pt-4">
            <p className="component-label">Request ID</p>
            <span className="mt-2 block break-all font-mono text-xs text-slate/65">
              {snapshot.requestId ?? "不可用"}
            </span>
          </div>
        </article>
      </div>
    </section>
  );
}

type MetricIcon = ComponentType<SVGProps<SVGSVGElement>>;

function MetricCard({
  icon: Icon,
  label,
  value,
  alert = false,
}: {
  icon: MetricIcon;
  label: string;
  value: number;
  alert?: boolean;
}) {
  return (
    <article className="panel panel-interactive p-6">
      <div className="flex items-start justify-between gap-4">
        <p className="component-label">{label}</p>
        <Icon
          aria-hidden="true"
          className={alert ? "size-4 stroke-[1.5] text-wine" : "size-4 stroke-[1.5] text-slate/48"}
        />
      </div>
      <p
        className={
          alert ? "mt-7 text-3xl font-light text-wine" : "mt-7 text-3xl font-light text-ink"
        }
      >
        {numberFormatter.format(value)}
      </p>
    </article>
  );
}

function ProjectionStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-2xl font-light text-ink">{numberFormatter.format(value)}</p>
      <p className="mt-2 text-[10px] font-normal uppercase tracking-[0.14em] text-slate/50">
        {label}
      </p>
    </div>
  );
}
