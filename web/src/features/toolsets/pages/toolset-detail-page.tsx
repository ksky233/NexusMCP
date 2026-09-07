import { ArrowLeft, Clipboard, Power, PowerOff, Save } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState, InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { FieldHelp, FieldLabel, Input, Select, Textarea } from "@/components/ui/form-controls";
import { StatusPill } from "@/components/ui/status-pill";
import { useTools } from "@/features/catalog/hooks/use-catalog";
import { useUpstreams } from "@/features/upstreams/hooks/use-upstreams";
import {
  useActivateToolset,
  useDisableToolset,
  useReplaceToolsetGrants,
  useReplaceToolsetMembers,
  useToolset,
  useUpdateToolset,
} from "@/features/toolsets/hooks/use-toolsets";
import type {
  ToolsetDiscoveryMode,
  ToolsetResponse,
  ToolSummaryResponse,
} from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function ToolsetDetailPage() {
  const toolsetId = useParams().toolsetId ?? "";
  const toolset = useToolset(toolsetId);
  if (toolset.isPending) return <LoadingState label="正在加载工具集 Profile…" />;
  if (toolset.isError)
    return <ErrorState error={toolset.error} onRetry={() => void toolset.refetch()} />;
  return <ToolsetDetail key={toolset.data.revision} toolset={toolset.data} />;
}

function ToolsetDetail({ toolset }: { toolset: ToolsetResponse }) {
  const activate = useActivateToolset(toolset.id);
  const disable = useDisableToolset(toolset.id);
  const statusError = activate.error ?? disable.error;
  const endpoint = `${window.location.origin}${toolset.endpoint_path}`;

  return (
    <section className="page-enter">
      <Link
        className="mb-7 inline-flex items-center gap-2 text-xs text-slate/60 hover:text-ink"
        to="/toolsets"
      >
        <ArrowLeft className="size-3.5" /> 返回工具集
      </Link>
      <PageHeader
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => void navigator.clipboard.writeText(endpoint)}
              size="small"
              variant="secondary"
            >
              <Clipboard className="size-3.5" /> 复制 Endpoint
            </Button>
            {toolset.status !== "active" ? (
              <Button
                disabled={activate.isPending}
                onClick={() => activate.mutate(toolset.revision)}
                size="small"
              >
                <Power className="size-3.5" /> 启用
              </Button>
            ) : null}
            {toolset.kind === "explicit" && toolset.status !== "disabled" ? (
              <Button
                disabled={disable.isPending}
                onClick={() => disable.mutate(toolset.revision)}
                size="small"
                variant="danger"
              >
                <PowerOff className="size-3.5" /> 停用
              </Button>
            ) : null}
          </div>
        }
        description={toolset.description ?? "未填写工具集描述。"}
        eyebrow={`${humanize(toolset.kind)} · Revision ${toolset.revision}`}
        title={toolset.name}
      />
      {statusError ? (
        <div className="mb-5">
          <InlineError error={statusError} />
        </div>
      ) : null}

      <article className="panel mb-5 p-6 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <p className="component-label">运行 Profile</p>
          <div className="flex gap-2">
            <StatusPill tone={statusTone(toolset.status)}>{humanize(toolset.status)}</StatusPill>
            <StatusPill tone={healthTone(toolset.health)}>{humanize(toolset.health)}</StatusPill>
          </div>
        </div>
        <dl className="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <Definition label="Endpoint" value={endpoint} mono />
          <Definition label="发现模式" value={humanize(toolset.discovery_mode)} />
          <Definition
            label="可用 Tool"
            value={`${toolset.available_tool_count} / ${toolset.tool_count}`}
          />
          <Definition label="Schema 体积" value={formatBytes(toolset.serialized_schema_size)} />
          <Definition label="Grant" value={String(toolset.grant_count)} />
          <Definition label="Membership Digest" value={toolset.membership_digest} mono />
          <Definition label="创建时间" value={formatDateTime(toolset.created_at)} />
          <Definition label="更新时间" value={formatDateTime(toolset.updated_at)} />
        </dl>
      </article>

      <div className="grid gap-5 xl:grid-cols-2">
        <ProfileEditor toolset={toolset} />
        <GrantEditor toolset={toolset} />
      </div>
      {toolset.kind === "explicit" ? (
        <MemberEditor toolset={toolset} />
      ) : (
        <SystemMembers toolset={toolset} />
      )}
    </section>
  );
}

