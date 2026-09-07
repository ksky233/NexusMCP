import {
  activateToolset,
  createToolset,
  disableToolset,
  getToolset,
  listToolsets,
  replaceToolsetAccessGrants,
  replaceToolsetMembers,
  updateToolset,
} from "@/generated/api/sdk.gen";
import type {
  ChangeToolsetStatusRequest,
  CreateToolsetRequest,
  ListToolsetsData,
  ReplaceToolsetAccessGrantsRequest,
  ReplaceToolsetMembersRequest,
  ToolsetPageResponse,
  ToolsetResponse,
  UpdateToolsetRequest,
} from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export type ToolsetListQuery = NonNullable<ListToolsetsData["query"]>;

export async function fetchToolsets(query: ToolsetListQuery): Promise<ToolsetPageResponse> {
  return (await listToolsets({ query, signal: createRequestSignal(), throwOnError: true })).data;
}

export async function fetchToolset(toolsetId: string): Promise<ToolsetResponse> {
  return (
    await getToolset({
      path: { toolset_id: toolsetId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function createToolsetProfile(body: CreateToolsetRequest): Promise<ToolsetResponse> {
  return (await createToolset({ body, signal: createRequestSignal(), throwOnError: true })).data;
}

export async function saveToolset(
  toolsetId: string,
  body: UpdateToolsetRequest,
): Promise<ToolsetResponse> {
  return (
    await updateToolset({
      body,
      path: { toolset_id: toolsetId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function saveToolsetMembers(
  toolsetId: string,
  body: ReplaceToolsetMembersRequest,
): Promise<ToolsetResponse> {
  return (
    await replaceToolsetMembers({
      body,
      path: { toolset_id: toolsetId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function saveToolsetGrants(
  toolsetId: string,
  body: ReplaceToolsetAccessGrantsRequest,
): Promise<ToolsetResponse> {
  return (
    await replaceToolsetAccessGrants({
      body,
      path: { toolset_id: toolsetId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function enableToolset(
  toolsetId: string,
  body: ChangeToolsetStatusRequest,
): Promise<ToolsetResponse> {
  return (
    await activateToolset({
      body,
      path: { toolset_id: toolsetId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function deactivateToolset(
  toolsetId: string,
  body: ChangeToolsetStatusRequest,
): Promise<ToolsetResponse> {
  return (
    await disableToolset({
      body,
      path: { toolset_id: toolsetId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}
