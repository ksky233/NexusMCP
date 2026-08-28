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

import { EmptyState, ErrorState, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { useDashboardQuery } from "@/features/dashboard/hooks/use-dashboard-query";

const numberFormatter = new Intl.NumberFormat("en-US");

export function DashboardPage() {
  const dashboard = useDashboardQuery();

  if (dashboard.isPending) {
    return <LoadingState label="Loading governance overview…" />;
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
      <div className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
        <div>
          <p className="eyebrow">Governance overview</p>
          <h1 className="page-title" id="dashboard-title">
            Enterprise tools, one control surface.
          </h1>
          <p className="page-description">
            Live PostgreSQL projections for registry, catalog, approvals, execution and search.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {dashboard.isFetching ? (
            <span className="inline-flex items-center gap-2 text-xs font-medium text-ink-muted">
              <RefreshCw aria-hidden="true" className="size-3.5 animate-spin" /> Refreshing
            </span>
          ) : null}
          <Button variant="secondary" size="small" onClick={() => void dashboard.refetch()}>
            <RefreshCw aria-hidden="true" className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {!hasGovernedState ? (
        <div className="mt-8">
          <EmptyState
            title="No governed resources yet"
            description="Register an HTTP/OpenAPI upstream to begin the import, review and publish lifecycle."
          />
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <MetricCard
            icon={Network}
            label="Active upstreams"
            value={data.active_upstreams}
            tone="blue"
          />
          <MetricCard
            icon={Boxes}
            label="Published tools"
            value={data.published_tools}
            tone="indigo"
          />
          <MetricCard
            icon={Clock3}
            label="Pending reviews"
            value={data.pending_reviews}
            tone="amber"
          />
          <MetricCard
            icon={ShieldCheck}
            label="Pending approvals"
            value={data.pending_approvals}
            tone="violet"
          />
          <MetricCard
            icon={AlertOctagon}
            label="Failed executions"
            value={data.failed_executions}
            tone="red"
          />
          <MetricCard
            icon={ArrowUpRight}
            label="Unknown outcomes"
            value={data.unknown_executions}
            tone="slate"
          />
        </div>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.45fr_1fr]">
        <article className="panel p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="eyebrow">Search projection</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
                Embedding coverage
              </h2>
            </div>
            <span className="rounded-full bg-success-soft px-3 py-1 text-xs font-semibold text-success">
              {data.search_projection.coverage_percent.toFixed(2)}%
            </span>
          </div>
          <div className="mt-7 h-2 overflow-hidden rounded-full bg-surface-strong">
            <div
              aria-label={`${data.search_projection.coverage_percent}% indexed`}
              className="h-full rounded-full bg-gradient-to-r from-accent to-cyan-400"
              style={{ width: `${Math.min(data.search_projection.coverage_percent, 100)}%` }}
            />
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <ProjectionStat label="Published" value={data.search_projection.published_tools} />
            <ProjectionStat label="Indexed" value={data.search_projection.indexed_tools} />
            <ProjectionStat label="Pending" value={data.search_projection.pending_tools} />
          </div>
          <p className="mt-6 break-all font-mono text-xs leading-5 text-ink-subtle">
            {data.search_projection.embedding_model}@{data.search_projection.embedding_dimensions}
          </p>
        </article>

        <article className="panel flex flex-col justify-between p-6">
          <div>
            <span className="grid size-10 place-items-center rounded-xl bg-success-soft text-success">
              <CheckCircle2 aria-hidden="true" className="size-5" />
            </span>
            <h2 className="mt-5 text-lg font-semibold text-ink">Contract-connected</h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">
              Dashboard data is fetched through the generated Hey API SDK, validated by generated
              Zod schemas and cached by TanStack Query.
            </p>
          </div>
          <div className="mt-7 border-t border-line pt-4">
            <p className="text-xs font-medium text-ink-subtle">
              Request ID
              <span className="mt-1 block break-all font-mono text-ink-muted">
                {snapshot.requestId ?? "Unavailable"}
              </span>
            </p>
          </div>
        </article>
      </div>
    </section>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Network;
  label: string;
  value: number;
  tone: "blue" | "indigo" | "amber" | "violet" | "red" | "slate";
}) {
  return (
    <article className="panel group p-5 transition-transform hover:-translate-y-0.5">
      <div className={`metric-icon metric-icon-${tone}`}>
        <Icon aria-hidden="true" className="size-4" />
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight text-ink">
        {numberFormatter.format(value)}
      </p>
      <p className="mt-1 text-sm font-medium text-ink-muted">{label}</p>
    </article>
  );
}

function ProjectionStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-2xl font-semibold text-ink">{numberFormatter.format(value)}</p>
      <p className="mt-1 text-xs font-medium uppercase tracking-[0.12em] text-ink-subtle">
        {label}
      </p>
    </div>
  );
}