function ProfileEditor({ toolset }: { toolset: ToolsetResponse }) {
  const update = useUpdateToolset(toolset.id);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await update.mutateAsync({
      expected_revision: toolset.revision,
      name: toolset.kind === "all_published" ? toolset.name : String(form.get("name") ?? "").trim(),
      description:
        toolset.kind === "all_published"
          ? toolset.description
          : String(form.get("description") ?? "").trim() || null,
      discovery_mode: String(form.get("discovery_mode")) as ToolsetDiscoveryMode,
    });
  }
  return (
    <form className="panel p-6 sm:p-7" onSubmit={(event) => void submit(event)}>
      <p className="component-label">基础配置</p>
      <div className="mt-5 space-y-4">
        <div>
          <FieldLabel htmlFor="toolset-name">名称</FieldLabel>
          <Input
            defaultValue={toolset.name}
            disabled={toolset.kind === "all_published"}
            id="toolset-name"
            name="name"
            required
          />
        </div>
        <div>
          <FieldLabel htmlFor="toolset-description">描述</FieldLabel>
          <Textarea
            defaultValue={toolset.description ?? ""}
            disabled={toolset.kind === "all_published"}
            id="toolset-description"
            name="description"
          />
        </div>
        <div>
          <FieldLabel htmlFor="toolset-discovery-mode">发现模式</FieldLabel>
          <Select
            defaultValue={toolset.discovery_mode}
            id="toolset-discovery-mode"
            name="discovery_mode"
          >
            <option value="direct">Direct：直接暴露成员 Tool</option>
            <option value="search_first">Search First：只暴露检索入口</option>
          </Select>
        </div>
      </div>
      {toolset.kind === "all_published" ? (
        <FieldHelp>系统工具集只允许调整发现模式。</FieldHelp>
      ) : null}
      {update.error ? (
        <div className="mt-4">
          <InlineError error={update.error} />
        </div>
      ) : null}
      <Button className="mt-5" disabled={update.isPending} type="submit">
        <Save className="size-3.5" /> 保存配置
      </Button>
    </form>
  );
}

function GrantEditor({ toolset }: { toolset: ToolsetResponse }) {
  const replace = useReplaceToolsetGrants(toolset.id);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const principalIds = String(form.get("principal_ids") ?? "")
      .split(/[\n,]/)
      .map((value) => value.trim())
      .filter(Boolean);
    await replace.mutateAsync({
      expected_revision: toolset.revision,
      principal_ids: principalIds,
    });
  }
  return (
    <form className="panel p-6 sm:p-7" onSubmit={(event) => void submit(event)}>
      <p className="component-label">Agent Service Access</p>
      <div className="mt-5">
        <FieldLabel htmlFor="toolset-principals">Principal IDs</FieldLabel>
        <Textarea
          defaultValue={toolset.principal_ids.join("\n")}
          id="toolset-principals"
          name="principal_ids"
          placeholder="operations-agent"
        />
        <FieldHelp>每行一个 Principal；保存时原子替换完整 Grant 集合。</FieldHelp>
      </div>
      {toolset.kind === "all_published" ? (
        <FieldHelp error>该 Grant 会允许 Agent 访问当前及未来全部 Published Tool。</FieldHelp>
      ) : null}
      {replace.error ? (
        <div className="mt-4">
          <InlineError error={replace.error} />
        </div>
      ) : null}
      <Button className="mt-5" disabled={replace.isPending} type="submit">
        <Save className="size-3.5" /> 保存 Grant
      </Button>
    </form>
  );
}

