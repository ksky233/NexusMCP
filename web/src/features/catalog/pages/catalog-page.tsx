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
import { useTools } from "@/features/catalog/hooks/use-catalog";
import type {
  ToolSideEffect,
  ToolStatus,
  ToolVersionStatus,
  ToolVisibility,
} from "@/generated/api/types.gen";
import { humanize, statusTone } from "@/lib/display";

const PAGE_SIZE = 10;

export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const page = positiveInteger(params.get("page"));
  const namespace = params.get("namespace")?.trim() || undefined;
  const status = (params.get("status") || undefined) as ToolStatus | undefined;
  const versionStatus = (params.get("version_status") || undefined) as
    | ToolVersionStatus
    | undefined;
  const visibility = (params.get("visibility") || undefined) as ToolVisibility | undefined;
  const sideEffect = (params.get("side_effect") || undefined) as ToolSideEffect | undefined;
  const tools = useTools({
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    namespace,
    status,
    version_status: versionStatus,
    visibility,
    side_effect: sideEffect,
  });

  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    setParams(next);
  }

  return (
    <section className="page-enter">
      <PageHeader
        actions={
          <Button onClick={() => void tools.refetch()} size="small" variant="secondary">
            <RefreshCw aria-hidden="true" className="size-3.5" /> Refresh
          </Button>
        }
        description="Inspect stable Tool identities, versioned contracts, visibility and execution bindings."
        eyebrow="Catalog"
        title="Tool Catalog"
      />

      <div className="mb-5 grid gap-4 border border-slate/18 bg-paper p-4 sm:grid-cols-2 xl:grid-cols-5">
        <div>
          <FieldLabel htmlFor="catalog-namespace">Namespace</FieldLabel>
          <Input
            defaultValue={namespace}
            id="catalog-namespace"
            key={namespace ?? "all"}
            onBlur={(event) => update("namespace", event.currentTarget.value.trim())}
            onKeyDown={(event) =>
              event.key === "Enter" && update("namespace", event.currentTarget.value.trim())
            }
            placeholder="All"
          />
        </div>
        <Filter
          id="catalog-status"
          label="Tool status"
          onChange={(value) => update("status", value)}
          value={status}
        >
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </Filter>
        <Filter
          id="catalog-version"
          label="Version status"
          onChange={(value) => update("version_status", value)}
          value={versionStatus}
        >
          <option value="draft">Draft</option>
          <option value="review">Review</option>
          <option value="published">Published</option>
          <option value="retired">Retired</option>
        </Filter>
        <Filter
          id="catalog-visibility"
          label="Visibility"
          onChange={(value) => update("visibility", value)}
          value={visibility}
        >
          <option value="public">Public</option>
          <option value="authenticated">Authenticated</option>
          <option value="restricted">Restricted</option>
        </Filter>
        <Filter
          id="catalog-side-effect"
          label="Side effect"
          onChange={(value) => update("side_effect", value)}
          value={sideEffect}
        >
          <option value="read_only">Read only</option>
          <option value="idempotent_write">Idempotent write</option>
          <option value="non_idempotent_write">Non-idempotent write</option>
          <option value="unknown">Unknown</option>
        </Filter>
      </div>

      {tools.isPending ? <LoadingState label="Loading tool catalog…" /> : null}
      {tools.isError ? (
        <ErrorState error={tools.error} onRetry={() => void tools.refetch()} />
      ) : null}
      {tools.data?.items.length === 0 ? (
        <EmptyState
          title="No tools found"
          description="Publish a reviewed operation or clear the catalog filters."
        />
      ) : null}
      {tools.data && tools.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Tool</TableHeaderCell>
                  <TableHeaderCell>Owner</TableHeaderCell>
                  <TableHeaderCell>Version</TableHeaderCell>
                  <TableHeaderCell>Contract</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {tools.data.items.map((tool) => (
                  <TableRow key={tool.id}>
                    <TableCell>
                      <Link
                        className="text-ink underline-offset-4 hover:underline"
                        to={`/catalog/${tool.id}`}
                      >
                        {tool.canonical_name}
                      </Link>
                      <span className="mt-1 block text-xs text-slate/50">{tool.description}</span>
                    </TableCell>
                    <TableCell>{tool.owner}</TableCell>
                    <TableCell>
                      v{tool.latest_version}
                      <span className="mt-1 block">
                        <StatusPill tone={statusTone(tool.version_status)}>
                          {humanize(tool.version_status)}
                        </StatusPill>
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="block">{humanize(tool.visibility)}</span>
                      <span className="mt-1 block text-xs text-slate/50">
                        {humanize(tool.side_effect)}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          <div className="mt-5 flex items-center justify-between gap-4">
            <span className="text-xs text-slate/50">{tools.data.page.total} tools</span>
            <Pagination
              page={page}
              totalPages={Math.ceil(tools.data.page.total / PAGE_SIZE)}
              onPageChange={(nextPage) => {
                const next = new URLSearchParams(params);
                if (nextPage === 1) next.delete("page");
                else next.set("page", String(nextPage));
                setParams(next);
              }}
            />
          </div>
        </>
      ) : null}
    </section>
  );
}

function Filter({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value?: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select id={id} onChange={(event) => onChange(event.currentTarget.value)} value={value ?? ""}>
        <option value="">All</option>
        {children}
      </Select>
    </div>
  );
}

function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
