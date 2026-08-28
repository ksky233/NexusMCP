import { RefreshCw } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableFrame,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/data-table";
import { FieldLabel, Input, Select } from "@/components/ui/form-controls";
import { Pagination } from "@/components/ui/pagination";
import { StatusPill } from "@/components/ui/status-pill";
import { useAuditEvents, useExecutions } from "@/features/executions/hooks/use-executions";
import type { AuditOutcome, ExecutionStatus } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

const PAGE_SIZE = 10;

export function ExecutionsPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "audit" ? "audit" : "executions";
  const page = positiveInteger(params.get("page"));
  const principalId = params.get("principal_id")?.trim() || undefined;
  const traceId = params.get("trace_id")?.trim() || undefined;
  const executionStatus = (params.get("status") || undefined) as ExecutionStatus | undefined;
  const outcome = (params.get("outcome") || undefined) as AuditOutcome | undefined;
  const executions = useExecutions({
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    status: executionStatus,
    principal_id: principalId,
    trace_id: traceId,
  });
  const audits = useAuditEvents({
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    outcome,
    principal_id: principalId,
    trace_id: traceId,
  });
  const activeQuery = view === "audit" ? audits : executions;

  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    setParams(next);
  }
  function changeView(nextView: "executions" | "audit") {
    const next = new URLSearchParams();
    if (nextView === "audit") next.set("view", "audit");
    setParams(next);
  }

  return (
    <section className="page-enter">
      <PageHeader
        eyebrow="Operations"
        title="Executions & Audit"
        description="Trace governed tool calls, retry attempts and append-only decisions without exposing payloads."
        actions={
          <Button onClick={() => void activeQuery.refetch()} size="small" variant="secondary">
            <RefreshCw className="size-3.5" /> Refresh
          </Button>
        }
      />
      <div className="mb-5 flex gap-6 border-b border-slate/15">
        <button
          className={
            view === "executions"
              ? "border-b border-ink px-1 pb-3 text-sm text-ink"
              : "px-1 pb-3 text-sm text-slate/55"
          }
          onClick={() => changeView("executions")}
          type="button"
        >
          Executions
        </button>
        <button
          className={
            view === "audit"
              ? "border-b border-ink px-1 pb-3 text-sm text-ink"
              : "px-1 pb-3 text-sm text-slate/55"
          }
          onClick={() => changeView("audit")}
          type="button"
        >
          Audit events
        </button>
      </div>
      <div className="mb-5 grid gap-4 border border-slate/18 bg-paper p-4 sm:grid-cols-2 xl:grid-cols-3">
        <div>
          <FieldLabel htmlFor="execution-principal">Principal</FieldLabel>
          <Input
            id="execution-principal"
            defaultValue={principalId}
            key={principalId ?? "all"}
            onBlur={(event) => update("principal_id", event.currentTarget.value.trim())}
            onKeyDown={(event) =>
              event.key === "Enter" && update("principal_id", event.currentTarget.value.trim())
            }
            placeholder="All principals"
          />
        </div>
        <div>
          <FieldLabel htmlFor="execution-trace">Trace ID</FieldLabel>
          <Input
            id="execution-trace"
            defaultValue={traceId}
            key={traceId ?? "all"}
            onBlur={(event) => update("trace_id", event.currentTarget.value.trim())}
            onKeyDown={(event) =>
              event.key === "Enter" && update("trace_id", event.currentTarget.value.trim())
            }
            placeholder="All traces"
          />
        </div>
        {view === "executions" ? (
          <div>
            <FieldLabel htmlFor="execution-status">Status</FieldLabel>
            <Select
              id="execution-status"
              onChange={(event) => update("status", event.currentTarget.value)}
              value={executionStatus ?? ""}
            >
              <option value="">All statuses</option>
              <option value="planned">Planned</option>
              <option value="running">Running</option>
              <option value="succeeded">Succeeded</option>
              <option value="failed">Failed</option>
              <option value="unknown">Unknown</option>
              <option value="cancelled">Cancelled</option>
            </Select>
          </div>
        ) : (
          <div>
            <FieldLabel htmlFor="audit-outcome">Outcome</FieldLabel>
            <Select
              id="audit-outcome"
              onChange={(event) => update("outcome", event.currentTarget.value)}
              value={outcome ?? ""}
            >
              <option value="">All outcomes</option>
              <option value="allowed">Allowed</option>
              <option value="denied">Denied</option>
              <option value="approval_required">Approval required</option>
              <option value="succeeded">Succeeded</option>
              <option value="failed">Failed</option>
              <option value="unknown">Unknown</option>
              <option value="cancelled">Cancelled</option>
            </Select>
          </div>
        )}
      </div>
      {activeQuery.isPending ? <LoadingState label={`Loading ${view}…`} /> : null}
      {activeQuery.isError ? (
        <ErrorState error={activeQuery.error} onRetry={() => void activeQuery.refetch()} />
      ) : null}
      {view === "executions" && executions.data ? (
        <ExecutionTable data={executions.data} page={page} params={params} setParams={setParams} />
      ) : null}
      {view === "audit" && audits.data ? (
        <AuditTable data={audits.data} page={page} params={params} setParams={setParams} />
      ) : null}
    </section>
  );
}