function MemberEditor({ toolset }: { toolset: ToolsetResponse }) {
  const [selected, setSelected] = useState(
    () => new Set(toolset.members.map((member) => member.tool_id)),
  );
  const [query, setQuery] = useState("");
  const [upstreamId, setUpstreamId] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const tools = useTools({
    offset: 0,
    limit: 100,
    q: query.trim() || undefined,
    upstream_service_id: upstreamId || undefined,
    version_status: "published",
  });
  const upstreams = useUpstreams({ offset: 0, limit: 100 });
  const replace = useReplaceToolsetMembers(toolset.id);
  const groups = useMemo(
    () => groupToolsByUpstream(tools.data?.items ?? [], selected, selectedOnly),
    [selected, selectedOnly, tools.data?.items],
  );

  async function save() {
    await replace.mutateAsync({
      expected_revision: toolset.revision,
      tool_ids: [...selected].sort(),
    });
  }

  return (
    <article className="panel mt-5 p-6 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="component-label">Members</p>
          <p className="mt-2 text-sm text-slate/60">
            从当前 Published Catalog 选择 Tool；保存时原子替换完整成员集合。
          </p>
        </div>
        <Button
          disabled={replace.isPending || tools.isPending}
          onClick={() => void save()}
          size="small"
        >
          <Save className="size-3.5" /> 保存成员
        </Button>
      </div>
      <div className="mt-5 grid gap-4 border-y border-slate/20 py-5 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,0.55fr)_auto] lg:items-end">
        <div>
          <FieldLabel htmlFor="toolset-member-query">搜索 Tool</FieldLabel>
          <Input
            id="toolset-member-query"
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder="名称、显示名称或描述"
            type="search"
            value={query}
          />
        </div>
        <div>
          <FieldLabel htmlFor="toolset-member-upstream">上游服务</FieldLabel>
          <Select
            id="toolset-member-upstream"
            onChange={(event) => setUpstreamId(event.currentTarget.value)}
            value={upstreamId}
          >
            <option value="">全部上游</option>
            {upstreams.data?.items.map((upstream) => (
              <option key={upstream.id} value={upstream.id}>
                {upstream.namespace}.{upstream.name}
              </option>
            ))}
          </Select>
        </div>
        <label className="flex h-[42px] cursor-pointer items-center gap-2 text-xs text-ink/75">
          <input
            checked={selectedOnly}
            className="size-4 accent-ink"
            onChange={(event) => setSelectedOnly(event.currentTarget.checked)}
            type="checkbox"
          />
          仅看已选（{selected.size}）
        </label>
      </div>
      {tools.isPending ? (
        <div className="mt-5">
          <LoadingState label="正在加载 Published Tool…" />
        </div>
      ) : null}
      {tools.isError ? (
        <div className="mt-5">
          <InlineError error={tools.error} />
        </div>
      ) : null}
      {replace.error ? (
        <div className="mt-5">
          <InlineError error={replace.error} />
        </div>
      ) : null}
      {upstreams.isError ? (
        <div className="mt-5">
          <InlineError error={upstreams.error} />
        </div>
      ) : null}
      {toolset.members.length > 0 ? (
        <div className="mt-5">
          <p className="component-label">当前成员状态</p>
          <MemberDiagnostics toolset={toolset} />
        </div>
      ) : null}
      {tools.data && groups.length === 0 ? (
        <p className="mt-5 border-y border-slate/20 py-6 text-sm text-slate/55">
          当前条件下没有可选的 Published Tool。
        </p>
      ) : null}
      {groups.map((group) => (
        <section className="mt-5" key={group.id}>
          <div className="flex items-center justify-between border-b border-slate/25 pb-2">
            <p className="font-mono text-xs font-medium text-ink">{group.label}</p>
            <span className="text-[11px] text-slate/50">{group.tools.length} Tools</span>
          </div>
          <div className="divide-y divide-slate/15">
            {group.tools.map((tool) => (
              <label className="flex cursor-pointer items-start gap-3 py-4" key={tool.id}>
                <input
                  checked={selected.has(tool.id)}
                  className="mt-1 size-4 accent-ink"
                  onChange={(event) => {
                    const next = new Set(selected);
                    if (event.currentTarget.checked) next.add(tool.id);
                    else next.delete(tool.id);
                    setSelected(next);
                  }}
                  type="checkbox"
                />
                <span className="min-w-0">
                  <span className="block font-mono text-xs text-ink">{tool.canonical_name}</span>
                  <span className="mt-1 block text-xs leading-5 text-slate/55">
                    {tool.description}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </section>
      ))}
    </article>
  );
}

type UpstreamToolGroup = {
  id: string;
  label: string;
  tools: ToolSummaryResponse[];
};

function groupToolsByUpstream(
  tools: ToolSummaryResponse[],
  selected: ReadonlySet<string>,
  selectedOnly: boolean,
): UpstreamToolGroup[] {
  const groups = new Map<string, UpstreamToolGroup>();
  for (const tool of tools) {
    if (selectedOnly && !selected.has(tool.id)) continue;
    const id = tool.upstream_service_id ?? "unbound";
    const label =
      tool.upstream_namespace && tool.upstream_name
        ? `${tool.upstream_namespace}.${tool.upstream_name}`
        : "未绑定上游";
    const group = groups.get(id) ?? { id, label, tools: [] };
    group.tools.push(tool);
    groups.set(id, group);
  }
  return [...groups.values()].sort((left, right) => left.label.localeCompare(right.label));
}

function SystemMembers({ toolset }: { toolset: ToolsetResponse }) {
  return (
    <article className="panel mt-5 p-6 sm:p-7">
      <p className="component-label">系统成员投影</p>
      <p className="mt-2 text-sm text-slate/60">
        该工具集动态包含所有当前 Published Tool，不提供手工成员编辑。
      </p>
      <MemberDiagnostics toolset={toolset} />
    </article>
  );
}

function MemberDiagnostics({ toolset }: { toolset: ToolsetResponse }) {
  return (
    <div className="mt-5 divide-y divide-slate/15 border-y border-slate/20">
      {toolset.members.map((member) => (
        <div className="flex items-start justify-between gap-4 py-4" key={member.tool_id}>
          <div>
            <p className="font-mono text-xs text-ink">{member.canonical_name ?? member.tool_id}</p>
            <p className="mt-1 text-xs text-slate/55">
              {member.description ?? "无 Published Version 描述"}
            </p>
          </div>
          <StatusPill tone={member.availability === "available" ? "active" : "failed"}>
            {humanize(member.availability)}
          </StatusPill>
        </div>
      ))}
    </div>
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

function healthTone(health: string): "active" | "failed" | "pending" {
  if (health === "healthy") return "active";
  if (health === "unavailable") return "failed";
  return "pending";
}

function formatBytes(value: number): string {
  return value < 1024 ? `${value} B` : `${(value / 1024).toFixed(1)} KiB`;
}
