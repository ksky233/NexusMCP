import { ArrowLeft, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState, InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import { useTool, useToolVersions, useVersionBinding } from "@/features/catalog/hooks/use-catalog";
import type { ToolVersionDetailResponse } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function ToolDetailPage() {
  const toolId = useParams().toolId ?? "";
  const tool = useTool(toolId);
  const versions = useToolVersions(toolId);
  if (tool.isPending || versions.isPending) return <LoadingState label="正在加载 Tool Contract…" />;
  if (tool.isError) return <ErrorState error={tool.error} onRetry={() => void tool.refetch()} />;
  if (versions.isError)
    return <ErrorState error={versions.error} onRetry={() => void versions.refetch()} />;
  return (
    <section className="page-enter">
      <Link
        className="mb-7 inline-flex items-center gap-2 text-xs text-slate/60 hover:text-ink"
        to="/catalog"
      >
        <ArrowLeft className="size-3.5" /> 返回工具目录
      </Link>
      <PageHeader
        actions={
          <StatusPill tone={statusTone(tool.data.status)}>{humanize(tool.data.status)}</StatusPill>
        }
        description={`负责人 ${tool.data.owner} · Namespace ${tool.data.namespace}`}
        eyebrow="Catalog · 稳定身份"
        title={tool.data.canonical_name}
      />
      <article className="panel mb-5 p-6 sm:p-7">
        <p className="component-label">身份信息</p>
        <dl className="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <Definition label="Tool ID" value={tool.data.id} mono />
          <Definition label="Tenant ID" value={tool.data.tenant_id} mono />
          <Definition label="创建时间" value={formatDateTime(tool.data.created_at)} />
          <Definition label="更新时间" value={formatDateTime(tool.data.updated_at)} />
        </dl>
      </article>
      <div className="space-y-4">
        {versions.data.items.map((version) => (
          <VersionPanel key={version.id} version={version} />
        ))}
      </div>
    </section>
  );
}

function VersionPanel({ version }: { version: ToolVersionDetailResponse }) {
  const [expanded, setExpanded] = useState(version.status === "published");
  const binding = useVersionBinding(version.id, expanded);
  return (
    <article className="panel p-6 sm:p-7">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <div className="flex items-center gap-2">
            <StatusPill tone={statusTone(version.status)}>{humanize(version.status)}</StatusPill>
            <span className="text-xs text-slate/50">v{version.version}</span>
          </div>
          <h2 className="mt-4 text-lg font-light text-ink">{version.display_name}</h2>
          <p className="mt-2 text-sm leading-6 text-slate/65">{version.description}</p>
        </div>
        <Button onClick={() => setExpanded((value) => !value)} size="small" variant="secondary">
          {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}{" "}
          {expanded ? "收起 Contract" : "查看 Contract"}
        </Button>
      </div>
      {expanded ? (
        <div className="mt-6 border-t border-slate/15 pt-6">
          <dl className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            <Definition label="可见范围" value={humanize(version.visibility)} />
            <Definition label="副作用" value={humanize(version.side_effect)} />
            <Definition label="Schema Digest" value={version.schema_digest} mono />
            <Definition label="发布时间" value={formatDateTime(version.published_at)} />
          </dl>
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Schema label="Input Schema" value={version.input_schema} />
            <Schema label="Output Schema" value={version.output_schema} />
          </div>
          {binding.isPending ? (
            <div className="mt-5">
              <LoadingState label="正在加载 Binding…" />
            </div>
          ) : null}
          {binding.error ? (
            <div className="mt-5">
              <InlineError error={binding.error} />
            </div>
          ) : null}
          {binding.data ? (
            <div className="mt-5 border border-slate/15 bg-canvas p-5">
              <div className="flex items-center justify-between gap-3">
                <p className="component-label">HTTP Binding</p>
                <StatusPill tone={statusTone(binding.data.status)}>
                  {humanize(binding.data.status)}
                </StatusPill>
              </div>
              <dl className="mt-5 grid gap-5 sm:grid-cols-2">
                <Definition label="Binding Digest" value={binding.data.binding_digest} mono />
                <Definition label="上游服务 ID" value={binding.data.upstream_service_id} mono />
              </dl>
              <Schema label="Binding Config" value={binding.data.binding_config} />
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function Schema({ label, value }: { label: string; value: Record<string, unknown> | null }) {
  return (
    <div className="min-w-0">
      <p className="component-label">{label}</p>
      <pre className="mt-3 max-h-80 overflow-auto border border-slate/15 bg-canvas p-4 font-mono text-[11px] leading-5 text-slate">
        {JSON.stringify(value, null, 2)}
      </pre>
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
