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
        eyebrow="Governance"
        title="Approvals"
        description="Review asynchronous tool-call decisions without exposing sensitive arguments."
        actions={
          <Button onClick={() => void approvals.refetch()} size="small" variant="secondary">
            <RefreshCw className="size-3.5" /> Refresh
          </Button>
        }
      />
      <div className="mb-5 grid max-w-2xl gap-4 border border-slate/18 bg-paper p-4 sm:grid-cols-2">
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
            placeholder="All principals"
          />
        </div>
        <div>
          <FieldLabel htmlFor="approval-status">Status</FieldLabel>
          <Select
            id="approval-status"
            onChange={(event) => update("status", event.currentTarget.value)}
            value={status ?? ""}
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="expired">Expired</option>
            <option value="consumed">Consumed</option>
          </Select>
        </div>
      </div>
      {decide.error ? (
        <div className="mb-5">
          <InlineError error={decide.error} />
        </div>
      ) : null}
      {approvals.isPending ? <LoadingState label="Loading approvals…" /> : null}
      {approvals.isError ? (
        <ErrorState error={approvals.error} onRetry={() => void approvals.refetch()} />
      ) : null}
      {approvals.data?.items.length === 0 ? (
        <EmptyState
          title="No approvals found"
          description="No approval requests match the current filters."
        />
      ) : null}
      {approvals.data && approvals.data.items.length > 0 ? (
        <>
          <TableFrame>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Tool / Principal</TableHeaderCell>
                  <TableHeaderCell>Requested</TableHeaderCell>
                  <TableHeaderCell>Evidence</TableHeaderCell>
                  <TableHeaderCell>Status / Action</TableHeaderCell>
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
                        Expires {formatDateTime(approval.expires_at)}
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
                            aria-label={`Approve ${approval.canonical_name}`}
                            onClick={() =>
                              setDecision({
                                approvalId: approval.id,
                                approved: true,
                                toolName: approval.canonical_name,
                              })
                            }
                            size="small"
                          >
                            <Check className="size-3.5" /> Approve
                          </Button>
                          <Button
                            aria-label={`Reject ${approval.canonical_name}`}
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
                            <X className="size-3.5" /> Reject
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
            <span className="text-xs text-slate/50">{approvals.data.page.total} approvals</span>
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
          decide.isPending
            ? "Saving decision…"
            : decision?.approved
              ? "Approve request"
              : "Reject request"
        }
        description="This decision is authoritative and will be recorded in the audit trail. The approval remains bound to the original principal, tool version and arguments digest."
        onConfirm={() => {
          if (!decision) return;
          void decide.mutateAsync(decision).then(() => setDecision(null));
        }}
        onOpenChange={(open) => !open && setDecision(null)}
        open={Boolean(decision)}
        title={`${decision?.approved ? "Approve" : "Reject"} ${decision?.toolName ?? "request"}?`}
      />
    </section>
  );
}

function positiveInteger(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}
