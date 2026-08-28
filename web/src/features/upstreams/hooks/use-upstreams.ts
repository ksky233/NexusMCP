import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createUpstream,
  deactivateUpstream,
  fetchUpstream,
  fetchUpstreams,
  saveUpstream,
  type UpstreamListQuery,
} from "@/features/upstreams/api/upstreams";
import type { RegisterUpstreamRequest, UpdateUpstreamRequest } from "@/generated/api/types.gen";

export const upstreamKeys = {
  all: ["upstreams"] as const,
  list: (query: UpstreamListQuery) => ["upstreams", "list", query] as const,
  detail: (upstreamId: string) => ["upstreams", "detail", upstreamId] as const,
};

export function useUpstreams(query: UpstreamListQuery) {
  return useQuery({ queryKey: upstreamKeys.list(query), queryFn: () => fetchUpstreams(query) });
}

export function useUpstream(upstreamId: string) {
  return useQuery({
    queryKey: upstreamKeys.detail(upstreamId),
    queryFn: () => fetchUpstream(upstreamId),
  });
}

export function useRegisterUpstream() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RegisterUpstreamRequest) => createUpstream(body),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: upstreamKeys.all }),
  });
}

export function useUpdateUpstream(upstreamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateUpstreamRequest) => saveUpstream(upstreamId, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: upstreamKeys.all }),
        queryClient.invalidateQueries({ queryKey: upstreamKeys.detail(upstreamId) }),
      ]);
    },
  });
}

export function useDisableUpstream(upstreamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deactivateUpstream(upstreamId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: upstreamKeys.all }),
        queryClient.invalidateQueries({ queryKey: upstreamKeys.detail(upstreamId) }),
      ]);
    },
  });
}
