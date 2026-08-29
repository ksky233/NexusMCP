import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StatusPill } from "@/components/ui/status-pill";
import {
  useSearchIndexJobs,
  useSearchIndexStatus,
  useStartSearchIndexJob,
} from "@/features/catalog/hooks/use-search-index";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function SearchIndexPanel() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const index = useSearchIndexStatus();
  const jobs = useSearchIndexJobs();
  const start = useStartSearchIndexJob();
  const latestJob = jobs.data?.items[0];
  const active = latestJob?.status === "pending" || latestJob?.status === "running";
  const pendingCount = (index.data?.missing_count ?? 0) + (index.data?.stale_count ?? 0);
  const embeddingAvailable = index.data?.embedding_available ?? false;

  return (
    <article className="panel mb-5 p-5 sm:p-6">
      <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
        <div>
          <p className="component-label">Tool Search Index</p>
          <h2 className="mt-3 text-xl font-normal text-ink">检索索引管理</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate/65">
            为已发布 Tool 生成 Canonical Search Document 向量；默认只处理未索引或已过期的
            Projection。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={() => {
              void Promise.all([index.refetch(), jobs.refetch()]);
            }}
            size="small"
            variant="secondary"
          >
            <RefreshCw className="size-3.5" /> 刷新状态
          </Button>
          <Button
            disabled={!embeddingAvailable || active || pendingCount === 0 || start.isPending}
            onClick={() => setConfirmOpen(true)}
            size="small"
          >
            {!embeddingAvailable
              ? "Embedding Provider 未配置"
              : active
                ? "正在更新…"
                : `更新检索索引${pendingCount ? ` (${pendingCount})` : ""}`}
          </Button>
        </div>
      </div>

      {index.isPending ? (
        <div className="mt-5">
          <LoadingState label="正在检查检索索引…" />
        </div>
      ) : null}
      {index.error ? (
        <div className="mt-5">
          <InlineError error={index.error} />
        </div>
      ) : null}
      {start.error ? (
        <div className="mt-5">
          <InlineError error={start.error} />
        </div>
      ) : null}

      {index.data ? (
        <div className="mt-6 grid gap-4 border-t border-slate/20 pt-5 sm:grid-cols-2 xl:grid-cols-5">
          <IndexMetric label="已发布" value={index.data.published_count} />
          <IndexMetric label="已索引" value={index.data.current_count} />
          <IndexMetric label="未索引" value={index.data.missing_count} />
          <IndexMetric label="等待更新" value={index.data.stale_count} />
          <div>
            <p className="component-label">模型与维度</p>
            <p className="mt-2 break-all font-mono text-[11px] text-ink">
              {index.data.embedding_model}@{index.data.embedding_dimensions}
            </p>
          </div>
        </div>
      ) : null}

      {latestJob ? (
        <div className="mt-5 flex flex-col justify-between gap-3 border border-slate/25 bg-canvas p-4 text-xs sm:flex-row sm:items-center">
          <div>
            <p className="component-label">最近任务</p>
            <p className="mt-2 text-slate/65">
              {formatDateTime(latestJob.created_at)} · 已生成 {latestJob.embedded_count} · Batch{" "}
              {latestJob.batch_count}
            </p>
            {latestJob.error_code ? (
              <p className="mt-2 font-mono text-[11px] text-wine">{latestJob.error_code}</p>
            ) : null}
          </div>
          <StatusPill tone={statusTone(latestJob.status)}>{humanize(latestJob.status)}</StatusPill>
        </div>
      ) : null}

      <ConfirmDialog
        confirmLabel={start.isPending ? "正在创建任务…" : "开始更新"}
        description={`将调用当前 Embedding Provider，为 ${pendingCount} 个未索引或等待更新的 Tool 生成向量。已是最新状态的 Tool 不会重复生成。`}
        onConfirm={() => {
          void start
            .mutateAsync({ force: false, batch_size: 16 })
            .then(() => setConfirmOpen(false));
        }}
        onOpenChange={setConfirmOpen}
        open={confirmOpen}
        title={`更新 ${pendingCount} 个 Tool 的检索索引？`}
      />
    </article>
  );
}

function IndexMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="component-label">{label}</p>
      <p className="mt-2 text-2xl font-light text-ink">{value}</p>
    </div>
  );
}
