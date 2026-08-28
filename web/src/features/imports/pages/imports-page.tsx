import { Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, InlineError, LoadingState } from "@/components/common/query-state";
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
import { useImports, useStartImport } from "@/features/imports/hooks/use-imports";
import { useUpstreams } from "@/features/upstreams/hooks/use-upstreams";
import type { ImportJobStatus } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

const PAGE_SIZE = 10;

export function ImportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [upstreamId, setUpstreamId] = useState("");
  const [sourceRef, setSourceRef] = useState("employee_directory/openapi.json");
  const [allowlist, setAllowlist] = useState("");
  const navigate = useNavigate();
  const page = positiveInteger(searchParams.get("page"));
  const status = (searchParams.get("status") || undefined) as ImportJobStatus | undefined;
  const imports = useImports({ offset: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE, status });
  const upstreams = useUpstreams({ offset: 0, limit: 100, status: "active" });
  const start = useStartImport();

  async function submitImport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await start.mutateAsync({
      upstream_service_id: upstreamId,
      source_ref: sourceRef.trim(),
      operation_allowlist: allowlist
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
    setCreating(false);
    await navigate(`/imports/${created.import_job_id}`);
  }

  return (
    <section className="page-enter">
      <PageHeader
        actions={
          <>
            <Button onClick={() => void imports.refetch()} size="small" variant="secondary">
              <RefreshCw aria-hidden="true" className="size-3.5" /> Refresh
            </Button>
            <Button onClick={() => setCreating((value) => !value)} size="small">
              <Plus aria-hidden="true" className="size-3.5" /> New import
            </Button>
          </>
        }
        description="Validate OpenAPI documents, inspect generated operations and move reviewed tools toward publication."
        eyebrow="OpenAPI"
        title="Imports & Review"
      />

      {creating ? (
        <form className="panel mb-6 p-6 sm:p-7" onSubmit={(event) => void submitImport(event)}>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <FieldLabel htmlFor="import-upstream">Active upstream</FieldLabel>
              <Select
                id="import-upstream"
                onChange={(event) => setUpstreamId(event.currentTarget.value)}
                required
                value={upstreamId}
              >
                <option value="">Select an upstream</option>
                {upstreams.data?.items.map((upstream) => (
                  <option key={upstream.id} value={upstream.id}>
                    {upstream.namespace}.{upstream.name}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <FieldLabel htmlFor="import-source">Fixture source</FieldLabel>
              <Input
                id="import-source"
                onChange={(event) => setSourceRef(event.currentTarget.value)}
                required
                value={sourceRef}
              />
            </div>
            <div className="sm:col-span-2">
              <FieldLabel htmlFor="import-allowlist">Operation allowlist</FieldLabel>
              <Input
                id="import-allowlist"
                onChange={(event) => setAllowlist(event.currentTarget.value)}
                placeholder="getEmployee, listEmployees (optional)"
                value={allowlist}
              />
            </div>
          </div>
          {start.error ? (
            <div className="mt-5">
              <InlineError error={start.error} />
            </div>
          ) : null}
          <div className="mt-7 flex justify-end gap-3 border-t border-slate/15 pt-5">
            <Button onClick={() => setCreating(false)} type="button" variant="secondary">
              Cancel
            </Button>
            <Button disabled={start.isPending || !upstreamId || !sourceRef.trim()} type="submit">
              {start.isPending ? "Importing…" : "Submit import"}
            </Button>
          </div>
        </form>
      ) : null}

      <div className="mb-5 max-w-xs">
        <FieldLabel htmlFor="import-status">Status</FieldLabel>
        <Select
          id="import-status"
          onChange={(event) => {
            const next = new URLSearchParams(searchParams);
            if (event.currentTarget.value) next.set("status", event.currentTarget.value);
            else next.delete("status");
            next.delete("page");
            setSearchParams(next);
          }}
          value={status ?? ""}
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="validating">Validating</option>
          <option value="parsing">Parsing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </Select>
      </div>

      {imports.isPending ? <LoadingState label="Loading OpenAPI imports…" /> : null}
      {imports.isError ? (
        <ErrorState error={imports.error} onRetry={() => void imports.refetch()} />
      ) : null}
      {imports.data?.items.length === 0 ? (
        <EmptyState
          description="Submit an OpenAPI fixture or clear the current status filter."
          title="No imports found"
        />
      ) : null}
      {imports.data && imports.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Source</TableHeaderCell>
                  <TableHeaderCell>Upstream</TableHeaderCell>
                  <TableHeaderCell>Created</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {imports.data.items.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>
                      <Link
                        className="text-ink underline-offset-4 hover:underline"
                        to={`/imports/${job.id}`}
                      >
                        {job.source_ref}
                      </Link>
                      <span className="mt-1 block font-mono text-[11px] text-slate/45">
                        {job.source_digest.slice(0, 12)}…
                      </span>
                    </TableCell>
                    <TableCell>{job.upstream_name}</TableCell>
                    <TableCell>{formatDateTime(job.created_at)}</TableCell>
                    <TableCell>
                      <StatusPill tone={statusTone(job.status)}>{humanize(job.status)}</StatusPill>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          <div className="mt-5 flex items-center justify-between gap-4">
            <span className="text-xs text-slate/50">{imports.data.page.total} imports</span>
            <Pagination
              onPageChange={(nextPage) => {
                const next = new URLSearchParams(searchParams);
                if (nextPage === 1) next.delete("page");
                else next.set("page", String(nextPage));
                setSearchParams(next);
              }}
              page={page}
              totalPages={Math.ceil(imports.data.page.total / PAGE_SIZE)}
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
