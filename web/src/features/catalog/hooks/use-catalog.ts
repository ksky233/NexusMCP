import { useQuery } from "@tanstack/react-query";

import {
  fetchTool,
  fetchTools,
  fetchToolVersions,
  fetchVersionBinding,
  type ToolListQuery,
} from "@/features/catalog/api/catalog";

export const catalogKeys = {
  all: ["tools"] as const,
  list: (query: ToolListQuery) => ["tools", "list", query] as const,
  detail: (toolId: string) => ["tools", "detail", toolId] as const,
  versions: (toolId: string) => ["tools", "versions", toolId] as const,
  binding: (versionId: string) => ["tools", "binding", versionId] as const,
};

export function useTools(query: ToolListQuery) {
  return useQuery({ queryKey: catalogKeys.list(query), queryFn: () => fetchTools(query) });
}

export function useTool(toolId: string) {
  return useQuery({ queryKey: catalogKeys.detail(toolId), queryFn: () => fetchTool(toolId) });
}

export function useToolVersions(toolId: string) {
  return useQuery({
    queryKey: catalogKeys.versions(toolId),
    queryFn: () => fetchToolVersions(toolId),
  });
}

export function useVersionBinding(versionId: string, enabled: boolean) {
  return useQuery({
    queryKey: catalogKeys.binding(versionId),
    queryFn: () => fetchVersionBinding(versionId),
    enabled,
  });
}
