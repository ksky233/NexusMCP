import { approveApproval, listApprovals, rejectApproval } from "@/generated/api/sdk.gen";
import type {
  ApprovalPageResponse,
  ApprovalResponse,
  ListApprovalsData,
} from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export type ApprovalListQuery = NonNullable<ListApprovalsData["query"]>;

export async function fetchApprovals(query: ApprovalListQuery): Promise<ApprovalPageResponse> {
  return (await listApprovals({ query, signal: createRequestSignal(), throwOnError: true })).data;
}

export async function decideApproval(
  approvalId: string,
  approved: boolean,
): Promise<ApprovalResponse> {
  const options = {
    path: { approval_id: approvalId },
    signal: createRequestSignal(),
    throwOnError: true as const,
  };
  return approved ? (await approveApproval(options)).data : (await rejectApproval(options)).data;
}
