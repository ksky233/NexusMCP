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
import { useSearchIndexStatus } from "@/features/catalog/hooks/use-search-index";
import { SearchIndexPanel } from "@/features/catalog/parts/search-index-panel";
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
  const searchIndex = useSearchIndexStatus();
  const indexByVersion = new Map(
    searchIndex.data?.items.map((item) => [item.tool_version_id, item]) ?? [],
  );

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
            <RefreshCw aria-hidden="true" className="size-3.5" /> 刷新
          </Button>
        }
        description="查看稳定 Tool Identity、版本化 Contract、可见范围与执行 Binding。"
        eyebrow="Catalog · 工具治理"
        title="工具目录"
      />

      <SearchIndexPanel />

      <div className="mb-5 grid gap-4 rounded-[10px] border border-slate/42 bg-paper p-4 sm:grid-cols-2 xl:grid-cols-5">
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
            placeholder="全部"
          />
        </div>
        <Filter
          id="catalog-status"
          label="Tool 状态"
          onChange={(value) => update("status", value)}
          value={status}
        >
          <option value="active">已启用</option>
          <option value="disabled">已停用</option>
        </Filter>
        <Filter
          id="catalog-version"
          label="版本状态"
          onChange={(value) => update("version_status", value)}
          value={versionStatus}
        >
          <option value="draft">草稿</option>
          <option value="review">审核中</option>
          <option value="published">已发布</option>
          <option value="retired">已退役</option>
        </Filter>
        <Filter
          id="catalog-visibility"
          label="可见范围"
          onChange={(value) => update("visibility", value)}
          value={visibility}
        >
          <option value="public">公开</option>
          <option value="authenticated">需认证</option>
          <option value="restricted">受限</option>
        </Filter>
        <Filter
          id="catalog-side-effect"
          label="副作用"
          onChange={(value) => update("side_effect", value)}
          value={sideEffect}
        >
          <option value="read_only">只读</option>
          <option value="idempotent_write">幂等写</option>
          <option value="non_idempotent_write">非幂等写</option>
          <option value="unknown">未知</option>
        </Filter>
      </div>

      {tools.isPending ? <LoadingState label="正在加载工具目录…" /> : null}
      {tools.isError ? (
        <ErrorState error={tools.error} onRetry={() => void tools.refetch()} />
      ) : null}
      {tools.data?.items.length === 0 ? (
        <EmptyState
          title="未找到 Tool"
          description="请发布一个审核通过的 Operation，或清除当前筛选条件。"
        />
      ) : null}
      {tools.data && tools.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Tool</TableHeaderCell>
                  <TableHeaderCell>负责人</TableHeaderCell>
                  <TableHeaderCell>版本</TableHeaderCell>
                  <TableHeaderCell>Contract</TableHeaderCell>
                  <TableHeaderCell>检索索引</TableHeaderCell>
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
                    <TableCell>
                      {indexByVersion.has(tool.latest_version_id) ? (
                        <>
                          <StatusPill
                            tone={indexTone(indexByVersion.get(tool.latest_version_id)?.state)}
                          >
                            {humanize(
                              indexByVersion.get(tool.latest_version_id)?.state ?? "missing",
                            )}
                          </StatusPill>
                          {indexByVersion.get(tool.latest_version_id)?.indexed_at ? (
                            <span className="mt-2 block text-xs text-slate/50">
                              {new Intl.DateTimeFormat("zh-CN", {
                                dateStyle: "short",
                                timeStyle: "short",
                              }).format(
                                new Date(
                                  indexByVersion.get(tool.latest_version_id)?.indexed_at ?? "",
                                ),
                              )}
                            </span>
                          ) : null}
                        </>
                      ) : (
                        <span className="text-xs text-slate/45">不适用</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          <div className="mt-5 flex items-center justify-between gap-4">
            <span className="text-xs text-slate/50">共 {tools.data.page.total} 个 Tool</span>
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

function indexTone(state: string | undefined) {
  if (state === "current") return "completed" as const;
  if (state === "stale") return "review" as const;
  return "pending" as const;
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
        <option value="">全部</option>
        {children}
      </Select>
    </div>
  );
}

function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
