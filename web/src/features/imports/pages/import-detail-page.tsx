import { ArrowLeft, Check } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState, InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { FieldLabel, Input, Select, Textarea } from "@/components/ui/form-controls";
import { StatusPill } from "@/components/ui/status-pill";
import {
  useDirectPublishOperation,
  useImport,
  useToolBinding,
  useToolVersion,
} from "@/features/imports/hooks/use-imports";
import { useToolsets } from "@/features/toolsets/hooks/use-toolsets";
import type { ImportedOperationResponse, ToolVisibility } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function ImportDetailPage() {
  const importId = useParams().importId ?? "";
  const detail = useImport(importId);
  const allPublished = useToolsets({ offset: 0, limit: 1, kind: "all_published" });

  if (detail.isPending) return <LoadingState label="正在加载导入详情…" />;
  if (detail.isError)
    return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;

  const { job, operations } = detail.data;
  return (
    <section className="page-enter">
      <Link
        className="mb-7 inline-flex items-center gap-2 text-xs text-slate/60 hover:text-ink"
        to="/imports"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" /> 返回导入记录
      </Link>
      <PageHeader
        actions={<StatusPill tone={statusTone(job.status)}>{humanize(job.status)}</StatusPill>}
        description={`${job.source_ref} · OpenAPI ${job.openapi_version ?? "未知版本"}`}
        eyebrow="OpenAPI 导入"
        title={`导入任务 ${job.id.slice(0, 8)}`}
      />

      <article className="panel mb-5 p-6 sm:p-7">
        <p className="component-label">导入证据</p>
        <dl className="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <Definition label="创建时间" value={formatDateTime(job.created_at)} />
          <Definition label="完成时间" value={formatDateTime(job.completed_at)} />
          <Definition label="来源 Digest" mono value={job.source_digest} />
          <Definition label="上游服务 ID" mono value={job.upstream_service_id} />
        </dl>
        {job.error_summary ? (
          <p className="mt-5 border border-wine/35 bg-wine/6 p-4 text-sm text-wine">
            {job.error_summary}
          </p>
        ) : null}
      </article>

      <div className="space-y-4">
        {operations.map((operation) => (
          <OperationWorkflow
            allPublishedGrantCount={allPublished.data?.items[0]?.grant_count ?? 0}
            importId={importId}
            key={operation.id}
            operation={operation}
          />
        ))}
      </div>
    </section>
  );
}

