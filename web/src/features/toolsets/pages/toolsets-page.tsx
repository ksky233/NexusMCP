import { Clipboard, Plus, RefreshCw } from "lucide-react";
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
import { FieldLabel, Input, Select, Textarea } from "@/components/ui/form-controls";
import { Pagination } from "@/components/ui/pagination";
import { StatusPill } from "@/components/ui/status-pill";
import { useCreateToolset, useToolsets } from "@/features/toolsets/hooks/use-toolsets";
import type { ToolsetDiscoveryMode, ToolsetKind, ToolsetStatus } from "@/generated/api/types.gen";
import { humanize, statusTone } from "@/lib/display";

const PAGE_SIZE = 10;
const statuses = new Set<ToolsetStatus>(["draft", "active", "disabled"]);
const kinds = new Set<ToolsetKind>(["explicit", "all_published"]);
const discoveryModes = new Set<ToolsetDiscoveryMode>(["direct", "search_first"]);

export function ToolsetsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const page = positiveInteger(searchParams.get("page"));
  const q = searchParams.get("q")?.trim() || undefined;
  const candidateStatus = searchParams.get("status") as ToolsetStatus | null;
  const status = candidateStatus && statuses.has(candidateStatus) ? candidateStatus : undefined;
  const candidateKind = searchParams.get("kind") as ToolsetKind | null;
  const kind = candidateKind && kinds.has(candidateKind) ? candidateKind : undefined;
  const candidateMode = searchParams.get("discovery_mode") as ToolsetDiscoveryMode | null;
  const discoveryMode =
    candidateMode && discoveryModes.has(candidateMode) ? candidateMode : undefined;
  const toolsets = useToolsets({
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    q,
    status,
    kind,
    discovery_mode: discoveryMode,
  });

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
            <Button onClick={() => void toolsets.refetch()} size="small" variant="secondary">
              <RefreshCw className="size-3.5" /> 刷新
            </Button>
            <Button onClick={() => setCreating((value) => !value)} size="small">
              <Plus className="size-3.5" /> 创建工具集
            </Button>
          </>
        }
        description="把已发布 Tool 组合成面向 Agent Service 的稳定 MCP Endpoint。"
        eyebrow="Gateway · Toolset"
        title="工具集"
      />

      {creating ? <CreateToolsetPanel onClose={() => setCreating(false)} /> : null}

      <div className="mb-5 grid gap-4 rounded-[10px] border border-slate/42 bg-paper p-4 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <FieldLabel htmlFor="toolset-search">名称或 Slug</FieldLabel>
          <Input
            defaultValue={q}
            id="toolset-search"
            key={q ?? "all"}
            onBlur={(event) => updateFilter("q", event.currentTarget.value.trim())}
            onKeyDown={(event) => {
              if (event.key === "Enter") updateFilter("q", event.currentTarget.value.trim());
            }}
            placeholder="搜索工具集"
          />
        </div>
        <div>
          <FieldLabel htmlFor="toolset-status">状态</FieldLabel>
          <Select
            id="toolset-status"
            onChange={(event) => updateFilter("status", event.currentTarget.value)}
            value={status ?? ""}
          >
            <option value="">全部状态</option>
            <option value="draft">草稿</option>
            <option value="active">已启用</option>
            <option value="disabled">已停用</option>
          </Select>
        </div>
        <div>
          <FieldLabel htmlFor="toolset-kind">类型</FieldLabel>
          <Select
            id="toolset-kind"
            onChange={(event) => updateFilter("kind", event.currentTarget.value)}
            value={kind ?? ""}
          >
            <option value="">全部类型</option>
            <option value="explicit">显式工具集</option>
            <option value="all_published">全部已发布工具</option>
          </Select>
        </div>
        <div>
          <FieldLabel htmlFor="toolset-mode-filter">发现模式</FieldLabel>
          <Select
            id="toolset-mode-filter"
            onChange={(event) => updateFilter("discovery_mode", event.currentTarget.value)}
            value={discoveryMode ?? ""}
          >
            <option value="">全部模式</option>
            <option value="direct">Direct</option>
            <option value="search_first">Search First</option>
          </Select>
        </div>
      </div>

      {toolsets.isPending ? <LoadingState label="正在加载工具集…" /> : null}
      {toolsets.isError ? (
        <ErrorState error={toolsets.error} onRetry={() => void toolsets.refetch()} />
      ) : null}
      {toolsets.data?.items.length === 0 ? (
        <EmptyState description="创建一个业务工具集，或清除当前筛选条件。" title="未找到工具集" />
      ) : null}
      {toolsets.data && toolsets.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>工具集</TableHeaderCell>
                  <TableHeaderCell>状态 / 健康度</TableHeaderCell>
                  <TableHeaderCell>发现模式</TableHeaderCell>
                  <TableHeaderCell>Tool / Grant</TableHeaderCell>
                  <TableHeaderCell>Revision</TableHeaderCell>
                  <TableHeaderCell>Endpoint</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {toolsets.data.items.map((toolset) => (
                  <TableRow key={toolset.id}>
                    <TableCell>
                      <Link
                        className="text-ink underline-offset-4 hover:underline"
                        to={`/toolsets/${toolset.id}`}
                      >
                        {toolset.name}
                      </Link>
                      <span className="mt-1 block font-mono text-[11px] text-slate/50">
                        {toolset.slug}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <StatusPill tone={statusTone(toolset.status)}>
                          {humanize(toolset.status)}
                        </StatusPill>
                        <StatusPill tone={healthTone(toolset.health)}>
                          {humanize(toolset.health)}
                        </StatusPill>
                      </div>
                    </TableCell>
                    <TableCell>{humanize(toolset.discovery_mode)}</TableCell>
                    <TableCell>
                      {toolset.available_tool_count}/{toolset.tool_count} · {toolset.grant_count}
                    </TableCell>
                    <TableCell>{toolset.revision}</TableCell>
                    <TableCell>
                      <Button
                        onClick={() => void copyEndpoint(toolset.endpoint_path)}
                        size="small"
                        variant="ghost"
                      >
                        <Clipboard className="size-3.5" /> 复制
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          <div className="mt-5 flex items-center justify-between gap-4">
            <span className="text-xs text-slate/50">共 {toolsets.data.page.total} 个工具集</span>
            <Pagination
              onPageChange={(nextPage) => {
                const next = new URLSearchParams(searchParams);
                if (nextPage === 1) next.delete("page");
                else next.set("page", String(nextPage));
                setSearchParams(next);
              }}
              page={page}
              totalPages={Math.ceil(toolsets.data.page.total / PAGE_SIZE)}
            />
          </div>
        </>
      ) : null}
    </section>
  );
}