function ExecutionTable({
  data,
  page,
  params,
  setParams,
}: {
  data: Awaited<ReturnType<typeof import("@/features/executions/api/executions").fetchExecutions>>;
  page: number;
  params: URLSearchParams;
  setParams: (params: URLSearchParams) => void;
}) {
  if (!data.items.length)
    return (
      <EmptyState
        title="No executions found"
        description="No governed calls match the current filters."
      />
    );
  return (
    <>
      <TableFrame>
        <Table>
          <TableHead>
            <tr>
              <TableHeaderCell>Tool / Principal</TableHeaderCell>
              <TableHeaderCell>Started</TableHeaderCell>
              <TableHeaderCell>Attempts</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
            </tr>
          </TableHead>
          <TableBody>
            {data.items.map((execution) => (
              <TableRow key={execution.id}>
                <TableCell>
                  <Link
                    className="text-ink underline-offset-4 hover:underline"
                    to={`/executions/${execution.id}`}
                  >
                    {execution.canonical_name}
                  </Link>
                  <span className="mt-1 block text-xs text-slate/50">{execution.principal_id}</span>
                </TableCell>
                <TableCell>
                  {formatDateTime(execution.started_at ?? execution.planned_at)}
                  <span className="mt-1 block font-mono text-[11px] text-slate/45">
                    {execution.trace_id}
                  </span>
                </TableCell>
                <TableCell>
                  {execution.attempt_count}
                  <span className="mt-1 block text-xs text-slate/50">
                    {humanize(execution.side_effect)}
                  </span>
                </TableCell>
                <TableCell>
                  <StatusPill tone={statusTone(execution.status)}>
                    {humanize(execution.status)}
                  </StatusPill>
                  {execution.error_code ? (
                    <span className="mt-2 block text-xs text-wine">{execution.error_code}</span>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableFrame>
      <PageFooter
        count={data.page.total}
        label="executions"
        page={page}
        params={params}
        setParams={setParams}
      />
    </>
  );
}

function AuditTable({
  data,
  page,
  params,
  setParams,
}: {
  data: Awaited<ReturnType<typeof import("@/features/executions/api/executions").fetchAudits>>;
  page: number;
  params: URLSearchParams;
  setParams: (params: URLSearchParams) => void;
}) {
  if (!data.items.length)
    return (
      <EmptyState
        title="No audit events found"
        description="No append-only events match the current filters."
      />
    );
  return (
    <>
      <TableFrame>
        <Table>
          <TableHead>
            <tr>
              <TableHeaderCell>Action / Actor</TableHeaderCell>
              <TableHeaderCell>Resource</TableHeaderCell>
              <TableHeaderCell>Trace</TableHeaderCell>
              <TableHeaderCell>Outcome</TableHeaderCell>
            </tr>
          </TableHead>
          <TableBody>
            {data.items.map((event) => (
              <TableRow key={event.id}>
                <TableCell>
                  <span className="text-ink">{humanize(event.action)}</span>
                  <span className="mt-1 block text-xs text-slate/50">{event.actor_id}</span>
                </TableCell>
                <TableCell>
                  <span>{event.resource_type}</span>
                  <span className="mt-1 block font-mono text-[11px] text-slate/45">
                    {event.resource_id}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="block font-mono text-[11px]">{event.trace_id}</span>
                  <span className="mt-1 block text-xs text-slate/50">
                    {formatDateTime(event.occurred_at)}
                  </span>
                </TableCell>
                <TableCell>
                  <StatusPill tone={statusTone(event.outcome)}>
                    {humanize(event.outcome)}
                  </StatusPill>
                  {event.reason_code ? (
                    <span className="mt-2 block text-xs text-slate/50">{event.reason_code}</span>
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableFrame>
      <PageFooter
        count={data.page.total}
        label="events"
        page={page}
        params={params}
        setParams={setParams}
      />
    </>
  );
}

function PageFooter({
  count,
  label,
  page,
  params,
  setParams,
}: {
  count: number;
  label: string;
  page: number;
  params: URLSearchParams;
  setParams: (params: URLSearchParams) => void;
}) {
  return (
    <div className="mt-5 flex items-center justify-between gap-4">
      <span className="text-xs text-slate/50">
        {count} {label}
      </span>
      <Pagination
        page={page}
        totalPages={Math.ceil(count / PAGE_SIZE)}
        onPageChange={(nextPage) => {
          const next = new URLSearchParams(params);
          if (nextPage === 1) next.delete("page");
          else next.set("page", String(nextPage));
          setParams(next);
        }}
      />
    </div>
  );
}
function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
