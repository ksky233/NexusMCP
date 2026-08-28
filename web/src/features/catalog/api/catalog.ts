import {
  getTool,
  getToolVersionBinding,
  listTools,
  listToolVersions,
} from "@/generated/api/sdk.gen";
import type {
  ListToolsData,
  ToolBindingDetailResponse,
  ToolDetailResponse,
  ToolPageResponse,
  ToolVersionPageResponse,
} from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export type ToolListQuery = NonNullable<ListToolsData["query"]>;

export async function fetchTools(query: ToolListQuery): Promise<ToolPageResponse> {
  return (await listTools({ query, signal: createRequestSignal(), throwOnError: true })).data;
}

export async function fetchTool(toolId: string): Promise<ToolDetailResponse> {
  return (
    await getTool({ path: { tool_id: toolId }, signal: createRequestSignal(), throwOnError: true })
  ).data;
}

export async function fetchToolVersions(toolId: string): Promise<ToolVersionPageResponse> {
  return (
    await listToolVersions({
      path: { tool_id: toolId },
      query: { offset: 0, limit: 100 },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchVersionBinding(versionId: string): Promise<ToolBindingDetailResponse> {
  return (
    await getToolVersionBinding({
      path: { tool_version_id: versionId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}