function CreateToolsetPanel({ onClose }: { onClose: () => void }) {
  const create = useCreateToolset();
  const navigate = useNavigate();

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const created = await create.mutateAsync({
      slug: String(form.get("slug") ?? "").trim(),
      name: String(form.get("name") ?? "").trim(),
      description: String(form.get("description") ?? "").trim() || null,
      discovery_mode: String(form.get("discovery_mode")) as ToolsetDiscoveryMode,
    });
    await navigate(`/toolsets/${created.id}`);
  }

  return (
    <form className="panel mb-6 p-6" onSubmit={(event) => void submit(event)}>
      <p className="component-label">创建 Explicit Toolset</p>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div>
          <FieldLabel htmlFor="toolset-slug">Slug</FieldLabel>
          <Input id="toolset-slug" name="slug" placeholder="operations" required />
        </div>
        <div>
          <FieldLabel htmlFor="toolset-name">名称</FieldLabel>
          <Input id="toolset-name" name="name" placeholder="运维工具集" required />
        </div>
        <div>
          <FieldLabel htmlFor="create-toolset-mode">发现模式</FieldLabel>
          <Select defaultValue="direct" id="create-toolset-mode" name="discovery_mode">
            <option value="direct">Direct</option>
            <option value="search_first">Search First</option>
          </Select>
        </div>
        <div className="md:col-span-2">
          <FieldLabel htmlFor="toolset-description">描述</FieldLabel>
          <Textarea id="toolset-description" name="description" />
        </div>
      </div>
      {create.error ? (
        <div className="mt-4">
          <InlineError error={create.error} />
        </div>
      ) : null}
      <div className="mt-5 flex gap-3">
        <Button disabled={create.isPending} type="submit">
          {create.isPending ? "正在创建…" : "创建草稿"}
        </Button>
        <Button onClick={onClose} type="button" variant="secondary">
          取消
        </Button>
      </div>
    </form>
  );
}

function healthTone(health: string): "active" | "failed" | "pending" {
  if (health === "healthy") return "active";
  if (health === "unavailable") return "failed";
  return "pending";
}

async function copyEndpoint(path: string) {
  await navigator.clipboard.writeText(`${window.location.origin}${path}`);
}

function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
