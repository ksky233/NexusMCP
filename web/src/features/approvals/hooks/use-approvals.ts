import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  decideApproval,
  fetchApprovals,
  type ApprovalListQuery,
} from "@/features/approvals/api/approvals";

export const approvalKeys = {
  all: ["approvals"] as const,
  list: (query: ApprovalListQuery) => ["approvals", "list", query] as const,
};

export function useApprovals(query: ApprovalListQuery) {
  return useQuery({
    queryKey: approvalKeys.list(query),
    queryFn: () => fetchApprovals(query),
    refetchInterval: 15_000,
  });
}

export function useDecideApproval() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, approved }: { approvalId: string; approved: boolean }) =>
      decideApproval(approvalId, approved),
    onSuccess: async () => client.invalidateQueries({ queryKey: approvalKeys.all }),
  });
}
