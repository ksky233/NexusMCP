import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createToolsetProfile,
  deactivateToolset,
  enableToolset,
  fetchToolset,
  fetchToolsets,
  saveToolset,
  saveToolsetGrants,
  saveToolsetMembers,
  type ToolsetListQuery,
} from "@/features/toolsets/api/toolsets";
import type {
  CreateToolsetRequest,
  ReplaceToolsetAccessGrantsRequest,
  ReplaceToolsetMembersRequest,
  ToolsetResponse,
  UpdateToolsetRequest,
} from "@/generated/api/types.gen";

export const toolsetKeys = {
  all: ["toolsets"] as const,
  list: (query: ToolsetListQuery) => ["toolsets", "list", query] as const,
  detail: (toolsetId: string) => ["toolsets", "detail", toolsetId] as const,
};

export function useToolsets(query: ToolsetListQuery) {
  return useQuery({ queryKey: toolsetKeys.list(query), queryFn: () => fetchToolsets(query) });
}

export function useToolset(toolsetId: string) {
  return useQuery({
    queryKey: toolsetKeys.detail(toolsetId),
    queryFn: () => fetchToolset(toolsetId),
  });
}

export function useCreateToolset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateToolsetRequest) => createToolsetProfile(body),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: toolsetKeys.all }),
  });
}

export function useUpdateToolset(toolsetId: string) {
  return useToolsetMutation(toolsetId, (body: UpdateToolsetRequest) =>
    saveToolset(toolsetId, body),
  );
}

export function useReplaceToolsetMembers(toolsetId: string) {
  return useToolsetMutation(toolsetId, (body: ReplaceToolsetMembersRequest) =>
    saveToolsetMembers(toolsetId, body),
  );
}

export function useReplaceToolsetGrants(toolsetId: string) {
  return useToolsetMutation(toolsetId, (body: ReplaceToolsetAccessGrantsRequest) =>
    saveToolsetGrants(toolsetId, body),
  );
}

export function useActivateToolset(toolsetId: string) {
  return useToolsetMutation(toolsetId, (expectedRevision: number) =>
    enableToolset(toolsetId, { expected_revision: expectedRevision }),
  );
}

export function useDisableToolset(toolsetId: string) {
  return useToolsetMutation(toolsetId, (expectedRevision: number) =>
    deactivateToolset(toolsetId, { expected_revision: expectedRevision }),
  );
}

function useToolsetMutation<TBody>(
  toolsetId: string,
  mutationFn: (body: TBody) => Promise<ToolsetResponse>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async (data) => {
      queryClient.setQueryData(toolsetKeys.detail(toolsetId), data);
      await queryClient.invalidateQueries({ queryKey: toolsetKeys.all });
    },
  });
}
