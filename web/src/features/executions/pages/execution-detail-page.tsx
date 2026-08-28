import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState, LoadingState } from "@/components/common/query-state";
import { StatusPill } from "@/components/ui/status-pill";
import {
  useAuditEvents,
  useExecution,
  useExecutionAttempts,
} from "@/features/executions/hooks/use-executions";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function ExecutionDetailPage() {
  const id = useParams().executionId ?? "";
  const execution = useExecution(id);
  const attempts = useExecutionAttempts(id);
  const audits = useAuditEvents({ offset: 0, limit: 100, execution_id: id });
  if (execution.isPending || attempts.isPending || audits.isPending)
    return <LoadingState label="Loading execution evidence…" />;
  if (execution.isError)
    return <ErrorState error={execution.error} onRetry={() => void execution.refetch()} />;
  if (attempts.isError)
    return <ErrorState error={attempts.error} onRetry={() => void attempts.refetch()} />;
  if (audits.isError)
    return <ErrorState error={audits.error} onRetry={() => void audits.refetch()} />;
  const data = execution.data;
  return (
    <section className="page-enter">
      <Link
        className="mb-7 inline-flex items-center gap-2 text-xs text-slate/60 hover:text-ink"
        to="/executions"
      >
        <ArrowLeft className="size-3.5" /> Back to executions
      </Link>
      <PageHeader
        eyebrow="Execution evidence"
        title={data.canonical_name}
        description={`Principal ${data.principal_id} · ${humanize(data.side_effect)}`}
        actions={<StatusPill tone={statusTone(data.status)}>{humanize(data.status)}</StatusPill>}
      />
      <article className="panel p-6 sm:p-7">
        <p className="component-label">Decision and trace</p>
        <dl className="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <Definition label="Execution ID" value={data.id} mono />
          <Definition label="Request ID" value={data.request_id} mono />
          <Definition label="Trace ID" value={data.trace_id} mono />
          <Definition
            label="Policy"
            value={`${data.policy_version} · ${data.policy_reason_code}`}
          />
          <Definition label="Planned" value={formatDateTime(data.planned_at)} />
          <Definition label="Started" value={formatDateTime(data.started_at)} />
          <Definition label="Finished" value={formatDateTime(data.finished_at)} />
          <Definition
            label="Idempotency"
            value={data.has_idempotency_key ? "Key present (redacted)" : "Not supplied"}
          />
        </dl>
        {data.error_code ? (
          <p className="mt-5 border border-wine/35 bg-wine/6 p-4 text-sm text-wine">
            {data.error_code} · {data.error_category}
          </p>
        ) : null}
      </article>
      <h2 className="mt-9 text-xl font-light text-ink">Attempt timeline</h2>
      <div className="mt-4 space-y-3">
        {attempts.data.items.map((attempt) => (
          <article
            className="panel flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center"
            key={attempt.id}
          >
            <div>
              <p className="component-label">Attempt {attempt.attempt_number}</p>
              <p className="mt-2 text-sm text-slate">
                {formatDateTime(attempt.started_at)} → {formatDateTime(attempt.finished_at)}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate/50">HTTP {attempt.upstream_status ?? "—"}</span>
              <StatusPill tone={statusTone(attempt.status)}>{humanize(attempt.status)}</StatusPill>
            </div>
          </article>
        ))}
      </div>
      <h2 className="mt-9 text-xl font-light text-ink">Audit timeline</h2>
      <div className="mt-4 space-y-3">
        {audits.data.items.map((event) => (
          <article className="panel p-5" key={event.id}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="component-label">
                  {humanize(event.action)} · {event.actor_id}
                </p>
                <p className="mt-2 text-sm text-slate">{event.reason_code ?? "No reason code"}</p>
              </div>
              <StatusPill tone={statusTone(event.outcome)}>{humanize(event.outcome)}</StatusPill>
            </div>
            <p className="mt-3 font-mono text-[11px] text-slate/50">
              {formatDateTime(event.occurred_at)} · {event.request_id}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Definition({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-[0.14em] text-slate/45">{label}</dt>
      <dd
        className={
          mono ? "mt-2 break-all font-mono text-[11px] text-slate" : "mt-2 text-sm text-slate"
        }
      >
        {value}
      </dd>
    </div>
  );
}
