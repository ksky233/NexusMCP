import { Check, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/common/page-header";
import { EmptyState, ErrorState, InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
import { useApprovals, useDecideApproval } from "@/features/approvals/hooks/use-approvals";
import type { ApprovalStatus } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

const PAGE_SIZE = 10;
type Decision = { approvalId: string; approved: boolean; toolName: string };

export function ApprovalsPage() {
  const [params, setParams] = useSearchParams();
  const [decision, setDecision] = useState<Decision | null>(null);
  const page = positiveInteger(params.get("page"));
  const status = (params.get("status") || undefined) as ApprovalStatus | undefined;
  const principalId = params.get("principal_id")?.trim() || undefined;
  const approvals = useApprovals({
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    status,
    principal_id: principalId,
  });
  const decide = useDecideApproval();

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
        eyebrow="治理"
        title="审批管理"
        description="审核异步工具调用决策，同时避免暴露敏感参数。"
        actions={
          <Button onClick={() => void approvals.refetch()} size="small" variant="secondary">
            <RefreshCw className="size-3.5" /> 刷新
          </Button>
        }
      />
      <div className="mb-5 grid max-w-2xl gap-4 border border-slate/30 bg-paper p-4 sm:grid-cols-2">
        <div>
          <FieldLabel htmlFor="approval-principal">Principal</FieldLabel>
          <Input
            id="approval-principal"
            defaultValue={principalId}
            key={principalId ?? "all"}
            onBlur={(event) => update("principal_id", event.currentTarget.value.trim())}
            onKeyDown={(event) =>
              event.key === "Enter" && update("principal_id", event.currentTarget.value.trim())
            }
            placeholder="全部 Principal"
          />
        </div>
        <div>
          <FieldLabel htmlFor="approval-status">状态</FieldLabel>
          <Select
            id="approval-status"
            onChange={(event) => update("status", event.currentTarget.value)}
            value={status ?? ""}
          >
            <option value="">全部状态</option>
            <option value="pending">待审批</option>
            <option value="approved">已批准</option>
            <option value="rejected">已拒绝</option>
            <option value="expired">已过期</option>
            <option value="consumed">已消费</option>
          </Select>
        </div>
      </div>
      {decide.error ? (
        <div className="mb-5">
          <InlineError error={decide.error} />
        </div>
      ) : null}
      {approvals.isPending ? <LoadingState label="正在加载审批请求…" /> : null}
      {approvals.isError ? (
        <ErrorState error={approvals.error} onRetry={() => void approvals.refetch()} />
      ) : null}
      {approvals.data?.items.length === 0 ? (
        <EmptyState title="未找到审批请求" description="当前筛选条件下没有匹配的审批请求。" />
      ) : null}
      {approvals.data && approvals.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Tool / Principal</TableHeaderCell>
                  <TableHeaderCell>申请时间</TableHeaderCell>
                  <TableHeaderCell>决策证据</TableHeaderCell>
                  <TableHeaderCell>状态 / 操作</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {approvals.data.items.map((approval) => (
                  <TableRow key={approval.id}>
                    <TableCell>
                      <span className="text-ink">{approval.canonical_name}</span>
                      <span className="mt-1 block text-xs text-slate/50">
                        {approval.principal_id}
                      </span>
                    </TableCell>
                    <TableCell>
                      {formatDateTime(approval.requested_at)}
                      <span className="mt-1 block text-xs text-slate/50">
                        过期于 {formatDateTime(approval.expires_at)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="block font-mono text-[11px]">
                        {approval.arguments_digest.slice(0, 14)}…
                      </span>
                      <span className="mt-1 block text-xs text-slate/50">
                        {approval.policy_version}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusPill tone={statusTone(approval.status)}>
                        {humanize(approval.status)}
                      </StatusPill>
                      {approval.status === "pending" ? (
                        <div className="mt-3 flex gap-2">
                          <Button
                            aria-label={`批准 ${approval.canonical_name}`}
                            onClick={() =>
                              setDecision({
                                approvalId: approval.id,
                                approved: true,
                                toolName: approval.canonical_name,
                              })
                            }
                            size="small"
                          >
                            <Check className="size-3.5" /> 批准
                          </Button>
                          <Button
                            aria-label={`拒绝 ${approval.canonical_name}`}
                            onClick={() =>
                              setDecision({
                                approvalId: approval.id,
                                approved: false,
                                toolName: approval.canonical_name,
                              })
                            }
                            size="small"
                            variant="danger"
                          >
                            <X className="size-3.5" /> 拒绝
                          </Button>
                        </div>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableFrame>
          <div className="mt-5 flex items-center justify-between gap-4">
            <span className="text-xs text-slate/50">共 {approvals.data.page.total} 条审批请求</span>
            <Pagination
              page={page}
              totalPages={Math.ceil(approvals.data.page.total / PAGE_SIZE)}
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
      <ConfirmDialog
        danger={decision?.approved === false}
        confirmLabel={
          decide.isPending ? "正在保存决策…" : decision?.approved ? "批准请求" : "拒绝请求"
        }
        description="该决策将立即生效并写入审计轨迹。审批结果仍与原始 Principal、Tool 版本及参数摘要绑定。"
        onConfirm={() => {
          if (!decision) return;
          void decide.mutateAsync(decision).then(() => setDecision(null));
        }}
        onOpenChange={(open) => !open && setDecision(null)}
        open={Boolean(decision)}
        title={`${decision?.approved ? "批准" : "拒绝"} ${decision?.toolName ?? "该请求"}？`}
      />
    </section>
  );
}

function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
