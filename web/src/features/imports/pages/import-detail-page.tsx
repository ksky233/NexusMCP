import { ArrowLeft, Check, Send } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { ErrorState, InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { FieldLabel, Input, Select, Textarea } from "@/components/ui/form-controls";
import { StatusPill } from "@/components/ui/status-pill";
import {
  useAcceptOperation,
  useImport,
  usePublishVersion,
  useSubmitVersion,
  useToolBinding,
  useToolVersion,
} from "@/features/imports/hooks/use-imports";
import type { ImportedOperationResponse, ToolVisibility } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function ImportDetailPage() {
  const importId = useParams().importId ?? "";
  const detail = useImport(importId);

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
          <OperationWorkflow importId={importId} key={operation.id} operation={operation} />
        ))}
      </div>
    </section>
  );
}

function OperationWorkflow({
  importId,
  operation,
}: {
  importId: string;
  operation: ImportedOperationResponse;
}) {
  const [reviewing, setReviewing] = useState(false);
  const [owner, setOwner] = useState("platform-team");
  const [visibility, setVisibility] = useState<ToolVisibility>("public");
  const [notes, setNotes] = useState("");
  const [publishOpen, setPublishOpen] = useState(false);
  const accept = useAcceptOperation(importId, operation.id);
  const version = useToolVersion(operation.draft_tool_version_id);
  const binding = useToolBinding(operation.draft_tool_binding_id);
  const submit = useSubmitVersion(operation.draft_tool_version_id ?? "");
  const publish = usePublishVersion(version.data?.tool_id ?? "", version.data?.id ?? "");
  const canReview = operation.review_status === "pending" && operation.conflict_status === "none";

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
        {canReview ? (
          <Button onClick={() => setReviewing((value) => !value)} size="small">
            <Check aria-hidden="true" className="size-3.5" /> 审核 Operation
          </Button>
        ) : null}
      </div>

      {reviewing ? (
        <form
          className="mt-6 grid gap-5 border-t border-slate/15 pt-6 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void accept
              .mutateAsync({ owner, visibility, review_notes: notes || null })
              .then(() => setReviewing(false));
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
            <FieldLabel htmlFor={`notes-${operation.id}`}>审核备注</FieldLabel>
            <Textarea
              id={`notes-${operation.id}`}
              onChange={(event) => setNotes(event.currentTarget.value)}
              value={notes}
            />
          </div>
          {accept.error ? (
            <div className="sm:col-span-2">
              <InlineError error={accept.error} />
            </div>
          ) : null}
          <div className="flex justify-end gap-3 sm:col-span-2">
            <Button onClick={() => setReviewing(false)} type="button" variant="secondary">
              取消
            </Button>
            <Button disabled={accept.isPending} type="submit">
              {accept.isPending ? "正在审核…" : "接受并创建草稿"}
            </Button>
          </div>
        </form>
      ) : null}

      {operation.draft_tool_version_id && operation.draft_tool_binding_id ? (
        <div className="mt-6 border-t border-slate/15 pt-6">
          {version.isPending || binding.isPending ? (
            <LoadingState label="正在加载草稿 Contract…" />
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
              <div className="flex shrink-0 gap-3">
                {version.data.status === "draft" ? (
                  <Button
                    disabled={submit.isPending}
                    onClick={() => void submit.mutateAsync()}
                    size="small"
                  >
                    <Send aria-hidden="true" className="size-3.5" />
                    {submit.isPending ? "正在提交…" : "提交审核"}
                  </Button>
                ) : null}
                {version.data.status === "review" ? (
                  <Button onClick={() => setPublishOpen(true)} size="small">
                    发布版本
                  </Button>
                ) : null}
                {version.data.status === "published" ? (
                  <StatusPill tone="completed">已发布</StatusPill>
                ) : null}
              </div>
            </div>
          ) : null}
          {submit.error ? (
            <div className="mt-4">
              <InlineError error={submit.error} />
            </div>
          ) : null}
          {publish.error ? (
            <div className="mt-4">
              <InlineError error={publish.error} />
            </div>
          ) : null}
        </div>
      ) : null}

      {version.data && binding.data ? (
        <ConfirmDialog
          confirmLabel={publish.isPending ? "正在发布…" : "发布 Tool 版本"}
          description="发布前会原子校验已审核的 Schema 与 Binding Digest；成功后该版本才会对 MCP Client 可见。"
          onConfirm={() => {
            void publish
              .mutateAsync({
                expected_schema_digest: version.data.schema_digest,
                expected_binding_digest: binding.data.binding_digest,
              })
              .then(() => setPublishOpen(false));
          }}
          onOpenChange={setPublishOpen}
          open={publishOpen}
          title={`确认发布 ${operation.generated_tool_name ?? "Tool"}？`}
        />
      ) : null}
    </article>
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
