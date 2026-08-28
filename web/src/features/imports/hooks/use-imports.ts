import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acceptOperation,
  fetchBinding,
  fetchImport,
  fetchImports,
  fetchReviewQueue,
  fetchToolVersion,
  publishVersion,
  startImport,
  submitVersion,
  type ImportListQuery,
  type ReviewListQuery,
} from "@/features/imports/api/imports";
import type {
  PublishToolRequest,
  ReviewOperationRequest,
  SubmitImportRequest,
} from "@/generated/api/types.gen";

export const importKeys = {
  all: ["imports"] as const,
  list: (query: ImportListQuery) => ["imports", "list", query] as const,
  detail: (importId: string) => ["imports", "detail", importId] as const,
  reviews: (query: ReviewListQuery) => ["imports", "reviews", query] as const,
  version: (versionId: string) => ["tool-version", versionId] as const,
  binding: (bindingId: string) => ["tool-binding", bindingId] as const,
};

export function useImports(query: ImportListQuery) {
  return useQuery({ queryKey: importKeys.list(query), queryFn: () => fetchImports(query) });
}

export function useImport(importId: string) {
  return useQuery({ queryKey: importKeys.detail(importId), queryFn: () => fetchImport(importId) });
}

export function useReviewQueue(query: ReviewListQuery) {
  return useQuery({ queryKey: importKeys.reviews(query), queryFn: () => fetchReviewQueue(query) });
}

export function useStartImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SubmitImportRequest) => startImport(body),
    onSuccess: async () => client.invalidateQueries({ queryKey: importKeys.all }),
  });
}

export function useAcceptOperation(importId: string, operationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ReviewOperationRequest) => acceptOperation(operationId, body),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: importKeys.detail(importId) }),
        client.invalidateQueries({ queryKey: ["imports", "reviews"] }),
      ]);
    },
  });
}

export function useToolVersion(versionId: string | null) {
  return useQuery({
    queryKey: importKeys.version(versionId ?? "missing"),
    queryFn: () => fetchToolVersion(versionId ?? ""),
    enabled: Boolean(versionId),
  });
}

export function useToolBinding(bindingId: string | null) {
  return useQuery({
    queryKey: importKeys.binding(bindingId ?? "missing"),
    queryFn: () => fetchBinding(bindingId ?? ""),
    enabled: Boolean(bindingId),
  });
}

export function useSubmitVersion(versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => submitVersion(versionId),
    onSuccess: async () => client.invalidateQueries({ queryKey: importKeys.version(versionId) }),
  });
}

export function usePublishVersion(toolId: string, versionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PublishToolRequest) => publishVersion(toolId, versionId, body),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: importKeys.version(versionId) }),
        client.invalidateQueries({ queryKey: ["tools"] }),
      ]);
    },
  });
}