function OperationWorkflow({
  allPublishedGrantCount,
  importId,
  operation,
}: {
  allPublishedGrantCount: number;
  importId: string;
  operation: ImportedOperationResponse;
}) {
  const [publishing, setPublishing] = useState(false);
  const [owner, setOwner] = useState("platform-team");
  const [visibility, setVisibility] = useState<ToolVisibility>("public");
  const [notes, setNotes] = useState("");
  const directPublish = useDirectPublishOperation(importId, operation.id);
  const version = useToolVersion(operation.draft_tool_version_id);
  const binding = useToolBinding(operation.draft_tool_binding_id);
  const canPublish = operation.conflict_status === "none" && version.data?.status !== "published";

  return (
    <article className="panel p-6 sm:p-7">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={statusTone(operation.review_status)}>
              {humanize(operation.review_status)}
            </StatusPill>
            {operation.conflict_status !== "none" ? (
              <StatusPill tone="failed">{humanize(operation.conflict_status)}</StatusPill>
            ) : null}
          </div>
          <h2 className="mt-4 break-all text-lg font-light text-ink">
            {operation.operation_id ?? operation.operation_key}
          </h2>
          <p className="mt-2 font-mono text-xs text-slate/60">
            {operation.method} {operation.path}
          </p>
          {operation.generated_tool_name ? (
            <p className="mt-3 text-sm text-slate/65">Tool：{operation.generated_tool_name}</p>
          ) : null}
        </div>
        {canPublish ? (
          <Button onClick={() => setPublishing((value) => !value)} size="small">
            <Check aria-hidden="true" className="size-3.5" /> 直接发布
          </Button>
        ) : null}
      </div>

      <div className="mt-6 border-t border-slate/15 pt-6">
        <p className="component-label">Generated Tool Contract</p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Definition
            label="名称"
            value={operation.summary ?? operation.generated_tool_name ?? "—"}
          />
          <Definition label="副作用" value={humanize(operation.side_effect)} />
          <Definition label="Tool Name" mono value={operation.generated_tool_name ?? "—"} />
          <Definition label="输出 Schema" value={operation.output_schema ? "已声明" : "未声明"} />
        </dl>
        {operation.description ? (
          <p className="mt-4 text-sm leading-6 text-slate/65">{operation.description}</p>
        ) : null}
        <details className="mt-4 border border-slate/15 bg-canvas p-4">
          <summary className="cursor-pointer text-xs text-slate">
            查看 Input / Output Schema
          </summary>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Schema label="Input Schema" value={operation.input_schema} />
            <Schema label="Output Schema" value={operation.output_schema} />
          </div>
        </details>
      </div>

      {publishing ? (
        <form
          className="mt-6 grid gap-5 border-t border-slate/15 pt-6 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void directPublish
              .mutateAsync({ owner, visibility, review_notes: notes || null })
              .then(() => setPublishing(false));
          }}
        >
          <div>
            <FieldLabel htmlFor={`owner-${operation.id}`}>负责人</FieldLabel>
            <Input
              id={`owner-${operation.id}`}
              onChange={(event) => setOwner(event.currentTarget.value)}
              required
              value={owner}
            />
          </div>
          <div>
            <FieldLabel htmlFor={`visibility-${operation.id}`}>可见范围</FieldLabel>
            <Select
              id={`visibility-${operation.id}`}
              onChange={(event) => setVisibility(event.currentTarget.value as ToolVisibility)}
              value={visibility}
            >
              <option value="public">公开</option>
              <option value="authenticated">需认证</option>
              <option value="restricted">受限</option>
            </Select>
          </div>
          <div className="sm:col-span-2">
            <FieldLabel htmlFor={`notes-${operation.id}`}>发布备注</FieldLabel>
            <Textarea
              id={`notes-${operation.id}`}
              onChange={(event) => setNotes(event.currentTarget.value)}
              value={notes}
            />
          </div>
          <div className="border border-slate/20 bg-canvas p-4 text-xs leading-5 text-slate/65 sm:col-span-2">
            {allPublishedGrantCount > 0
              ? `发布后会立即对 ${allPublishedGrantCount} 个拥有 all_published Grant 的 Agent Service 生效。`
              : "发布后进入 Catalog；普通 Agent 仍需通过 Explicit Toolset Membership 与 Grant 才能使用。"}
          </div>
          {directPublish.error ? (
            <div className="sm:col-span-2">
              <InlineError error={directPublish.error} />
            </div>
          ) : null}
          <div className="flex justify-end gap-3 sm:col-span-2">
            <Button onClick={() => setPublishing(false)} type="button" variant="secondary">
              取消
            </Button>
            <Button disabled={directPublish.isPending} type="submit">
              {directPublish.isPending ? "正在发布…" : "确认并直接发布"}
            </Button>
          </div>
        </form>
      ) : null}

      {operation.draft_tool_version_id && operation.draft_tool_binding_id ? (
        <div className="mt-6 border-t border-slate/15 pt-6">
          {version.isPending || binding.isPending ? (
            <LoadingState label="正在加载发布结果…" />
          ) : null}
          {version.error ? <InlineError error={version.error} /> : null}
          {binding.error ? <InlineError error={binding.error} /> : null}
          {version.data && binding.data ? (
            <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
              <dl className="grid min-w-0 gap-4 sm:grid-cols-2">
                <Definition
                  label="版本"
                  value={`v${version.data.version} · ${humanize(version.data.status)}`}
                />
                <Definition label="副作用" value={humanize(version.data.side_effect)} />
                <Definition label="Schema Digest" mono value={version.data.schema_digest} />
                <Definition label="Binding Digest" mono value={binding.data.binding_digest} />
              </dl>
              <StatusPill tone={statusTone(version.data.status)}>
                {humanize(version.data.status)}
              </StatusPill>
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
      <pre className="mt-3 max-h-64 overflow-auto border border-slate/15 bg-paper p-3 font-mono text-[11px] leading-5 text-slate">
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
