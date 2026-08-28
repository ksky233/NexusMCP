import { Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { EmptyState, ErrorState, LoadingState } from "@/components/common/query-state";
import { PageHeader } from "@/components/common/page-header";
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
import { useRegisterUpstream, useUpstreams } from "@/features/upstreams/hooks/use-upstreams";
import { UpstreamForm } from "@/features/upstreams/parts/upstream-form";
import type { RegisterUpstreamRequest, UpstreamStatus } from "@/generated/api/types.gen";
import { humanize, statusTone } from "@/lib/display";

const PAGE_SIZE = 10;
const upstreamStatuses = new Set<UpstreamStatus>(["draft", "active", "disabled"]);

export function UpstreamsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [registering, setRegistering] = useState(false);
  const navigate = useNavigate();
  const page = positiveInteger(searchParams.get("page"));
  const namespace = searchParams.get("namespace")?.trim() || undefined;
  const statusValue = searchParams.get("status") as UpstreamStatus | null;
  const status = statusValue && upstreamStatuses.has(statusValue) ? statusValue : undefined;
  const upstreams = useUpstreams({
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    namespace,
    status,
  });
  const registration = useRegisterUpstream();

  async function submitRegistration(body: RegisterUpstreamRequest) {
    const created = await registration.mutateAsync(body);
    setRegistering(false);
    await navigate(`/upstreams/${created.id}`);
  }

  function updateFilter(name: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    setSearchParams(next);
  }

  return (
    <section className="page-enter">
      <PageHeader
        actions={
          <>
            <Button onClick={() => void upstreams.refetch()} size="small" variant="secondary">
              <RefreshCw aria-hidden="true" className="size-3.5 stroke-[1.5]" /> Refresh
            </Button>
            <Button onClick={() => setRegistering((current) => !current)} size="small">
              <Plus aria-hidden="true" className="size-3.5 stroke-[1.5]" /> Register upstream
            </Button>
          </>
        }
        description="Register and govern HTTP/OpenAPI systems before they can produce MCP tools."
        eyebrow="Registry"
        title="Upstreams"
      />

      {registering ? (
        <div className="mb-6">
          <UpstreamForm
            error={registration.error}
            mode="register"
            onCancel={() => setRegistering(false)}
            onSubmit={(body) => submitRegistration(body as RegisterUpstreamRequest)}
            pending={registration.isPending}
          />
        </div>
      ) : null}

      <div className="mb-5 grid gap-4 border border-slate/18 bg-paper p-4 sm:grid-cols-2 lg:max-w-2xl">
        <div>
          <FieldLabel htmlFor="upstream-namespace-filter">Namespace</FieldLabel>
          <Input
            defaultValue={namespace}
            id="upstream-namespace-filter"
            key={namespace ?? "all"}
            onBlur={(event) => updateFilter("namespace", event.currentTarget.value.trim())}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                updateFilter("namespace", event.currentTarget.value.trim());
              }
            }}
            placeholder="All namespaces"
          />
        </div>
        <div>
          <FieldLabel htmlFor="upstream-status-filter">Status</FieldLabel>
          <Select
            id="upstream-status-filter"
            onChange={(event) => updateFilter("status", event.currentTarget.value)}
            value={status ?? ""}
          >
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </Select>
        </div>
      </div>

      {upstreams.isPending ? <LoadingState label="Loading upstream registry…" /> : null}
      {upstreams.isError ? (
        <ErrorState error={upstreams.error} onRetry={() => void upstreams.refetch()} />
      ) : null}
      {upstreams.data?.items.length === 0 ? (
        <EmptyState
          description="Register an HTTP/OpenAPI upstream or clear the current filters."
          title="No upstreams found"
        />
      ) : null}
      {upstreams.data && upstreams.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Upstream</TableHeaderCell>
                  <TableHeaderCell>Owner</TableHeaderCell>
                  <TableHeaderCell>Endpoint</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {upstreams.data.items.map((upstream) => (
                  <TableRow key={upstream.id}>
                    <TableCell>
                      <Link
                        className="font-normal text-ink underline-offset-4 hover:underline"
                        to={`/upstreams/${upstream.id}`}
                      >
                        {upstream.namespace}.{upstream.name}
                      </Link>
                      <span className="mt-1 block text-xs text-slate/50">
                        {upstream.service_type.toUpperCase()}
                      </span>
                    </TableCell>
                    <TableCell>{upstream.owner}</TableCell>
                    <TableCell className="max-w-xs truncate font-mono text-xs">
                      {upstream.endpoint}
                    </TableCell>
                    <TableCell>
                      <StatusPill tone={statusTone(upstream.status)}>
                        {humanize(upstream.status)}
                      </StatusPill>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
            <span className="text-xs text-slate/50">{upstreams.data.page.total} upstreams</span>
            <Pagination
              onPageChange={(nextPage) => {
                const next = new URLSearchParams(searchParams);
                if (nextPage === 1) next.delete("page");
                else next.set("page", String(nextPage));
                setSearchParams(next);
              }}
              page={page}
              totalPages={Math.ceil(upstreams.data.page.total / PAGE_SIZE)}
            />
          </div>
        </>
      ) : null}
    </section>
  );
}

function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
